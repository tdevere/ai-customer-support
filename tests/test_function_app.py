"""
Unit tests for Azure Functions HTTP route handlers.

All calls to run_aan_orchestrator and shared.memory are mocked —
no real Azure services required.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import azure.functions as func

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ORCHESTRATOR_RESULT_OK = {
    "status": "success",
    "message": "Your plan is active.",
    "confidence": 0.91,
    "sources": [],
    "escalation_summary": "",
    "agent": "billing",
    "topic": "billing",
    "resolution_state": "resolved_assumed",
    "custom_answer_used": False,
    "handoff_summary": "",
}


def _build_request(
    method: str,
    body: dict | None = None,
    route_params: dict | None = None,
) -> func.HttpRequest:
    """Construct a func.HttpRequest for use in handler tests."""
    return func.HttpRequest(
        method=method,
        url="https://localhost/api/test",
        headers={"Content-Type": "application/json"},
        params={},
        route_params=route_params or {},
        body=json.dumps(body).encode() if body is not None else b"",
    )


# ---------------------------------------------------------------------------
# POST /api/conversations  (start_conversation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_conversation_success():
    """Returns 201 with conversation_id and orchestrator result."""
    from function_app import start_conversation

    with patch(
        "orchestrator.graph.run_aan_orchestrator",
        new=AsyncMock(return_value=_ORCHESTRATOR_RESULT_OK),
    ):
        req = _build_request(
            "POST",
            body={"user_id": "u1", "message": "What is my plan cost?"},
        )
        resp = await start_conversation(req)

    assert resp.status_code == 201
    data = json.loads(resp.get_body())
    assert "conversation_id" in data
    assert data["status"] == "success"
    assert data["message"] == "Your plan is active."


@pytest.mark.asyncio
async def test_start_conversation_missing_fields():
    """Returns 422 when user_id or message is absent."""
    from function_app import start_conversation

    req = _build_request("POST", body={"user_id": "u1"})  # message missing
    resp = await start_conversation(req)

    assert resp.status_code == 422
    data = json.loads(resp.get_body())
    assert "error" in data


@pytest.mark.asyncio
async def test_start_conversation_invalid_json():
    """Returns 400 on malformed request body."""
    from function_app import start_conversation

    req = func.HttpRequest(
        method="POST",
        url="https://localhost/api/test",
        headers={},
        params={},
        route_params={},
        body=b"not json at all",
    )
    resp = await start_conversation(req)

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/conversations/{conversation_id}/messages  (reply_to_conversation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reply_to_conversation_success():
    """Returns 200 with conversation_id echoed back."""
    from function_app import reply_to_conversation

    with patch(
        "orchestrator.graph.run_aan_orchestrator",
        new=AsyncMock(return_value=_ORCHESTRATOR_RESULT_OK),
    ):
        req = _build_request(
            "POST",
            body={"message": "Can you explain the invoice?", "user_id": "u1"},
            route_params={"conversation_id": "conv-abc"},
        )
        resp = await reply_to_conversation(req)

    assert resp.status_code == 200
    data = json.loads(resp.get_body())
    assert data["conversation_id"] == "conv-abc"
    assert data["status"] == "success"


@pytest.mark.asyncio
async def test_reply_to_conversation_missing_message():
    """Returns 422 when message field is absent."""
    from function_app import reply_to_conversation

    req = _build_request(
        "POST",
        body={"user_id": "u1"},  # message missing
        route_params={"conversation_id": "conv-abc"},
    )
    resp = await reply_to_conversation(req)

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/conversations/{conversation_id}  (get_conversation)
# ---------------------------------------------------------------------------


def test_get_conversation_found():
    """Returns 200 with state when conversation exists in Cosmos."""
    from function_app import get_conversation

    mock_state = {"status": "success", "message": "Your plan is active."}
    with patch("shared.memory.memory") as mock_memory:
        mock_memory.get_state.return_value = mock_state
        req = _build_request(
            "GET",
            route_params={"conversation_id": "conv-123"},
        )
        resp = get_conversation(req)

    assert resp.status_code == 200
    data = json.loads(resp.get_body())
    assert data["conversation_id"] == "conv-123"
    assert data["status"] == "success"


def test_get_conversation_not_found():
    """Returns 404 when conversation does not exist."""
    from function_app import get_conversation

    with patch("shared.memory.memory") as mock_memory:
        mock_memory.get_state.return_value = None
        req = _build_request(
            "GET",
            route_params={"conversation_id": "missing-id"},
        )
        resp = get_conversation(req)

    assert resp.status_code == 404
    data = json.loads(resp.get_body())
    assert "error" in data


# ---------------------------------------------------------------------------
# GET /api/health  (health_check)
# ---------------------------------------------------------------------------


def test_health_check():
    """Returns 200 with status: healthy."""
    from function_app import health_check

    req = _build_request("GET")
    resp = health_check(req)

    assert resp.status_code == 200
    data = json.loads(resp.get_body())
    assert data["status"] == "healthy"
    assert "service" in data


# ---------------------------------------------------------------------------
# POST /api/webhook  (webhook_trigger)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_invalid_signature():
    """Returns 403 when HMAC signature fails validation."""
    from function_app import webhook_trigger

    payload = json.dumps(
        {"topic": "conversation.user.replied", "data": {"item": {}}}
    ).encode()

    with patch("integrations.intercom.validate_webhook_signature", return_value=False):
        req = func.HttpRequest(
            method="POST",
            url="https://localhost/api/webhook",
            headers={"X-Hub-Signature-256": "sha256=invalid"},
            params={},
            route_params={},
            body=payload,
        )
        resp = await webhook_trigger(req)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_non_conversation_topic():
    """Returns 200 for topics we don't act on (no orchestrator call)."""
    from function_app import webhook_trigger

    payload = json.dumps({"topic": "ping", "data": {"item": {}}}).encode()

    with patch("integrations.intercom.validate_webhook_signature", return_value=True):
        req = func.HttpRequest(
            method="POST",
            url="https://localhost/api/webhook",
            headers={},
            params={},
            route_params={},
            body=payload,
        )
        resp = await webhook_trigger(req)

    assert resp.status_code == 200
    data = json.loads(resp.get_body())
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_conversation_topic_success():
    """Full webhook flow: valid sig, conversation topic, success → reply sent."""
    from function_app import webhook_trigger

    item = {
        "id": "conv-webhook-1",
        "conversation_message": {"body": "How do I cancel?"},
        "user": {"id": "usr-99"},
    }
    payload = json.dumps(
        {"topic": "conversation.user.replied", "data": {"item": item}}
    ).encode()

    mock_result = {**_ORCHESTRATOR_RESULT_OK, "status": "success"}

    with (
        patch("integrations.intercom.validate_webhook_signature", return_value=True),
        patch(
            "orchestrator.graph.run_aan_orchestrator",
            new=AsyncMock(return_value=mock_result),
        ),
        patch(
            "integrations.intercom.post_reply_to_intercom",
            new=AsyncMock(return_value=None),
        ),
    ):
        req = func.HttpRequest(
            method="POST",
            url="https://localhost/api/webhook",
            headers={},
            params={},
            route_params={},
            body=payload,
        )
        resp = await webhook_trigger(req)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_reply_to_conversation_invalid_json():
    """Returns 400 when reply body is not valid JSON."""
    from function_app import reply_to_conversation

    req = func.HttpRequest(
        method="POST",
        url="https://localhost/api/test",
        headers={},
        params={},
        route_params={"conversation_id": "conv-abc"},
        body=b"not valid json {{",
    )
    resp = await reply_to_conversation(req)

    assert resp.status_code == 400
    data = json.loads(resp.get_body())
    assert "error" in data


