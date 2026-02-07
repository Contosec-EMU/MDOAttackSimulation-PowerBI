#!/bin/bash
# Deploy the Streamlit Executive Dashboard to Azure
#
# Usage:
#   ./deploy-dashboard.sh -g <resource-group> -c <dashboard-client-id>

set -euo pipefail

usage() {
    echo "Usage: $0 -g <resource-group> -c <dashboard-client-id>"
    exit 1
}

while getopts "g:c:" opt; do
    case $opt in
        g) RESOURCE_GROUP="$OPTARG" ;;
        c) DASHBOARD_CLIENT_ID="$OPTARG" ;;
        *) usage ;;
    esac
done

[ -z "${RESOURCE_GROUP:-}" ] || [ -z "${DASHBOARD_CLIENT_ID:-}" ] && usage

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

# Deploy Bicep
echo -e "\n2. Deploying dashboard infrastructure..."
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

# Deploy code
echo -e "\n3. Publishing Streamlit app..."
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
echo ""
echo "Note: It may take 1-2 minutes for the app to start after deployment."
