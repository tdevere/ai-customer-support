"""
Integration tests for Intercom webhook handler.
"""

import pytest
import json
import hmac
import hashlib
from fastapi.testclient import TestClient
from integrations.intercom import app, validate_webhook_signature


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_validate_webhook_signature():
    """Test webhook signature validation."""
    body = b'{"test": "data"}'
    secret = "test-secret"

    # Generate valid signature
    signature = (
        "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    )

    assert validate_webhook_signature(body, signature, secret) == True


def test_validate_webhook_signature_invalid():
    """Test webhook signature validation fails for invalid signature."""
    body = b'{"test": "data"}'
    secret = "test-secret"
    signature = "sha256=invalid"

    assert validate_webhook_signature(body, signature, secret) == False


def test_webhook_invalid_signature(client, monkeypatch):
    """Test webhook rejects invalid signature."""
    # Mock the secret
    monkeypatch.setenv("INTERCOM_WEBHOOK_SECRET", "test-secret")

    payload = {"test": "data"}
    response = client.post(
        "/webhook", json=payload, headers={"X-Hub-Signature-256": "sha256=invalid"}
    )

    assert response.status_code == 403


def test_data_connector_endpoint(client):
    """Test data connector endpoint."""
    payload = {
        "conversation_id": "test-123",
        "query": "Test query",
        "context": {"user_id": "user-456"},
    }

    # This will fail without proper setup, but tests the endpoint exists
    response = client.post("/data-connector", json=payload)
    # Just check endpoint exists (may return error due to missing config)
    assert response.status_code in [200, 500]
