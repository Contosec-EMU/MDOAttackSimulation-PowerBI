# MDO Attack Simulation Training - Power BI Data Pipeline

End-to-end Azure solution to ingest Microsoft Defender for Office 365 Attack Simulation Training reporting data from Microsoft Graph into Azure Data Lake Storage Gen2, consumable by Power BI with scheduled refresh.

## Architecture Overview

```
┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Microsoft Graph │────▶│  Azure Function │────▶│  ADLS Gen2       │────▶│  Power BI   │
│  (Attack Sim API)│     │  (Timer Trigger)│     │  (Parquet)       │     │  (Refresh)  │
└──────────────────┘     └─────────────────┘     └──────────────────┘     └─────────────┘
                                │                         │
                                ▼                         │
                         ┌─────────────────┐              │
                         │    Key Vault    │              │
                         │ (Client Secret) │              │
                         └─────────────────┘              │
                                │                         │
                                ▼                         │
                         ┌─────────────────┐              │
                         │  App Insights   │◀─────────────┘
                         │  (Monitoring)   │
                         └─────────────────┘
```

## Data Sources (Graph APIs)

| API | Endpoint | Description |
|-----|----------|-------------|
| Repeat Offenders | `reports/security/getAttackSimulationRepeatOffenders` | Users who have fallen for simulations multiple times |
| Simulation User Coverage | `reports/security/getAttackSimulationSimulationUserCoverage` | Per-user simulation statistics |
| Training User Coverage | `reports/security/getAttackSimulationTrainingUserCoverage` | Per-user training completion status |

## Prerequisites

1. **Azure Subscription** with permissions to create resources
2. **Azure CLI** (v2.50+) installed and authenticated
3. **Azure Functions Core Tools** (v4.x) for local testing
4. **Entra ID App Registration** with `AttackSimulation.Read.All` permission (Application type)
5. **Power BI Pro** or Premium capacity for scheduled refresh

## Deployment Service Principal Requirements

The identity deploying this solution needs:

| Scope | Role | Purpose |
|-------|------|---------|
| Resource Group | `Contributor` | Create all Azure resources |
| Resource Group | `User Access Administrator` OR `Owner` | Create RBAC role assignments in Bicep |

## Deployment Steps

### 1. Create Entra ID App Registration

```powershell
# Login to Azure
az login

# Create app registration
$appName = "MDOAttackSimulation-GraphAPI"
$app = az ad app create --display-name $appName --query "{appId:appId, id:id}" -o json | ConvertFrom-Json

# Create service principal
az ad sp create --id $app.appId

# Add API permission: AttackSimulation.Read.All (Application)
# Permission ID for AttackSimulation.Read.All: 93283d0a-6322-4fa8-966b-8c121624760d
az ad app permission add --id $app.appId --api 00000003-0000-0000-c000-000000000000 --api-permissions 93283d0a-6322-4fa8-966b-8c121624760d=Role

# Grant admin consent (requires Global Admin or Privileged Role Admin)
az ad app permission admin-consent --id $app.appId

# Create client secret (save this securely!)
$secret = az ad app credential reset --id $app.appId --append --query password -o tsv

Write-Host "App (Client) ID: $($app.appId)"
Write-Host "Client Secret: $secret"
Write-Host "Tenant ID: $(az account show --query tenantId -o tsv)"
```

> ⚠️ **Save the Client Secret** - it's only shown once!

### 2. Create Resource Group

```bash
# Variables
SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="rg-mdo-attack-simulation"
LOCATION="eastus"

# Set subscription
az account set --subscription $SUBSCRIPTION_ID

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION
```

### 3. Update Parameters File

Edit `infra/main.bicepparam`:

```bicep
param tenantId = '<YOUR_TENANT_ID>'
param graphClientId = '<YOUR_APP_REGISTRATION_CLIENT_ID>'
```

### 4. Deploy Infrastructure

```bash
# Deploy Bicep template
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --query "properties.outputs"

# Capture outputs
KEYVAULT_NAME=$(az deployment group show -g $RESOURCE_GROUP -n main --query "properties.outputs.keyVaultName.value" -o tsv)
FUNCTION_APP_NAME=$(az deployment group show -g $RESOURCE_GROUP -n main --query "properties.outputs.functionAppName.value" -o tsv)
STORAGE_ACCOUNT_NAME=$(az deployment group show -g $RESOURCE_GROUP -n main --query "properties.outputs.storageAccountName.value" -o tsv)
```

### 5. Store Client Secret in Key Vault

```bash
# Store the Graph API client secret
az keyvault secret set \
  --vault-name $KEYVAULT_NAME \
  --name "graph-client-secret" \
  --value "<YOUR_CLIENT_SECRET>"
```

### 6. Deploy Function Code

```bash
# Navigate to function directory
cd src/function_app

# Deploy using Azure Functions Core Tools
func azure functionapp publish $FUNCTION_APP_NAME --python

# OR using zip deploy
cd src/function_app
zip -r ../function.zip .
az functionapp deployment source config-zip \
  --resource-group $RESOURCE_GROUP \
  --name $FUNCTION_APP_NAME \
  --src ../function.zip
```

