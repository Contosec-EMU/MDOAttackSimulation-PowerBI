# MDO Attack Simulation Training - Power BI Data Pipeline

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Azure Functions v4](https://img.shields.io/badge/Azure%20Functions-v4-blue.svg)](https://azure.microsoft.com/en-us/products/functions)

End-to-end Azure solution to ingest Microsoft Defender for Office 365 (MDO) Attack Simulation Training data from Microsoft Graph API into Azure Data Lake Storage Gen2 as Parquet files, optimized for Power BI consumption.

> **Inspired by** [cammurray/ASTSync](https://github.com/cammurray/ASTSync) — reimplemented in Python with ADLS Gen2 Parquet output, async architecture, and Power BI integration.

## ✨ Features

- **9 Data Tables** — Full parity with ASTSync: simulations, users, events, trainings, payloads, and more
- **Async Architecture** — Built with `aiohttp` and Azure SDK async for high throughput
- **Power BI Optimized** — Parquet files with explicit schemas, Snappy compression, and INT64 timestamps
- **Incremental Sync** — 7-day lookback reduces API calls by ~70–80% after initial sync
- **Secure by Design** — Managed Identity, Key Vault, network isolation, RBAC least privilege
- **Three Deployment Methods** — GitHub Actions CI/CD, Azure CLI, or Azure Portal manual setup

## Table of Contents

- [Architecture](#architecture)
- [Data Model (9 Tables)](#data-model-9-tables)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Deployment Methods](#deployment-methods)
- [Configuration](#configuration)
- [Power BI Setup](#power-bi-setup)
- [Project Structure](#project-structure)
- [Output Data Structure](#output-data-structure)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Cost Estimation](#cost-estimation)
- [Security](#security)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Microsoft Graph │────▶│  Azure Function  │────▶│  ADLS Gen2       │────▶│  Power BI   │
│  (9 API sources) │     │  (Timer/HTTP)    │     │  (Parquet + JSON)│     │  (Refresh)  │
└──────────────────┘     └──────────────────┘     └──────────────────┘     └─────────────┘
                                  │                         │
                                  ▼                         │
                          ┌───────────────┐                 │
                          │   Key Vault   │                 │
                          │  (Secrets)    │                 │
                          └───────────────┘                 │
                                  │                         │
                                  ▼                         │
                          ┌───────────────┐                 │
                          │ App Insights  │◀────────────────┘
                          │ (Monitoring)  │
                          └───────────────┘
```

**Data flow:**

1. Timer trigger fires on schedule (default: daily 2:00 AM UTC)
2. Function authenticates via Managed Identity → Key Vault → OAuth2 client credentials
3. Paginates through 9 Microsoft Graph API endpoints with retry + exponential backoff
4. Writes Parquet (curated) and JSON (raw archive) to ADLS Gen2, date-partitioned
5. Power BI connects directly to ADLS Gen2 for scheduled refresh

## Data Model (9 Tables)

| Table | API Version | Source Endpoint | Description |
|-------|-------------|-----------------|-------------|
| `repeatOffenders` | v1.0 | `reports/security/getAttackSimulationRepeatOffenders` | Users who fell for multiple simulations |
| `simulationUserCoverage` | v1.0 | `reports/security/getAttackSimulationSimulationUserCoverage` | Per-user simulation stats |
| `trainingUserCoverage` | v1.0 | `reports/security/getAttackSimulationTrainingUserCoverage` | Per-user training completion |
| `simulations` | beta | `security/attackSimulation/simulations` | Simulation definitions and metrics |
| `simulationUsers` | beta | `.../simulations/{id}/report/simulationUsers` | Per-user per-simulation details |
| `simulationUserEvents` | beta | *(extracted from simulationUsers)* | User events (clicks, reports, etc.) |
| `trainings` | beta | `security/attackSimulation/trainings` | Training definitions |
| `payloads` | beta | `security/attackSimulation/payloads` | Phishing payload templates |
| `users` | v1.0 | `users/{id}` | Entra ID user enrichment |

> The first 3 tables (core endpoints) always run. The remaining 6 (extended endpoints) run when `SYNC_SIMULATIONS=true` (default).

## Prerequisites

- **Azure subscription** with permissions to create resources
- **Entra ID app registration** with the following **Application** permissions:
  - `AttackSimulation.Read.All`
  - `User.Read.All`
- **Admin consent** granted for the above permissions
- **Azure CLI** (v2.50+) — [Install](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- **Azure Functions Core Tools v4** — [Install](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local#install-the-azure-functions-core-tools)
- **Python 3.11** — [Download](https://www.python.org/downloads/)
- **Power BI Pro** or Premium capacity (for scheduled refresh)

## Quick Start

Choose a deployment method:

| Method | Best for | Guide |
|--------|----------|-------|
| **GitHub Actions** (Recommended) | Teams, CI/CD, repeatable deployments | [GitHub Actions Setup](GITHUB_ACTIONS_SETUP.md) |
| **Azure CLI** | Developers, scripted deployments | [CLI steps below](#option-2-azure-cli) |
| **Azure Portal** | One-off setup, learning | [Portal steps below](#option-3-azure-portal-manual) |

## Deployment Methods

### Option 1: GitHub Actions (Recommended)

Automated CI/CD with OIDC authentication — no secrets to rotate.

→ **See [GitHub Actions Setup Guide](GITHUB_ACTIONS_SETUP.md)** for full instructions, or follow the [Quick Start](scripts/QUICK_START.md) for a 10-minute setup.

### Option 2: Azure CLI

#### Step 1: Create the Entra ID App Registration

```powershell
# Login to Azure
az login

# Create app registration
$appName = "MDOAttackSimulation-GraphAPI"
$app = az ad app create --display-name $appName --query "{appId:appId, id:id}" -o json | ConvertFrom-Json

# Create service principal
az ad sp create --id $app.appId

# Add API permissions (Application type)
# AttackSimulation.Read.All
az ad app permission add --id $app.appId \
  --api 00000003-0000-0000-c000-000000000000 \
  --api-permissions 93283d0a-6322-4fa8-966b-8c121624760d=Role

# User.Read.All
az ad app permission add --id $app.appId \
  --api 00000003-0000-0000-c000-000000000000 \
  --api-permissions df021288-bdef-4463-88db-98f22de89214=Role

# Grant admin consent (requires Global Admin or Privileged Role Admin)
az ad app permission admin-consent --id $app.appId

# Create client secret — save this securely!
$secret = az ad app credential reset --id $app.appId --append --query password -o tsv

Write-Host "App (Client) ID: $($app.appId)"
Write-Host "Client Secret: $secret"
Write-Host "Tenant ID: $(az account show --query tenantId -o tsv)"
```

> ⚠️ **Save the Client Secret** — it is only shown once.

#### Step 2: Create a Resource Group

```bash
SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="rg-mdo-attack-simulation"
LOCATION="eastus"

az account set --subscription $SUBSCRIPTION_ID
az group create --name $RESOURCE_GROUP --location $LOCATION
```

#### Step 3: Update Parameters

Edit `infra/main.bicepparam`:

```bicep
param tenantId = '<YOUR_TENANT_ID>'
param graphClientId = '<YOUR_APP_REGISTRATION_CLIENT_ID>'
```

#### Step 4: Deploy Infrastructure

```bash
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --query "properties.outputs"

# Capture outputs
KEYVAULT_NAME=$(az deployment group show -g $RESOURCE_GROUP -n main \
  --query "properties.outputs.keyVaultName.value" -o tsv)
FUNCTION_APP_NAME=$(az deployment group show -g $RESOURCE_GROUP -n main \
  --query "properties.outputs.functionAppName.value" -o tsv)
STORAGE_ACCOUNT_NAME=$(az deployment group show -g $RESOURCE_GROUP -n main \
  --query "properties.outputs.storageAccountName.value" -o tsv)
```

#### Step 5: Store the Client Secret

```bash
az keyvault secret set \
  --vault-name $KEYVAULT_NAME \
  --name "graph-client-secret" \
  --value "<YOUR_CLIENT_SECRET>"
```

#### Step 6: Deploy Function Code

```bash
cd src/function_app
func azure functionapp publish $FUNCTION_APP_NAME --python
```

#### Step 7: Validate

```bash
# Health check
curl "https://${FUNCTION_APP_NAME}.azurewebsites.net/api/health"

# Trigger a manual test run
FUNCTION_KEY=$(az functionapp keys list -g $RESOURCE_GROUP -n $FUNCTION_APP_NAME \
  --query "functionKeys.default" -o tsv)
curl -X POST "https://${FUNCTION_APP_NAME}.azurewebsites.net/api/test-run?code=${FUNCTION_KEY}"

# Verify Parquet files exist
az storage fs file list \
  --account-name $STORAGE_ACCOUNT_NAME \
  --file-system curated \
  --recursive --auth-mode login
```

> You can also use the included helper scripts: `scripts/deploy.ps1` (PowerShell) or `scripts/deploy.sh` (Bash).

### Option 3: Azure Portal (Manual)

1. **Create a Resource Group** in the Azure Portal
2. **Deploy Bicep** — use the Portal's "Deploy a custom template" blade, upload `infra/main.bicep`, and fill in the parameters
3. **Store client secret** in the Key Vault under the name `graph-client-secret`
4. **Deploy function code** — use VS Code Azure Functions extension or zip deploy

## Configuration

All configuration is via environment variables (set in Bicep or Function App Settings):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TENANT_ID` | ✅ | — | Entra ID tenant ID |
| `GRAPH_CLIENT_ID` | ✅ | — | App registration client ID |
| `KEY_VAULT_URL` | ✅ | — | Key Vault URL (`https://<name>.vault.azure.net/`) |
| `STORAGE_ACCOUNT_URL` | ✅ | — | ADLS Gen2 URL (`https://<name>.dfs.core.windows.net/`) |
| `TIMER_SCHEDULE` | | `0 0 2 * * *` | CRON schedule (6-field Azure Functions format) |
| `SYNC_MODE` | | `full` | `full` or `incremental` (7-day lookback) |
| `SYNC_SIMULATIONS` | | `true` | Enable extended endpoints (simulations, users, trainings, payloads) |

### Timer Schedule (CRON)

```
{second} {minute} {hour} {day} {month} {day-of-week}

Examples:
  0 0 2 * * *     = Daily at 2:00 AM UTC
  0 0 */6 * * *   = Every 6 hours
  0 30 9 * * 1-5  = Weekdays at 9:30 AM UTC
  0 0 0 1 * *     = First day of each month at midnight
```

## Power BI Setup

### Connect to ADLS Gen2

1. Open **Power BI Desktop** → **Get Data** → **Azure** → **Azure Data Lake Storage Gen2**
2. Enter the storage URL: `https://<storage-account>.dfs.core.windows.net/`
3. Sign in with your organizational account (requires **Storage Blob Data Reader** on the `curated` container)
4. Navigate to `curated/` → select a table folder (e.g., `repeatOffenders`)
5. Combine files to load all date-partitioned Parquet files

### Power Query (M) Example

```powerquery
let
    Source = AzureStorage.DataLake("https://<storage-account>.dfs.core.windows.net/"),
    curated = Source{[Name="curated"]}[Content],
    repeatOffenders = curated{[Name="repeatOffenders"]}[Content],
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(repeatOffenders, {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```

### Scheduled Refresh

1. **Publish** the report to Power BI Service
2. Go to **Dataset Settings** → **Scheduled Refresh**
3. Configure credentials using OAuth2 with your organizational account
4. Set the refresh schedule to run **1 hour after** the Function timer (e.g., 3:00 AM if the Function runs at 2:00 AM)
5. Enable scheduled refresh

> 💡 **Tip**: For Power BI Pro without Premium, you may need an [On-Premises Data Gateway](https://learn.microsoft.com/en-us/power-bi/connect-data/service-gateway-onprem) to access ADLS Gen2.

## Project Structure

```
MDOAttackSimulation_PowerBI/
├── .github/
│   ├── ISSUE_TEMPLATE/         # GitHub issue templates
│   └── workflows/
│       ├── deploy.yml          # CI/CD deployment workflow
│       └── test.yml            # Test workflow
├── docs/
│   ├── GATEWAY_QUICK_REFERENCE.md
│   └── GATEWAY_VM_SETUP.md
├── infra/
│   ├── main.bicep              # Azure infrastructure (IaC)
│   ├── main.bicepparam         # Deployment parameters
│   ├── main.bicepparam.example # Example parameters (safe to commit)
│   ├── gateway-vm.bicep        # Optional gateway VM infrastructure
│   ├── gateway-vm.bicepparam
│   └── gateway-vm.bicepparam.example
├── scripts/
│   ├── create-app-registration.ps1
│   ├── deploy.ps1              # PowerShell deployment script
│   ├── deploy.sh               # Bash deployment script
│   ├── deploy-gateway-vm.ps1
│   ├── deploy-gateway-vm.sh
│   ├── setup-github-oidc.ps1   # GitHub OIDC setup (PowerShell)
│   ├── setup-github-oidc.sh    # GitHub OIDC setup (Bash)
│   └── QUICK_START.md          # 10-minute quick start guide
├── src/
│   └── function_app/
│       ├── clients/
│       │   ├── graph_api.py    # Async Graph API client (aiohttp)
│       │   └── adls_writer.py  # Async ADLS Gen2 writer
│       ├── processors/
│       │   └── transformers.py # Data transformation (9 processors)
│       ├── services/
│       │   └── sync_state.py   # Incremental sync state manager
│       ├── utils/
│       │   └── security.py     # Security headers, sanitization
│       ├── function_app.py     # Main entry point (timer + HTTP endpoints)
│       ├── config.py           # Centralized configuration
│       ├── host.json           # Function runtime config (15 min timeout)
│       └── requirements.txt    # Python dependencies
├── tests/                      # Test suite
├── CONTRIBUTING.md             # Development guide
├── GITHUB_ACTIONS_SETUP.md     # CI/CD setup guide
└── README.md                   # This file
```

## Output Data Structure

### Curated Container (Parquet — for Power BI)

```
curated/
├── repeatOffenders/
│   └── 2025-01-15/
│       └── repeatOffenders.parquet
├── simulationUserCoverage/
│   └── 2025-01-15/
│       └── simulationUserCoverage.parquet
├── trainingUserCoverage/
│   └── 2025-01-15/
│       └── trainingUserCoverage.parquet
├── simulations/
│   └── 2025-01-15/
│       └── simulations.parquet
├── simulationUsers/
│   └── 2025-01-15/
│       └── simulationUsers.parquet
├── simulationUserEvents/
│   └── 2025-01-15/
│       └── simulationUserEvents.parquet
├── trainings/
│   └── 2025-01-15/
│       └── trainings.parquet
├── payloads/
│   └── 2025-01-15/
│       └── payloads.parquet
└── users/
    └── 2025-01-15/
        └── users.parquet
```

### Raw Container (JSON — archival)

```
raw/
├── repeatOffenders/
│   └── 2025-01-15/
│       └── repeatOffenders_raw.json
├── simulations/
│   └── 2025-01-15/
│       └── simulations_raw.json
└── ...  (same structure for all 9 tables)
```

### Sync State

```
state/
└── sync_state.json             # Tracks last sync time for incremental mode
```

## Monitoring

### Application Insights Queries (KQL)

```kusto
// Function execution summary (last 7 days)
traces
| where operation_Name == "mdo_attack_simulation_ingest"
| where timestamp > ago(7d)
| summarize
    Runs = count(),
    Errors = countif(severityLevel >= 3),
    AvgDuration = avg(duration)
    by bin(timestamp, 1d)

// Recent errors
exceptions
| where timestamp > ago(24h)
| order by timestamp desc
| project timestamp, operation_Name, outerMessage, details
```

### HTTP Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/health` | GET | Anonymous | Health check |
| `/api/test-run` | POST | Function key | Manual trigger |
| `/api/sync-status` | GET | Function key | View sync configuration and state |
| `/api/reset-sync-state` | POST | Function key | Reset state to force full sync |

## Troubleshooting

### Authentication Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` | Invalid credentials | Verify tenant ID, client ID, and client secret |
| `403 Forbidden` | Missing permission | Ensure `AttackSimulation.Read.All` and `User.Read.All` are granted with admin consent |
| `AADSTS700016` | App not found in tenant | Verify app registration exists and client ID is correct |

### Storage Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `403 AuthorizationPermissionMismatch` | Missing RBAC | Grant `Storage Blob Data Contributor` to Function managed identity |
| `ContainerNotFound` | Container missing | Containers are auto-created; check Bicep deployment logs |

### Key Vault Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `403 Forbidden` | Missing RBAC | Grant `Key Vault Secrets User` to Function managed identity |
| `SecretNotFound` | Secret missing | Run `az keyvault secret set --name graph-client-secret` |

### Power BI Errors

| Error | Cause | Fix |
|-------|-------|-----|
| Cannot connect to ADLS | Wrong URL or auth | Use `dfs.core.windows.net` endpoint (not `blob`); verify OAuth credentials |
| Refresh fails | Gateway needed | For Pro without Premium, set up an [On-Premises Data Gateway](https://learn.microsoft.com/en-us/power-bi/connect-data/service-gateway-onprem) |
| No data shown | Wrong path | Verify container and folder paths in Power Query |

### General

| Issue | Fix |
|-------|-----|
| Incomplete data | Pagination is automatic (`@odata.nextLink`); check App Insights for errors |
| Function timeout | Default timeout is 15 minutes; for very large tenants, consider incremental sync mode |

## Cost Estimation

| Resource | SKU | Est. Monthly Cost |
|----------|-----|-------------------|
| Function App (App Service) | Basic B1 | ~$13 |
| Storage (ADLS Gen2) | Hot tier, <1 GB | ~$0.50 |
| Key Vault | Standard | ~$0.03 |
| Application Insights | Pay-as-you-go, 5 GB free | ~$0–5 |
| **Total** | | **~$15–20/month** |

> Costs may vary by region and usage. The Function App uses an always-on Basic B1 plan to avoid cold start delays.

## Security

This solution follows Azure security best practices:

- ✅ **No secrets in code** — Graph API client secret stored in Key Vault
- ✅ **Managed Identity** — Function authenticates to Key Vault and Storage without stored credentials
- ✅ **RBAC least privilege** — `Storage Blob Data Contributor` and `Key Vault Secrets User` only
- ✅ **Network isolation** — Key Vault and Storage deny public access by default, allow Azure services only
- ✅ **Input sanitization** — All API response strings are sanitized (max 1,000 chars, trimmed)
- ✅ **Security headers** — All HTTP responses include `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Strict-Transport-Security`
- ✅ **Sanitized error messages** — HTTP responses expose correlation IDs, not internal error details
- ✅ **HTTPS-only** — TLS 1.2 minimum enforced on all Azure resources
- ✅ **90-day log retention** — Configured in Log Analytics for audit compliance
- ✅ **Application permissions** — Uses app-only auth (not delegated) for unattended execution

To report a security vulnerability, please open a private issue or contact the maintainers directly.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development environment setup
- Code style guidelines (PEP 8, type hints, naming conventions)
- Testing requirements
- Pull request process

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [cammurray/ASTSync](https://github.com/cammurray/ASTSync) — Original C# implementation that inspired this project
- [Microsoft Graph API — Attack Simulation Training](https://learn.microsoft.com/en-us/graph/api/resources/security-attacksimulation-overview) — API documentation
- [Azure Functions Python Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python) — Runtime reference
