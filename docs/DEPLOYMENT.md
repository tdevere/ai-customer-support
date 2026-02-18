# Deployment Guide

This guide walks you through deploying the AAN Customer Support System to Azure.

## Prerequisites

- Azure CLI installed (`az --version`)
- Azure subscription with Owner or Contributor role
- Terraform >= 1.0
- Python 3.11+
- Azure Functions Core Tools (`func --version`)

## Step 1: Azure Login

```bash
az login
az account set --subscription "Your-Subscription-Name"
```

## Step 2: Deploy Infrastructure with Terraform

```bash
cd infra
terraform init
terraform plan -var="environment=dev" -var="location=eastus"
terraform apply -var="environment=dev" -var="location=eastus"
```

## Step 3: Configure Secrets in Key Vault

```bash
# Get Key Vault name
KV_NAME=$(cd infra && terraform output -raw key_vault_url | cut -d'/' -f3 | cut -d'.' -f1)

# Set secrets
az keyvault secret set --vault-name $KV_NAME \
  --name "azure-openai-api-key" --value "your-key"

az keyvault secret set --vault-name $KV_NAME \
  --name "intercom-access-token" --value "your-token"

az keyvault secret set --vault-name $KV_NAME \
  --name "intercom-webhook-secret" --value "your-secret"
```

## Step 4: Deploy Function App

```bash
func azure functionapp publish func-aan-support-dev --python
```

## Step 5: Configure Intercom Webhook

1. Go to Intercom Settings → Webhooks
2. Add webhook URL: `https://func-aan-support-dev.azurewebsites.net/api/webhook`
3. Subscribe to: `conversation.user.replied`, `conversation.user.created`

## Step 6: Test

```bash
curl https://func-aan-support-dev.azurewebsites.net/api/health
```

For detailed instructions, see the full documentation in the repository.
