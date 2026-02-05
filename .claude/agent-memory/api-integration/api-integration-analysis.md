# API Integration Analysis - MDO Attack Simulation Power BI

**Date**: 2026-02-04
**Analyzed File**: `C:\repos\MDOAttackSimulation_PowerBI\src\function_app\function_app.py`

## Executive Summary

The project implements a basic but functional integration with Microsoft Graph API, Azure Key Vault, and ADLS Gen2. While the core OAuth2 client credentials flow is correctly implemented, there are **several critical issues** around error handling, retry logic, connection management, and observability that should be addressed for production reliability.

**Overall Grade**: C+ (Functional but needs hardening)

---

## Detailed Analysis

### 1. OAuth2 Implementation: ✅ PASS (with minor issues)

#### Correct Implementation
- **Client credentials flow** properly implemented (lines 46-66)
- Uses correct token endpoint: `https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token`
- Correct grant_type: `client_credentials`
- Correct scope: `https://graph.microsoft.com/.default`
- Token caching with expiration tracking

#### Issues & Recommendations

**ISSUE 1: No token refresh error handling**
```python
response = requests.post(token_url, data=data)
response.raise_for_status()  # Line 60
```

**Problem**: If token acquisition fails (network issue, credential expiry, service outage), the entire function fails without retry.

**Recommendation**:
```python
def _get_access_token(self) -> str:
    """Get OAuth2 access token using client credentials flow."""
    if self._access_token and time.time() < self._token_expires - 60:
        return self._access_token

    max_retries = 3
    for attempt in range(max_retries):
        try:
            token_url = self.TOKEN_URL.format(tenant_id=self.tenant_id)
            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default"
            }

            response = requests.post(token_url, data=data, timeout=30)
            response.raise_for_status()

            token_data = response.json()
            self._access_token = token_data["access_token"]
            self._token_expires = time.time() + token_data.get("expires_in", 3600)

            logger.info("Successfully acquired access token")
            return self._access_token

        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed to acquire token after {max_retries} attempts: {e}")
                raise
            wait_time = (2 ** attempt) * 2
            logger.warning(f"Token acquisition failed (attempt {attempt + 1}): {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
```

**ISSUE 2: No timeout on token request**

Line 59 has no timeout, which could hang indefinitely.

**Recommendation**: Add `timeout=30` parameter.

**ISSUE 3: Token buffer too aggressive**

60-second buffer (line 48) is reasonable, but consider making it configurable or using 5 minutes for high-volume scenarios to avoid unnecessary token refreshes.

---

### 2. Token Management: ⚠️ NEEDS IMPROVEMENT

#### Current State
- Token cached in instance variable (lines 43-44)
- Expiration checked before each token use
- 60-second safety buffer

#### Issues & Recommendations

**ISSUE 4: No token invalidation on 401 errors**

If a token becomes invalid (revoked, policy change), the code doesn't detect and refresh.

**Recommendation**: Add token invalidation in `_make_request`:
```python
def _make_request(self, url: str, retries: int = 3) -> dict:
    """Make HTTP GET request with retry logic."""
    for attempt in range(retries):
        try:
            headers = {
                "Authorization": f"Bearer {self._get_access_token()}",
                "Content-Type": "application/json"
            }

            response = requests.get(url, headers=headers, timeout=30)

            # Handle 401 by invalidating token
            if response.status_code == 401:
                logger.warning("Received 401 Unauthorized, invalidating token")
                self._access_token = None
                self._token_expires = 0
                if attempt < retries - 1:
                    continue  # Retry with fresh token

            # ... rest of logic
```

**ISSUE 5: Thread-safety concerns**

If Azure Functions scales out or uses threading (unlikely in this code, but worth noting), token caching isn't thread-safe. The `GraphAPIClient` instance is created per function invocation, so this is likely fine for current usage.

---

### 3. Pagination: ✅ MOSTLY CORRECT

