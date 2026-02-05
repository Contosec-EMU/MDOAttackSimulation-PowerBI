# API Integration Memory - MDO Attack Simulation Power BI

## Project Overview
Azure Functions timer-triggered pipeline that ingests Microsoft Defender for Office 365 Attack Simulation Training data from Microsoft Graph API into Azure Data Lake Storage Gen2 for Power BI consumption.

## Key Integration Patterns

### Authentication
- **OAuth2 Client Credentials Flow**: Used for Microsoft Graph API (service-to-service, no user context)
- **Managed Identity**: Used for Azure SDK clients (Key Vault, ADLS Gen2)
- Token caching with 60-second buffer before expiry
- **NEW**: Token auto-refresh on 401 responses (prevents auth failures from clock skew)

### HTTP Client
- Uses `requests` library (not Azure SDK's GraphServiceClient)
- Custom `GraphAPIClient` class wraps Graph API calls
- **NEW**: Connection pooling enabled via `requests.Session()` (reduces latency)

### API Endpoints
- `/reports/security/getAttackSimulationRepeatOffenders`
- `/reports/security/getAttackSimulationSimulationUserCoverage`
- `/reports/security/getAttackSimulationTrainingUserCoverage`

### Error Handling Patterns
- Retry with exponential backoff: 0s, 5s, 10s (fixed multiplier)
- 429 rate limiting: Respects Retry-After header
- Timeout: 30 seconds for all requests (including token acquisition)
- **NEW**: JSON parsing errors caught and logged with response preview
- **NEW**: Pagination safety limit (1000 pages max) prevents infinite loops
- **NEW**: Input sanitization on all user fields (max 1000 chars, whitespace stripped)

## Recent Improvements (2026-02-04)
See `reliability-improvements.md` for full details on:
1. Connection pooling implementation
2. Token timeout and auto-refresh on 401
3. JSON response validation
4. Pagination safety limits
5. Input sanitization

## Configuration
- Credentials from Key Vault (client secret)
- Environment variables for tenant/client IDs
- Function timeout: 10 minutes
- Timer schedule: CRON-based (default 2 AM UTC daily)
