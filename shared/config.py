"""
Shared configuration management for the AAN system.
Loads settings from environment variables and Azure Key Vault.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Azure OpenAI
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_api_version: str = "2024-02-15-preview"
    # Deployment names vary by Azure subscription — override via env if yours differ.
    azure_openai_deployment_gpt4: str = os.getenv(
        "AZURE_OPENAI_DEPLOYMENT_GPT4", "gpt-4o"
    )
    azure_openai_deployment_gpt4_mini: str = os.getenv(
        "AZURE_OPENAI_DEPLOYMENT_GPT4_MINI", "gpt-4o-mini"
    )

    # Azure Cosmos DB
    cosmos_endpoint: str = os.getenv("COSMOS_ENDPOINT", "")
    cosmos_key: str = os.getenv("COSMOS_KEY", "")
    cosmos_database: str = "aan_support"
    cosmos_container_state: str = "conversation_state"
    cosmos_container_registry: str = "agent_registry"

    # Azure AI Search
    azure_search_endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    azure_search_key: str = os.getenv("AZURE_SEARCH_KEY", "")
    azure_search_index: str = "support_knowledge"

    # Intercom (legacy – kept for backward compat; not required by conversations.py)
    intercom_access_token: str = os.getenv("INTERCOM_ACCESS_TOKEN", "")
    intercom_webhook_secret: str = os.getenv("INTERCOM_WEBHOOK_SECRET", "")

    # Generic conversation API
    support_api_key: str = os.getenv("SUPPORT_API_KEY", "")
    # Leave blank to disable authentication (useful in dev / CI)

    # External Services
    stripe_api_key: str = os.getenv("STRIPE_API_KEY", "")
    jira_api_token: str = os.getenv("JIRA_API_TOKEN", "")
    jira_base_url: str = os.getenv("JIRA_BASE_URL", "")
    # Jira Cloud REST API v3 requires Basic auth with email:api_token (base64-encoded).
    # JIRA_EMAIL should be the Atlassian account email associated with the API token.
    jira_email: str = os.getenv("JIRA_EMAIL", "")
    jira_project_key: str = os.getenv("JIRA_PROJECT_KEY", "SUP")
    shopify_api_key: str = os.getenv("SHOPIFY_API_KEY", "")
    shopify_shop_url: str = os.getenv("SHOPIFY_SHOP_URL", "")

    # Application
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    confidence_threshold: float = 0.7
    max_retry_attempts: int = 3
    request_timeout: int = 30

    # Key Vault (optional)
    key_vault_url: Optional[str] = os.getenv("KEY_VAULT_URL")

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_secret_from_keyvault(secret_name: str) -> Optional[str]:
    """
    Retrieve a secret from Azure Key Vault.

    Args:
        secret_name: Name of the secret to retrieve

    Returns:
        Secret value or None if not found
    """
    if not settings.key_vault_url:
        return None

    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=settings.key_vault_url, credential=credential)
        secret = client.get_secret(secret_name)
        return secret.value
    except Exception as e:
        print(f"Failed to retrieve secret {secret_name}: {e}")
        return None


def load_secrets_from_keyvault():
    """Load all secrets from Key Vault if configured."""
    if not settings.key_vault_url:
        return

    secret_mappings = {
        "azure-openai-api-key": "azure_openai_api_key",
        "cosmos-key": "cosmos_key",
        "azure-search-key": "azure_search_key",
        "intercom-access-token": "intercom_access_token",
        "intercom-webhook-secret": "intercom_webhook_secret",
        "stripe-api-key": "stripe_api_key",
        "jira-api-token": "jira_api_token",
        "shopify-api-key": "shopify_api_key",
    }

    for kv_name, setting_name in secret_mappings.items():
        value = get_secret_from_keyvault(kv_name)
        if value:
            setattr(settings, setting_name, value)
