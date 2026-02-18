"""
Unit tests for the supervisor/classifier.
"""
import pytest
from orchestrator.supervisor import TopicClassifier


@pytest.fixture
def classifier():
    """Create classifier instance."""
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
