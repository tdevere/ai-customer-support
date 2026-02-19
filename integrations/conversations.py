"""
Generic platform-agnostic conversation API.

Replaces Intercom-specific webhooks with a clean REST interface that any
front-end or integration layer can call.  The actual orchestration logic
lives entirely in orchestrator/graph.py – this module is purely the HTTP
boundary.

Endpoints
---------
POST /conversations
    Start a new conversation.  Returns a conversation_id that callers must
    include in subsequent requests.

POST /conversations/{id}/messages
    Send a follow-up message in an existing conversation.

GET  /conversations/{id}
    Retrieve the current state of a conversation (status, last response,
    resolution state, etc.).

GET  /health
    Liveness check consumed by load balancers and CI smoke tests.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from shared.config import settings
from shared.memory import memory

app = FastAPI(
    title="AAN Customer Support API",
    description="Platform-agnostic adaptive agent network for customer support.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Optional API-key protection
# Set SUPPORT_API_KEY env var to enable; leave blank to allow unauthenticated
# access (useful for local dev / CI).
# ---------------------------------------------------------------------------
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _check_api_key(api_key: Optional[str] = Security(_api_key_header)) -> None:
    """Validate X-API-Key header when SUPPORT_API_KEY is configured."""
    required = getattr(settings, "support_api_key", "")
    if required and api_key != required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class StartConversationRequest(BaseModel):
    """Payload to open a new conversation."""

    user_id: str = Field(..., description="Opaque caller-supplied user identifier")
    message: str = Field(..., description="Opening message from the user")
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata (e.g. customer tier, order_id, locale)",
    )
    channel: Optional[str] = Field(
        default="api",
        description="Originating channel: 'api', 'web', 'mobile', 'email', etc.",
    )


class MessageRequest(BaseModel):
    """Payload for a follow-up message in an existing conversation."""

    message: str = Field(..., description="Follow-up message from the user")
    user_id: Optional[str] = Field(default=None)
    context: Optional[Dict[str, Any]] = Field(default=None)


class ConversationResponse(BaseModel):
    """Unified response shape returned by all conversation endpoints."""

    conversation_id: str
    status: str = Field(
        ...,
        description=(
            "One of: 'success', 'escalated', 'error', "
            "'resolved_confirmed', 'resolved_assumed', 'in_progress'"
        ),
    )
    response: Optional[str] = Field(default=None, description="Bot reply to the user")
    confidence: Optional[float] = Field(
        default=None, description="0–1 confidence score for the response"
    )
    sources: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="RAG source chunks that informed the response"
    )
    escalation_summary: Optional[str] = Field(
        default=None,
        description="Structured handoff summary generated when escalating",
    )
    resolution_state: Optional[str] = Field(
        default=None,
        description=(
            "Resolution tracking: 'in_progress', 'resolved_assumed', "
            "'resolved_confirmed', 'escalated'"
        ),
    )
    agent: Optional[str] = Field(
        default=None, description="Specialist agent that handled the request"
    )
    topic: Optional[str] = Field(
        default=None, description="Primary topic classification"
    )
    custom_answer_used: Optional[bool] = Field(
        default=None,
        description="True when response came from the custom-answers override layer",
    )


class HealthResponse(BaseModel):
    status: str
    version: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["Operations"])
async def health_check() -> HealthResponse:
    """Liveness check."""
    return HealthResponse(status="ok", version="1.0.0")


@app.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Conversations"],
)
async def start_conversation(
    request: StartConversationRequest,
    _: None = Security(_check_api_key),
) -> ConversationResponse:
    """
    Start a new conversation and return the first bot response.

    A fresh `conversation_id` (UUID4) is allocated server-side and returned
    in the response.  Callers must send this id in all subsequent requests
    for the same conversation.
    """
    conversation_id = str(uuid.uuid4())

    # Lazy import to avoid circular deps and keep module-level import fast
    from orchestrator.graph import run_aan_orchestrator

    context = request.context or {}
    context["channel"] = request.channel

    result = await run_aan_orchestrator(
        conversation_id=conversation_id,
        user_id=request.user_id,
        message=request.message,
        context=context,
    )

    return _build_response(conversation_id, result)


@app.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationResponse,
    tags=["Conversations"],
)
async def reply_to_conversation(
    conversation_id: str,
    request: MessageRequest,
    _: None = Security(_check_api_key),
) -> ConversationResponse:
    """
    Send a follow-up message in an existing conversation.

    The orchestrator loads prior conversation state from Cosmos DB so the
    specialist agents have full context of what has already been tried.
    """
    from orchestrator.graph import run_aan_orchestrator

    context = request.context or {}

    result = await run_aan_orchestrator(
        conversation_id=conversation_id,
        user_id=request.user_id or "anonymous",
        message=request.message,
        context=context,
    )

    return _build_response(conversation_id, result)


@app.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    tags=["Conversations"],
)
async def get_conversation(
    conversation_id: str,
    _: None = Security(_check_api_key),
) -> ConversationResponse:
    """
    Retrieve the last persisted state of a conversation.

    Returns 404 if the conversation_id has never been seen (or if Cosmos DB
    state has expired / been purged).
    """
    state = memory.get_state(conversation_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )

    return ConversationResponse(
        conversation_id=conversation_id,
        status=state.get("status", "unknown"),
        response=state.get("response"),
        confidence=state.get("confidence"),
        resolution_state=state.get("resolution_state"),
        escalation_summary=state.get("escalation_summary"),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_response(
    conversation_id: str, result: Dict[str, Any]
) -> ConversationResponse:
    """Map the orchestrator result dict to a ConversationResponse."""
    return ConversationResponse(
        conversation_id=conversation_id,
        status=result.get("status", "error"),
        response=result.get("message"),
        confidence=result.get("confidence"),
        sources=result.get("sources"),
        escalation_summary=result.get("escalation_summary"),
        resolution_state=result.get("resolution_state"),
        agent=result.get("agent"),
        topic=result.get("topic"),
        custom_answer_used=result.get("custom_answer_used", False),
    )
