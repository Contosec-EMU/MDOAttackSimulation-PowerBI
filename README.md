# MDO Attack Simulation Training - Power BI Data Pipeline

> **Disclaimer:** This is a personal open-source project. It is **not** an official Microsoft product, does not represent Microsoft's opinions or endorsements, and is **not** supported by Microsoft in any way. Use it at your own risk.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Azure Functions v4](https://img.shields.io/badge/Azure%20Functions-v4-blue.svg)](https://azure.microsoft.com/en-us/products/functions)

Azure data pipeline that ingests Microsoft Defender for Office 365 (MDO) Attack Simulation Training data from Microsoft Graph API into Azure Data Lake Storage Gen2 as Parquet files for Power BI.

### Why this solution?

Attack Simulation Training reports are only available within the Microsoft Defender XDR console, which presents challenges for many organizations:

- **Limited audience** - C-level executives and business stakeholders who need to see phishing readiness metrics from a business or executive perspective often don't have (or shouldn't need) access to the Defender XDR security console.
- **Manual workarounds are unsustainable** - The common alternative of manually exporting CSV files from XDR and importing them into Power BI is time-consuming, error-prone, and doesn't scale for teams running regular simulation campaigns.
- **No native Power BI integration** - There is no built-in connector to bring Attack Simulation Training data directly into Power BI for custom dashboards and automated reporting.

I built this to sync simulation data into Azure Data Lake on a schedule so Power BI can read it, without requiring XDR access or manual data exports.

> **Modular design** - The data processing and storage layers are decoupled, so you can swap the destination if needed. This implementation writes to ADLS Gen2 for Power BI, but the writer module can also target **Microsoft Fabric / OneLake**, **Azure SQL Database**, **Azure Synapse Analytics**, or **Dataverse** with minimal code changes.

## Features

- **9 Data Tables** - Simulations, users, events, trainings, payloads, and more
- **Async Architecture** - Built with `aiohttp` and Azure SDK async for high throughput
- **Power BI Optimized** - Parquet files with explicit schemas, Snappy compression, and INT64 timestamps
- **Incremental Sync** - 7-day lookback reduces API calls by ~70-80% after initial sync
- **Secure by Design** - Managed Identity, Key Vault, network isolation, RBAC least privilege
- **Three Deployment Methods** - Azure CLI, GitHub Actions CI/CD, or Azure Portal manual setup

## Report Examples

The included Power BI template provides several report pages out of the box. These were built by a security engineer, not a data analytics specialist, so treat them as functional starting points. You can customize them or build entirely new reports to fit your organization's needs.

| | |
|---|---|
| ![Executive Dashboard](docs/images/executive-dashboard.png) | ![Overview](docs/images/overview.png) |
| **Executive Dashboard** - High-level KPIs and trends | **Organization Overview** - Coverage across departments |
| ![Simulation Analysis](docs/images/simulation-analysis.png) | ![Training Compliance](docs/images/training-compliance.png) |
| **Simulation Analysis** - Per-simulation drill-down | **Training Compliance** - Completion rates and status |
| ![User Risk Profile](docs/images/user-risk-profile.png) | ![Department Overview](docs/images/department-overview.png) |
| **User Risk Profile** - Individual user behavior | **Department Overview** - Department-level comparison |
| ![Improving Submissions](docs/images/improving-submissions.png) | |
| **Improving Submissions** - Reporting trends over time | |

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

**ETL Pipeline:**

```
Graph API  ──Extract──▶  Raw JSON  ──Transform──▶  Flat Dicts  ──Load──▶  Parquet + JSON
 (9 endpoints)           (paginated)               (sanitized)           (date-partitioned)
                                                                               │
                                                                      Power BI reads
```

