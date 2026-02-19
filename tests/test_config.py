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


# ---------------------------------------------------------------------------
# get_secret_from_keyvault
# ---------------------------------------------------------------------------


class TestGetSecretFromKeyvault:
    def _call(self, secret_name: str):
        from shared.config import get_secret_from_keyvault

        return get_secret_from_keyvault(secret_name)

    def test_returns_none_when_no_vault_url(self, monkeypatch):
        """Returns None immediately when key_vault_url is not configured."""
        from shared.config import settings

        monkeypatch.setattr(settings, "key_vault_url", None)
        result = self._call("my-secret")
        assert result is None

    def test_returns_secret_value_when_configured(self, monkeypatch):
        """Returns the secret value from Key Vault when credentials are valid."""
        from unittest.mock import MagicMock, patch
        from shared.config import settings

        monkeypatch.setattr(
            settings, "key_vault_url", "https://myvault.vault.azure.net/"
        )

        mock_secret = MagicMock()
        mock_secret.value = "super-secret-value"

        mock_kv_client = MagicMock()
        mock_kv_client.get_secret.return_value = mock_secret

        with (
            patch("shared.config.DefaultAzureCredential", return_value=MagicMock()),
            patch("shared.config.SecretClient", return_value=mock_kv_client),
        ):
            result = self._call("my-secret")

        assert result == "super-secret-value"
        mock_kv_client.get_secret.assert_called_once_with("my-secret")

    def test_returns_none_on_exception(self, monkeypatch):
        """Returns None (not raises) when Key Vault access fails."""
        from unittest.mock import patch
        from shared.config import settings

        monkeypatch.setattr(
            settings, "key_vault_url", "https://myvault.vault.azure.net/"
        )

        with patch(
            "shared.config.DefaultAzureCredential",
            side_effect=RuntimeError("auth failed"),
        ):
            result = self._call("my-secret")

        assert result is None

    def test_secret_client_called_with_correct_vault_url(self, monkeypatch):
        """SecretClient is constructed with the configured vault URL."""
        from unittest.mock import MagicMock, patch
        from shared.config import settings

        vault_url = "https://testvault.vault.azure.net/"
        monkeypatch.setattr(settings, "key_vault_url", vault_url)

        mock_secret = MagicMock()
        mock_secret.value = "val"
        mock_kv_client = MagicMock()
        mock_kv_client.get_secret.return_value = mock_secret
        mock_cred = MagicMock()

        with (
            patch("shared.config.DefaultAzureCredential", return_value=mock_cred),
            patch(
                "shared.config.SecretClient", return_value=mock_kv_client
            ) as mock_sc_cls,
        ):
            self._call("db-password")

        mock_sc_cls.assert_called_once_with(vault_url=vault_url, credential=mock_cred)


# ---------------------------------------------------------------------------
# load_secrets_from_keyvault
# ---------------------------------------------------------------------------


class TestLoadSecretsFromKeyvault:
    def test_does_nothing_when_no_vault_url(self, monkeypatch):
        """Returns immediately without calling Key Vault when vault URL is absent."""
        from unittest.mock import patch
        from shared.config import settings, load_secrets_from_keyvault

        monkeypatch.setattr(settings, "key_vault_url", None)

        with patch("shared.config.get_secret_from_keyvault") as mock_get:
            load_secrets_from_keyvault()

        mock_get.assert_not_called()

    def test_loads_all_mapped_secrets(self, monkeypatch):
        """Calls get_secret_from_keyvault for every mapped key and applies values."""
        from unittest.mock import patch
        from shared.config import settings, load_secrets_from_keyvault

        monkeypatch.setattr(settings, "key_vault_url", "https://vault.azure.net/")

        def fake_get_secret(name: str):
            return f"value-for-{name}"

        with patch(
            "shared.config.get_secret_from_keyvault", side_effect=fake_get_secret
        ):
            load_secrets_from_keyvault()

        assert settings.azure_openai_api_key == "value-for-azure-openai-api-key"
        assert settings.cosmos_key == "value-for-cosmos-key"
        assert settings.stripe_api_key == "value-for-stripe-api-key"
        assert settings.jira_api_token == "value-for-jira-api-token"

    def test_skips_none_values(self, monkeypatch):
        """Does not overwrite settings attributes when Key Vault returns None."""
        from unittest.mock import patch
        from shared.config import settings, load_secrets_from_keyvault

        monkeypatch.setattr(settings, "key_vault_url", "https://vault.azure.net/")
        original_key = settings.stripe_api_key

        with patch("shared.config.get_secret_from_keyvault", return_value=None):
            load_secrets_from_keyvault()

        assert settings.stripe_api_key == original_key

    def test_partial_secrets_only_updates_available_ones(self, monkeypatch):
        """Only secrets with non-None values overwrite the corresponding settings."""
        from unittest.mock import patch
        from shared.config import settings, load_secrets_from_keyvault

        monkeypatch.setattr(settings, "key_vault_url", "https://vault.azure.net/")
        monkeypatch.setattr(settings, "cosmos_key", "old-cosmos-key")

        def selective_get(name: str):
            return "new-cosmos-key" if name == "cosmos-key" else None

        with patch("shared.config.get_secret_from_keyvault", side_effect=selective_get):
            load_secrets_from_keyvault()

        assert settings.cosmos_key == "new-cosmos-key"