#### Current Implementation (lines 97-111)
```python
def get_paginated_data(self, endpoint: str) -> Generator[dict, None, None]:
    """Fetch all pages of data from a Graph API endpoint."""
    url = f"{self.GRAPH_BASE_URL}/{endpoint}"

    while url:
        logger.info(f"Fetching: {url[:100]}...")
        data = self._make_request(url)

        for item in data.get("value", []):
            yield item

        url = data.get("@odata.nextLink")

        if url:
            time.sleep(0.5)
```

#### Issues & Recommendations

**ISSUE 6: No pagination safety limits**

If the API returns millions of records or has a pagination bug (circular links), this could run indefinitely.

**Recommendation**: Add max page limit:
```python
def get_paginated_data(self, endpoint: str, max_pages: int = 1000) -> Generator[dict, None, None]:
    """Fetch all pages of data from a Graph API endpoint."""
    url = f"{self.GRAPH_BASE_URL}/{endpoint}"
    page_count = 0

    while url:
        page_count += 1
        if page_count > max_pages:
            logger.error(f"Exceeded max pages ({max_pages}). Possible pagination loop or unexpectedly large dataset.")
            raise RuntimeError(f"Pagination limit exceeded: {max_pages} pages")

        logger.info(f"Fetching page {page_count}: {url[:100]}...")
        data = self._make_request(url)

        for item in data.get("value", []):
            yield item

        url = data.get("@odata.nextLink")

        if url:
            time.sleep(0.5)  # Consider making this configurable
```

**ISSUE 7: Fixed 0.5s sleep between pages**

This is reasonable for rate limiting, but may be too conservative for small datasets or too aggressive for strict rate limits.

**Recommendation**: Make configurable or remove if not needed (Graph API has generous limits for reporting endpoints).

**ISSUE 8: Empty response handling**

If `data` is `None` or doesn't have "value" key, the code handles it gracefully with `.get("value", [])`, which is good. However, no logging of empty pages.

---

### 4. Retry Logic: ⚠️ NEEDS IMPROVEMENT

#### Current Implementation (lines 75-94)
```python
for attempt in range(retries):
    try:
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            continue

        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        if attempt == retries - 1:
            raise
        wait_time = (2 ** attempt) * 5
        logger.warning(f"Request failed (attempt {attempt + 1}): {e}. Retrying in {wait_time}s...")
        time.sleep(wait_time)
```

#### Issues & Recommendations

**ISSUE 9: 429 handling doesn't count against retry budget**

The 429 handling uses `continue` (line 83), which doesn't increment the retry counter. This is actually GOOD behavior, but should be documented.

**ISSUE 10: No jitter in backoff**

Fixed exponential backoff without jitter can cause thundering herd if multiple instances retry simultaneously.

**Recommendation**:
```python
import random

# In _make_request:
wait_time = (2 ** attempt) * 5
jitter = random.uniform(0, wait_time * 0.1)  # 0-10% jitter
total_wait = wait_time + jitter
logger.warning(f"Request failed (attempt {attempt + 1}): {e}. Retrying in {total_wait:.2f}s...")
time.sleep(total_wait)
```

**ISSUE 11: Doesn't distinguish retryable vs non-retryable errors**

All `RequestException` errors are retried, including 400 Bad Request, 403 Forbidden, etc., which will never succeed.

**Recommendation**:
```python
def _make_request(self, url: str, retries: int = 3) -> dict:
    """Make HTTP GET request with retry logic."""
    headers = {
        "Authorization": f"Bearer {self._get_access_token()}",
        "Content-Type": "application/json"
    }

    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)

            # Handle rate limiting (429)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                continue

            # Handle 401 by invalidating token
            if response.status_code == 401:
                logger.warning("Received 401 Unauthorized, invalidating token")
                self._access_token = None
                self._token_expires = 0
                if attempt < retries - 1:
                    continue

            # Don't retry client errors (except 401, 429)
            if 400 <= response.status_code < 500 and response.status_code not in [401, 429]:
                logger.error(f"Client error {response.status_code}: {response.text}")
                response.raise_for_status()

            # Retry server errors (5xx) and network issues
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout as e:
            if attempt == retries - 1:
                logger.error(f"Request timed out after {retries} attempts")
                raise
            wait_time = (2 ** attempt) * 5
            logger.warning(f"Request timeout (attempt {attempt + 1}): {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)

        except requests.exceptions.RequestException as e:
            if attempt == retries - 1:
                raise
            wait_time = (2 ** attempt) * 5
            logger.warning(f"Request failed (attempt {attempt + 1}): {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)

    return {}
```