1. **Extract** - Timer fires on schedule (default: every hour). Function authenticates via Managed Identity > Key Vault > OAuth2 client credentials. Paginates through 9 Graph API endpoints with retry + exponential backoff.
2. **Transform** - Flattens nested JSON, sanitizes all strings, adds `snapshotDate` for partitioning, filters out non-Entra users.
3. **Load** - Writes Parquet (curated/, with PyArrow schemas) and JSON (raw/, for audit) to ADLS Gen2, date-partitioned as `curated/{table}/YYYY-MM-DD/`.
4. **Consume** - Power BI connects directly to ADLS Gen2 and reads Parquet files on scheduled refresh.

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

- **Azure subscription** with **Owner** role (or **Contributor** + **User Access Administrator**) - required to create resources and assign RBAC roles
- **Entra ID app registration** with the following **Application** permissions:
  - `AttackSimulation.Read.All`
  - `User.Read.All`
- **Admin consent** granted for the above permissions (requires **Global Administrator** or **Privileged Role Administrator**)
- **Azure CLI** (v2.50+) - [Install](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- **Azure Functions Core Tools v4** - [Install](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local#install-the-azure-functions-core-tools)
- **Python 3.11** - [Download](https://www.python.org/downloads/)
- **Power BI Pro** or Premium capacity (for scheduled refresh)

## Quick Start

Choose a deployment method:

| Method | Best for | Guide |
|--------|----------|-------|
| **Azure CLI** | Developers, scripted deployments | [CLI steps below](#option-1-azure-cli) |
| **GitHub Actions** | Teams, CI/CD, repeatable deployments | [GitHub Actions Setup](docs/GITHUB_ACTIONS_SETUP.md) |
| **Azure Portal** | One-off setup, learning | [Portal steps below](#option-3-azure-portal-manual) |

## Deployment Methods

### Option 1: Azure CLI

> **Resource group naming:** The CLI examples below use `rg-mdo-attack-simulation` as the resource group name. Replace it with your organization's naming convention (for example, `rg-mdo-attack-sim-prod`).

**Required permissions:**

- **Azure subscription:** Owner, or Contributor + User Access Administrator (for RBAC assignments in the Bicep template)
- **Entra ID:** Cloud Application Administrator or Application Administrator (to create the app registration)
- **Admin consent:** Global Administrator or Privileged Role Administrator (to grant Graph API permissions)

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

# Create client secret - save this securely!
$secret = az ad app credential reset --id $app.appId --append --query password -o tsv

Write-Host "App (Client) ID: $($app.appId)"
Write-Host "Client Secret: $secret"
Write-Host "Tenant ID: $(az account show --query tenantId -o tsv)"
```

> **Warning:** **Save the Client Secret** - it is only shown once.

#### Step 2: Create a Resource Group

```powershell
$SUBSCRIPTION_ID = "<your-subscription-id>"
$RESOURCE_GROUP  = "rg-mdo-attack-simulation"
$LOCATION        = "eastus"

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

```powershell
$DEPLOYMENT_OUTPUT = az deployment group create `
  --resource-group $RESOURCE_GROUP `
  --template-file infra/main.bicep `
  --parameters infra/main.bicepparam | ConvertFrom-Json

# Capture outputs
$KEYVAULT_NAME        = $DEPLOYMENT_OUTPUT.properties.outputs.keyVaultName.value
$FUNCTION_APP_NAME    = $DEPLOYMENT_OUTPUT.properties.outputs.functionAppName.value
$STORAGE_ACCOUNT_NAME = $DEPLOYMENT_OUTPUT.properties.outputs.dataLakeAccountName.value

Write-Host "Key Vault:        $KEYVAULT_NAME"
Write-Host "Function App:     $FUNCTION_APP_NAME"
Write-Host "Storage Account:  $STORAGE_ACCOUNT_NAME"
```

#### Step 5: Store the Client Secret

The Key Vault uses RBAC authorization. You need `Key Vault Secrets Officer` to write secrets:

```powershell
# Grant yourself Key Vault Secrets Officer on the vault
$CURRENT_USER_ID = (az ad signed-in-user show --query id -o tsv)
$KV_SCOPE = (az keyvault show --name $KEYVAULT_NAME --resource-group $RESOURCE_GROUP --query id -o tsv)
az role assignment create --role "Key Vault Secrets Officer" --assignee $CURRENT_USER_ID --scope $KV_SCOPE

# Wait for RBAC propagation
Start-Sleep -Seconds 60

# Store the Graph API client secret
az keyvault secret set `
  --vault-name $KEYVAULT_NAME `
  --name "graph-client-secret" `
  --value "<YOUR_CLIENT_SECRET>"
```

> **Warning:** **Firewall note:** The Key Vault is deployed with network rules that deny public access by default. If you are running this from outside the VNet (e.g., your local machine), you will get a `ForbiddenByFirewall` error. Temporarily add your IP to the Key Vault firewall:
>
> ```powershell
> # Add your current public IP to the Key Vault firewall
> $MY_IP = (Invoke-RestMethod -Uri "https://api.ipify.org")
> az keyvault network-rule add --name $KEYVAULT_NAME --ip-address "$MY_IP/32"
> ```
>
> After storing the secret, you can remove the exception:
>
> ```powershell
> az keyvault network-rule remove --name $KEYVAULT_NAME --ip-address "$MY_IP/32"
> ```

#### Step 6: Deploy Function Code

```powershell
cd src/function_app
func azure functionapp publish $FUNCTION_APP_NAME --python
```

#### Step 7: Validate

Before browsing data, grant yourself `Storage Blob Data Reader` on the ADLS Gen2 account (the Bicep only assigns roles to the Function App's managed identity, not to the deploying user):

```powershell
# Grant yourself Storage Blob Data Reader on the data lake
$CURRENT_USER_ID = (az ad signed-in-user show --query id -o tsv)
$STORAGE_SCOPE = (az storage account show --name $STORAGE_ACCOUNT_NAME --resource-group $RESOURCE_GROUP --query id -o tsv)
az role assignment create --role "Storage Blob Data Reader" --assignee $CURRENT_USER_ID --scope $STORAGE_SCOPE

# Wait for RBAC propagation
Start-Sleep -Seconds 60

# Get the function key (all endpoints require authentication)
$FUNCTION_KEY = (az functionapp keys list -g $RESOURCE_GROUP -n $FUNCTION_APP_NAME --query "functionKeys.default" -o tsv)

# Health check
Invoke-RestMethod "https://$FUNCTION_APP_NAME.azurewebsites.net/api/health?code=$FUNCTION_KEY"

# Trigger a manual test run
Invoke-RestMethod -Method Post "https://$FUNCTION_APP_NAME.azurewebsites.net/api/test-run?code=$FUNCTION_KEY"

# Verify Parquet files exist
az storage fs file list `
  --account-name $STORAGE_ACCOUNT_NAME `
  --file-system curated `
  --recursive --auth-mode login
```

> **Warning:** **Storage firewall note:** The ADLS Gen2 storage account is deployed with network rules that deny public access by default. If you are listing or browsing files from outside the VNet, you will get an authorization error. To verify data from your local machine, temporarily add your IP:
>
> ```powershell
> $MY_IP = (Invoke-RestMethod -Uri "https://api.ipify.org")
> az storage account network-rule add --account-name $STORAGE_ACCOUNT_NAME --ip-address "$MY_IP"
> # After verifying, remove the exception:
> az storage account network-rule remove --account-name $STORAGE_ACCOUNT_NAME --ip-address "$MY_IP"
> ```
>
> Alternatively, for testing from a network outside your organization, you can temporarily enable public access via **Azure Portal > Storage account > Networking > Enabled from all networks**. This is not recommended for production.

> You can also use the included helper scripts: `scripts/deploy.ps1` (PowerShell) or `scripts/deploy.sh` (Bash).

#### Next Steps: Set Up Reporting

Your data pipeline is running. Choose how to visualize the data:

| Option | Best for | Guide |
|--------|----------|-------|
| **Power BI Desktop** | Rich dashboards, scheduled refresh, sharing via Power BI Service | [Power BI Setup Guide](docs/POWERBI_SETUP.md) |

Power BI reads the same data from ADLS Gen2.

### Option 2: GitHub Actions

Use the workflow in this repo if you want repeatable deployments from GitHub with OIDC authentication.

See the [GitHub Actions Setup Guide](docs/GITHUB_ACTIONS_SETUP.md) for the setup steps.

### Option 3: Azure Portal (Manual)

1. **Create a Resource Group** in the Azure Portal
2. **Deploy Bicep** - use the Portal's "Deploy a custom template" blade, upload `infra/main.bicep`, and fill in the parameters
3. **Store client secret** in the Key Vault under the name `graph-client-secret`
4. **Deploy function code** - use VS Code Azure Functions extension or zip deploy

## Configuration

All configuration is via environment variables (set in Bicep or Function App Settings):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TENANT_ID` | Yes | - | Entra ID tenant ID |
| `GRAPH_CLIENT_ID` | Yes | - | App registration client ID |
| `KEY_VAULT_URL` | Yes | - | Key Vault URL (`https://<name>.vault.azure.net/`) |
| `STORAGE_ACCOUNT_URL` | Yes | - | ADLS Gen2 URL (`https://<name>.dfs.core.windows.net/`) |
| `TIMER_SCHEDULE` | | `0 0 * * * *` | CRON schedule (6-field Azure Functions format) |
| `SYNC_MODE` | | `full` | `full` or `incremental` (7-day lookback) |
| `SYNC_SIMULATIONS` | | `true` | Enable extended endpoints (simulations, users, trainings, payloads) |

### Network Isolation

The Bicep template accepts a `networkIsolation` parameter (`"none"` or `"private"`). Private mode creates private endpoints for all storage accounts and Key Vault, suitable for tenants with Azure Policy restricting public access. See the [Quick Start guide](scripts/QUICK_START.md#network-isolation-private-endpoints) for usage details.

### Timer Schedule (CRON)

```
{second} {minute} {hour} {day} {month} {day-of-week}

Examples:
  0 0 * * * *     = Every hour at :00 (default)
  0 0 */6 * * *   = Every 6 hours
  0 30 9 * * 1-5  = Weekdays at 9:30 AM UTC
  0 0 0 1 * *     = First day of each month at midnight
```

## Power BI Setup

### Pre-Built Report Templates (Recommended)

This repository includes ready-to-use Power BI report templates in the [`reports/`](reports/) folder with 7 dashboard pages, 28 DAX measures, and all table relationships pre-configured. These are **basic starter templates** - the authors are security engineers, not data visualization designers - so you are encouraged to customize them to fit your organization's needs.

1. Open **Power BI Desktop** (March 2024+) with Developer Mode enabled
2. In **File Explorer**, double-click `reports/MDOAttackSimulation.pbip` (or open from Power BI Desktop via **File > Open report**)
3. Set the `StorageAccountUrl` parameter to your ADLS Gen2 DFS endpoint (e.g., `https://<name>.dfs.core.windows.net`)
4. Click **Refresh** to load data

See the [reports README](reports/README.md) for detailed setup instructions and troubleshooting.

### Manual Connection (Alternative)

If you prefer to build your own report:

1. Open **Power BI Desktop** > **Get Data** > **Azure** > **Azure Data Lake Storage Gen2**
2. Enter the storage URL: `https://<storage-account>.dfs.core.windows.net/`
3. Sign in with your organizational account
4. Navigate to `curated/` > select a table folder (e.g., `repeatOffenders`)
5. Combine files to load all date-partitioned Parquet files

> **Important:** Each Power BI user must have the **Storage Blob Data Reader** role on the ADLS Gen2 storage account. See the [Power BI Setup Guide](docs/POWERBI_SETUP.md#verify-storage-access) for instructions on granting access.

### Power Query (M) Example

```powerquery
let
    Source = AzureStorage.DataLake("https://<storage-account>.dfs.core.windows.net/curated/repeatOffenders"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```

### Scheduled Refresh

1. **Publish** the report to Power BI Service
2. Go to **Dataset Settings** > **Scheduled Refresh**
3. Configure credentials using OAuth2 with your organizational account
4. Set the refresh schedule (e.g., every 3 hours, or daily at a time that suits your reporting needs - the Function ingests fresh data every hour by default)
5. Enable scheduled refresh

> **Tip**: For Power BI Pro without Premium, you may need an [On-Premises Data Gateway](https://learn.microsoft.com/en-us/power-bi/connect-data/service-gateway-onprem) to access ADLS Gen2.

## Project Structure

```
MDOAttackSimulation_PowerBI/
├── .github/
│   ├── ISSUE_TEMPLATE/         # GitHub issue templates
│   └── workflows/
│       ├── deploy.yml          # CI/CD deployment workflow
│       └── test.yml            # Test workflow
├── docs/
├── infra/
│   ├── main.bicep              # Azure infrastructure (IaC)
│   ├── main.bicepparam         # Deployment parameters
│   └── main.bicepparam.example # Example parameters (safe to commit)
├── reports/                    # Power BI report templates (PBIR format)
│   ├── MDOAttackSimulation.pbip
│   ├── MDOAttackSimulation.Report/    # 7 report pages, 63 visuals
│   └── MDOAttackSimulation.SemanticModel/  # 9 tables, 28 DAX measures
├── scripts/
│   ├── create-app-registration.ps1
│   ├── deploy.ps1              # PowerShell deployment script
│   ├── deploy.sh               # Bash deployment script
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
├── docs/                       # Deployment & setup guides
└── README.md                   # This file
```

## Output Data Structure

### Curated Container (Parquet - for Power BI)

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

### Raw Container (JSON - archival)

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
| `/api/health` | GET | Function key | Health check |
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
| Application Insights | Pay-as-you-go, 5 GB free | ~$0-5 |
| **Total** | | **~$15-20/month** |

> Costs may vary by region and usage. The Function App uses an always-on Basic B1 plan to avoid cold start delays.

## Security

This solution follows Azure security best practices:

- **No secrets in code** - Graph API client secret stored securely in Key Vault
- **Managed Identity** - Function authenticates to Key Vault and Storage without stored credentials; Key Vault is used to securely retrieve the Graph API client secret for OAuth2 authentication
- **RBAC least privilege** - Storage Blob Data Contributor and Key Vault Secrets User only
- **Network isolation** - Key Vault and Storage deny public access by default, allow Azure services only
- **Input sanitization** - All API response strings are sanitized (max 1,000 chars, trimmed)
- **Security headers** - All HTTP responses include X-Content-Type-Options, X-Frame-Options, Content-Security-Policy, Strict-Transport-Security
- **Sanitized error messages** - HTTP responses expose correlation IDs, not internal error details
- **HTTPS-only** - TLS 1.2 minimum enforced on all Azure resources
- **90-day log retention** - Configured in Log Analytics for audit compliance
- **Application permissions** - Uses app-only auth (not delegated) for unattended execution

To report a security vulnerability, please open a private issue or contact the maintainers directly.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development environment setup
- Code style guidelines (PEP 8, type hints, naming conventions)
- Testing requirements
- Pull request process

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Microsoft Graph API - Attack Simulation Training](https://learn.microsoft.com/en-us/graph/api/resources/attacksimulationroot?view=graph-rest-1.0) - API reference
- [Attack simulation training in Microsoft Defender for Office 365](https://learn.microsoft.com/en-us/defender-office-365/attack-simulation-training-get-started) - Product documentation
- [Azure Functions Python Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python?tabs=get-started%2Casgi%2Capplication-level&pivots=python-mode-v2) - Runtime reference
