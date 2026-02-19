# Deployment Guide

This guide walks you through deploying the AAN Customer Support System to Azure.

## Prerequisites

- Azure CLI installed (`az --version`)
- Azure subscription with Owner or Contributor role
- Terraform >= 1.0
- Python 3.11+
- Azure Functions Core Tools (`func --version`)
- `uv` package manager (`pip install uv`)

## Step 0: Run Tests Locally

Verify everything is green before deploying:

```powershell
# Windows
.\scripts\test_local.ps1
```

```bash
# Linux / macOS
pytest tests/ -q --cov-fail-under=90
```

## Step 1: Azure Login

```bash
az login
az account set --subscription "Your-Subscription-Name"
```

## Step 2: Provision Remote State Backend (first deploy only)

Terraform state is stored in Azure Blob Storage.  Run this once per environment:

```bash
az group create --name rg-terraform-state --location eastus

az storage account create \
  --name stterraformaan<suffix> \
  --resource-group rg-terraform-state \
  --sku Standard_LRS \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false

az storage container create \
  --name tfstate \
  --account-name stterraformaan<suffix>
```

Then uncomment the `backend "azurerm"` block in [infra/backend.tf](../infra/backend.tf)
and update the storage account name.  Run:

```bash
cd infra
terraform init -migrate-state
```

## Step 3: Deploy Infrastructure with Terraform

```bash
cd infra
terraform init
terraform plan -var="environment=dev" -var="location=eastus"
terraform apply -var="environment=dev" -var="location=eastus"
```

## Step 4: Configure Secrets in Key Vault

```bash
# Get Key Vault name from Terraform output
KV_NAME=$(terraform output -raw key_vault_url | cut -d'/' -f3 | cut -d'.' -f1)

# Core secrets
az keyvault secret set --vault-name $KV_NAME \
  --name "azure-openai-api-key" --value "your-key"

az keyvault secret set --vault-name $KV_NAME \
  --name "intercom-access-token" --value "your-token"

az keyvault secret set --vault-name $KV_NAME \
  --name "intercom-webhook-secret" --value "your-secret"

# Optional: Application Insights
az keyvault secret set --vault-name $KV_NAME \
  --name "appinsights-connection-string" --value "InstrumentationKey=..."
```

## Step 5: Deploy Function App

```bash
# From the repo root
func azure functionapp publish func-aan-support-dev --python
```

The `APPINSIGHTS_CONNECTION_STRING` setting is automatically populated from the
Application Insights resource created by Terraform.  Telemetry is enabled in
production without any code changes.

## Step 6: Configure Intercom Webhook (optional)

Skip this step if using the REST API directly.

1. Go to Intercom Settings → Webhooks
2. Add webhook URL: `https://func-aan-support-dev.azurewebsites.net/api/webhook`
3. Subscribe to: `conversation.user.replied`, `conversation.user.created`
4. Copy the webhook secret to Key Vault (Step 4)

## Step 7: Smoke Test

```bash
# Health check
curl https://func-aan-support-dev.azurewebsites.net/api/health

# Start a conversation via the REST API
curl -X POST https://func-aan-support-dev.azurewebsites.net/api/conversations \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user", "message": "What are your prices?"}'

# Verify X-Request-ID is returned for tracing
curl -v https://func-aan-support-dev.azurewebsites.net/api/health 2>&1 | grep -i x-request-id
```

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY` | Yes | Azure OpenAI API key |
| `COSMOS_ENDPOINT` | Yes | Cosmos DB endpoint |
| `COSMOS_KEY` | Yes | Cosmos DB key (base64) |
| `AZURE_SEARCH_ENDPOINT` | Yes | Azure AI Search endpoint |
| `AZURE_SEARCH_KEY` | Yes | Azure AI Search key |
| `INTERCOM_ACCESS_TOKEN` | Optional | Required for Intercom webhook |
| `INTERCOM_WEBHOOK_SECRET` | Optional | Required for Intercom webhook |
| `SUPPORT_API_KEY` | Optional | Set to enable REST API key auth |
| `APPINSIGHTS_CONNECTION_STRING` | Optional | Application Insights telemetry |
| `LOG_LEVEL` | Optional | `DEBUG`/`INFO`/`WARNING` (default: `INFO`) |
| `ENVIRONMENT` | Optional | `development`/`production` (default: `development`) |
