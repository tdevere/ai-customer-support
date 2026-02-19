"""
Unit tests for configuration management.
"""

import pytest
import os
from shared.config import Settings


def test_settings_initialization():
    """Test settings can be initialized."""
    settings = Settings()

    assert hasattr(settings, "azure_openai_endpoint")
    assert hasattr(settings, "cosmos_endpoint")
    assert hasattr(settings, "confidence_threshold")


def test_settings_defaults():
    """Test default values."""
    settings = Settings()

    assert settings.confidence_threshold == 0.7
    assert settings.max_retry_attempts == 3
    assert settings.azure_openai_api_version == "2024-02-15-preview"


def test_settings_from_env(monkeypatch):
    """Test settings load from environment variables."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.8")

    settings = Settings()

    assert settings.azure_openai_endpoint == "https://test.openai.azure.com"
    assert settings.confidence_threshold == 0.8
