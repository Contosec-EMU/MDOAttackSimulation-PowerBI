# CLI Deployment Guide

Step-by-step guide to deploy the MDO Attack Simulation Training data pipeline using Azure CLI and Azure Functions Core Tools. Every command includes both **Bash** and **PowerShell** variants.

---

## Prerequisites

| Tool | Minimum Version | Install |
|------|----------------|---------|
| Azure CLI | v2.50+ | [Install](https://learn.microsoft.com/cli/azure/install-azure-cli) |
| Azure Functions Core Tools | v4.x | [Install](https://learn.microsoft.com/azure/azure-functions/functions-run-local#install-the-azure-functions-core-tools) |
| Python | 3.11 | [Download](https://www.python.org/downloads/) |
| Git | Latest | [Download](https://git-scm.com/downloads) |
| Bicep CLI | Latest (bundled with Azure CLI) | Verify: `az bicep version` |

### Azure Permissions

The deploying user must have **Owner** role on the target Azure subscription (or resource group), or the combination of **Contributor** + **User Access Administrator**. This is required because the Bicep template creates RBAC role assignments (e.g., Storage Blob Data Contributor, Key Vault Secrets User) for the Function App's managed identity.

---

## Step 1: Clone and Configure

### Bash

```bash
git clone https://github.com/YOUR_ORG/MDOAttackSimulation-PowerBI.git
cd MDOAttackSimulation-PowerBI

# Copy parameter template and edit with your values
cp infra/main.bicepparam.example infra/main.bicepparam
```

### PowerShell

```powershell
git clone https://github.com/YOUR_ORG/MDOAttackSimulation-PowerBI.git
Set-Location MDOAttackSimulation-PowerBI

# Copy parameter template and edit with your values
Copy-Item infra/main.bicepparam.example infra/main.bicepparam
```

Edit `infra/main.bicepparam` and update the required parameters:

```bicep
param tenantId = '<YOUR_ENTRA_ID_TENANT_ID>'
param graphClientId = '<YOUR_APP_REGISTRATION_CLIENT_ID>'
param timerSchedule = '0 0 2 * * *'   // Daily at 2:00 AM UTC
param syncMode = 'full'                // 'full' or 'incremental'
param syncSimulations = true           // Set false to skip simulation details
```

---

## Step 2: Create Entra ID App Registration

### Bash

```bash
# Login to Azure
az login

# Create app registration
az ad app create \
  --display-name "MDO Attack Simulation Ingestion" \
  --sign-in-audience AzureADMyOrg

# Get the application (client) ID
APP_ID=$(az ad app list \
  --display-name "MDO Attack Simulation Ingestion" \
  --query "[0].appId" -o tsv)

echo "App (Client) ID: $APP_ID"

# Create service principal
az ad sp create --id "$APP_ID"

# Add Microsoft Graph API permissions (Application type):
#   AttackSimulation.Read.All = 93283d0a-6322-4fa8-966b-8c121624760d
az ad app permission add \
  --id "$APP_ID" \
  --api 00000003-0000-0000-c000-000000000000 \
  --api-permissions 93283d0a-6322-4fa8-966b-8c121624760d=Role

# Grant admin consent (requires Global Admin or Privileged Role Admin)
az ad app permission admin-consent --id "$APP_ID"

# Create client secret (valid for 2 years)
CLIENT_SECRET=$(az ad app credential reset \
  --id "$APP_ID" \
  --display-name "Function App Secret" \
  --years 2 \
  --query "password" -o tsv)

echo "Client Secret: $CLIENT_SECRET"
echo "Tenant ID: $(az account show --query tenantId -o tsv)"
```

### PowerShell

```powershell
# Login to Azure
az login

# Create app registration
az ad app create `
  --display-name "MDO Attack Simulation Ingestion" `
  --sign-in-audience AzureADMyOrg

# Get the application (client) ID
$APP_ID = az ad app list `
  --display-name "MDO Attack Simulation Ingestion" `
  --query "[0].appId" -o tsv

Write-Host "App (Client) ID: $APP_ID"

# Create service principal
az ad sp create --id $APP_ID

# Add Microsoft Graph API permissions (Application type):
#   AttackSimulation.Read.All = 93283d0a-6322-4fa8-966b-8c121624760d
az ad app permission add `
  --id $APP_ID `
  --api 00000003-0000-0000-c000-000000000000 `
  --api-permissions 93283d0a-6322-4fa8-966b-8c121624760d=Role

# Grant admin consent (requires Global Admin or Privileged Role Admin)
az ad app permission admin-consent --id $APP_ID

# Create client secret (valid for 2 years)
$CLIENT_SECRET = az ad app credential reset `
  --id $APP_ID `
  --display-name "Function App Secret" `
  --years 2 `
  --query "password" -o tsv

Write-Host "Client Secret: $CLIENT_SECRET"
Write-Host "Tenant ID: $(az account show --query tenantId -o tsv)"
```

> ⚠️ **Save the Client Secret immediately** — it is only displayed once. You will need it in [Step 4](#step-4-store-secret-in-key-vault).

---

## Step 3: Deploy Infrastructure

### Bash

```bash
# Set variables
SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="rg-mdo-attack-simulation"
LOCATION="westus2"

# Select subscription
az account set --subscription "$SUBSCRIPTION_ID"

# Create resource group
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"

# Deploy Bicep template
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam

# Capture deployment outputs for subsequent steps
DEPLOYMENT_NAME="main"

FUNC_NAME=$(az deployment group show \
  -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" \
  --query "properties.outputs.functionAppName.value" -o tsv)

KV_NAME=$(az deployment group show \
  -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" \
  --query "properties.outputs.keyVaultName.value" -o tsv)

DL_NAME=$(az deployment group show \
  -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" \
  --query "properties.outputs.dataLakeAccountName.value" -o tsv)

APPINSIGHTS_NAME=$(az deployment group show \
  -g "$RESOURCE_GROUP" -n "$DEPLOYMENT_NAME" \
  --query "properties.outputs.appInsightsName.value" -o tsv)

echo "Function App:  $FUNC_NAME"
echo "Key Vault:     $KV_NAME"
echo "Data Lake:     $DL_NAME"
echo "App Insights:  $APPINSIGHTS_NAME"
```

### PowerShell

```powershell
# Set variables
$SUBSCRIPTION_ID = "<your-subscription-id>"
$RESOURCE_GROUP  = "rg-mdo-attack-simulation"
$LOCATION        = "westus2"

# Select subscription
az account set --subscription $SUBSCRIPTION_ID

# Create resource group
az group create `
  --name $RESOURCE_GROUP `
  --location $LOCATION

# Deploy Bicep template
az deployment group create `
  --resource-group $RESOURCE_GROUP `
  --template-file infra/main.bicep `
  --parameters infra/main.bicepparam

# Capture deployment outputs for subsequent steps
$DEPLOYMENT_NAME = "main"

$FUNC_NAME = az deployment group show `
  -g $RESOURCE_GROUP -n $DEPLOYMENT_NAME `
  --query "properties.outputs.functionAppName.value" -o tsv

$KV_NAME = az deployment group show `
  -g $RESOURCE_GROUP -n $DEPLOYMENT_NAME `
  --query "properties.outputs.keyVaultName.value" -o tsv

$DL_NAME = az deployment group show `
  -g $RESOURCE_GROUP -n $DEPLOYMENT_NAME `
  --query "properties.outputs.dataLakeAccountName.value" -o tsv

$APPINSIGHTS_NAME = az deployment group show `
  -g $RESOURCE_GROUP -n $DEPLOYMENT_NAME `
  --query "properties.outputs.appInsightsName.value" -o tsv

Write-Host "Function App:  $FUNC_NAME"
Write-Host "Key Vault:     $KV_NAME"
Write-Host "Data Lake:     $DL_NAME"
Write-Host "App Insights:  $APPINSIGHTS_NAME"
```

> **Tip:** The Bicep deployment outputs all resource names. Keep the variables set in your terminal for the remaining steps.

<details>
<summary>All available deployment outputs</summary>

| Output | Description |
|--------|-------------|
| `functionAppName` | Azure Function App name |
| `keyVaultName` | Key Vault name |
| `keyVaultUri` | Key Vault URI |
| `dataLakeAccountName` | ADLS Gen2 storage account name |
| `dataLakeAccountId` | ADLS Gen2 resource ID |
| `funcStorageAccountName` | Function internal storage account |
| `functionAppPrincipalId` | Function managed identity principal ID |
| `appInsightsName` | Application Insights instance name |
| `resourceGroupName` | Resource group name |
| `adlsGen2Endpoint` | ADLS Gen2 DFS endpoint URL |
| `curatedContainerPath` | Full path to the curated container |
| `powerBiAccessEnabled` | Whether Power BI resource access rules are enabled |
| `vnetName` | Virtual network name |
| `functionSubnetId` | Function App subnet resource ID |

</details>

---

## Step 4: Store Secret in Key Vault

The Key Vault uses RBAC authorization. Before you can write secrets, you need the `Key Vault Secrets Officer` role on the vault.

### Bash

```bash
# Grant yourself Key Vault Secrets Officer on the vault
CURRENT_USER_ID=$(az ad signed-in-user show --query id -o tsv)
az role assignment create \
  --role "Key Vault Secrets Officer" \
  --assignee "$CURRENT_USER_ID" \
  --scope "$(az keyvault show --name "$KV_NAME" --query id -o tsv)"

# Wait for RBAC propagation
sleep 60

# Store the Graph API client secret from Step 2
az keyvault secret set \
  --vault-name "$KV_NAME" \
  --name "graph-client-secret" \
  --value "$CLIENT_SECRET"
```

### PowerShell

```powershell
# Grant yourself Key Vault Secrets Officer on the vault
$CURRENT_USER_ID = az ad signed-in-user show --query id -o tsv
az role assignment create `
  --role "Key Vault Secrets Officer" `
  --assignee $CURRENT_USER_ID `
  --scope $(az keyvault show --name $KV_NAME --query id -o tsv)

# Wait for RBAC propagation
Start-Sleep -Seconds 60

# Store the Graph API client secret from Step 2
az keyvault secret set `
  --vault-name $KV_NAME `
  --name "graph-client-secret" `
  --value $CLIENT_SECRET
```

> **Note:** If your terminal session from Step 2 expired, replace `$CLIENT_SECRET` with the secret value you saved earlier.

---

## Step 5: Deploy Function Code

### Bash

```bash
cd src/function_app

# Deploy using Azure Functions Core Tools
func azure functionapp publish "$FUNC_NAME" --python
```

### PowerShell

```powershell
Set-Location src\function_app

# Deploy using Azure Functions Core Tools
func azure functionapp publish $FUNC_NAME --python
```

#### Alternative: Zip Deploy (no Core Tools required)

### Bash

```bash
cd src/function_app
zip -r ../../function.zip .

az functionapp deployment source config-zip \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FUNC_NAME" \
  --src ../../function.zip

# Clean up
rm ../../function.zip
```

### PowerShell

```powershell
Set-Location src\function_app
Compress-Archive -Path * -DestinationPath ..\..\function.zip -Force

az functionapp deployment source config-zip `
  --resource-group $RESOURCE_GROUP `
  --name $FUNC_NAME `
  --src ..\..\function.zip

# Clean up
Remove-Item ..\..\function.zip
```

---

## Step 6: Verify Deployment

### Bash

```bash
# Get the function host key
FUNC_KEY=$(az functionapp keys list \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FUNC_NAME" \
  --query "functionKeys.default" -o tsv)

FUNC_URL="https://${FUNC_NAME}.azurewebsites.net"

# 1. Health check
echo "--- Health Check ---"
curl -s "${FUNC_URL}/api/health?code=${FUNC_KEY}" | python -m json.tool

# 2. Check sync status
echo "--- Sync Status ---"
curl -s "${FUNC_URL}/api/sync-status?code=${FUNC_KEY}" | python -m json.tool

# 3. Trigger a test run
echo "--- Test Run ---"
curl -s -X POST "${FUNC_URL}/api/test-run?code=${FUNC_KEY}" | python -m json.tool

# 4. Verify Parquet files were written to Data Lake
echo "--- Data Lake Files ---"
az storage fs file list \
  --account-name "$DL_NAME" \
  --file-system curated \
  --recursive \
  --auth-mode login \
  --query "[].name" -o table

# 5. Check recent logs in Application Insights
echo "--- Recent Logs ---"
az monitor app-insights query \
  --app "$APPINSIGHTS_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --analytics-query "traces | where timestamp > ago(30m) | order by timestamp desc | take 20 | project timestamp, message, severityLevel"
```

### PowerShell

```powershell
# Get the function host key
$FUNC_KEY = az functionapp keys list `
  --resource-group $RESOURCE_GROUP `
  --name $FUNC_NAME `
  --query "functionKeys.default" -o tsv

$FUNC_URL = "https://$FUNC_NAME.azurewebsites.net"

# 1. Health check
Write-Host "--- Health Check ---"
Invoke-RestMethod -Uri "$FUNC_URL/api/health?code=$FUNC_KEY" | ConvertTo-Json

# 2. Check sync status
Write-Host "--- Sync Status ---"
Invoke-RestMethod -Uri "$FUNC_URL/api/sync-status?code=$FUNC_KEY" | ConvertTo-Json

# 3. Trigger a test run
Write-Host "--- Test Run ---"
Invoke-RestMethod -Method Post -Uri "$FUNC_URL/api/test-run?code=$FUNC_KEY" | ConvertTo-Json

# 4. Verify Parquet files were written to Data Lake
Write-Host "--- Data Lake Files ---"
az storage fs file list `
  --account-name $DL_NAME `
  --file-system curated `
  --recursive `
  --auth-mode login `
  --query "[].name" -o table

# 5. Check recent logs in Application Insights
Write-Host "--- Recent Logs ---"
az monitor app-insights query `
  --app $APPINSIGHTS_NAME `
  --resource-group $RESOURCE_GROUP `
  --analytics-query "traces | where timestamp > ago(30m) | order by timestamp desc | take 20 | project timestamp, message, severityLevel"
```

### Expected Results

| Check | Expected |
|-------|----------|
| Health | `{"status": "healthy", ...}` |
| Sync status | Shows current sync mode and last run |
| Test run | `{"status": "accepted", "correlationId": "..."}` |
| Data Lake files | Parquet files under `curated/{apiName}/{YYYY-MM-DD}/` |
| Logs | Trace messages showing ingestion progress |

---

## Post-Deployment Configuration

### Change the Timer Schedule

### Bash

```bash
# Example: run every 6 hours
az functionapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FUNC_NAME" \
  --settings "TIMER_SCHEDULE=0 0 */6 * * *"
```

### PowerShell

```powershell
# Example: run every 6 hours
az functionapp config appsettings set `
  --resource-group $RESOURCE_GROUP `
  --name $FUNC_NAME `
  --settings "TIMER_SCHEDULE=0 0 */6 * * *"
```

### Switch to Incremental Sync

### Bash

```bash
az functionapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FUNC_NAME" \
  --settings "SYNC_MODE=incremental"
```

### PowerShell

```powershell
az functionapp config appsettings set `
  --resource-group $RESOURCE_GROUP `
  --name $FUNC_NAME `
  --settings "SYNC_MODE=incremental"
```

### Reset Sync State (Force Full Refresh)

### Bash

```bash
curl -s -X POST "${FUNC_URL}/api/reset-sync-state?code=${FUNC_KEY}" | python -m json.tool
```

### PowerShell

```powershell
Invoke-RestMethod -Method Post -Uri "$FUNC_URL/api/reset-sync-state?code=$FUNC_KEY" | ConvertTo-Json
```

### View All App Settings

### Bash

```bash
az functionapp config appsettings list \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FUNC_NAME" \
  --query "[?starts_with(name,'SYNC_') || starts_with(name,'TIMER_') || starts_with(name,'TENANT_') || starts_with(name,'GRAPH_')].{Name:name, Value:value}" \
  -o table
```

### PowerShell

```powershell
az functionapp config appsettings list `
  --resource-group $RESOURCE_GROUP `
  --name $FUNC_NAME `
  --query "[?starts_with(name,'SYNC_') || starts_with(name,'TIMER_') || starts_with(name,'TENANT_') || starts_with(name,'GRAPH_')].{Name:name, Value:value}" `
  -o table
```

---

## Troubleshooting

### View Live Logs

### Bash

```bash
az webapp log tail \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FUNC_NAME"
```

### PowerShell

```powershell
az webapp log tail `
  --resource-group $RESOURCE_GROUP `
  --name $FUNC_NAME
```

### Check Function App Status

### Bash

```bash
az functionapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FUNC_NAME" \
  --query "{State:state, DefaultHostName:defaultHostName, Kind:kind}" \
  -o table
```

### PowerShell

```powershell
az functionapp show `
  --resource-group $RESOURCE_GROUP `
  --name $FUNC_NAME `
  --query "{State:state, DefaultHostName:defaultHostName, Kind:kind}" `
  -o table
```

### Restart Function App

### Bash

```bash
az functionapp restart \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FUNC_NAME"
```

### PowerShell

```powershell
az functionapp restart `
  --resource-group $RESOURCE_GROUP `
  --name $FUNC_NAME
```

### Verify RBAC Assignments

### Bash

```bash
# Get the Function App managed identity principal ID
PRINCIPAL_ID=$(az functionapp identity show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FUNC_NAME" \
  --query "principalId" -o tsv)

# List role assignments for the managed identity
az role assignment list \
  --assignee "$PRINCIPAL_ID" \
  --query "[].{Role:roleDefinitionName, Scope:scope}" \
  -o table
```

### PowerShell

```powershell
# Get the Function App managed identity principal ID
$PRINCIPAL_ID = az functionapp identity show `
  --resource-group $RESOURCE_GROUP `
  --name $FUNC_NAME `
  --query "principalId" -o tsv

# List role assignments for the managed identity
az role assignment list `
  --assignee $PRINCIPAL_ID `
  --query "[].{Role:roleDefinitionName, Scope:scope}" `
  -o table
```

Expected RBAC roles (assigned automatically by Bicep):

| Role | Scope |
|------|-------|
| Storage Blob Data Contributor | Function storage account |
| Storage Queue Data Contributor | Function storage account |
| Storage Table Data Contributor | Function storage account |
| Storage Blob Data Contributor | Data Lake storage account |
| Key Vault Secrets User | Key Vault |

---

## Tear Down

### Bash

```bash
# Delete the entire resource group and all resources
az group delete \
  --name "$RESOURCE_GROUP" \
  --yes --no-wait

# Optionally remove the Entra ID app registration
az ad app delete --id "$APP_ID"
```

### PowerShell

```powershell
# Delete the entire resource group and all resources
az group delete `
  --name $RESOURCE_GROUP `
  --yes --no-wait

# Optionally remove the Entra ID app registration
az ad app delete --id $APP_ID
```

---

## Quick Reference

| API Endpoint | Function Route | Method |
|-------------|---------------|--------|
| Health check | `/api/health` | GET |
| Manual test run | `/api/test-run` | POST |
| Sync status | `/api/sync-status` | GET |
| Reset sync state | `/api/reset-sync-state` | POST |

| Bicep Parameter | Default | Description |
|----------------|---------|-------------|
| `prefix` | `mdoast` | Resource naming prefix |
| `location` | Resource group location | Azure region |
| `tenantId` | *(required)* | Entra ID tenant ID |
| `graphClientId` | *(required)* | App registration client ID |
| `timerSchedule` | `0 0 2 * * *` | CRON schedule (daily 2 AM UTC) |
| `syncMode` | `full` | `full` or `incremental` |
| `syncSimulations` | `true` | Sync simulation details |
| `enablePowerBiAccess` | `true` | Allow Power BI to access ADLS Gen2 |