@pytest.mark.asyncio
async def test_webhook_conversation_topic_escalated():
    """Full webhook flow: valid sig, conversation topic, escalated → note added."""
    from function_app import webhook_trigger

    item = {
        "id": "conv-webhook-esc",
        "conversation_message": {"body": "Urgent refund needed"},
        "user": {"id": "usr-42"},
    }
    payload = json.dumps(
        {"topic": "conversation.user.replied", "data": {"item": item}}
    ).encode()

    mock_result = {
        **_ORCHESTRATOR_RESULT_OK,
        "status": "escalated",
        "escalation_summary": "Needs human review",
    }

    with (
        patch("integrations.intercom.validate_webhook_signature", return_value=True),
        patch(
            "orchestrator.graph.run_aan_orchestrator",
            new=AsyncMock(return_value=mock_result),
        ),
        patch(
            "integrations.intercom.add_note_to_intercom",
            new=AsyncMock(return_value=None),
        ),
    ):
        req = func.HttpRequest(
            method="POST",
            url="https://localhost/api/webhook",
            headers={},
            params={},
            route_params={},
            body=payload,
        )
        resp = await webhook_trigger(req)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_webhook_trigger_exception_returns_500():
    """Exception raised during webhook processing returns 500."""
    from function_app import webhook_trigger

    item = {
        "id": "conv-err",
        "conversation_message": {"body": "Test"},
        "user": {"id": "u1"},
    }
    payload = json.dumps(
        {"topic": "conversation.user.replied", "data": {"item": item}}
    ).encode()

    with (
        patch("integrations.intercom.validate_webhook_signature", return_value=True),
        patch(
            "orchestrator.graph.run_aan_orchestrator",
            new=AsyncMock(side_effect=RuntimeError("orchestrator exploded")),
        ),
    ):
        req = func.HttpRequest(
            method="POST",
            url="https://localhost/api/webhook",
            headers={},
            params={},
            route_params={},
            body=payload,
        )
        resp = await webhook_trigger(req)

    assert resp.status_code == 500
    data = json.loads(resp.get_body())
    assert "error" in data
