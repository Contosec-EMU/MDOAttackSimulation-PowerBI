#!/bin/bash
set -euo pipefail

# ============================================================================
# Setup Azure OIDC Federation with GitHub Actions
# ============================================================================
# This script configures Azure Entra ID to trust GitHub's OIDC provider,
# eliminating the need for long-lived secrets in GitHub Actions.
#
# Prerequisites:
#   - Azure CLI installed and authenticated (az login)
#   - GitHub repository created (can be empty)
#   - Permissions: Entra ID Application Administrator + Subscription Owner/User Access Administrator
#
# Usage:
#   ./scripts/setup-github-oidc.sh <github-org> <github-repo>
#
# Example:
#   ./scripts/setup-github-oidc.sh myorg MDOAttackSimulation_PowerBI
# ============================================================================

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✅${NC} $1"; }
warn() { echo -e "${YELLOW}⚠️${NC} $1"; }
error() { echo -e "${RED}❌${NC} $1"; exit 1; }

# ============================================================================
# Validate inputs
# ============================================================================

if [ $# -ne 2 ]; then
  error "Usage: $0 <github-org> <github-repo>"
fi

GITHUB_ORG="$1"
GITHUB_REPO="$2"
APP_NAME="gh-oidc-${GITHUB_REPO}"
RESOURCE_GROUP="rg-mdo-attack-simulation"
AZURE_REGION="westus2"

info "GitHub Repository: ${GITHUB_ORG}/${GITHUB_REPO}"
info "Azure App Registration: ${APP_NAME}"
info "Resource Group: ${RESOURCE_GROUP}"

# ============================================================================
# Check Azure CLI authentication
# ============================================================================

info "Checking Azure CLI authentication..."
if ! az account show &>/dev/null; then
  error "Not logged into Azure CLI. Run: az login"
fi

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
SUBSCRIPTION_NAME=$(az account show --query name -o tsv)

success "Authenticated to Azure"
info "  Subscription: ${SUBSCRIPTION_NAME}"
info "  Subscription ID: ${SUBSCRIPTION_ID}"
info "  Tenant ID: ${TENANT_ID}"

# ============================================================================
# Create or update App Registration
# ============================================================================

info "Creating/updating Entra ID App Registration..."

# Check if app exists
APP_ID=$(az ad app list --display-name "${APP_NAME}" --query "[0].appId" -o tsv 2>/dev/null || echo "")

if [ -z "$APP_ID" ]; then
  info "Creating new app registration: ${APP_NAME}"
  APP_ID=$(az ad app create \
    --display-name "${APP_NAME}" \
    --query appId -o tsv)
  success "App registration created: ${APP_ID}"
else
  warn "App registration already exists: ${APP_ID}"
fi

# Get object ID for the app
APP_OBJECT_ID=$(az ad app show --id "${APP_ID}" --query id -o tsv)

# ============================================================================
# Configure OIDC Federated Credentials for GitHub
# ============================================================================

info "Configuring federated credentials for GitHub OIDC..."

# Credential for main branch
CRED_NAME_MAIN="github-${GITHUB_ORG}-${GITHUB_REPO}-main"
SUBJECT_MAIN="repo:${GITHUB_ORG}/${GITHUB_REPO}:ref:refs/heads/main"

# Check if credential exists
if az ad app federated-credential show \
  --id "${APP_ID}" \
  --federated-credential-id "${CRED_NAME_MAIN}" &>/dev/null; then
  warn "Federated credential already exists: ${CRED_NAME_MAIN}"
else
  az ad app federated-credential create \
    --id "${APP_ID}" \
    --parameters "{
      \"name\": \"${CRED_NAME_MAIN}\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"${SUBJECT_MAIN}\",
      \"audiences\": [\"api://AzureADTokenExchange\"],
      \"description\": \"GitHub Actions OIDC for ${GITHUB_ORG}/${GITHUB_REPO} main branch\"
    }" >/dev/null

  success "Federated credential created: ${CRED_NAME_MAIN}"
fi

# ============================================================================
# Create Service Principal
# ============================================================================

info "Creating/updating Service Principal..."

# Check if service principal exists
SP_ID=$(az ad sp list --filter "appId eq '${APP_ID}'" --query "[0].id" -o tsv 2>/dev/null || echo "")

if [ -z "$SP_ID" ]; then
  info "Creating service principal..."
  SP_ID=$(az ad sp create --id "${APP_ID}" --query id -o tsv)
  success "Service principal created: ${SP_ID}"
else
  warn "Service principal already exists: ${SP_ID}"
fi

# ============================================================================
# Create Resource Group (if not exists)
# ============================================================================

info "Ensuring resource group exists: ${RESOURCE_GROUP}"

if az group show --name "${RESOURCE_GROUP}" &>/dev/null; then
  warn "Resource group already exists: ${RESOURCE_GROUP}"
else
  az group create \
    --name "${RESOURCE_GROUP}" \
    --location "${AZURE_REGION}" \
    --tags project=MDOAttackSimulation environment=production deployment=github-actions
  success "Resource group created: ${RESOURCE_GROUP}"
fi

# ============================================================================
# Assign RBAC Roles
# ============================================================================

info "Assigning RBAC roles to service principal..."

# Contributor role (to create resources)
CONTRIBUTOR_ASSIGNMENT=$(az role assignment list \
  --assignee "${APP_ID}" \
  --role "Contributor" \
  --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}" \
  --query "[0].id" -o tsv 2>/dev/null || echo "")

if [ -z "$CONTRIBUTOR_ASSIGNMENT" ]; then
  az role assignment create \
    --assignee "${APP_ID}" \
    --role "Contributor" \
    --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}" \
    >/dev/null
  success "Assigned 'Contributor' role on resource group"
else
  warn "Contributor role already assigned"
fi

# User Access Administrator role (to create RBAC assignments in Bicep)
UAA_ASSIGNMENT=$(az role assignment list \
  --assignee "${APP_ID}" \
  --role "User Access Administrator" \
  --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}" \
  --query "[0].id" -o tsv 2>/dev/null || echo "")

if [ -z "$UAA_ASSIGNMENT" ]; then
  az role assignment create \
    --assignee "${APP_ID}" \
    --role "User Access Administrator" \
    --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}" \
    >/dev/null
  success "Assigned 'User Access Administrator' role on resource group"
else
  warn "User Access Administrator role already assigned"
fi

# ============================================================================
# Summary
# ============================================================================

echo ""
echo "========================================================================"
success "Azure OIDC setup complete!"
echo "========================================================================"
echo ""
info "Next steps:"
echo ""
echo "1. Add these secrets to your GitHub repository:"
echo "   Repository Settings > Secrets and variables > Actions > New repository secret"
echo ""
echo "   AZURE_CLIENT_ID:       ${APP_ID}"
echo "   AZURE_TENANT_ID:       ${TENANT_ID}"
echo "   AZURE_SUBSCRIPTION_ID: ${SUBSCRIPTION_ID}"
echo ""
echo "2. Store your Graph API client secret in Azure Key Vault:"
echo "   (After infrastructure is deployed)"
echo ""
echo "   az keyvault secret set \\"
echo "     --vault-name <keyvault-name> \\"
echo "     --name \"graph-client-secret\" \\"
echo "     --value \"<your-graph-api-secret>\""
echo ""
echo "3. Push code to main branch to trigger deployment:"
echo ""
echo "   git add ."
echo "   git commit -m \"Initial commit with GitHub Actions\""
echo "   git push origin main"
echo ""
info "GitHub Actions workflow will automatically deploy on push to main"
echo ""
