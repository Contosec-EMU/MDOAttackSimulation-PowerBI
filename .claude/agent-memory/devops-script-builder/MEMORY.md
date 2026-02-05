# MDO Attack Simulation PowerBI - DevOps Memory

## Project Architecture
- **Type**: Azure Functions-based data ingestion pipeline
- **Purpose**: Fetches Microsoft Defender attack simulation data via Graph API, stores in ADLS Gen2 for Power BI
- **Stack**: Python 3.11, Azure Functions v4, Bicep IaC
- **Deployment**: Dual scripts (PowerShell + Bash) for cross-platform support

## Infrastructure Components (Bicep)
- Storage: Separate accounts for Function App (standard) and Data Lake (ADLS Gen2 with HNS)
- Containers: `raw` (JSON), `curated` (Parquet for Power BI)
- Compute: Basic B1 App Service Plan (Linux)
- Security: Key Vault with RBAC, Managed Identity for Function App
- Monitoring: App Insights + Log Analytics workspace

## Known Issues Fixed
1. **Bash script output parsing bug**: Script references `storageAccountName` but Bicep outputs `dataLakeAccountName`
2. **Missing Parquet support**: requirements.txt lacks `pyarrow` - critical for Power BI integration
3. **Secret exposure**: Both scripts handle secrets insecurely (plaintext, command args)

## Security Patterns
- RBAC preferred over access keys (Storage Blob Data Contributor, Key Vault Secrets User)
- Managed Identity for Function App authentication
- Graph API auth: App registration with AttackSimulation.Read.All permission

## Deployment Dependencies
- Azure CLI
- Azure Functions Core Tools (`func`)
- jq (bash script only)
- PowerShell 5.1+ or Core (for PS script)

## Common Pitfalls
- Network security defaults to wide-open (defaultAction: Allow)
- No diagnostic logging configured by default
- Soft delete retention minimal (7 days)
- Scripts lack idempotency - fail on re-runs
