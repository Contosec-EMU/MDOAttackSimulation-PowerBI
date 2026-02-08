#!/bin/bash
# Deploy the Streamlit Executive Dashboard to Azure
#
# Usage:
#   ./deploy-dashboard.sh -g <resource-group> [-c <dashboard-client-id>]
#
# If -c is omitted, an Entra ID app registration is created automatically.

set -euo pipefail

usage() {
    echo "Usage: $0 -g <resource-group> [-c <dashboard-client-id>]"
    exit 1
}

DASHBOARD_CLIENT_ID=""

while getopts "g:c:" opt; do
    case $opt in
        g) RESOURCE_GROUP="$OPTARG" ;;
        c) DASHBOARD_CLIENT_ID="$OPTARG" ;;
        *) usage ;;
    esac
done

[ -z "${RESOURCE_GROUP:-}" ] && usage

echo "=== MDO Attack Simulation — Dashboard Deployment ==="

# Verify resource group exists
echo -e "\n1. Reading existing infrastructure..."
if [ "$(az group exists --name "$RESOURCE_GROUP" -o tsv)" != "true" ]; then
    echo "ERROR: Resource group '$RESOURCE_GROUP' not found. Deploy the main infrastructure first." >&2
    exit 1
fi

# Find the main deployment outputs (try common deployment names)
MAIN_OUTPUT_JSON=""
for DEPLOY_NAME in main azure-deploy "$RESOURCE_GROUP"; do
    MAIN_OUTPUT_JSON=$(az deployment group show \
        --resource-group "$RESOURCE_GROUP" \
        --name "$DEPLOY_NAME" \
        --query "properties.outputs" -o json 2>/dev/null) && break
    MAIN_OUTPUT_JSON=""
done

if [ -z "$MAIN_OUTPUT_JSON" ]; then
    echo "ERROR: Could not find the main Bicep deployment in resource group '$RESOURCE_GROUP'." >&2
    echo "  Expected a deployment named 'main'. List deployments with:" >&2
    echo "    az deployment group list --resource-group $RESOURCE_GROUP --query \"[].name\" -o tsv" >&2
    exit 1
fi

APP_SERVICE_PLAN_ID=$(az appservice plan list \
    --resource-group "$RESOURCE_GROUP" \
    --query "[0].id" -o tsv)

if [ -z "$APP_SERVICE_PLAN_ID" ]; then
    echo "ERROR: No App Service Plan found in resource group '$RESOURCE_GROUP'." >&2
    exit 1
fi

DATA_LAKE_NAME=$(echo "$MAIN_OUTPUT_JSON" | jq -r '.dataLakeAccountName.value')
STORAGE_URL=$(echo "$MAIN_OUTPUT_JSON" | jq -r '.adlsGen2Endpoint.value')
SUBNET_ID=$(echo "$MAIN_OUTPUT_JSON" | jq -r '.functionSubnetId.value')

if [ -z "$DATA_LAKE_NAME" ] || [ "$DATA_LAKE_NAME" = "null" ] || \
   [ -z "$STORAGE_URL" ] || [ "$STORAGE_URL" = "null" ] || \
   [ -z "$SUBNET_ID" ] || [ "$SUBNET_ID" = "null" ]; then
    echo "ERROR: Missing expected outputs from main deployment (dataLakeAccountName, adlsGen2Endpoint, functionSubnetId)." >&2
    echo "  The main infrastructure may need to be redeployed." >&2
    exit 1
fi

APP_INSIGHTS_CS=$(az monitor app-insights component show \
    --resource-group "$RESOURCE_GROUP" \
    --query "[0].connectionString" -o tsv)

TENANT_ID=$(az account show --query tenantId -o tsv)

echo "  Data Lake: $DATA_LAKE_NAME"
echo "  Storage URL: $STORAGE_URL"

