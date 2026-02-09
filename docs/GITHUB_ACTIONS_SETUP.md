# GitHub Actions Deployment Setup Guide

This guide walks you through setting up automated deployments using GitHub Actions with Azure OIDC authentication (no secrets to rotate!).

## Overview

The GitHub Actions workflow (`deploy.yml`) automatically:
- Detects changes to infrastructure (`infra/`) or function code (`src/`)
- Deploys Bicep infrastructure when `infra/` files change
- Deploys Python function code when `src/` files change
- Uses Azure OIDC (OpenID Connect) for secure, secret-free authentication
- Supports manual triggers with force-deploy options

## Prerequisites

1. **Azure Subscription** with permissions to:
   - Create Entra ID app registrations (Application Administrator)
   - Assign RBAC roles (Owner or User Access Administrator)

2. **GitHub Repository** (public or private)
   - This repository pushed to GitHub
   - Admin access to configure secrets

3. **Local Tools**:
   - Azure CLI (v2.50+): [Install](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
   - Git: [Install](https://git-scm.com/downloads)

## Step 1: Initialize Git Repository (If Not Already Done)

```bash
# Navigate to project directory
cd C:\repos\MDOAttackSimulation_PowerBI

# Initialize git repo
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: Azure Functions MDO Attack Simulation"

# Add GitHub remote (replace with your repo URL)
git remote add origin https://github.com/<YOUR_ORG>/<YOUR_REPO>.git

# Push to GitHub (creates main branch)
git branch -M main
git push -u origin main
```

## Step 2: Configure Azure OIDC with GitHub

Run the setup script to create the Azure app registration and federated credentials:

### Option A: PowerShell (Windows/Linux/macOS)

```powershell
# Authenticate to Azure
az login

# Run setup script
.\scripts\setup-github-oidc.ps1 `
    -GitHubOrg "your-github-org" `
    -GitHubRepo "MDOAttackSimulation_PowerBI"
```

### Option B: Bash (Linux/macOS/WSL)

```bash
# Authenticate to Azure
az login

# Make script executable
chmod +x scripts/setup-github-oidc.sh

# Run setup script
./scripts/setup-github-oidc.sh your-github-org MDOAttackSimulation_PowerBI
```

The script will output three values you need for GitHub secrets:
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

## Step 3: Add Secrets to GitHub Repository

1. Navigate to your GitHub repository
2. Go to **Settings** > **Secrets and variables** > **Actions**
3. Click **New repository secret** and add each of the following:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `AZURE_CLIENT_ID` | From setup script output | App registration client ID |
| `AZURE_TENANT_ID` | From setup script output | Your Entra ID tenant ID |
| `AZURE_SUBSCRIPTION_ID` | From setup script output | Your Azure subscription ID |

**Important**: These are NOT sensitive values when using OIDC. GitHub securely exchanges tokens with Azure during workflow runs.

## Step 4: Verify Bicep Parameters

Update `infra/main.bicepparam` with your environment-specific values:

```bicep
// Required: Update these values
param tenantId = 'your-tenant-id'           // Same as AZURE_TENANT_ID
param graphClientId = 'your-graph-app-id'   // Your Graph API app registration ID

// Optional: Customize if needed
param prefix = 'mdoast'                     // Resource name prefix
param location = 'westus2'                  // Azure region
param timerSchedule = '0 0 2 * * *'        // Daily at 2 AM UTC
```

Commit any changes:

```bash
git add infra/main.bicepparam
git commit -m "Update Bicep parameters for environment"
git push
```

## Step 5: Trigger First Deployment

### Automatic Trigger (on push to main)

```bash
# Any push to main triggers the workflow
git add .
git commit -m "Trigger GitHub Actions deployment"
git push
```

### Manual Trigger (via GitHub UI)

1. Go to **Actions** tab in your GitHub repository
2. Select **Deploy MDO Attack Simulation** workflow
3. Click **Run workflow**
4. Choose options:
   - ✅ Force deploy infrastructure (deploys even without changes)
   - ✅ Force deploy function code (deploys even without changes)
5. Click **Run workflow**

### Manual Trigger (via GitHub CLI)

```bash
# Install GitHub CLI: https://cli.github.com/
gh auth login

# Trigger workflow
gh workflow run deploy.yml

# Trigger with force options
gh workflow run deploy.yml \
  -f deploy_infra=true \
  -f deploy_code=true
```

## Step 6: Monitor Deployment

### Via GitHub UI

1. Go to **Actions** tab
2. Click on the running workflow
3. View real-time logs for each job:
   - **Detect Changes**: Shows which components changed
   - **Deploy Infrastructure**: Bicep deployment logs
   - **Deploy Function Code**: Function publishing logs
   - **Deployment Summary**: Overall status

### Via GitHub CLI

```bash
# List recent workflow runs
gh run list --workflow=deploy.yml

# View specific run logs
gh run view <run-id>

# Watch live run
gh run watch
```

## Step 7: Store Graph API Client Secret

After infrastructure deployment completes:

```bash
# Get Key Vault name from deployment output (format: kv-<prefix>-<region>)
KV_NAME="kv-mdoast-west"  # Update with actual name
RESOURCE_GROUP="rg-mdo-attack-simulation"
```

> 📝 **RBAC required:** You need `Key Vault Secrets Officer` on the vault before you can write secrets. If you get an "Access denied" or "Forbidden" error, grant yourself the role first:
>
> ```bash
> CURRENT_USER_ID=$(az ad signed-in-user show --query id -o tsv)
> KV_SCOPE=$(az keyvault show --name "$KV_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
> az role assignment create --role "Key Vault Secrets Officer" --assignee "$CURRENT_USER_ID" --scope "$KV_SCOPE"
> sleep 60
> ```

```bash
# Store Graph API client secret
az keyvault secret set \
  --vault-name $KV_NAME \
  --name "graph-client-secret" \
  --value "<your-graph-api-client-secret>"
```

> ⚠️ **Firewall note:** The Key Vault is deployed with network rules that deny public access by default. If running from outside the VNet, temporarily add your IP: `az keyvault network-rule add --name "$KV_NAME" --ip-address "$(curl -s https://api.ipify.org)/32"`

**Important**: This is the ONLY secret you need to manually store. The Function App retrieves it at runtime using its managed identity.

## Step 8: Verify Deployment

### Check Function App Health

```bash
# Get function app name (format: <prefix>-func-<region>)
FUNC_NAME="mdoast-func-west"  # Update with actual name

# Get function app hostname
az functionapp show \
  --name $FUNC_NAME \
  --resource-group rg-mdo-attack-simulation \
  --query defaultHostName -o tsv

# Get function key (all HTTP endpoints require AuthLevel.FUNCTION)
FUNCTION_KEY=$(az functionapp keys list \
  --name $FUNC_NAME \
  --resource-group rg-mdo-attack-simulation \
  --query functionKeys.default -o tsv)

# Test health endpoint
curl "https://<function-app-url>/api/health?code=${FUNCTION_KEY}"
```

Expected response: `{"status": "healthy"}`

### Trigger Manual Test Run

```bash
# Trigger test run
curl -X POST "https://<function-app-url>/api/test-run?code=${FUNCTION_KEY}"
```

### Verify Data in Storage

To browse ingested data in ADLS Gen2, your user account needs `Storage Blob Data Reader`:

```bash
CURRENT_USER_ID=$(az ad signed-in-user show --query id -o tsv)
DL_NAME="<your-datalake-account-name>"  # Update with actual name
STORAGE_SCOPE=$(az storage account show --name "$DL_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
az role assignment create --role "Storage Blob Data Reader" --assignee "$CURRENT_USER_ID" --scope "$STORAGE_SCOPE"
```

> ⚠️ **Firewall note:** The storage account is deployed with network rules that deny public access by default. If running from outside the VNet, temporarily add your IP: `az storage account network-rule add --account-name "$DL_NAME" --ip-address "$(curl -s https://api.ipify.org)"`

### View Logs in Azure

```bash
# Stream live logs
az webapp log tail \
  --name $FUNC_NAME \
  --resource-group rg-mdo-attack-simulation

# Query Application Insights
az monitor app-insights query \
  --app <app-insights-name> \
  --analytics-query "traces | where timestamp > ago(1h) | order by timestamp desc"
```

## Workflow Behavior

### Smart Change Detection

The workflow automatically detects which components changed:

| Files Changed | Infrastructure Deploy | Code Deploy |
|--------------|----------------------|-------------|
| `infra/**` | ✅ Yes | ⏭️ No |
| `src/**` | ⏭️ No | ✅ Yes |
| `infra/**` + `src/**` | ✅ Yes | ✅ Yes (sequential) |
| `README.md`, `docs/**` | ⏭️ No | ⏭️ No |

### Deployment Order

When both infrastructure and code change:
1. **Deploy Infrastructure** (creates/updates Azure resources)
2. **Deploy Function Code** (publishes Python code to Function App)
3. **Deployment Summary** (shows overall status)

### Environment Protection

The workflow uses the `production` environment:
- Can add approval gates (Settings > Environments > production > Required reviewers)
- Can restrict deployments to specific branches
- Can configure environment secrets (override repository secrets)

> **Note:** The workflow reads the resource group from the `AZURE_RESOURCE_GROUP` repository variable. Set this in your GitHub repo under **Settings → Secrets and variables → Actions → Variables**.

## Troubleshooting

### Error: "az: command not found"

**Solution**: Install Azure CLI
```bash
# macOS
brew install azure-cli

# Windows (PowerShell as admin)
winget install Microsoft.AzureCLI

# Linux (Ubuntu/Debian)
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

### Error: "No subscription found"

**Solution**: Authenticate to Azure
```bash
az login
az account set --subscription <subscription-id>
```

### Error: "Insufficient privileges to complete the operation"

**Solutions**:
1. **For app registration creation**: Request "Application Administrator" role in Entra ID
2. **For RBAC assignments**: Request "Owner" or "User Access Administrator" on subscription/resource group

### Error: "Federated credential subject already exists"

**Solution**: The OIDC setup is already complete. You can proceed to Step 3 (add GitHub secrets).

### Workflow fails with "OIDC token validation failed"

**Check**:
1. GitHub secrets match values from setup script
2. Federated credential subject matches your repository: `repo:ORG/REPO:ref:refs/heads/main`
3. App registration has service principal created

**Fix**: Re-run setup script to ensure configuration is correct

### Infrastructure deploys but function code fails

**Check**:
1. Function App name in workflow matches actual name (extracted from Bicep output)
2. Azure Functions Core Tools installed in GitHub runner (handled automatically)
3. Python version matches `PYTHON_VERSION` in workflow (3.11)

**Fix**: Manually trigger workflow with "Force deploy function code" option

### Health check returns 401/403

**Check**:
1. Function App has system-assigned managed identity enabled
2. Managed identity has "Storage Blob Data Contributor" on ADLS Gen2
3. Managed identity has "Key Vault Secrets User" on Key Vault
4. Graph API client secret stored in Key Vault

**Fix**: Check RBAC assignments in Azure Portal

## Advanced Configuration

### Add Deployment Approvals

1. Go to **Settings** > **Environments** > **production**
2. Check **Required reviewers**
3. Add team members who can approve deployments
4. Save

Now deployments to production will wait for manual approval.

### Customize Deployment Schedule

Add a schedule trigger to `.github/workflows/deploy.yml`:

```yaml
on:
  push:
    branches:
      - main
  schedule:
    - cron: '0 3 * * 1'  # Every Monday at 3 AM UTC
  workflow_dispatch:
```

### Deploy to Multiple Environments

1. Create separate `main.bicepparam` files:
   - `infra/main.bicepparam` (production)
   - `infra/main.dev.bicepparam` (development)

2. Duplicate workflow for dev environment:
   - `.github/workflows/deploy-dev.yml`
   - Trigger on push to `develop` branch
   - Use different resource group and bicepparam file

### Add Deployment Notifications

Add Slack/Teams notification step to workflow:

```yaml
- name: Notify Teams
  if: always()
  uses: aliencube/microsoft-teams-actions@v0.8.0
  with:
    webhook_uri: ${{ secrets.TEAMS_WEBHOOK }}
    title: Deployment ${{ job.status }}
    summary: Function app deployed to production
```

## Security Best Practices

### What This Setup Does

- **No long-lived secrets**: OIDC tokens are short-lived (1 hour) and auto-rotated
- **Principle of least privilege**: Service principal only has Contributor on resource group
- **Audit trail**: All deployments logged in Azure Activity Log and GitHub Actions
- **Scoped credentials**: Federated credentials only work from specific GitHub repo/branch

### ⚠️ Additional Recommendations

1. **Enable branch protection** on `main`:
   - Settings > Branches > Add rule
   - Require pull request reviews before merging
   - Require status checks to pass before merging

2. **Rotate Graph API client secret** annually:
   - Create new secret in app registration
   - Update Key Vault secret
   - Delete old secret after validation

3. **Monitor workflow runs**:
   - Set up alerts for failed deployments
   - Review Action logs monthly for suspicious activity

4. **Use environment secrets** for sensitive overrides:
   - Settings > Environments > production > Add secret
   - Environment secrets override repository secrets

## Cost Optimization

The GitHub Actions workflow is designed to minimize Azure costs:

- **Smart change detection**: Only deploys what changed
- **Basic B1 App Service Plan**: ~$13/month (always-on, no cold starts)
- **ADLS Gen2 storage**: ~$0.02/GB/month + minimal transaction costs
- **Application Insights**: 5GB free tier (90-day retention configured)

**Estimated monthly cost**: $15-20 USD for low-to-medium usage

## Support and Resources

- **GitHub Actions Docs**: https://docs.github.com/en/actions
- **Azure OIDC Guide**: https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure
- **Bicep Docs**: https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/
- **Azure Functions Deployment**: https://learn.microsoft.com/en-us/azure/azure-functions/functions-how-to-github-actions

## Next Steps: Set Up Reporting

Your data pipeline is running and writing Parquet files to ADLS Gen2. Choose how you want to visualize the data:

| Option | Best for | Guide |
|--------|----------|-------|
| **Power BI Desktop** | Rich interactive dashboards, scheduled refresh, sharing via Power BI Service | [Power BI Setup Guide](POWERBI_SETUP.md) |

Power BI reads the same data from ADLS Gen2.

---

**Questions or issues?** Check the troubleshooting section above or review workflow logs in GitHub Actions.
