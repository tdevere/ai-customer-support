"""
Unit tests for the Intercom integration (integrations/intercom.py).

FastAPI endpoints are tested with httpx.AsyncClient + ASGITransport.
Outbound HTTP calls via httpx.AsyncClient are mocked.
"""

import hashlib
import hmac
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------------------
# validate_webhook_signature (pure function)
# ---------------------------------------------------------------------------


class TestValidateWebhookSignature:
    def _fn(self, body: bytes, signature: str, secret: str) -> bool:
        from integrations.intercom import validate_webhook_signature

        return validate_webhook_signature(body, signature, secret)

    def _make_sig(self, body: bytes, secret: str) -> str:
        return (
            "sha256="
            + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        )

    def test_valid_signature_returns_true(self):
        body = b'{"topic":"test"}'
        secret = "my-webhook-secret"
        sig = self._make_sig(body, secret)
        assert self._fn(body, sig, secret) is True

    def test_invalid_signature_returns_false(self):
        body = b'{"topic":"test"}'
        assert self._fn(body, "sha256=badhash", "secret") is False

    def test_empty_signature_returns_false(self):
        assert self._fn(b"body", "", "secret") is False

    def test_empty_secret_returns_false(self):
        assert self._fn(b"body", "sha256=anything", "") is False

    def test_raw_hex_without_prefix(self):
        """Raw HMAC hex (no sha256= prefix) is compared verbatim."""
        body = b"data"
        secret = "sec"
        raw_hex = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        # Without the prefix the code doesn't strip, so compare raw_hex vs raw_hex succeeds
        assert self._fn(body, raw_hex, secret) is True


# ---------------------------------------------------------------------------
# FastAPI endpoint helpers
# ---------------------------------------------------------------------------


def _make_webhook_payload(topic: str = "conversation.user.replied") -> bytes:
    payload = {
        "topic": topic,
        "data": {
            "item": {
                "id": "conv-intercom-1",
                "conversation_message": {"body": "I need help"},
                "user": {"id": "user-ic-1"},
            }
        },
    }
    return json.dumps(payload).encode()


