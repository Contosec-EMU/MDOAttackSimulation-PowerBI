# GitHub Actions Deployment Setup Guide

This guide documents the workflows that are currently checked into this repository. It matches the actual workflow files under `.github/workflows/`.

## What the workflows actually do

### `deploy.yml`

- Trigger: `workflow_dispatch` only
- No workflow inputs are defined
- Runs as a single `deploy` job in the `production` environment
- Logs in to Azure with OIDC
- Creates the resource group if it does not exist
- Deploys `infra/main.bicep` with `infra/main.bicepparam`
- Waits 60 seconds for RBAC propagation
- Publishes the Azure Function code with Azure Functions Core Tools

### `test.yml`

- Triggers on pull requests targeting `main`
- Can also be run manually with `workflow_dispatch`
- Runs checkout, Python 3.11 setup, dependency install, `ruff`, `mypy`, `pytest` with coverage, and `pip-audit`
- `mypy` and `pip-audit` are non-blocking because those steps use `continue-on-error: true`

## Prerequisites

1. Azure subscription access with permission to:
   - Create Entra ID app registrations
   - Assign RBAC roles
   - Create or update resources in the target subscription
2. GitHub repository admin access to configure Actions secrets and variables
3. Local tools:
   - Azure CLI
   - Git
   - Optional: GitHub CLI (`gh`)

## Step 1: Configure Azure OIDC with GitHub

Run one of the setup scripts to create the Azure app registration and federated credential.

### PowerShell

```powershell
az login

.\scripts\setup-github-oidc.ps1 `
    -GitHubOrg "your-github-org" `
    -GitHubRepo "MDOAttackSimulation_PowerBI"
```

### Bash

```bash
az login
chmod +x scripts/setup-github-oidc.sh
./scripts/setup-github-oidc.sh your-github-org MDOAttackSimulation_PowerBI
```

The script outputs the three values required by `deploy.yml`:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

## Step 2: Add GitHub Actions secrets and variables

In GitHub, go to **Settings** > **Secrets and variables** > **Actions**.

Add these repository secrets:

| Name | Required | Purpose |
| --- | --- | --- |
| `AZURE_CLIENT_ID` | Yes | Azure app registration client ID used by OIDC login |
| `AZURE_TENANT_ID` | Yes | Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Yes | Azure subscription ID |

Add this repository variable if you do not want to use the default resource group name:

| Name | Required | Default | Purpose |
| --- | --- | --- | --- |
| `AZURE_RESOURCE_GROUP` | No | `rg-mdo-attack-simulation` | Resource group used by the deployment workflow |

If `AZURE_RESOURCE_GROUP` is not set, `deploy.yml` uses `rg-mdo-attack-simulation`.

## Step 3: Prepare `infra/main.bicepparam`

Update `infra/main.bicepparam` with values for your environment.

At minimum, confirm the non-secret parameters such as:

- `tenantId`
- `graphClientId`
- `prefix`
- `location`
- `timerSchedule`

### Known issue: `graphClientSecret` is required during deployment

This repository currently has a mismatch between the workflow and the Bicep template:

- `deploy.yml` runs `az deployment group create --parameters infra/main.bicepparam`
- `infra/main.bicep` requires a `graphClientSecret` parameter
- `infra/main.bicepparam` does not currently supply `graphClientSecret`

Result: the infrastructure deployment step in `deploy.yml` will fail unless `graphClientSecret` is supplied before the workflow runs.

You have two ways to handle this:

1. Add `graphClientSecret` to `infra/main.bicepparam` in the branch you will deploy.
2. Run the equivalent `az deployment group create` command yourself and pass `graphClientSecret` as an override.

Example override for a manual Azure CLI deployment:

```bash
az deployment group create \
  --resource-group rg-mdo-attack-simulation \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --parameters graphClientSecret="<your-graph-api-client-secret>"
```

Important notes:

- The secret is needed during the infrastructure deployment, not after it.
- The current GitHub Actions workflow does not define an input or secret mapping for `graphClientSecret`.
- Do not commit real secret values to a shared or public repository.

## Step 4: Run the deployment workflow manually

`deploy.yml` is manual only. A push to `main` does not trigger deployment.

### GitHub UI

1. Open the **Actions** tab.
2. Select **Deploy MDO Attack Simulation**.
3. Click **Run workflow**.
4. Start the run.

There are no workflow inputs to set.

### GitHub CLI

```bash
gh auth login
gh workflow run deploy.yml
```

## Step 5: Monitor the deployment

The deployment workflow has one job. The useful steps to watch are:

1. **Azure Login (OIDC)**
2. **Create Resource Group**
3. **Deploy Infrastructure (Bicep)**
4. **Wait for RBAC Propagation**
5. **Get Function App Name**
6. **Install Azure Functions Core Tools**
7. **Deploy Function Code**

Example GitHub CLI commands:

```bash
gh run list --workflow=deploy.yml
gh run view <run-id>
gh run watch
```

## Step 6: Verify the deployed function app

The HTTP endpoints in this function app use `AuthLevel.FUNCTION`. Include a function key when testing them.

```bash
# Example values. Replace with your deployed names.
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

Expected response:

```json
{"status": "healthy"}
```

Manual test run:

```bash
curl -X POST "https://${FUNCTION_HOST}/api/test-run?code=${FUNCTION_KEY}"
```

## Step 7: Understand the test workflow

`test.yml` is separate from deployment.

It runs in these cases:

- Pull requests targeting `main`
- Manual execution from the Actions tab

The job performs:

- Repository checkout
- Python 3.11 setup with pip cache
- Dependency installation from `requirements.txt` and `requirements-dev.txt`
- `ruff check`
- `mypy` for `config.py`, `utils/`, and `processors/` with `continue-on-error: true`
- `pytest` with coverage output
- Coverage artifact upload
- `pip-audit` with `continue-on-error: true`

## Troubleshooting

### Deployment does not start after pushing to `main`

That is expected. `deploy.yml` only supports `workflow_dispatch`.

### Deployment fails during the Bicep step with a missing parameter error

Check the known issue above. The workflow only passes `infra/main.bicepparam`, and `graphClientSecret` must be supplied before the deployment step runs.

### Health check returns 401 or 403

The health endpoint requires a function key. Retrieve the key and call:

```bash
curl "https://<function-host>/api/health?code=<function-key>"
```

### OIDC login fails

Verify that:

1. `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID` are present in GitHub Actions secrets.
2. The federated credential created by the setup script matches your repository.
3. The Azure app registration has an associated service principal.

## References

- GitHub Actions: https://docs.github.com/en/actions
- Azure OIDC for GitHub Actions: https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure
- Azure Functions GitHub Actions guidance: https://learn.microsoft.com/en-us/azure/azure-functions/functions-how-to-github-actions
- Bicep: https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/
