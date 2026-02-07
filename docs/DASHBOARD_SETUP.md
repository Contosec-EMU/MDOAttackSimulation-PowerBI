# Dashboard Setup Guide — Streamlit Executive Dashboard

Browser-based alternative to Power BI for viewing MDO Attack Simulation Training data.

---

## Prerequisites

| Requirement | Details |
|---|---|
| **Existing infrastructure** | The main `infra/main.bicep` must be deployed first |
| **Azure CLI** | v2.50+ ([Install](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)) |
| **Entra ID App Registration** | A separate app registration for the dashboard (for EasyAuth) |

## Step 1: Create an App Registration for the Dashboard

```powershell
$dashboardApp = az ad app create `
    --display-name "MDOAttackSimulation-Dashboard" `
    --web-redirect-uris "https://<dashboard-app-name>.azurewebsites.net/.auth/login/aad/callback" `
    --query "{appId:appId, id:id}" -o json | ConvertFrom-Json

az ad sp create --id $dashboardApp.appId

Write-Host "Dashboard Client ID: $($dashboardApp.appId)"
```

> **Note:** You will update the redirect URI after deployment when you know the actual app name. See Step 3.

## Step 2: Deploy the Dashboard

### Option A: Deploy Script (Recommended)

```powershell
# PowerShell
.\scripts\deploy-dashboard.ps1 `
    -ResourceGroup "rg-mdo-attack-simulation" `
    -DashboardClientId $dashboardApp.appId
```

```bash
# Bash
./scripts/deploy-dashboard.sh \
    -g "rg-mdo-attack-simulation" \
    -c "<dashboard-client-id>"
```

### Option B: Manual Deployment

```powershell
# 1. Deploy infrastructure
az deployment group create `
    --resource-group "rg-mdo-attack-simulation" `
    --template-file infra/dashboard.bicep `
    --parameters `
        appServicePlanId="<existing-asp-id>" `
        dataLakeAccountName="<adls-account-name>" `
        storageAccountUrl="https://<account>.dfs.core.windows.net" `
        tenantId="<tenant-id>" `
        dashboardClientId="<dashboard-client-id>" `
        appInsightsConnectionString="<connection-string>" `
        subnetId="<subnet-id>"

# 2. Deploy code
cd src/dashboard
Compress-Archive -Path * -DestinationPath dashboard.zip
az webapp deployment source config-zip `
    --resource-group "rg-mdo-attack-simulation" `
    --name "<dashboard-app-name>" `
    --src dashboard.zip
```

## Step 3: Update the Redirect URI

After deployment, update the app registration with the actual URL:

```powershell
$DASHBOARD_URL = az webapp show `
    --resource-group "rg-mdo-attack-simulation" `
    --name "<dashboard-app-name>" `
    --query "defaultHostName" -o tsv

az ad app update --id $dashboardApp.appId `
    --web-redirect-uris "https://$DASHBOARD_URL/.auth/login/aad/callback"
```

## Step 4: Verify

Open `https://<dashboard-app-name>.azurewebsites.net` in your browser. You should be prompted to sign in with your Entra ID credentials, then see the dashboard home page.

## Troubleshooting

| Issue | Fix |
|---|---|
| "Application not found" on login | Verify the app registration exists and the redirect URI matches |
| Empty tables / no data | Ensure the Azure Function has run at least once |
| 403 on storage access | Check that the dashboard's managed identity has Storage Blob Data Reader |
| App takes a long time to start | First cold start can take 30-60 seconds on B1; subsequent loads are faster |
| CSS not loading | Ensure `startup.sh` has execute permissions and the working directory is `src/dashboard` |