**ISSUE 12: Hardcoded retry count**

`retries=3` is hardcoded. Consider making configurable via environment variable.

---

### 5. Rate Limiting: ✅ GOOD (with enhancement opportunities)

#### Current Implementation
- 429 handling respects `Retry-After` header (line 80)
- Falls back to 60 seconds if header missing (reasonable)
- 0.5s sleep between pagination requests (line 111)

#### Recommendations

**ENHANCEMENT 1: Log rate limit events for monitoring**
```python
if response.status_code == 429:
    retry_after = int(response.headers.get("Retry-After", 60))
    logger.warning(f"Rate limited on {url}. Waiting {retry_after} seconds. Headers: {response.headers}")
    # Consider emitting custom metric for Azure Monitor
    time.sleep(retry_after)
    continue
```

**ENHANCEMENT 2: Proactive rate limiting**

Microsoft Graph has throttling limits. Consider adding a token bucket or sliding window to prevent hitting limits in the first place. For this use case (nightly batch), current approach is likely sufficient.

---

### 6. Error Handling: ❌ CRITICAL ISSUES

#### Issues & Recommendations

**ISSUE 13: No response validation**

Lines 86, 139 assume JSON responses are well-formed. If Graph API returns HTML error page or malformed JSON, `response.json()` will fail.

**Recommendation**:
```python
try:
    response.raise_for_status()
    return response.json()
except requests.exceptions.JSONDecodeError as e:
    logger.error(f"Invalid JSON response from {url}: {response.text[:500]}")
    raise ValueError(f"API returned invalid JSON: {e}")
```

**ISSUE 14: Silent failures in main function**

Lines 292-294 catch ALL exceptions, log them, and re-raise. This is good, but doesn't provide actionable context.

**Recommendation**: Add structured logging with context:
```python
except KeyError as e:
    logger.error(f"Missing required environment variable: {e}", exc_info=True)
    raise
except requests.exceptions.RequestException as e:
    logger.error(f"Graph API request failed: {e}", exc_info=True)
    raise
except Exception as e:
    logger.error(f"Unexpected error during ingestion: {type(e).__name__}: {str(e)}", exc_info=True)
    raise
```

**ISSUE 15: No timeout on ADLS write operations**

Line 139 `file_client.upload_data()` has no timeout. Large files could hang.

**Recommendation**: Azure SDK clients should have timeout configured:
```python
self.service_client = DataLakeServiceClient(
    account_url=account_url,
    credential=credential,
    connection_timeout=30,
    read_timeout=300  # 5 minutes for large uploads
)
```

**ISSUE 16: Key Vault call has no error handling**

Lines 145-150 assume Key Vault is always available. If managed identity isn't configured or secret doesn't exist, function crashes without helpful context.

**Recommendation**:
```python
def get_key_vault_secret(vault_url: str, secret_name: str) -> str:
    """Retrieve secret from Key Vault using managed identity."""
    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)
        secret = client.get_secret(secret_name)
        logger.info(f"Successfully retrieved secret '{secret_name}' from Key Vault")
        return secret.value
    except Exception as e:
        logger.error(f"Failed to retrieve secret '{secret_name}' from {vault_url}: {e}", exc_info=True)
        raise RuntimeError(f"Key Vault error: {e}") from e
```

**ISSUE 17: No data validation**

Processing functions (lines 164-212) assume all fields exist. If Graph API changes schema, silent data corruption occurs.

