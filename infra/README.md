# Azure Infrastructure for AAN Customer Support System

This directory contains Terraform configurations for provisioning the complete Azure infrastructure required for the Adaptive Agent Network (AAN) customer support system.

## Resources Provisioned

- **Azure Functions**: Serverless compute for webhook handlers and orchestrator
- **Cosmos DB**: NoSQL database for conversation state and agent registry
- **Azure AI Search**: Vector search and RAG knowledge base
- **Key Vault**: Secure storage for API keys and secrets
- **Application Insights**: Monitoring and observability
- **Storage Account**: Backend storage for Functions

## Prerequisites

1. Azure CLI installed and configured
2. Terraform >= 1.0
3. Azure subscription with appropriate permissions

## Usage

### Initialize Terraform

```bash
cd infra
terraform init
```

### Plan Deployment

```bash
terraform plan -var="environment=dev"
```

### Apply Infrastructure

```bash
terraform apply -var="environment=dev"
```

### Destroy Infrastructure

```bash
terraform destroy -var="environment=dev"
```

## Variables

- `environment`: Environment name (dev, staging, prod) - default: "dev"
- `location`: Azure region - default: "eastus"
- `project_name`: Project name - default: "aan-support"

## Outputs

After successful deployment, Terraform will output:

- `function_app_name`: Name of the deployed Function App
- `function_app_url`: URL of the Function App
- `key_vault_url`: Key Vault URI
- `cosmos_endpoint`: Cosmos DB endpoint
- `search_endpoint`: Azure AI Search endpoint
- `application_insights_key`: Application Insights instrumentation key (sensitive)

## Post-Deployment Steps

1. **Configure Secrets in Key Vault**:
   ```bash
   az keyvault secret set --vault-name <key-vault-name> --name "azure-openai-api-key" --value "<your-key>"
   az keyvault secret set --vault-name <key-vault-name> --name "intercom-access-token" --value "<your-token>"
   az keyvault secret set --vault-name <key-vault-name> --name "intercom-webhook-secret" --value "<your-secret>"
   az keyvault secret set --vault-name <key-vault-name> --name "stripe-api-key" --value "<your-key>"
   ```

2. **Initialize Agent Registry in Cosmos DB**:
   Upload agent configurations from `agents/registry.yaml` to the `agent_registry` container.

3. **Create Azure AI Search Index**:
   Create a search index named `support_knowledge` with vector fields.

4. **Deploy Function App Code**:
   ```bash
   func azure functionapp publish <function-app-name>
   ```

5. **Configure Intercom Webhook**:
   Set webhook URL to: `https://<function-app-url>/api/webhook`

## Cost Estimates

For development environment with moderate usage (1000 queries/day):

- Azure Functions (Consumption): ~$5-10/mo
- Cosmos DB (400 RU/s): ~$25/mo
- Azure AI Search (Basic): ~$75/mo
- Key Vault: ~$0.50/mo
- Storage Account: ~$1/mo
- Application Insights: ~$2/mo

**Total: ~$110-115/month**

Production environments should adjust SKUs and throughput accordingly.

## Security Considerations

- Function App uses Managed Identity to access Key Vault
- All secrets stored in Key Vault
- Cosmos DB uses encryption at rest
- TTL set on conversation state for GDPR compliance (7 days)
- Network security rules should be configured for production

## Monitoring

Access Application Insights through Azure Portal for:
- Request traces
- Failures and exceptions
- Performance metrics
- Custom events and logs
