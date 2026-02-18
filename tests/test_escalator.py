"""
Unit tests for the escalator agent.
"""
import pytest
from orchestrator.escalator import EscalatorAgent


@pytest.fixture
def escalator():
    """Create escalator instance."""
    return EscalatorAgent()


def test_escalate_basic(escalator):
    """Test basic escalation."""
    result = escalator.escalate(
        conversation_id="test-123",
        query="Complex issue",
        attempted_responses=[
            {
                "agent": "billing",
                "response": "Unable to resolve",
                "confidence": 0.3
            }
        ],
        verification_result={
            "final_confidence": 0.3,
            "grounded": "no",
            "concerns": ["Low confidence"]
        }
    )
    
    assert result["status"] == "escalated"
    assert "summary" in result
    assert "priority" in result
    assert "tags" in result
    assert result["requires_human"] == True


def test_escalate_with_context(escalator):
    """Test escalation with user context."""
    result = escalator.escalate(
        conversation_id="test-456",
        query="Billing issue",
        attempted_responses=[],
        verification_result={"final_confidence": 0.4},
        user_context={
            "customer_id": "cust_123",
            "tier": "premium"
        }
    )
    
    assert "customer_id" in result["summary"]
    assert "premium" in result["summary"]


def test_determine_priority_high(escalator):
    """Test high priority determination."""
    verification = {
        "final_confidence": 0.2,
        "concerns": ["Issue 1", "Issue 2", "Issue 3", "Issue 4"]
    }
    
    priority = escalator._determine_priority(verification)
    assert priority == "high"


def test_determine_priority_normal(escalator):
    """Test normal priority determination."""
    verification = {
        "final_confidence": 0.6,
        "concerns": []
    }
    
    priority = escalator._determine_priority(verification)
    assert priority == "normal"


def test_suggest_tags(escalator):
    """Test tag suggestion."""
    tags = escalator._suggest_tags(
        query="Test query",
        attempted_responses=[
            {"agent": "billing", "confidence": 0.4}
        ],
        verification={"final_confidence": 0.3}
    )
    
    assert "escalated" in tags
    assert "attempted_billing" in tags
    assert len(tags) > 0