### 7. Validate Deployment

```bash
# Trigger function manually for testing
FUNCTION_KEY=$(az functionapp keys list -g $RESOURCE_GROUP -n $FUNCTION_APP_NAME --query "functionKeys.default" -o tsv)

curl -X POST "https://${FUNCTION_APP_NAME}.azurewebsites.net/api/test-run?code=${FUNCTION_KEY}"

# Check logs
az monitor app-insights query \
  --app $(az deployment group show -g $RESOURCE_GROUP -n main --query "properties.outputs.appInsightsName.value" -o tsv) \
  --analytics-query "traces | where timestamp > ago(1h) | order by timestamp desc | take 50"

# Verify Parquet files exist
az storage fs file list \
  --account-name $STORAGE_ACCOUNT_NAME \
  --file-system curated \
  --recursive \
  --auth-mode login
```

## Timer Schedule Configuration

The function runs on a CRON schedule defined by `TIMER_SCHEDULE`. Default: `0 0 2 * * *` (daily at 2:00 AM UTC).

### Change Schedule

```bash
# Update via CLI
az functionapp config appsettings set \
  --resource-group $RESOURCE_GROUP \
  --name $FUNCTION_APP_NAME \
  --settings "TIMER_SCHEDULE=0 0 6 * * *"  # 6:00 AM UTC
```

### CRON Format

```
{second} {minute} {hour} {day} {month} {day-of-week}

Examples:
- 0 0 2 * * *     = Daily at 2:00 AM
- 0 0 */6 * * *   = Every 6 hours
- 0 30 9 * * 1-5  = Weekdays at 9:30 AM
- 0 0 0 1 * *     = First day of each month at midnight
```

## Output Data Structure

### Curated Container (Parquet)

```
curated/
├── repeatOffenders/
│   └── 2026-02-04/
│       └── repeatOffenders.parquet
├── simulationUserCoverage/
│   └── 2026-02-04/
│       └── simulationUserCoverage.parquet
└── trainingUserCoverage/
    └── 2026-02-04/
        └── trainingUserCoverage.parquet
```

### Raw Container (JSON Archive)

```
raw/
├── repeatOffenders/
│   └── 2026-02-04/
│       └── repeatOffenders_raw.json
├── simulationUserCoverage/
│   └── 2026-02-04/
│       └── simulationUserCoverage_raw.json
└── trainingUserCoverage/
    └── 2026-02-04/
        └── trainingUserCoverage_raw.json
```

### Schema: repeatOffenders

| Column | Type | Description |
|--------|------|-------------|
| snapshotDateUtc | string | Date of data extraction (YYYY-MM-DD) |
| userId | string | Entra ID user ID |
| displayName | string | User display name |
| email | string | User email address |
| repeatOffenceCount | int | Number of times user compromised |

### Schema: simulationUserCoverage

| Column | Type | Description |
|--------|------|-------------|
| snapshotDateUtc | string | Date of data extraction |
| userId | string | Entra ID user ID |
| displayName | string | User display name |
| email | string | User email address |
| simulationCount | int | Number of simulations received |
| latestSimulationDateTime | string | Most recent simulation date |
| clickCount | int | Number of clicks on simulation links |
| compromisedCount | int | Number of times compromised |

### Schema: trainingUserCoverage

| Column | Type | Description |
|--------|------|-------------|
| snapshotDateUtc | string | Date of data extraction |
| userId | string | Entra ID user ID |
| displayName | string | User display name |
| email | string | User email address |
| assignedTrainingsCount | int | Total trainings assigned |
| completedTrainingsCount | int | Trainings completed |
| inProgressTrainingsCount | int | Trainings in progress |
| notStartedTrainingsCount | int | Trainings not started |

## Power BI Configuration

### Connect to ADLS Gen2

1. **Open Power BI Desktop**
2. **Get Data** → **Azure** → **Azure Data Lake Storage Gen2**
3. **Enter Storage URL**: `https://<storage-account>.dfs.core.windows.net/`
4. **Sign in** with your organizational account (must have Storage Blob Data Reader on the curated container)
5. **Navigate** to `curated` → select folder (e.g., `repeatOffenders`)
6. **Combine files** to load all Parquet partitions

### Power Query (M) Example

```powerquery
let
    Source = AzureStorage.DataLake("https://mdoaststxxxxxxxxx.dfs.core.windows.net/"),
    curated = Source{[Name="curated"]}[Content],
    repeatOffenders = curated{[Name="repeatOffenders"]}[Content],
    
    // Combine all partitioned Parquet files
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(repeatOffenders, {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```

### Configure Scheduled Refresh

1. **Publish** report to Power BI Service
2. **Dataset Settings** → **Scheduled Refresh**
3. **Configure credentials**: Use OAuth2 with organizational account
4. **Set refresh schedule**: Align with Function timer (e.g., 3:00 AM if Function runs at 2:00 AM)
5. **Enable** scheduled refresh