**Recommendation**: Add basic validation:
```python
def flatten_attack_user(user_detail: dict) -> dict:
    """Flatten attackSimulationUser nested structure."""
    if not user_detail:
        logger.warning("Empty user detail received")
        return {"userId": None, "displayName": None, "email": None}

    required_fields = ["userId", "email"]
    missing_fields = [f for f in required_fields if f not in user_detail]
    if missing_fields:
        logger.warning(f"User detail missing fields: {missing_fields}. Data: {user_detail}")

    return {
        "userId": user_detail.get("userId"),
        "displayName": user_detail.get("displayName"),
        "email": user_detail.get("email")
    }
```

---

### 7. Connection Management: ⚠️ NEEDS IMPROVEMENT

#### Issues & Recommendations

**ISSUE 18: No connection pooling**

The `requests` library creates a new connection for every request by default. For paginated APIs with many pages, this is inefficient.

**Recommendation**: Use a `Session` object:
```python
class GraphAPIClient:
    """Client for Microsoft Graph API with pagination and retry support."""

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: Optional[str] = None
        self._token_expires: float = 0

        # Create session for connection pooling
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=0  # We handle retries manually
        )
        self.session.mount("https://", adapter)

    def _make_request(self, url: str, retries: int = 3) -> dict:
        # Use self.session.get() instead of requests.get()
        response = self.session.get(url, headers=headers, timeout=30)
        # ... rest of logic
```

**ISSUE 19: No cleanup/close of connections**

Azure SDK clients and requests sessions should be closed properly.

**Recommendation**: Implement context manager or cleanup:
```python
def __del__(self):
    """Cleanup resources."""
    if hasattr(self, 'session'):
        self.session.close()
```

Or use within context manager in main function:
```python
with GraphAPIClient(tenant_id, client_id, client_secret) as graph_client:
    # ... use client
```

---

## Additional Recommendations

### 8. Observability & Logging

**ISSUE 20: Insufficient structured logging**

Current logging is basic strings. Application Insights can ingest custom dimensions for better querying.

**Recommendation**:
```python
logger.info("Fetched records", extra={
    "custom_dimensions": {
        "api_name": api_name,
        "record_count": len(raw_data),
        "snapshot_date": snapshot_date,
        "endpoint": api_config["endpoint"]
    }
})
```

**ISSUE 21: No performance metrics**

Track API latency, data volume, and success rates.

**Recommendation**:
```python
import time

def _make_request(self, url: str, retries: int = 3) -> dict:
    start_time = time.time()
    try:
        # ... existing logic
        response = self.session.get(url, headers=headers, timeout=30)
        duration = time.time() - start_time

        logger.info(f"API request completed", extra={
            "custom_dimensions": {
                "url": url[:100],
                "status_code": response.status_code,
                "duration_ms": duration * 1000,
                "response_size_bytes": len(response.content)
            }
        })
        # ... rest
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API request failed after {duration:.2f}s", exc_info=True)
        raise
```

**ISSUE 22: Sensitive data logging**

Line 102 logs URLs which may contain query parameters. Ensure no sensitive data (tokens, secrets) are logged.

Current code is safe (only logs first 100 chars), but be cautious with future changes.

### 9. Configuration Management

**ISSUE 23: Hardcoded values**

- Retry count: 3 (line 68, 75)
- Timeout: 30 seconds (line 77)
- Pagination sleep: 0.5 seconds (line 111)
- Token buffer: 60 seconds (line 48)

**Recommendation**: Move to environment variables or config class:
```python
class Config:
    GRAPH_RETRY_COUNT = int(os.getenv("GRAPH_RETRY_COUNT", "3"))
    GRAPH_TIMEOUT_SECONDS = int(os.getenv("GRAPH_TIMEOUT_SECONDS", "30"))
    GRAPH_PAGINATION_SLEEP = float(os.getenv("GRAPH_PAGINATION_SLEEP", "0.5"))
    TOKEN_REFRESH_BUFFER = int(os.getenv("TOKEN_REFRESH_BUFFER", "60"))
```

