"""
Test configuration and fixtures.
"""

import pytest
import os


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for all tests."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://mock.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "mock-api-key")
    monkeypatch.setenv("COSMOS_ENDPOINT", "https://mock.cosmos.azure.com")
    monkeypatch.setenv("COSMOS_KEY", "mock-cosmos-key")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://mock.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_KEY", "mock-search-key")
    monkeypatch.setenv("INTERCOM_ACCESS_TOKEN", "mock-intercom-token")
    monkeypatch.setenv("INTERCOM_WEBHOOK_SECRET", "mock-webhook-secret")
    monkeypatch.setenv("STRIPE_API_KEY", "mock-stripe-key")
    monkeypatch.setenv("ENVIRONMENT", "test")


@pytest.fixture
def sample_conversation_state():
    """Sample conversation state for testing."""
    return {
        "conversation_id": "test-conv-123",
        "user_id": "user-456",
        "message": "Test message",
        "context": {"customer_id": "cust_789", "email": "test@example.com"},
        "classification": {"primary_topic": "billing", "primary_confidence": 0.8},
        "specialist_responses": [
            {
                "agent": "billing",
                "response": "Test response",
                "confidence": 0.8,
                "sources": [],
            }
        ],
        "verification": {
            "final_confidence": 0.75,
            "grounded": "yes",
            "should_escalate": False,
        },
        "status": "success",
    }


@pytest.fixture
def sample_verification_result():
    """Sample verification result for testing."""
    return {
        "grounded": "yes",
        "complete": "yes",
        "concerns": [],
        "final_confidence": 0.8,
        "critique": "Good response",
        "should_escalate": False,
    }
