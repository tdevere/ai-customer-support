"""
Unit tests for the returns specialist agent.

Creates a fresh agent with mocked LLM and mocked Shopify HTTP calls for each test.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from shared.config import settings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def shopify_settings(monkeypatch):
    monkeypatch.setattr(settings, "shopify_api_key", "mock-shopify-token")
    monkeypatch.setattr(settings, "shopify_shop_url", "https://mock.myshopify.com")


def _base_state(**overrides) -> dict:
    state = {
        "messages": [],
        "order_id": "ORD-9001",
        "customer_email": "customer@example.com",
        "query": "I want to return my order.",
        "response": "",
        "confidence": 0.0,
        "sources": [],
        "tool_results": [],
    }
    state.update(overrides)
    return state


def _make_llm_pair(
    mocker, *, tool_calls=None, final_text="Return approved.\nCONFIDENCE: 0.88"
):
    mock_llm_with_tools = MagicMock()
    tool_response = MagicMock()
    tool_response.content = ""
    tool_response.tool_calls = tool_calls or []
    mock_llm_with_tools.invoke.return_value = tool_response

    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools
    final_response = MagicMock()
    final_response.content = final_text
    mock_llm.invoke.return_value = final_response

    mocker.patch("agents.returns_agent.AzureChatOpenAI", return_value=mock_llm)
    mocker.patch("agents.returns_agent.rag.retrieve_context", return_value=[])
    mocker.patch("agents.returns_agent.rag.format_context_for_prompt", return_value="")

    return mock_llm, mock_llm_with_tools


def _mock_shopify_get(mocker, json_body: dict):
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_body
    mock_resp.raise_for_status.return_value = None
    mocker.patch("integrations.tools.shopify_tools.httpx.get", return_value=mock_resp)


def _mock_shopify_post(mocker, json_body: dict):
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_body
    mock_resp.raise_for_status.return_value = None
    mocker.patch("integrations.tools.shopify_tools.httpx.post", return_value=mock_resp)


def _recent_order_body(order_id: str = "ORD-9001", days_ago: int = 5) -> dict:
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "order": {
            "id": order_id,
            "order_number": 9001,
            "created_at": created.isoformat(),
            "total_price": "79.99",
            "currency": "USD",
            "financial_status": "paid",
            "fulfillment_status": "fulfilled",
            "line_items": [
                {"id": "li1", "title": "Blue Hoodie", "quantity": 1, "price": "79.99"}
            ],
        }
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_agent_no_tool_calls(mocker):
    """Agent returns a response when LLM needs no tools (e.g., policy question)."""
    _make_llm_pair(
        mocker,
        final_text="Our return policy allows returns within 30 days.\nCONFIDENCE: 0.95",
    )

    from agents.returns_agent import create_returns_agent

    agent = create_returns_agent()
    result = agent.invoke(_base_state(query="What is your return policy?"))

    assert "30 days" in result["response"]
    assert result["confidence"] == pytest.approx(0.95)
    assert result["tool_results"] == []


def test_returns_agent_checks_eligibility(mocker):
    """Agent dispatches check_return_eligibility for a specific order."""
    _make_llm_pair(
        mocker,
        tool_calls=[
            {"name": "check_return_eligibility", "args": {"order_id": "ORD-9001"}}
        ],
        final_text="Your order is eligible for return.\nCONFIDENCE: 0.91",
    )
    _mock_shopify_get(mocker, _recent_order_body("ORD-9001", days_ago=7))

    from agents.returns_agent import create_returns_agent

    agent = create_returns_agent()
    result = agent.invoke(_base_state())

    assert len(result["tool_results"]) == 1
    tr = result["tool_results"][0]
    assert tr["tool"] == "check_return_eligibility"
    assert tr["result"]["eligible"] is True


def test_returns_agent_processes_refund(mocker):
    """Agent dispatches create_refund when customer approves the return."""
    _make_llm_pair(
        mocker,
        tool_calls=[
            {"name": "create_refund", "args": {"order_id": "ORD-9001", "amount": 79.99}}
        ],
        final_text="Refund of $79.99 has been initiated.\nCONFIDENCE: 0.94",
    )
    _mock_shopify_post(
        mocker,
        {
            "refund": {
                "id": "refund_555",
                "order_id": "ORD-9001",
                "created_at": "2026-02-01T00:00:00+00:00",
                "note": "customer_request",
                "transactions": [],
            }
        },
    )

    from agents.returns_agent import create_returns_agent

    agent = create_returns_agent()
    result = agent.invoke(_base_state())

    assert len(result["tool_results"]) == 1
    tr = result["tool_results"][0]
    assert tr["tool"] == "create_refund"
    assert tr["result"]["id"] == "refund_555"


def test_returns_agent_unknown_tool_recorded_as_error(mocker):
    """Unknown tool requests are captured without raising an exception."""
    _make_llm_pair(
        mocker,
        tool_calls=[{"name": "teleport_package", "args": {}}],
        final_text="I cannot do that.\nCONFIDENCE: 0.20",
    )

    from agents.returns_agent import create_returns_agent

    agent = create_returns_agent()
    result = agent.invoke(_base_state())

    assert len(result["tool_results"]) == 1
    assert "Unknown tool" in result["tool_results"][0]["result"]["error"]
