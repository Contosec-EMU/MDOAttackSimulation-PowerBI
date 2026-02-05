# MDO Attack Simulation - AI Assistant Project Brief

This document helps AI coding assistants (Claude Code, GitHub Copilot, Cursor) understand this project quickly.

## Project Overview

Azure Function that ingests Microsoft Defender for Office 365 Attack Simulation Training data from Microsoft Graph API into Azure Data Lake Storage Gen2 as Parquet files, optimized for Power BI consumption.

## Tech Stack

- **Runtime**: Azure Functions v4, Python 3.11 (Linux)
- **Infrastructure**: Bicep (Infrastructure as Code)
- **Storage**: Azure Data Lake Storage Gen2 (ADLS Gen2) with hierarchical namespace
- **Data Format**: Parquet (curated), JSON (raw archive)
- **Authentication**: Managed Identity + Azure Key Vault
- **Monitoring**: Application Insights + Log Analytics (90-day retention)
- **APIs**: Microsoft Graph API (Attack Simulation Training endpoints)

## Directory Structure

```
C:\repos\MDOAttackSimulation_PowerBI\
├── infra/
│   ├── main.bicep            # Azure infrastructure definition
│   └── main.bicepparam       # Deployment parameters (update tenant/client IDs)
├── src/
│   └── function_app/
│       ├── function_app.py   # Main function code (timer + HTTP endpoints)
│       ├── requirements.txt  # Python dependencies
│       ├── host.json        # Function runtime config (10 min timeout)
│       └── local.settings.json # Local dev config (gitignored)
├── README.md                # Complete deployment guide
├── CONTRIBUTING.md          # Development setup and guidelines
└── CLAUDE.md               # This file
```

## Key Files and Their Purpose

### `src/function_app/function_app.py` (570 lines)
Main application logic:
- **GraphAPIClient**: Handles OAuth2 authentication, pagination, retry logic with exponential backoff
- **ADLSWriter**: Writes Parquet (curated) and JSON (raw) to ADLS Gen2 with retry logic
- **Processors**: Transform Graph API responses into flat schemas for Power BI
- **Endpoints**:
  - `mdo_attack_simulation_ingest` (timer trigger): Main ingestion job
  - `/api/health` (GET): Health check
  - `/api/test-run` (POST): Manual trigger for testing

### `infra/main.bicep` (285 lines)
Creates all Azure resources:
- Function App (Basic B1, Linux) with system-assigned managed identity
- ADLS Gen2 account with network ACLs (deny by default, allow Azure services)
- Key Vault with network ACLs and RBAC authorization
- App Insights + Log Analytics (90-day retention)
- RBAC assignments (Storage Blob Data Contributor, Key Vault Secrets User)

### `infra/main.bicepparam`
Must update before deployment:
- `tenantId`: Your Entra ID tenant ID
- `graphClientId`: App registration client ID
- `timerSchedule`: CRON schedule (default: daily at 2:00 AM UTC)

## Important Patterns and Conventions

### Data Flow
1. Timer triggers function (default: 2:00 AM UTC daily)
2. Fetch Graph API token using client credentials flow (secret from Key Vault)
3. Paginate through 3 API endpoints (repeat offenders, simulation coverage, training coverage)
4. Write to two containers:
   - `curated/{api_name}/{YYYY-MM-DD}/{api_name}.parquet` (for Power BI)
   - `raw/{api_name}/{YYYY-MM-DD}/{api_name}_raw.json` (archival)

### Security Patterns
- **No secrets in code**: Graph API client secret stored in Key Vault
- **Managed Identity**: Function authenticates to Key Vault and Storage using managed identity (no keys)
- **Network ACLs**: Key Vault and Storage deny by default, allow Azure services only
- **Input sanitization**: All string fields from API are sanitized (max 1000 chars, trimmed)
- **Security headers**: All HTTP responses include X-Content-Type-Options, X-Frame-Options, CSP, HSTS
- **Sanitized errors**: HTTP responses don't expose internal error details (correlation IDs for log lookup)

### Retry Logic
- **Graph API**: 3 retries with exponential backoff + jitter (base 5s), handles 429 rate limiting
- **Storage uploads**: 3 retries with exponential backoff (base 2s) + jitter
- **Token refresh**: Auto-refreshes 60s before expiration, retries on 401

### Schema Optimization for Power BI
- Parquet with Snappy compression
- INT64 timestamps (not deprecated INT96)
- Explicit data types: datetime64, int32 for counts, string for text
- Flat schemas (no nested objects)
- Column naming: camelCase matching Graph API convention

## Common Tasks

### Deploy Infrastructure
```bash
cd infra
# Update main.bicepparam first
az deployment group create \
  --resource-group rg-mdo-attack-simulation \
  --template-file main.bicep \
  --parameters main.bicepparam
```

### Deploy Function Code
```bash
cd src/function_app
func azure functionapp publish <function-app-name> --python
```

### Store Client Secret
```bash
az keyvault secret set \
  --vault-name <keyvault-name> \
  --name "graph-client-secret" \
  --value "<secret-value>"
```

