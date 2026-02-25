# GitHub Actions Quick Start

Fast-track guide to get GitHub Actions deployment running in 10 minutes.

> **Note:** Examples use `rg-mdo-attack-simulation` — replace with your resource group name.

## Quick Setup (4 Steps)

### 1. Authenticate to Azure

```bash
az login
```

### 2. Run OIDC Setup Script

**Windows (PowerShell)**:
```powershell
.\scripts\setup-github-oidc.ps1 -GitHubOrg "YOUR_ORG" -GitHubRepo "YOUR_REPO"
```

**Linux/macOS (Bash)**:
```bash
chmod +x scripts/setup-github-oidc.sh
./scripts/setup-github-oidc.sh YOUR_ORG YOUR_REPO
```

The script outputs three values. **Copy them**.

### 3. Add GitHub Secrets

Go to: `https://github.com/YOUR_ORG/YOUR_REPO/settings/secrets/actions`

Add these three secrets (paste values from script output):
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

### 4. Push to Main

```bash
git add .
git commit -m "Setup GitHub Actions deployment"
git push origin main
```

**Done!** Check deployment progress at:
`https://github.com/YOUR_ORG/YOUR_REPO/actions`

---

## Network Isolation (Private Endpoints)

If your tenant has Azure Policy that disables public network access on storage and Key Vault, use private endpoint mode:

**PowerShell:**
```powershell
.\deploy.ps1 -NetworkIsolation "private" -GraphClientSecret "your-secret"
```

**Bash:**
```bash
./deploy.sh --network-isolation private
```

This creates private endpoints for all storage accounts and Key Vault (~$36/month additional cost). The Function App retains public access for deployment and HTTP triggers.

### What private mode does:
- Creates 6 private endpoints (function storage blob/queue/table, ADLS blob/dfs, Key Vault)
- Creates 5 Private DNS Zones linked to the VNet
- Disables public network access on storage accounts and Key Vault
- All data plane traffic stays on the Azure backbone

---

## Post-Deployment Checklist

After GitHub Actions completes successfully:

### Store Graph API Secret in Key Vault

```bash
# Get Key Vault name from Azure Portal or Bicep output
az keyvault secret set \
  --vault-name "kv-mdoast-west" \
  --name "graph-client-secret" \
  --value "YOUR_GRAPH_API_CLIENT_SECRET"
```

### Verify Function Health

```bash
# Test health endpoint
curl https://mdoast-func-west.azurewebsites.net/api/health
```

Expected: `{"status": "healthy"}`

### Trigger Test Run

```bash
# Get function key
FUNCTION_KEY=$(az functionapp keys list \
  --name mdoast-func-west \
  --resource-group rg-mdo-attack-simulation \
  --query functionKeys.default -o tsv)

# Trigger ingestion
curl -X POST "https://mdoast-func-west.azurewebsites.net/api/test-run?code=${FUNCTION_KEY}"
```

### Check Data in Storage

```bash
# List parquet files
az storage blob list \
  --account-name <storage-account-name> \
  --container-name curated \
  --auth-mode login
```

---

## Common Commands

### Manual Workflow Trigger

```bash
gh workflow run deploy.yml
```

### View Recent Deployments

```bash
gh run list --workflow=deploy.yml --limit 5
```

### Stream Function Logs

```bash
az webapp log tail \
  --name mdoast-func-west \
  --resource-group rg-mdo-attack-simulation
```

### Redeploy Infrastructure Only

```bash
gh workflow run deploy.yml -f deploy_infra=true
```

### Redeploy Function Code Only

```bash
gh workflow run deploy.yml -f deploy_code=true
```

---

## 🐛 Troubleshooting

### Setup script fails with "Not logged into Azure"

```bash
az login
az account set --subscription YOUR_SUBSCRIPTION_ID
```

### GitHub Actions workflow fails with "OIDC validation failed"

1. Verify GitHub secrets match output from setup script
2. Check federated credential exists:
   ```bash
   az ad app federated-credential list --id YOUR_APP_ID
   ```

### Function deployment succeeds but health check fails

Wait 60 seconds for function app warmup, then retry:
```bash
curl https://YOUR_FUNCTION_APP.azurewebsites.net/api/health
```

### "Insufficient privileges" error during OIDC setup

You need:
- **Entra ID**: Application Administrator role
- **Subscription**: Owner or User Access Administrator role

Request these from your Azure admin.

---

## 📚 Full Documentation

- **Complete setup guide**: [GITHUB_ACTIONS_SETUP.md](../GITHUB_ACTIONS_SETUP.md)
- **Project architecture**: [README.md](../README.md)
- **Development guide**: [CONTRIBUTING.md](../CONTRIBUTING.md)
- **AI assistant context**: [CLAUDE.md](../CLAUDE.md)

---

## 🔐 Security Notes

✅ **No long-lived secrets**: OIDC tokens expire after 1 hour
✅ **Scoped access**: Service principal limited to single resource group
✅ **Audit trail**: All deployments logged in Azure Activity Log
✅ **Branch protection**: Consider enabling on `main` branch

---

## Tips

- **First deployment takes 5-10 minutes** (infrastructure creation)
- **Subsequent code deployments take 2-3 minutes**
- **Infrastructure only deploys when `infra/` files change**
- **Function code only deploys when `src/` files change**
- **Add deployment approvals** in GitHub Settings > Environments > production

---

**Need help?** See [GITHUB_ACTIONS_SETUP.md](../GITHUB_ACTIONS_SETUP.md) for detailed troubleshooting.
