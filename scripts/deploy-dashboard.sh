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

# Get existing infrastructure outputs
echo -e "\n1. Reading existing infrastructure..."
APP_SERVICE_PLAN_ID=$(az appservice plan list \
    --resource-group "$RESOURCE_GROUP" \
    --query "[0].id" -o tsv)

DATA_LAKE_NAME=$(az deployment group show \
    --resource-group "$RESOURCE_GROUP" \
    --name main \
    --query "properties.outputs.dataLakeAccountName.value" -o tsv)

STORAGE_URL=$(az deployment group show \
    --resource-group "$RESOURCE_GROUP" \
    --name main \
    --query "properties.outputs.adlsGen2Endpoint.value" -o tsv)

APP_INSIGHTS_CS=$(az monitor app-insights component show \
    --resource-group "$RESOURCE_GROUP" \
    --query "[0].connectionString" -o tsv)

TENANT_ID=$(az account show --query tenantId -o tsv)

SUBNET_ID=$(az deployment group show \
    --resource-group "$RESOURCE_GROUP" \
    --name main \
    --query "properties.outputs.functionSubnetId.value" -o tsv)

echo "  Data Lake: $DATA_LAKE_NAME"
echo "  Storage URL: $STORAGE_URL"

# Create app registration if not provided
if [ -z "$DASHBOARD_CLIENT_ID" ]; then
    echo -e "\n2. Creating Entra ID app registration..."
    APP_DISPLAY_NAME="MDOAttackSimulation-Dashboard"
    DASHBOARD_CLIENT_ID=$(az ad app create \
        --display-name "$APP_DISPLAY_NAME" \
        --sign-in-audience AzureADMyOrg \
        --query "appId" -o tsv)
    az ad sp create --id "$DASHBOARD_CLIENT_ID" > /dev/null
    echo "  App Registration: $APP_DISPLAY_NAME ($DASHBOARD_CLIENT_ID)"
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

# Deploy code
echo -e "\n5. Publishing Streamlit app..."
cd src/dashboard
ZIP_FILE=$(mktemp).zip
zip -r "$ZIP_FILE" . -x '__pycache__/*' '*.pyc' '.venv/*'
az webapp deployment source config-zip \
    --resource-group "$RESOURCE_GROUP" \
    --name "$DASHBOARD_NAME" \
    --src "$ZIP_FILE"
rm -f "$ZIP_FILE"
cd ../..

echo -e "\n=== Deployment Complete ==="
echo "Dashboard URL: $DASHBOARD_URL"
echo "Client ID:     $DASHBOARD_CLIENT_ID"
echo ""
echo "Note: It may take 1-2 minutes for the app to start after deployment."
