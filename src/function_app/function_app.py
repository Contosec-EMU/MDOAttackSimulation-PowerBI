"""
MDO Attack Simulation Training - Graph API Ingestion Function
Ingests data from Microsoft Graph Attack Simulation Training APIs into ADLS Gen2.

APIs covered:
- getAttackSimulationRepeatOffenders
- getAttackSimulationSimulationUserCoverage
- getAttackSimulationTrainingUserCoverage

Output:
- Raw container: JSON files (archival)
- Curated container: Parquet files (optimized for Power BI)
"""

import azure.functions as func
import logging
import os
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Generator
import time
import io
import random

import requests
from requests.exceptions import JSONDecodeError
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.filedatalake import DataLakeServiceClient

# Initialize Function App
app = func.FunctionApp()

# Configure logging
logger = logging.getLogger(__name__)

# Configuration constants
TOKEN_REFRESH_BUFFER_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_RETRY_AFTER_SECONDS = 60
BACKOFF_BASE_SECONDS = 5
PAGINATION_DELAY_SECONDS = 0.5
MAX_PAGES_DEFAULT = 1000
MAX_STRING_LENGTH = 1000

# Required environment variables for the function to operate
REQUIRED_ENV_VARS = ["TENANT_ID", "GRAPH_CLIENT_ID", "KEY_VAULT_URL", "STORAGE_ACCOUNT_URL"]


def validate_environment_variables() -> None:
    """Validate that all required environment variables are set.

    Raises:
        EnvironmentError: If any required variables are missing
    """
    missing = [var for var in REQUIRED_ENV_VARS if var not in os.environ]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")


def sanitize_string(value, max_length: int = MAX_STRING_LENGTH) -> Optional[str]:
    """Sanitize string input from API responses."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if len(value) > max_length:
        logger.warning(f"String truncated from {len(value)} to {max_length} chars")
        value = value[:max_length]
    return value


def add_security_headers(response: func.HttpResponse) -> func.HttpResponse:
    """Add security headers to HTTP response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
    return response


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
        self.session = requests.Session()  # Connection pooling

    def _get_access_token(self, force_refresh: bool = False) -> str:
        """Get OAuth2 access token using client credentials flow."""
        if not force_refresh and self._access_token and time.time() < self._token_expires - TOKEN_REFRESH_BUFFER_SECONDS:
            return self._access_token

        token_url = self.TOKEN_URL.format(tenant_id=self.tenant_id)
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default"
        }

        response = self.session.post(token_url, data=data, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()

        try:
            token_data = response.json()
        except JSONDecodeError as e:
            logger.error(f"Failed to parse token response as JSON: {e}. Response text (first 500 chars): {response.text[:500]}")
            raise

        self._access_token = token_data["access_token"]
        self._token_expires = time.time() + token_data.get("expires_in", 3600)

        return self._access_token

    def _make_request(self, url: str, retries: int = 3, _token_retry: bool = False) -> dict:
        """Make HTTP GET request with retry logic."""
        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }

        for attempt in range(retries):
            try:
                response = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)

                if response.status_code == 401 and not _token_retry:
                    logger.warning("Received 401 Unauthorized. Invalidating token and retrying once...")
                    self._access_token = None
                    self._token_expires = 0
                    return self._make_request(url, retries=retries, _token_retry=True)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", DEFAULT_RETRY_AFTER_SECONDS))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue

                # Don't retry non-retryable client errors (4xx except 401, 429)
                if 400 <= response.status_code < 500 and response.status_code not in (401, 429):
                    logger.error(f"Non-retryable client error: {response.status_code}")
                    response.raise_for_status()

                response.raise_for_status()

                try:
                    return response.json()
                except JSONDecodeError as e:
                    logger.error(f"Failed to parse response as JSON: {e}. Response text (first 500 chars): {response.text[:500]}")
                    raise

            except requests.exceptions.RequestException as e:
                if attempt == retries - 1:
                    raise
                # Add jitter to exponential backoff
                wait_time = (2 ** attempt) * BACKOFF_BASE_SECONDS + random.uniform(0, 2)
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}. Retrying in {wait_time:.2f}s...")
                time.sleep(wait_time)

        # This line is now reachable if all retries are exhausted without raising
        raise RuntimeError(f"Failed to complete request after {retries} retries")

    def get_paginated_data(self, endpoint: str, max_pages: int = MAX_PAGES_DEFAULT) -> Generator[dict, None, None]:
        """Fetch all pages of data from a Graph API endpoint.

        Args:
            endpoint: The Graph API endpoint to query
            max_pages: Maximum number of pages to fetch (safety limit)

        Raises:
            RuntimeError: If max_pages is exceeded
        """
        url = f"{self.GRAPH_BASE_URL}/{endpoint}"
        page_count = 0

        while url:
            page_count += 1
            if page_count > max_pages:
                raise RuntimeError(f"Pagination safety limit exceeded: {max_pages} pages")

            logger.info(f"Fetching page {page_count}: {url[:100]}...")
            data = self._make_request(url)

            for item in data.get("value", []):
                yield item

            url = data.get("@odata.nextLink")

            if url:
                time.sleep(PAGINATION_DELAY_SECONDS)


