"""
Unit tests for the billing specialist agent.

Creates a fresh agent with mocked LLM and mocked Stripe SDK for each test.
"""

import pytest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _base_state(**overrides) -> dict:
    state = {
        "messages": [],
        "customer_id": "cust_test_123",
        "query": "What is my current invoice amount?",
        "response": "",
        "confidence": 0.0,
        "sources": [],
        "tool_results": [],
    }
    state.update(overrides)
    return state


def _make_llm_pair(
    mocker, *, tool_calls=None, final_text="I can help.\nCONFIDENCE: 0.85"
):
    """
    Return (mock_llm, mock_llm_with_tools).

    mock_llm         – used in generate_response
    mock_llm_with_tools – returned by mock_llm.bind_tools(...)
    """
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

    mocker.patch("agents.billing_agent.AzureChatOpenAI", return_value=mock_llm)
    mocker.patch("agents.billing_agent.rag.retrieve_context", return_value=[])
    mocker.patch("agents.billing_agent.rag.format_context_for_prompt", return_value="")

    return mock_llm, mock_llm_with_tools


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_billing_agent_no_tool_calls(mocker):
    """Agent returns a valid response when LLM makes no tool calls."""
    _make_llm_pair(mocker, final_text="Your subscription is active.\nCONFIDENCE: 0.90")

    from agents.billing_agent import create_billing_agent

    agent = create_billing_agent()
    result = agent.invoke(_base_state())

    assert result["response"] == "Your subscription is active."
    assert result["confidence"] == pytest.approx(0.90)
    assert result["tool_results"] == []


def test_billing_agent_confidence_extraction(mocker):
    """CONFIDENCE: x.xx is stripped from response text and stored as float."""
    _make_llm_pair(mocker, final_text="Invoice total is $49.99.\nCONFIDENCE: 0.75")

    from agents.billing_agent import create_billing_agent

    agent = create_billing_agent()
    result = agent.invoke(_base_state())

    assert "CONFIDENCE" not in result["response"]
    assert result["confidence"] == pytest.approx(0.75)


def test_billing_agent_with_stripe_tool_call(mocker):
    """Agent dispatches get_customer_info when LLM requests it, returns tool result."""
    _make_llm_pair(
        mocker,
        tool_calls=[
            {"name": "get_customer_info", "args": {"customer_id": "cust_test_123"}}
        ],
        final_text="Customer account is active.\nCONFIDENCE: 0.92",
    )

    # Mock Stripe SDK
    mock_customer = MagicMock()
    mock_customer.id = "cust_test_123"
    mock_customer.email = "test@example.com"
    mock_customer.name = "Test User"
    mock_customer.balance = 0
    mock_customer.currency = "usd"
    mock_customer.created = 1700000000
    mock_customer.subscriptions = MagicMock(data=[])
    mocker.patch(
        "integrations.tools.stripe_tools.stripe.Customer.retrieve",
        return_value=mock_customer,
    )

    from agents.billing_agent import create_billing_agent

    agent = create_billing_agent()
    result = agent.invoke(_base_state())

    assert len(result["tool_results"]) == 1
    assert result["tool_results"][0]["tool"] == "get_customer_info"
    assert "error" not in result["tool_results"][0]["result"]
    assert result["confidence"] == pytest.approx(0.92)


def test_billing_agent_unknown_tool_returns_error_in_results(mocker):
    """If LLM requests a tool that does not exist, tool_results captures the error."""
    _make_llm_pair(
        mocker,
        tool_calls=[{"name": "delete_everything", "args": {}}],
        final_text="I couldn't find that.\nCONFIDENCE: 0.30",
    )

    from agents.billing_agent import create_billing_agent

    agent = create_billing_agent()
    result = agent.invoke(_base_state())

    assert len(result["tool_results"]) == 1
    assert "error" in result["tool_results"][0]["result"]
    assert "Unknown tool" in result["tool_results"][0]["result"]["error"]


def test_billing_tool_invoke_raises_error_stored(mocker):
    """When a known tool's invoke() raises, the exception is captured in tool_results."""
    mock_tool = mocker.MagicMock()
    mock_tool.name = "get_customer_info"
    mock_tool.invoke.side_effect = Exception("Stripe connection failed")
    mocker.patch("agents.billing_agent.stripe_tools", [mock_tool])

    _make_llm_pair(
        mocker,
        tool_calls=[{"name": "get_customer_info", "args": {"customer_id": "cust_bad"}}],
        final_text="An error occurred.\nCONFIDENCE: 0.40",
    )

    from agents.billing_agent import create_billing_agent

    agent = create_billing_agent()
    result = agent.invoke(_base_state())

    assert len(result["tool_results"]) == 1
    assert "error" in result["tool_results"][0]["result"]
    assert "Stripe connection failed" in result["tool_results"][0]["result"]["error"]


def test_billing_confidence_parse_failure_stays_default(mocker):
    """Non-numeric CONFIDENCE value falls back to 0.5 without crashing."""
    _make_llm_pair(mocker, final_text="Your invoice is ready.\nCONFIDENCE: high")

    from agents.billing_agent import create_billing_agent

    agent = create_billing_agent()
    result = agent.invoke(_base_state())

    assert result["confidence"] == pytest.approx(0.5)
