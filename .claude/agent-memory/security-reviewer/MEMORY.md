# Security Review Memory - MDO Attack Simulation PowerBI Project

## Project Architecture
- **Type**: Azure Functions-based data pipeline
- **Purpose**: Ingest Microsoft Graph Attack Simulation Training data to ADLS Gen2 for Power BI
- **Authentication**: OAuth2 client credentials flow for Graph API
- **Secrets Management**: Azure Key Vault with managed identity
- **Storage**: Azure Data Lake Storage Gen2 (ADLS)
- **Infrastructure**: Bicep IaC deployment

## Key Security Observations

### Authentication Patterns
- Uses managed identity (System Assigned) for Azure resource access
- OAuth2 client credentials flow for Microsoft Graph API
- DefaultAzureCredential pattern for Key Vault and Storage authentication
- Client secret stored in Key Vault (graph-client-secret)

### Secrets Management
- **Good**: Key Vault used for Graph client secret storage
- **Issue**: Client secret printed to console in PowerShell script (create-app-registration.ps1 line 83)
- **Issue**: Bicep template exposes storage account key in app settings (line 193)
- **Issue**: local.settings.json committed to repo with placeholder values

### Infrastructure Security
- **Good**: HTTPS enforced, TLS 1.2 minimum
- **Good**: RBAC used for Function App permissions
- **Good**: Blob public access disabled
- **FIXED**: Health check endpoint now requires authentication (AuthLevel.FUNCTION)
- **FIXED**: Security headers added to all HTTP responses (X-Content-Type-Options, X-Frame-Options, HSTS, CSP)
- **FIXED**: Environment variable validation at startup
- **Issue**: Network ACLs set to "Allow" from all networks (line 106)
- **Issue**: Key Vault and App Insights have public network access enabled

### Input Validation
- **FIXED**: String sanitization added (max length, trimming)
- Direct dictionary access with .get() but no type checking on numeric fields
- No validation of Graph API response structure

### Error Handling
- **FIXED**: Correlation IDs implemented for request tracking
- **FIXED**: Generic error messages returned to clients
- Full exception details logged server-side with exc_info=True

### Dependencies
- All Azure SDK versions appear current (azure-identity 1.15.0, etc.)
- requests library version 2.31.0 (check for known vulnerabilities)

## Common Vulnerability Patterns
1. Secrets in logs/console output
2. Overly permissive network access
3. Missing input validation on external API data
4. Anonymous endpoints exposing functionality
5. Verbose error messages in production