class ADLSWriter:
    """Writer for Azure Data Lake Storage Gen2 with JSON and Parquet support."""

    def __init__(self, account_url: str):
        account_url = account_url.rstrip('/')
        if not account_url.startswith("https://"):
            account_url = f"https://{account_url}"
        if ".dfs.core.windows.net" not in account_url:
            account_name = account_url.replace("https://", "").split(".")[0]
            account_url = f"https://{account_name}.dfs.core.windows.net"

        credential = DefaultAzureCredential()
        self.service_client = DataLakeServiceClient(account_url=account_url, credential=credential)

    def _ensure_container_exists(self, container: str) -> None:
        """Verify container exists, create if not."""
        try:
            file_system_client = self.service_client.get_file_system_client(container)
            if not file_system_client.exists():
                logger.info(f"Creating container: {container}")
                file_system_client.create_file_system()
        except Exception as e:
            logger.error(f"Failed to verify/create container {container}: {e}")
            raise

    def _upload_with_retry(self, file_client, data: bytes, max_retries: int = 3) -> None:
        """Upload data with retry logic for transient failures."""
        for attempt in range(max_retries):
            try:
                file_client.upload_data(data, overwrite=True)
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = (2 ** attempt) * 2 + random.uniform(0, 1)
                logger.warning(f"Storage upload failed (attempt {attempt + 1}): {e}. Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)

    def write_json(self, container: str, path: str, data: list) -> int:
        """Write JSON data to ADLS Gen2."""
        if not data:
            logger.warning(f"No data to write to {container}/{path}")
            return 0

        # Ensure container exists before writing
        self._ensure_container_exists(container)

        json_bytes = json.dumps(data, indent=2, default=str).encode('utf-8')

        file_system_client = self.service_client.get_file_system_client(container)
        file_client = file_system_client.get_file_client(path)

        # Upload with retry logic
        self._upload_with_retry(file_client, json_bytes)

        logger.info(f"Written {len(data)} records to {container}/{path}")
        return len(data)

    def write_parquet(self, container: str, path: str, data: list) -> int:
        """Write data to ADLS Gen2 as Parquet format.

        Optimized for Power BI consumption with appropriate data types and compression.
        """
        if not data:
            logger.warning(f"No data to write to {container}/{path}")
            return 0

        # Convert to pandas DataFrame for easier type inference
        df = pd.DataFrame(data)

        # Optimize data types for Power BI
        df = self._optimize_schema_for_powerbi(df)

        # Write to Parquet with optimal settings for Power BI
        parquet_buffer = io.BytesIO()
        df.to_parquet(
            parquet_buffer,
            engine='pyarrow',
            compression='snappy',  # Fast compression, good balance for Power BI
            index=False,
            use_deprecated_int96_timestamps=False,  # Use INT64 timestamps (better for Power BI)
            coerce_timestamps='ms',  # Millisecond precision
            allow_truncated_timestamps=True
        )

        parquet_bytes = parquet_buffer.getvalue()

        # Ensure container exists before writing
        self._ensure_container_exists(container)

        # Upload to ADLS
        file_system_client = self.service_client.get_file_system_client(container)
        file_client = file_system_client.get_file_client(path)

        # Upload with retry logic
        self._upload_with_retry(file_client, parquet_bytes)

        logger.info(f"Written {len(data)} records to {container}/{path} (Parquet, {len(parquet_bytes):,} bytes)")
        return len(data)

    def _optimize_schema_for_powerbi(self, df: pd.DataFrame) -> pd.DataFrame:
        """Optimize DataFrame schema for Power BI consumption.

        Power BI works best with:
        - Explicit data types (avoid objects where possible)
        - Datetime columns as datetime64
        - Numeric columns as appropriate int/float types
        - String columns as string dtype
        """
        for col in df.columns:
            # Convert datetime strings to datetime64
            if 'date' in col.lower() or 'datetime' in col.lower():
                if df[col].dtype == 'object':
                    try:
                        df[col] = pd.to_datetime(df[col], utc=True, errors='coerce')
                    except Exception as e:
                        logger.warning(f"Could not convert {col} to datetime: {e}")

            # Convert count columns to int32 (sufficient for most counts)
            elif 'count' in col.lower() or col.endswith('Count'):
                if df[col].dtype == 'object' or df[col].dtype == 'float64':
                    try:
                        df[col] = df[col].fillna(0).astype('int32')
                    except Exception as e:
                        logger.warning(f"Could not convert {col} to int32: {e}")

            # Ensure string columns are explicitly string type
            elif df[col].dtype == 'object':
                try:
                    df[col] = df[col].astype('string')
                except Exception as e:
                    logger.warning(f"Could not convert {col} to string: {e}")

        return df


def get_key_vault_secret(vault_url: str, secret_name: str) -> str:
    """Retrieve secret from Key Vault using managed identity."""
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)
    secret = client.get_secret(secret_name)
    return secret.value


