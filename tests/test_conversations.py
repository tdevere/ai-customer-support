"""Integration tests for the generic conversation REST API.

All orchestrator calls are mocked so no Azure services are required.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from integrations.conversations import app

# Patch target for run_aan_orchestrator (lazy-imported inside endpoint functions)
_ORCHESTRATOR_PATCH = "orchestrator.graph.run_aan_orchestrator"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_orchestrator_success():
    """Mock run_aan_orchestrator returning a successful (resolved) result."""
    return {
        "status": "success",
        "message": "Your plan costs $29/month on the Starter tier.",
        "confidence": 0.92,
        "sources": [],
        "escalation_summary": "",
        "agent": "billing",
        "topic": "billing",
        "resolution_state": "resolved_assumed",
        "custom_answer_used": False,
        "handoff_summary": "",
    }


@pytest.fixture
def mock_orchestrator_escalated():
    """Mock run_aan_orchestrator returning an escalation result."""
    return {
        "status": "escalated",
        "message": "",
        "confidence": 0.3,
        "sources": [],
        "escalation_summary": "CUSTOMER ISSUE: Complex dispute\nACTION: Manual review required",
        "agent": "billing",
        "topic": "billing",
        "resolution_state": "escalated",
        "custom_answer_used": False,
        "handoff_summary": "Customer has a billing dispute that requires human review.",
    }


@pytest.fixture
def mock_orchestrator_custom():
    """Mock run_aan_orchestrator returning a custom-answer-matched result."""
    return {
        "status": "success",
        "message": "Our plans start at $29/month.",
        "confidence": 0.99,
        "sources": [],
        "escalation_summary": "",
        "agent": "billing",
        "topic": "billing",
        "resolution_state": "resolved_assumed",
        "custom_answer_used": True,
        "handoff_summary": "",
    }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


# ---------------------------------------------------------------------------
# POST /conversations  (start new conversation)
# ---------------------------------------------------------------------------


def test_start_conversation_success(client, mock_orchestrator_success):
    with patch(
        _ORCHESTRATOR_PATCH,
        new=AsyncMock(return_value=mock_orchestrator_success),
    ):
        response = client.post(
            "/conversations",
            json={
                "user_id": "user-123",
                "message": "What plan should I choose?",
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert "conversation_id" in data
    assert data["status"] == "success"
    assert data["response"] == mock_orchestrator_success["message"]
    assert data["resolution_state"] == "resolved_assumed"
    assert data["custom_answer_used"] is False


def test_start_conversation_with_context(client, mock_orchestrator_success):
    with patch(
        _ORCHESTRATOR_PATCH,
        new=AsyncMock(return_value=mock_orchestrator_success),
    ) as mock_fn:
        response = client.post(
            "/conversations",
            json={
                "user_id": "user-123",
                "message": "I need help",
                "context": {"customer_tier": "premium", "order_id": "ORD-999"},
                "channel": "web",
            },
        )
        # Check that channel was injected into context
        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs["context"]["channel"] == "web"
        assert call_kwargs["context"]["customer_tier"] == "premium"

    assert response.status_code == 201


def test_start_conversation_escalated(client, mock_orchestrator_escalated):
    with patch(
        _ORCHESTRATOR_PATCH,
        new=AsyncMock(return_value=mock_orchestrator_escalated),
    ):
        response = client.post(
            "/conversations",
            json={"user_id": "user-456", "message": "I have a very complex issue."},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "escalated"
    assert data["resolution_state"] == "escalated"
    assert data["escalation_summary"] is not None
    assert len(data["escalation_summary"]) > 0


def test_start_conversation_custom_answer(client, mock_orchestrator_custom):
    with patch(
        _ORCHESTRATOR_PATCH,
        new=AsyncMock(return_value=mock_orchestrator_custom),
    ):
        response = client.post(
            "/conversations",
            json={"user_id": "user-789", "message": "How much does it cost?"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["custom_answer_used"] is True


def test_start_conversation_allocates_unique_ids(client, mock_orchestrator_success):
    ids = set()
    with patch(
        _ORCHESTRATOR_PATCH,
        new=AsyncMock(return_value=mock_orchestrator_success),
    ):
        for _ in range(5):
            response = client.post(
                "/conversations",
                json={"user_id": "u", "message": "hi"},
            )
            ids.add(response.json()["conversation_id"])

    assert len(ids) == 5, "Each call should produce a unique conversation_id"


# ---------------------------------------------------------------------------
# POST /conversations/{id}/messages  (follow-up message)
# ---------------------------------------------------------------------------


def test_reply_to_conversation(client, mock_orchestrator_success):
    with patch(
        _ORCHESTRATOR_PATCH,
        new=AsyncMock(return_value=mock_orchestrator_success),
    ):
        response = client.post(
            "/conversations/conv-abc-123/messages",
            json={"message": "Thanks, that helped!"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == "conv-abc-123"
    assert data["status"] == "success"


def test_reply_preserves_conversation_id(client, mock_orchestrator_success):
    cid = "my-existing-conversation"
    with patch(
        _ORCHESTRATOR_PATCH,
        new=AsyncMock(return_value=mock_orchestrator_success),
    ) as mock_fn:
        client.post(
            f"/conversations/{cid}/messages",
            json={"message": "follow up"},
        )
        assert mock_fn.call_args.kwargs["conversation_id"] == cid


# ---------------------------------------------------------------------------
# GET /conversations/{id}
# ---------------------------------------------------------------------------


def test_get_conversation_not_found(client):
    with patch("integrations.conversations.memory") as mock_mem:
        mock_mem.get_state.return_value = None
        response = client.get("/conversations/unknown-id")

    assert response.status_code == 404


def test_get_conversation_found(client):
    stored = {
        "status": "success",
        "response": "We start at $29/month.",
        "confidence": 0.91,
        "resolution_state": "resolved_assumed",
    }
    with patch("integrations.conversations.memory") as mock_mem:
        mock_mem.get_state.return_value = stored
        response = client.get("/conversations/conv-xyz")

    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == "conv-xyz"
    assert data["resolution_state"] == "resolved_assumed"
    assert data["response"] == stored["response"]


# ---------------------------------------------------------------------------
# Response shape contract
# ---------------------------------------------------------------------------


def test_response_includes_all_expected_fields(client, mock_orchestrator_success):
    with patch(
        _ORCHESTRATOR_PATCH,
        new=AsyncMock(return_value=mock_orchestrator_success),
    ):
        response = client.post(
            "/conversations",
            json={"user_id": "u", "message": "hello"},
        )

    data = response.json()
    expected_keys = {
        "conversation_id",
        "status",
        "response",
        "confidence",
        "sources",
        "escalation_summary",
        "resolution_state",
        "agent",
        "topic",
        "custom_answer_used",
    }
    for key in expected_keys:
        assert key in data, f"Missing key in response: {key}"
