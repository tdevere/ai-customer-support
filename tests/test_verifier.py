"""
Unit tests for the verifier agent.
"""

import pytest
from unittest.mock import MagicMock
from orchestrator.verifier import VerifierAgent


@pytest.fixture
def verifier(mocker):
    """Create verifier instance with mocked LLM to avoid real API calls.

    The mock response intentionally omits FINAL_CONFIDENCE so the verifier
    falls back to agent_confidence — this allows high/low confidence tests
    to behave correctly with their respective agent_confidence inputs.
    """
    mock_response = MagicMock()
    mock_response.content = (
        "GROUNDED: yes\nCOMPLETE: yes\nCONCERNS: none\nCRITIQUE: Mocked response"
    )
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response
    mocker.patch("orchestrator.verifier.AzureChatOpenAI", return_value=mock_llm)
    return VerifierAgent()


def test_verify_high_confidence_response(verifier):
    """Test verification of high confidence response."""
    query = "What is the return policy?"
    response = "Our return policy allows returns within 30 days of purchase."
    sources = [
        {
            "title": "Return Policy",
            "content": "Returns accepted within 30 days",
            "score": 0.9,
        }
    ]

    result = verifier.verify(
        query=query, response=response, sources=sources, agent_confidence=0.9
    )

    assert "final_confidence" in result
    assert "grounded" in result
    assert "should_escalate" in result
    assert isinstance(result["final_confidence"], float)


def test_verify_low_confidence_response(verifier):
    """Test verification triggers escalation for low confidence."""
    query = "Complex technical issue"
    response = "I'm not sure about this."
    sources = []

    result = verifier.verify(
        query=query, response=response, sources=sources, agent_confidence=0.3
    )

    assert result["final_confidence"] < 0.7
    assert result["should_escalate"] == True


def test_verify_with_tool_results(verifier):
    """Test verification with tool results."""
    query = "Check my invoice"
    response = "Your invoice total is $100"
    sources = []
    tool_results = [{"tool": "get_invoice", "result": {"total": 100}}]

    result = verifier.verify(
        query=query,
        response=response,
        sources=sources,
        agent_confidence=0.8,
        tool_results=tool_results,
    )

    assert "final_confidence" in result


def test_format_sources(verifier):
    """Test source formatting."""
    sources = [
        {"title": "Test", "content": "Content here"},
        {"title": "Test 2", "content": "More content"},
    ]

    formatted = verifier._format_sources(sources)
    assert isinstance(formatted, str)
    assert "Test" in formatted


def test_format_tools_empty_returns_no_tools_used(verifier):
    """_format_tools returns 'No tools used' when tool_results list is empty."""
    result = verifier._format_tools([])
    assert result == "No tools used"


def test_parse_verification_with_actual_concerns(verifier):
    """Actual concerns (not 'none') are parsed into a list."""
    result = verifier._parse_verification(
        "GROUNDED: partial\nCOMPLETE: no\nCONCERNS: missing data, unclear response\nCRITIQUE: Needs work",
        agent_confidence=0.6,
    )

    assert "missing data" in result["concerns"]
    assert "unclear response" in result["concerns"]


def test_parse_verification_with_valid_final_confidence(verifier):
    """FINAL_CONFIDENCE: <float> is parsed and stored."""
    result = verifier._parse_verification(
        "GROUNDED: yes\nCOMPLETE: yes\nCONCERNS: none\nFINAL_CONFIDENCE: 0.87\nCRITIQUE: Good",
        agent_confidence=0.5,
    )

    assert result["final_confidence"] == pytest.approx(0.87)


def test_parse_verification_invalid_final_confidence_uses_default(verifier):
    """Non-numeric FINAL_CONFIDENCE leaves the default agent_confidence unchanged."""
    result = verifier._parse_verification(
        "GROUNDED: yes\nCOMPLETE: yes\nCONCERNS: none\nFINAL_CONFIDENCE: unknown",
        agent_confidence=0.72,
    )

    # float("unknown") raises → except: pass → falls back to agent_confidence
    assert result["final_confidence"] == pytest.approx(0.72)