def flatten_attack_user(user_detail: dict) -> dict:
    """Flatten attackSimulationUser nested structure with input sanitization."""
    if not user_detail:
        return {"userId": None, "displayName": None, "email": None}
    return {
        "userId": sanitize_string(user_detail.get("userId")),
        "displayName": sanitize_string(user_detail.get("displayName")),
        "email": sanitize_string(user_detail.get("email"))
    }


def process_repeat_offenders(records: list, snapshot_date: str) -> list:
    """Process repeat offenders data."""
    processed = []
    for record in records:
        user = flatten_attack_user(record.get("attackSimulationUser", {}))
        processed.append({
            "snapshotDateUtc": snapshot_date,
            "userId": user.get("userId"),
            "displayName": user.get("displayName"),
            "email": user.get("email"),
            "repeatOffenceCount": record.get("repeatOffenceCount")
        })
    return processed


def process_simulation_user_coverage(records: list, snapshot_date: str) -> list:
    """Process simulation user coverage data."""
    processed = []
    for record in records:
        user = flatten_attack_user(record.get("attackSimulationUser", {}))
        processed.append({
            "snapshotDateUtc": snapshot_date,
            "userId": user.get("userId"),
            "displayName": user.get("displayName"),
            "email": user.get("email"),
            "simulationCount": record.get("simulationCount"),
            "latestSimulationDateTime": record.get("latestSimulationDateTime"),
            "clickCount": record.get("clickCount"),
            "compromisedCount": record.get("compromisedCount")
        })
    return processed


def process_training_user_coverage(records: list, snapshot_date: str) -> list:
    """Process training user coverage data.

    The Graph API returns userTrainings as an array of training objects with status,
    not pre-aggregated counts. This function aggregates them into counts.

    API Response structure:
    {
        "userTrainings": [
            {"trainingStatus": "completed", "displayName": "...", ...},
            {"trainingStatus": "assigned", ...}
        ],
        "attackSimulationUser": {...}
    }
    """
    processed = []
    for record in records:
        user = flatten_attack_user(record.get("attackSimulationUser", {}))
        trainings = record.get("userTrainings", [])

        # Aggregate counts from the userTrainings array
        # Valid statuses per MS docs: assigned, completed, inProgress, notStarted
        assigned_count = len(trainings)
        completed_count = sum(1 for t in trainings if t.get("trainingStatus") == "completed")
        in_progress_count = sum(1 for t in trainings if t.get("trainingStatus") == "inProgress")
        not_started_count = sum(1 for t in trainings if t.get("trainingStatus") in ("notStarted", "assigned"))

        processed.append({
            "snapshotDateUtc": snapshot_date,
            "userId": user.get("userId"),
            "displayName": user.get("displayName"),
            "email": user.get("email"),
            "assignedTrainingsCount": assigned_count,
            "completedTrainingsCount": completed_count,
            "inProgressTrainingsCount": in_progress_count,
            "notStartedTrainingsCount": not_started_count
        })
    return processed