### 10. Testing Considerations

**ISSUE 24: No testability**

The `GraphAPIClient` and `ADLSWriter` classes are tightly coupled to external services with no abstraction layer.

**Recommendation**: Add interfaces/protocols for mocking:
```python
from typing import Protocol

class SecretProvider(Protocol):
    def get_secret(self, secret_name: str) -> str: ...

class StorageWriter(Protocol):
    def write_json(self, container: str, path: str, data: list) -> int: ...
```

Then modify main function to accept these as parameters for easier unit testing.

---

## Security Analysis

### Strengths
- ✅ Secrets stored in Key Vault (not in code)
- ✅ Managed identity for Azure services (no credential management)
- ✅ HTTPS enforced for all API calls
- ✅ No logging of sensitive data

### Concerns
- ⚠️ Client secret retrieved at runtime (line 259) - ensure Key Vault RBAC is properly configured
- ⚠️ No encryption at rest validation for ADLS (should be enabled in Bicep)
- ⚠️ DefaultAzureCredential tries multiple credential types - consider using ManagedIdentityCredential explicitly in production for faster auth and clearer intent

---

## Priority Fixes

### P0 (Critical - Fix Before Production)
1. **Add response JSON validation** (ISSUE 13)
2. **Implement connection pooling** (ISSUE 18)
3. **Add retryable vs non-retryable error detection** (ISSUE 11)
4. **Add pagination safety limits** (ISSUE 6)

### P1 (High - Fix Soon)
5. **Add token refresh error handling** (ISSUE 1)
6. **Add timeout to token acquisition** (ISSUE 2)
7. **Add 401 token invalidation** (ISSUE 4)
8. **Add structured logging with custom dimensions** (ISSUE 20)
9. **Add Key Vault error handling** (ISSUE 16)

### P2 (Medium - Improve Over Time)
10. **Add jitter to exponential backoff** (ISSUE 10)
11. **Make retry/timeout configurable** (ISSUE 23)
12. **Add data validation** (ISSUE 17)
13. **Add performance metrics** (ISSUE 21)

### P3 (Low - Nice to Have)
14. **Add testability interfaces** (ISSUE 24)
15. **Optimize token refresh buffer** (ISSUE 3)
16. **Add proactive rate limiting** (ENHANCEMENT 2)

---

## Comparison to Best Practices

| Best Practice | Status | Notes |
|---------------|--------|-------|
| OAuth2 implemented correctly | ✅ | Client credentials flow correct |
| Token caching | ✅ | With expiration tracking |
| Token refresh on 401 | ❌ | Not implemented |
| Pagination handled | ✅ | Follows @odata.nextLink |
| Pagination limits | ❌ | No max page protection |
| Retry with exponential backoff | ⚠️ | Implemented but no jitter |
| Retryable vs non-retryable errors | ❌ | All errors retried |
| 429 rate limit handling | ✅ | Respects Retry-After |
| Timeouts configured | ⚠️ | HTTP yes, Azure SDK no |
| Connection pooling | ❌ | Not implemented |
| Structured logging | ⚠️ | Basic, needs custom dimensions |
| Secrets management | ✅ | Key Vault integration |
| Error context | ⚠️ | Logs errors but limited context |
| Response validation | ❌ | No JSON validation |
| Data validation | ❌ | No schema validation |
| Testability | ❌ | Tightly coupled to services |

---

## Conclusion

The integration is **functionally correct** for the happy path and handles basic error scenarios. However, it needs **hardening for production** to handle edge cases, improve reliability, and provide better observability.

**Key Action Items**:
1. Add response validation and better error discrimination
2. Implement connection pooling with requests.Session
3. Add comprehensive structured logging
4. Add safety limits (pagination, retries)
5. Make configuration values externalized

**Estimated Effort**: 1-2 days to address P0/P1 issues.

**Risk if not addressed**: Function may fail silently, waste compute on non-retryable errors, or miss data due to pagination issues.
