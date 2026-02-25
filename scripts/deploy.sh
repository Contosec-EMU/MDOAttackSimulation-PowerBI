#!/bin/bash
# MDO Attack Simulation Pipeline - Deployment Script (Bash)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}=== MDO Attack Simulation Pipeline Deployment ===${NC}"

# Check required parameters
if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ]; then
    echo "Usage: ./deploy.sh <subscription-id> <tenant-id> <graph-client-id> <graph-client-secret> [--network-isolation none|private]"
    echo ""
    echo "Optional environment variables:"
    echo "  RESOURCE_GROUP  - Resource group name (default: rg-mdo-attack-simulation)"
    echo "  LOCATION        - Azure region (default: eastus)"
    exit 1
fi

SUBSCRIPTION_ID=$1
TENANT_ID=$2
GRAPH_CLIENT_ID=$3
GRAPH_CLIENT_SECRET=$4
RESOURCE_GROUP=${RESOURCE_GROUP:-"rg-mdo-attack-simulation"}
LOCATION=${LOCATION:-"eastus"}
NETWORK_ISOLATION="none"

# Parse optional flags
shift 4
while [[ $# -gt 0 ]]; do
    case "$1" in
        --network-isolation)
            NETWORK_ISOLATION="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Validate network isolation value
if [[ "$NETWORK_ISOLATION" != "none" && "$NETWORK_ISOLATION" != "private" ]]; then
    echo -e "${RED}NetworkIsolation must be 'none' or 'private', got: $NETWORK_ISOLATION${NC}"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${CYAN}Network isolation: $NETWORK_ISOLATION${NC}"

# Step 1: Set subscription
echo -e "\n${YELLOW}[1/4] Setting Azure subscription...${NC}"
az account set --subscription "$SUBSCRIPTION_ID"

# Step 2: Create resource group
echo -e "\n${YELLOW}[2/4] Creating resource group: $RESOURCE_GROUP...${NC}"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# Step 3: Deploy Bicep
echo -e "\n${YELLOW}[3/4] Deploying infrastructure (Bicep)...${NC}"
DEPLOYMENT_OUTPUT=$(az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file "$SCRIPT_DIR/../infra/main.bicep" \
    --parameters prefix=mdoast location="$LOCATION" tenantId="$TENANT_ID" graphClientId="$GRAPH_CLIENT_ID" graphClientSecret="$GRAPH_CLIENT_SECRET" networkIsolation="$NETWORK_ISOLATION" \
    --query "properties.outputs" \
    --output json)

KEYVAULT_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.keyVaultName.value')
FUNCTION_APP_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.functionAppName.value')
STORAGE_ACCOUNT_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.dataLakeAccountName.value')

echo -e "  ${GREEN}Key Vault: $KEYVAULT_NAME${NC}"
echo -e "  ${GREEN}Function App: $FUNCTION_APP_NAME${NC}"
echo -e "  ${GREEN}Storage Account: $STORAGE_ACCOUNT_NAME${NC}"

# Step 4: Graph client secret is now managed by Bicep deployment (graphClientSecret parameter)
# No need for a separate az keyvault secret set step.

# Step 5: Deploy Function code
echo -e "\n${YELLOW}[4/4] Deploying Function App code...${NC}"
pushd "$SCRIPT_DIR/../src/function_app" > /dev/null
func azure functionapp publish "$FUNCTION_APP_NAME" --python
popd > /dev/null

# Summary
echo -e "\n${GREEN}=== Deployment Complete ===${NC}"
echo -e "${CYAN}"
cat << EOF

Resources Created:
  Resource Group:    $RESOURCE_GROUP
  Storage Account:   $STORAGE_ACCOUNT_NAME
  Function App:      $FUNCTION_APP_NAME
  Key Vault:         $KEYVAULT_NAME

Next Steps:
  1. Verify deployment: az functionapp show -g $RESOURCE_GROUP -n $FUNCTION_APP_NAME
  2. Test function manually via Azure Portal or CLI
  3. Configure Power BI to connect to: https://$STORAGE_ACCOUNT_NAME.dfs.core.windows.net/curated

Power BI Connection:
  Storage URL: https://$STORAGE_ACCOUNT_NAME.dfs.core.windows.net/
  Container:   curated
  Format:      Parquet (partitioned by date)

EOF
echo -e "${NC}"