# API endpoint configurations
API_CONFIGS = [
    {
        "name": "repeatOffenders",
        "endpoint": "reports/security/getAttackSimulationRepeatOffenders",
        "processor": process_repeat_offenders
    },
    {
        "name": "simulationUserCoverage",
        "endpoint": "reports/security/getAttackSimulationSimulationUserCoverage",
        "processor": process_simulation_user_coverage
    },
    {
        "name": "trainingUserCoverage",
        "endpoint": "reports/security/getAttackSimulationTrainingUserCoverage",
        "processor": process_training_user_coverage
    }
]


@app.timer_trigger(schedule="%TIMER_SCHEDULE%",
                   arg_name="timer",
                   run_on_startup=False)
def mdo_attack_simulation_ingest(timer: func.TimerRequest) -> None:
    """
    Timer-triggered function to ingest MDO Attack Simulation Training data.
    Runs on schedule defined by TIMER_SCHEDULE environment variable.
    """
    start_time = time.time()
    snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info(f"Starting MDO Attack Simulation ingestion - Snapshot: {snapshot_date}")

    if timer.past_due:
        logger.warning("Timer is running late!")

    try:
        # Validate environment before proceeding
        validate_environment_variables()

        # Get configuration from environment
        tenant_id = os.environ["TENANT_ID"]
        client_id = os.environ["GRAPH_CLIENT_ID"]
        key_vault_url = os.environ["KEY_VAULT_URL"]
        storage_url = os.environ["STORAGE_ACCOUNT_URL"]

        # Get client secret from Key Vault
        client_secret = get_key_vault_secret(key_vault_url, "graph-client-secret")

        # Initialize clients
        graph_client = GraphAPIClient(tenant_id, client_id, client_secret)
        adls_writer = ADLSWriter(storage_url)

        total_records = 0

        for api_config in API_CONFIGS:
            api_name = api_config["name"]
            logger.info(f"Processing {api_name}...")

            # Fetch all data from API
            raw_data = list(graph_client.get_paginated_data(api_config["endpoint"]))
            logger.info(f"Fetched {len(raw_data)} records from {api_name}")

            if raw_data:
                # Process data
                processed_data = api_config["processor"](raw_data, snapshot_date)

                # Write to curated container as Parquet (optimized for Power BI)
                curated_path = f"{api_name}/{snapshot_date}/{api_name}.parquet"
                adls_writer.write_parquet("curated", curated_path, processed_data)

                # Also write raw data for archival (JSON)
                raw_path = f"{api_name}/{snapshot_date}/{api_name}_raw.json"
                adls_writer.write_json("raw", raw_path, raw_data)

                total_records += len(processed_data)

        elapsed = time.time() - start_time
        logger.info(f"Ingestion complete. Total records: {total_records}, Time: {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"Ingestion failed: {str(e)}", exc_info=True)
        raise


@app.function_name(name="health_check")
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint (requires function key)."""
    response = func.HttpResponse(
        json.dumps({"status": "healthy"}),
        mimetype="application/json",
        status_code=200
    )
    return add_security_headers(response)


@app.function_name(name="test_run")
@app.route(route="test-run", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def test_run(req: func.HttpRequest) -> func.HttpResponse:
    """Manual trigger endpoint for testing (requires function key)."""
    correlation_id = str(uuid.uuid4())
    logger.info(f"Test run initiated - Correlation ID: {correlation_id}")

    try:
        # Simulate timer request
        class MockTimer:
            past_due = False

        mdo_attack_simulation_ingest(MockTimer())

        response = func.HttpResponse(
            json.dumps({
                "status": "success",
                "message": "Ingestion completed",
                "correlationId": correlation_id
            }),
            mimetype="application/json",
            status_code=200
        )
        return add_security_headers(response)
    except Exception as e:
        # Log full error details server-side
        logger.error(f"Test run failed - Correlation ID: {correlation_id}", exc_info=True)

        # Return sanitized error to client (no internal details)
        response = func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": "An error occurred during ingestion. Check logs for details.",
                "correlationId": correlation_id
            }),
            mimetype="application/json",
            status_code=500
        )
        return add_security_headers(response)
