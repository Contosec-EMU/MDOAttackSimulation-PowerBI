# GitHub Actions Quick Start

This is a short setup guide for the workflows that are currently in this repository.

> Note: Resource names in this document such as `rg-mdo-attack-simulation` and `mdoast-func-west` are examples. Replace them with your actual deployed names.

## Quick setup

### 1. Authenticate to Azure

```bash
az login
```

### 2. Run the OIDC setup script

**Windows - PowerShell**

```powershell
.\scripts\setup-github-oidc.ps1 -GitHubOrg "YOUR_ORG" -GitHubRepo "YOUR_REPO"
```

**Linux or macOS - Bash**

```bash
chmod +x scripts/setup-github-oidc.sh
./scripts/setup-github-oidc.sh YOUR_ORG YOUR_REPO
```

Copy the three values printed by the script.

### 3. Add GitHub Actions secrets

Go to:

`https://github.com/YOUR_ORG/YOUR_REPO/settings/secrets/actions`

Add these repository secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

Optional: add the repository variable `AZURE_RESOURCE_GROUP` if you do not want the workflow default of `rg-mdo-attack-simulation`.

### 4. Prepare the Bicep parameter file

Before you run the deployment workflow, review `infra/main.bicepparam`.

Known issue:

- `deploy.yml` passes `infra/main.bicepparam`
- `infra/main.bicep` requires `graphClientSecret`
- `infra/main.bicepparam` does not currently define `graphClientSecret`

That means the infrastructure deployment step will fail unless you supply `graphClientSecret` before the run.

You can either:

1. Add `graphClientSecret` to `infra/main.bicepparam` in the branch you plan to deploy.
2. Run the equivalent Azure CLI deployment yourself and pass `graphClientSecret` as an override.

Example manual deployment command:

```bash
az deployment group create \
  --resource-group rg-mdo-attack-simulation \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --parameters graphClientSecret="<your-graph-api-client-secret>"
```

Do not commit real secret values to a shared or public repository.

### 5. Run the deployment workflow manually

The deployment workflow is manual only. It does not run on push.

From the GitHub UI:

1. Open the **Actions** tab.
2. Select **Deploy MDO Attack Simulation**.
3. Click **Run workflow**.

From GitHub CLI:

```bash
gh auth login
gh workflow run deploy.yml
```

## Post-deployment checks

### Verify function health

The health endpoint requires a function key.

```bash
# Example values. Replace them with your actual names.
RESOURCE_GROUP="rg-mdo-attack-simulation"
FUNCTION_APP_NAME="mdoast-func-west"

FUNCTION_HOST=$(az functionapp show \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query defaultHostName -o tsv)

FUNCTION_KEY=$(az functionapp keys list \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query functionKeys.default -o tsv)

curl "https://${FUNCTION_HOST}/api/health?code=${FUNCTION_KEY}"
```

Expected output:

```json
{"status": "healthy"}
```

### Trigger a test run

```bash
curl -X POST "https://${FUNCTION_HOST}/api/test-run?code=${FUNCTION_KEY}"
```

### Check data in storage

```bash
az storage blob list \
  --account-name <storage-account-name> \
  --container-name curated \
  --auth-mode login
```

## Common commands

### Run deployment manually

```bash
gh workflow run deploy.yml
```

### View recent deployment runs

```bash
gh run list --workflow=deploy.yml --limit 5
```

### View recent test runs

```bash
gh run list --workflow=test.yml --limit 5
```

### Stream function logs

```bash
az webapp log tail \
  --name mdoast-func-west \
  --resource-group rg-mdo-attack-simulation
```

## Troubleshooting

### Nothing happens after pushing to `main`

That is expected. `deploy.yml` only runs when started manually.

### The Bicep deployment step fails with a missing `graphClientSecret`

That is a known issue in the current repo state. Supply `graphClientSecret` before the run by updating `infra/main.bicepparam` in the deployed branch, or run the deployment command yourself with an override.

### Health check fails with 401 or 403

The endpoint requires a function key. Re-run the health check with `?code=<function-key>`.

### OIDC setup fails with insufficient privileges

You need:

- Entra ID permission to create app registrations
- Subscription permission to assign RBAC roles

## Full documentation

- Complete setup guide: [GITHUB_ACTIONS_SETUP.md](../docs/GITHUB_ACTIONS_SETUP.md)
- Project overview: [README.md](../README.md)
- Development guide: [CONTRIBUTING.md](../CONTRIBUTING.md)

## Notes

- The deployment workflow always runs infrastructure deployment and function publishing in one job.
- There is no change detection step.
- There are no `deploy_infra` or `deploy_code` workflow inputs.
- The test workflow runs on pull requests to `main` and can also be run manually.
