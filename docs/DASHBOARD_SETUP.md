# Dashboard Setup Guide — Streamlit Executive Dashboard

Browser-based alternative to Power BI for viewing MDO Attack Simulation Training data.

---

## Prerequisites

| Requirement | Details |
|---|---|
| **Existing infrastructure** | The main `infra/main.bicep` must be deployed first |
| **Azure CLI** | v2.50+ ([Install](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)) |
| **Permissions** | Ability to create Entra ID app registrations (Application Administrator or Global Admin) |

> **Note:** Examples use `rg-mdo-attack-simulation` — replace with your actual resource group name.

## Deploy (One Command)

The deploy script handles everything: creates the app registration, deploys infrastructure, configures authentication, and publishes the code.

### PowerShell

```powershell
.\scripts\deploy-dashboard.ps1 -ResourceGroup "rg-mdo-attack-simulation"
```

### Bash

```bash
./scripts/deploy-dashboard.sh -g "rg-mdo-attack-simulation"
```

The script will:
1. Read existing infrastructure outputs (storage account, App Service Plan, etc.)
2. Create an Entra ID app registration (single-tenant, scoped to your org)
3. Deploy `infra/dashboard.bicep` with EasyAuth configured
4. Update the app registration redirect URI with the actual dashboard URL
5. Publish the Streamlit app code

> **Already have an app registration?** Pass it with `-DashboardClientId`:
> ```powershell
> .\scripts\deploy-dashboard.ps1 -ResourceGroup "rg-mdo-attack-simulation" -DashboardClientId "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
> ```

## Verify

Open the dashboard URL shown in the script output. You should be prompted to sign in with your Entra ID credentials, then see the dashboard home page.

## Alternative: Configure Auth via Azure Portal

If you prefer a manual approach or the CLI-based app registration fails due to permissions:

1. Deploy without auth by creating the app registration manually in the Azure Portal:
   - **Entra ID** → **App registrations** → **New registration**
   - **Name**: `MDOAttackSimulation-Dashboard`
   - **Supported account types**: Single tenant
   - **Redirect URI**: `https://<dashboard-app-name>.azurewebsites.net/.auth/login/aad/callback`
2. Copy the **Application (client) ID** and re-run the deploy script with `-DashboardClientId`

Or, after deploying the web app without auth:
1. Navigate to **App Service** → your dashboard app → **Authentication**
2. Click **Add identity provider** → **Microsoft**
3. Follow the wizard — it auto-creates the app registration and configures everything

## Troubleshooting

| Issue | Fix |
|---|---|
| "Application not found" on login | Verify the app registration exists and the redirect URI matches the dashboard URL |
| Empty tables / no data | Ensure the Azure Function has run at least once |
| 403 on storage access | Check that the dashboard's managed identity has Storage Blob Data Reader |
| App takes a long time to start | First cold start can take 30-60 seconds on B1; subsequent loads are faster |
| CSS not loading | Ensure `startup.sh` has execute permissions and the working directory is `src/dashboard` |