# Create app registration if not provided
if [ -z "$DASHBOARD_CLIENT_ID" ]; then
    echo -e "\n2. Creating Entra ID app registration..."
    APP_DISPLAY_NAME="MDOAttackSimulation-Dashboard"
    # Check if app registration already exists
    EXISTING_APP_ID=$(az ad app list --display-name "$APP_DISPLAY_NAME" --query "[0].appId" -o tsv 2>/dev/null)
    if [ -n "$EXISTING_APP_ID" ] && [ "$EXISTING_APP_ID" != "None" ]; then
        DASHBOARD_CLIENT_ID="$EXISTING_APP_ID"
        echo "  Found existing app registration: $APP_DISPLAY_NAME ($DASHBOARD_CLIENT_ID)"
    else
        DASHBOARD_CLIENT_ID=$(az ad app create \
            --display-name "$APP_DISPLAY_NAME" \
            --sign-in-audience AzureADMyOrg \
            --query "appId" -o tsv)
        if [ -z "$DASHBOARD_CLIENT_ID" ]; then
            echo "ERROR: Failed to create app registration. Check your Entra ID permissions." >&2
            exit 1
        fi
        az ad sp create --id "$DASHBOARD_CLIENT_ID" > /dev/null
        echo "  Created app registration: $APP_DISPLAY_NAME ($DASHBOARD_CLIENT_ID)"
    fi
    # Ensure identifier URI and ID token issuance are set (required by EasyAuth)
    az ad app update --id "$DASHBOARD_CLIENT_ID" --identifier-uris "api://$DASHBOARD_CLIENT_ID" 2>/dev/null
    az ad app update --id "$DASHBOARD_CLIENT_ID" --enable-id-token-issuance true 2>/dev/null
else
    echo -e "\n2. Using existing app registration: $DASHBOARD_CLIENT_ID"
fi

# Deploy Bicep
echo -e "\n3. Deploying dashboard infrastructure..."
DEPLOY_OUTPUT=$(az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file infra/dashboard.bicep \
    --parameters \
        appServicePlanId="$APP_SERVICE_PLAN_ID" \
        dataLakeAccountName="$DATA_LAKE_NAME" \
        storageAccountUrl="$STORAGE_URL" \
        tenantId="$TENANT_ID" \
        dashboardClientId="$DASHBOARD_CLIENT_ID" \
        appInsightsConnectionString="$APP_INSIGHTS_CS" \
        subnetId="$SUBNET_ID")

DASHBOARD_NAME=$(echo "$DEPLOY_OUTPUT" | jq -r '.properties.outputs.dashboardAppName.value')
DASHBOARD_URL=$(echo "$DEPLOY_OUTPUT" | jq -r '.properties.outputs.dashboardUrl.value')

echo "  Dashboard App: $DASHBOARD_NAME"
echo "  Dashboard URL: $DASHBOARD_URL"

# Update app registration redirect URI with the actual URL
echo -e "\n4. Updating app registration redirect URI..."
REDIRECT_URI="$DASHBOARD_URL/.auth/login/aad/callback"
az ad app update --id "$DASHBOARD_CLIENT_ID" --web-redirect-uris "$REDIRECT_URI"
echo "  Redirect URI: $REDIRECT_URI"

# Deploy code — source only, startup.sh installs deps on first boot
echo -e "\n5. Publishing Streamlit app..."
echo "  Packaging source code (dependencies install on first app boot via startup.sh)..."

cd src/dashboard
ZIP_FILE=$(mktemp).zip
zip -r "$ZIP_FILE" . -x '__pycache__/*' '*.pyc' '.venv/*' > /dev/null

echo "  Deploying to Azure..."
az webapp deploy \
    --resource-group "$RESOURCE_GROUP" \
    --name "$DASHBOARD_NAME" \
    --src-path "$ZIP_FILE" \
    --type zip
DEPLOY_EXIT=$?

rm -f "$ZIP_FILE"
cd ../..

if [ $DEPLOY_EXIT -ne 0 ]; then
    echo -e "\n=== Deployment Failed ==="
    echo "The code deployment failed."
    echo ""
    echo "To retry just the code deployment, re-run this script."
    echo "The infrastructure and auth configuration are already deployed."
    exit 1
fi

echo -e "\n=== Deployment Complete ==="
echo "Dashboard URL: $DASHBOARD_URL"
echo "Client ID:     $DASHBOARD_CLIENT_ID"
echo ""
echo "Note: The first load takes 3-5 minutes while dependencies install."
echo "      Subsequent restarts are fast (packages persist in /home storage)."