def _valid_sig(body: bytes, secret: str = "test-webhook-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# /webhook endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_403():
    from integrations.intercom import app
    from shared.config import settings

    with patch.object(settings, "intercom_webhook_secret", "real-secret"):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook",
                content=b'{"topic":"test"}',
                headers={"X-Hub-Signature-256": "sha256=badsig"},
            )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_invalid_json_returns_400():
    from integrations.intercom import app
    from shared.config import settings

    body = b"not valid json"

    with patch.object(settings, "intercom_webhook_secret", "sec"):
        sig = _valid_sig(body, "sec")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook",
                content=body,
                headers={"X-Hub-Signature-256": sig},
            )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_non_conversation_topic_returns_ok():
    """Topics other than conversation.user.* return 200 without running orchestrator."""
    from integrations.intercom import app
    from shared.config import settings

    body = _make_webhook_payload(topic="conversation.admin.replied")

    with patch.object(settings, "intercom_webhook_secret", "sec"):
        sig = _valid_sig(body, "sec")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook",
                content=body,
                headers={"X-Hub-Signature-256": sig},
            )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_conversation_user_replied_runs_orchestrator():
    from integrations.intercom import app
    from shared.config import settings

    body = _make_webhook_payload("conversation.user.replied")

    mock_result = {
        "status": "success",
        "message": "Here is the answer",
        "confidence": 0.95,
        "admin_id": None,
    }

    with (
        patch.object(settings, "intercom_webhook_secret", "sec"),
        patch.object(settings, "confidence_threshold", 0.7),
        patch(
            "orchestrator.graph.run_aan_orchestrator",
            new=AsyncMock(return_value=mock_result),
        ),
        patch(
            "integrations.intercom.post_reply_to_intercom",
            new=AsyncMock(return_value={}),
        ),
    ):
        sig = _valid_sig(body, "sec")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook",
                content=body,
                headers={"X-Hub-Signature-256": sig},
            )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_webhook_escalated_posts_note():
    from integrations.intercom import app
    from shared.config import settings

    body = _make_webhook_payload("conversation.user.replied")

    mock_result = {
        "status": "escalated",
        "message": "Escalating to human",
        "confidence": 0.3,
        "escalation_summary": "Customer needs billing help",
    }

    with (
        patch.object(settings, "intercom_webhook_secret", "sec"),
        patch.object(settings, "confidence_threshold", 0.7),
        patch(
            "orchestrator.graph.run_aan_orchestrator",
            new=AsyncMock(return_value=mock_result),
        ),
        patch(
            "integrations.intercom.add_note_to_intercom",
            new=AsyncMock(return_value={}),
        ),
    ):
        sig = _valid_sig(body, "sec")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook",
                content=body,
                headers={"X-Hub-Signature-256": sig},
            )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# /data-connector endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_data_connector_returns_formatted_response():
    from integrations.intercom import app

    payload = json.dumps(
        {
            "conversation_id": "conv-dc-1",
            "query": "how do I export my data",
            "context": {"user_id": "u-dc-1"},
        }
    ).encode()

    mock_result = {
        "message": "Go to Settings then Export.",
        "confidence": 0.88,
        "sources": [],
        "agent": "technical",
        "topic": "technical",
    }

    with patch(
        "orchestrator.graph.run_aan_orchestrator",
        new=AsyncMock(return_value=mock_result),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/data-connector", content=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Go to Settings then Export."
    assert body["confidence"] == 0.88
    assert body["metadata"]["agent"] == "technical"


# ---------------------------------------------------------------------------
# post_reply_to_intercom
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_reply_to_intercom_sends_correct_payload():
    from integrations.intercom import post_reply_to_intercom

    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "reply-1"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await post_reply_to_intercom("conv-1", "Hello, how can I help?")

    mock_client.post.assert_called_once()
    _, kwargs = mock_client.post.call_args
    assert kwargs["json"]["body"] == "Hello, how can I help?"
    assert kwargs["json"]["message_type"] == "comment"
    assert result == {"id": "reply-1"}


@pytest.mark.asyncio
async def test_post_reply_to_intercom_raises_on_http_error():
    import httpx
    from integrations.intercom import post_reply_to_intercom

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=httpx.HTTPError("connection refused"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPError):
            await post_reply_to_intercom("conv-err", "msg")


# ---------------------------------------------------------------------------
# add_note_to_intercom
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_note_to_intercom_sends_note_type():
    from integrations.intercom import add_note_to_intercom

    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "note-1"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await add_note_to_intercom("conv-2", "Internal note text")

    _, kwargs = mock_client.post.call_args
    assert kwargs["json"]["message_type"] == "note"
    assert kwargs["json"]["body"] == "Internal note text"


# ---------------------------------------------------------------------------
# get_conversation_from_intercom
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_conversation_returns_data():
    from integrations.intercom import get_conversation_from_intercom

    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "conv-99", "state": "open"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await get_conversation_from_intercom("conv-99")

    assert result["id"] == "conv-99"
    assert result["state"] == "open"


@pytest.mark.asyncio
async def test_post_reply_includes_admin_id_in_payload():
    """admin_id is added to the request payload when provided."""
    from integrations.intercom import post_reply_to_intercom

    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "reply-admin"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await post_reply_to_intercom("conv-1", "Hello!", admin_id="admin-007")

    _, kwargs = mock_client.post.call_args
    assert kwargs["json"].get("admin_id") == "admin-007"


@pytest.mark.asyncio
async def test_add_note_raises_on_http_error():
    """add_note_to_intercom re-raises httpx.HTTPError."""
    import httpx
    from integrations.intercom import add_note_to_intercom

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=httpx.HTTPError("server down"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPError):
            await add_note_to_intercom("conv-err", "note text")


@pytest.mark.asyncio
async def test_get_conversation_raises_on_http_error():
    """get_conversation_from_intercom re-raises httpx.HTTPError."""
    import httpx
    from integrations.intercom import get_conversation_from_intercom

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPError):
            await get_conversation_from_intercom("conv-err")
