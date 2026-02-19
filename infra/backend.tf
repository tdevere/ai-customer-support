# ---------------------------------------------------------------------------
# Terraform Remote State Backend — Azure Blob Storage
# ---------------------------------------------------------------------------
#
# The AAN infrastructure uses Azure Blob Storage as a remote Terraform
# backend so that state is shared across team members and CI/CD pipelines.
#
# HOW TO ENABLE
# -------------
# 1. Provision the storage resources (one-time, per environment):
#
#    az group create \
#      --name rg-terraform-state \
#      --location eastus
#
#    az storage account create \
#      --name stterraformaan<suffix> \
#      --resource-group rg-terraform-state \
#      --sku Standard_LRS \
#      --encryption-services blob \
#      --min-tls-version TLS1_2 \
#      --allow-blob-public-access false
#
#    az storage container create \
#      --name tfstate \
#      --account-name stterraformaan<suffix>
#
# 2. Uncomment the `terraform { backend "azurerm" { … } }` block below.
#
# 3. Re-run `terraform init` to migrate local state to remote storage:
#
#    terraform init -migrate-state
#
# 4. Authenticate using one of:
#    - Azure CLI  : `az login` (local dev)
#    - Env vars   : ARM_CLIENT_ID / ARM_CLIENT_SECRET / ARM_TENANT_ID /
#                   ARM_SUBSCRIPTION_ID  (CI/CD)
#    - Managed identity (GitHub Actions with azure/login@v2)
#
# SECURITY NOTE
# -------------
# Do NOT hard-code storage account keys here.  Use `ARM_ACCESS_KEY` env var,
# a managed identity, or `az storage account keys list` in CI via OIDC.
# ---------------------------------------------------------------------------

# Uncomment and adjust the values to enable remote state:
#
# terraform {
#   backend "azurerm" {
#     resource_group_name  = "rg-terraform-state"
#     storage_account_name = "stterraformaan<suffix>"
#     container_name       = "tfstate"
#     key                  = "aan-support.tfstate"
#
#     # Use Azure CLI credentials locally.
#     # In CI set ARM_CLIENT_ID / ARM_CLIENT_SECRET / ARM_TENANT_ID /
#     # ARM_SUBSCRIPTION_ID as environment variables.
#     use_azuread_auth = true
#   }
# }