### Trigger Manual Test Run
```bash
FUNCTION_KEY=$(az functionapp keys list -g <rg> -n <func-name> --query "functionKeys.default" -o tsv)
curl -X POST "https://<func-name>.azurewebsites.net/api/test-run?code=${FUNCTION_KEY}"
```

### View Logs
```kusto
// Recent function executions
traces
| where operation_Name == "mdo_attack_simulation_ingest"
| where timestamp > ago(24h)
| order by timestamp desc

// Errors only
exceptions
| where timestamp > ago(24h)
| order by timestamp desc
```

## Testing Instructions

### Local Development
1. Copy `local.settings.json.example` to `local.settings.json`
2. Fill in required values (TENANT_ID, GRAPH_CLIENT_ID, etc.)
3. Store Graph API secret locally or point to dev Key Vault
4. Run: `func start` from `src/function_app/`
5. Trigger: POST to `http://localhost:7071/api/test-run`

### Validation After Deployment
1. Check managed identity assigned: `az functionapp identity show`
2. Verify RBAC on storage: Function should have Storage Blob Data Contributor
3. Verify RBAC on Key Vault: Function should have Key Vault Secrets User
4. Verify secret exists: `az keyvault secret show --name graph-client-secret`
5. Trigger test run via `/api/test-run` endpoint
6. Check logs in App Insights for errors
7. Verify Parquet files in `curated/` container
8. Test Power BI connection to ADLS Gen2

## Deployment Commands Summary

```bash
# 1. Create app registration (with AttackSimulation.Read.All permission)
az ad app create --display-name "MDOAttackSimulation-GraphAPI"
az ad app permission add --api 00000003-0000-0000-c000-000000000000 --api-permissions 93283d0a-6322-4fa8-966b-8c121624760d=Role
az ad app permission admin-consent

# 2. Deploy infrastructure
az deployment group create \
  --resource-group rg-mdo-attack-simulation \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam

# 3. Store secret
az keyvault secret set --vault-name <kv-name> --name "graph-client-secret" --value "<secret>"

# 4. Deploy function code
cd src/function_app && func azure functionapp publish <func-name> --python
```

## Known Issues and Gotchas

1. **Output path structure**: Code writes to `{api_name}/{snapshot_date}/{api_name}.parquet`, NOT `dt=2026-02-04/data.parquet`
2. **Test endpoint is POST**: Use `curl -X POST`, not GET
3. **Container auto-creation**: Function creates containers if missing (no manual creation needed)
4. **B1 plan required**: Using Basic B1 instead of Consumption for reliability
5. **Linux-only**: Python functions on Azure require Linux plan
6. **Network ACLs**: Key Vault and Storage block public access (Function accesses via managed identity + Azure backbone)
7. **Pagination safety**: Max 1000 pages per API to prevent infinite loops
8. **Token caching**: Access token cached and reused until 60s before expiration
9. **Large string truncation**: API response strings truncated at 1000 chars with warning logged
10. **Training coverage aggregation**: `trainingUserCoverage` API returns array of trainings, function aggregates counts by status

## Links to Other Docs

- [README.md](./README.md) - Complete deployment guide with architecture, prerequisites, and troubleshooting
- [CONTRIBUTING.md](./CONTRIBUTING.md) - Development setup, code style, and PR process
- [Microsoft Graph API - Attack Simulation Training](https://learn.microsoft.com/en-us/graph/api/resources/security-attacksimulation-overview)
- [Azure Functions Python Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python)
- [Power BI ADLS Gen2 Connector](https://learn.microsoft.com/en-us/power-bi/connect-data/service-azure-data-lake-storage-gen2)

## Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `TENANT_ID` | Yes | Entra ID tenant ID | `12345678-1234-...` |
| `GRAPH_CLIENT_ID` | Yes | App registration client ID | `87654321-4321-...` |
| `KEY_VAULT_URL` | Yes | Key Vault URI | `https://kv-name.vault.azure.net/` |
| `STORAGE_ACCOUNT_URL` | Yes | ADLS Gen2 DFS endpoint | `https://storageacct.dfs.core.windows.net/` |
| `TIMER_SCHEDULE` | Yes | CRON schedule | `0 0 2 * * *` (daily 2 AM) |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Yes | App Insights connection string | Auto-configured by Bicep |
| `AzureWebJobsStorage` | Yes | Function storage connection string | Auto-configured by Bicep |

## Quick Reference: Graph API Endpoints

| API Name | Endpoint | Output Schema |
|----------|----------|---------------|
| repeatOffenders | `reports/security/getAttackSimulationRepeatOffenders` | userId, displayName, email, repeatOffenceCount |
| simulationUserCoverage | `reports/security/getAttackSimulationSimulationUserCoverage` | userId, displayName, email, simulationCount, latestSimulationDateTime, clickCount, compromisedCount |
| trainingUserCoverage | `reports/security/getAttackSimulationTrainingUserCoverage` | userId, displayName, email, assignedTrainingsCount, completedTrainingsCount, inProgressTrainingsCount, notStartedTrainingsCount |

All schemas include `snapshotDateUtc` column (YYYY-MM-DD format).