> 💡 **Tip**: Set Power BI refresh 1 hour after Function runs to ensure data is ready.

## Validation Checklist

- [ ] Entra ID app has `AttackSimulation.Read.All` permission (Application type)
- [ ] Admin consent granted for the permission
- [ ] Client secret stored in Key Vault as `graph-client-secret`
- [ ] Function App has managed identity enabled
- [ ] Function identity has `Storage Blob Data Contributor` on storage account
- [ ] Function identity has `Key Vault Secrets User` on Key Vault
- [ ] Token acquisition successful (check App Insights logs)
- [ ] Graph API returns data (test with manual trigger)
- [ ] Parquet files appear in `curated/` container
- [ ] Power BI can connect and load data
- [ ] Power BI scheduled refresh works

## Common Errors and Fixes

### Authentication Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` | Invalid credentials | Verify tenant ID, client ID, and client secret |
| `403 Forbidden` | Missing permission | Ensure `AttackSimulation.Read.All` is granted with admin consent |
| `AADSTS700016` | App not found in tenant | Verify app registration exists and client ID is correct |

### Storage Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `403 AuthorizationPermissionMismatch` | Missing RBAC | Grant `Storage Blob Data Contributor` to Function identity |
| `ContainerNotFound` | Container doesn't exist | Check Bicep deployment created containers |

### Key Vault Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `403 Forbidden` | Missing RBAC | Grant `Key Vault Secrets User` to Function identity |
| `SecretNotFound` | Secret doesn't exist | Run `az keyvault secret set` command |

### Pagination Issues

| Error | Cause | Fix |
|-------|-------|-----|
| Incomplete data | Pagination not handled | Code handles `@odata.nextLink` automatically; check logs for errors |
| Timeout | Large dataset | Function timeout is 10 min; increase if needed |

### Power BI Issues

| Error | Cause | Fix |
|-------|-------|-----|
| Cannot connect to ADLS | Wrong URL or auth | Use `dfs` endpoint, not `blob`; verify OAuth credentials |
| Refresh fails | Gateway needed | For Premium, direct connect works; for Pro, may need On-Premises Data Gateway |
| No data | Wrong path | Verify container/folder paths in Power Query |

## Local Development

```bash
# Install dependencies
cd src/function_app
pip install -r requirements.txt

# Copy and edit local settings
cp local.settings.json.example local.settings.json
# Edit with your values

# Run locally
func start
```

## Monitoring

### Application Insights Queries

```kusto
// Function execution summary
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

## Cost Estimate (Monthly)

| Resource | SKU | Est. Cost |
|----------|-----|-----------|
| Function App | Consumption | ~$0-5 (depends on executions) |
| Storage (ADLS Gen2) | Hot tier, <1GB | ~$0.50 |
| Key Vault | Standard | ~$0.03/10k operations |
| App Insights | Pay-as-you-go | ~$2-5 |
| **Total** | | **~$5-15/month** |

## Recent Updates

### Performance and Reliability Improvements
- **Parquet output format**: Optimized for Power BI with Snappy compression, explicit data types, and INT64 timestamps
- **Retry logic with exponential backoff**: Handles transient failures in Graph API calls and storage uploads
- **Jitter added to backoff**: Reduces thundering herd problem when retrying
- **Container auto-creation**: Function automatically creates storage containers if missing
- **Pagination safety**: Max 1000 pages per API to prevent infinite loops

### Security Enhancements
- **Input sanitization**: All API response strings are sanitized (max 1000 chars, trimmed)
- **Network ACLs**: Key Vault and Storage deny public access by default, allow Azure services only
- **Security headers**: All HTTP responses include X-Content-Type-Options, X-Frame-Options, CSP, HSTS, XSS protection
- **Sanitized error messages**: HTTP responses don't expose internal error details (use correlation IDs for log lookup)
- **90-day log retention**: Configured in Log Analytics for compliance
- **RBAC-only Key Vault**: No access policies, only RBAC authorization

### Operational Improvements
- **Environment variable validation**: Function fails fast if required variables are missing
- **Token refresh buffer**: Refresh OAuth tokens 60s before expiration to avoid auth failures
- **Connection pooling**: Reuses HTTP connections for Graph API calls
- **Correlation IDs**: All manual test runs get unique correlation IDs for tracing

## Security Considerations

- ✅ No secrets in code (Key Vault integration with managed identity)
- ✅ Managed identity for Azure service authentication (no keys)
- ✅ HTTPS-only enforcement for storage and Function
- ✅ No public blob access on any containers
- ✅ RBAC authorization on Key Vault (access policies disabled)
- ✅ Network ACLs on Key Vault and Storage (deny by default, allow Azure services)
- ✅ Application permissions (not delegated) for unattended execution
- ✅ Input sanitization on all API response data
- ✅ Security headers on all HTTP responses (X-Content-Type-Options, X-Frame-Options, CSP, HSTS)
- ✅ Sanitized error messages (no internal details exposed to clients)
- ✅ 90-day log retention in Log Analytics for audit compliance
- ✅ Minimum TLS 1.2 enforced on all Azure resources

## License

MIT
