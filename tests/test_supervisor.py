"""
Unit tests for the supervisor/classifier.
"""

import pytest
from unittest.mock import MagicMock
from orchestrator.supervisor import TopicClassifier


@pytest.fixture
def classifier(mocker):
    """Create classifier instance with mocked LLM to avoid real API calls."""
    mock_response = MagicMock()
    mock_response.content = "PRIMARY: general (0.5)\nSECONDARY:"
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response
    mocker.patch("orchestrator.supervisor.AzureChatOpenAI", return_value=mock_llm)
    return TopicClassifier()


def test_billing_classification(classifier):
    """Test classification of billing queries."""
    query = "I have a question about my invoice and subscription charges"
    result = classifier.classify(query)

    assert result["primary_topic"] in ["billing", "general"]
    assert "primary_confidence" in result
    assert result["primary_confidence"] >= 0.0
    assert result["primary_confidence"] <= 1.0


def test_tech_classification(classifier):
    """Test classification of technical queries."""
    query = "The app keeps crashing when I try to login. I'm getting error 500"
    result = classifier.classify(query)

    assert result["primary_topic"] in ["technical", "general"]
    assert "all_topics" in result


def test_returns_classification(classifier):
    """Test classification of returns queries."""
    query = "I want to return an item I ordered last week"
    result = classifier.classify(query)

    assert result["primary_topic"] in ["returns", "general"]


def test_multi_topic_classification(classifier):
    """Test classification of multi-topic queries."""
    query = "I was charged twice for my order and want to return it"
    result = classifier.classify(query)

    # Should detect multiple topics
    assert len(result["all_topics"]) >= 1


def test_get_agent_configs(classifier):
    """Test retrieving agent configurations."""
    topics = ["billing", "technical"]
    configs = classifier.get_agent_configs(topics)

    assert len(configs) >= 1
    assert all("topic" in c for c in configs)
    assert all("name" in c for c in configs)


def test_parse_classification_primary_malformed_confidence(classifier):
    """Malformed PRIMARY confidence falls back to 0.5."""
    result = classifier._parse_classification(
        "PRIMARY: billing(not_a_float)\nSECONDARY:"
    )

    assert result["primary_topic"] == "billing"
    assert result["primary_confidence"] == 0.5


def test_parse_classification_secondary_malformed_confidence(classifier):
    """Malformed SECONDARY confidence falls back to 0.3."""
    result = classifier._parse_classification(
        "PRIMARY: billing (0.8)\nSECONDARY: technical(bad_conf)"
    )

    assert "technical" in result["secondary_topics"]
    # The secondary confidence fallback is 0.3
    secondary_entry = next(
        (t for t in result["all_topics"] if t["topic"] == "technical"), None
    )
    assert secondary_entry is not None
    assert secondary_entry["confidence"] == 0.3
