"""
MDO Attack Simulation Training - Graph API Ingestion Function
Ingests data from Microsoft Graph Attack Simulation Training APIs into ADLS Gen2.

APIs covered:
- getAttackSimulationRepeatOffenders
- getAttackSimulationSimulationUserCoverage  
- getAttackSimulationTrainingUserCoverage

Output: JSON files (Power BI compatible)
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

# Required environment variables
REQUIRED_ENV_VARS = [
    "TENANT_ID",
    "GRAPH_CLIENT_ID",
    "KEY_VAULT_URL",
    "STORAGE_ACCOUNT_URL"
]


def validate_environment_variables() -> None:
    """Validate that all required environment variables are set."""
    missing_vars = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise EnvironmentError(error_msg)
    logger.info("All required environment variables are present")


def add_security_headers(response: func.HttpResponse) -> func.HttpResponse:
    """Add security headers to HTTP response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
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
        if not force_refresh and self._access_token and time.time() < self._token_expires - 60:
            return self._access_token

        token_url = self.TOKEN_URL.format(tenant_id=self.tenant_id)
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default"
        }

        response = self.session.post(token_url, data=data, timeout=30)
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
                response = self.session.get(url, headers=headers, timeout=30)

                if response.status_code == 401 and not _token_retry:
                    logger.warning("Received 401 Unauthorized. Invalidating token and retrying once...")
                    self._access_token = None
                    self._token_expires = 0
                    return self._make_request(url, retries=retries, _token_retry=True)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()

                try:
                    return response.json()
                except JSONDecodeError as e:
                    logger.error(f"Failed to parse response as JSON: {e}. Response text (first 500 chars): {response.text[:500]}")
                    raise

            except requests.exceptions.RequestException as e:
                if attempt == retries - 1:
                    raise
                wait_time = (2 ** attempt) * 5
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)

        return {}
    
    def get_paginated_data(self, endpoint: str, max_pages: int = 1000) -> Generator[dict, None, None]:
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
                time.sleep(0.5)


class ADLSWriter:
    """Writer for Azure Data Lake Storage Gen2."""
    
    def __init__(self, account_url: str):
        account_url = account_url.rstrip('/')
        if not account_url.startswith("https://"):
            account_url = f"https://{account_url}"
        if ".dfs.core.windows.net" not in account_url:
            account_name = account_url.replace("https://", "").split(".")[0]
            account_url = f"https://{account_name}.dfs.core.windows.net"
            
        credential = DefaultAzureCredential()
        self.service_client = DataLakeServiceClient(account_url=account_url, credential=credential)
    
    def write_json(self, container: str, path: str, data: list) -> int:
        """Write JSON data to ADLS Gen2."""
        if not data:
            logger.warning(f"No data to write to {container}/{path}")
            return 0
            
        json_bytes = json.dumps(data, indent=2, default=str).encode('utf-8')
        
        file_system_client = self.service_client.get_file_system_client(container)
        file_client = file_system_client.get_file_client(path)
        
        file_client.upload_data(json_bytes, overwrite=True)
        
        logger.info(f"Written {len(data)} records to {container}/{path}")
        return len(data)


def get_key_vault_secret(vault_url: str, secret_name: str) -> str:
    """Retrieve secret from Key Vault using managed identity."""
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)
    secret = client.get_secret(secret_name)
    return secret.value


def sanitize_string(value: Optional[str], max_length: int = 1000) -> Optional[str]:
    """Sanitize string fields from API responses.

    Args:
        value: The string value to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized string or None if input is None
    """
    if value is None:
        return None

    # Convert to string if not already
    if not isinstance(value, str):
        value = str(value)

    # Truncate if too long
    if len(value) > max_length:
        logger.warning(f"Truncating string value from {len(value)} to {max_length} characters")
        value = value[:max_length]

    # Strip whitespace
    value = value.strip()

    return value if value else None


def flatten_attack_user(user_detail: dict) -> dict:
    """Flatten attackSimulationUser nested structure with input validation."""
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
        # Validate environment variables at startup
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
                
                # Write to curated container (JSON)
                curated_path = f"{api_name}/{snapshot_date}/{api_name}.json"
                adls_writer.write_json("curated", curated_path, processed_data)
                
                # Also write raw data for archival
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
    """Health check endpoint."""
    response = func.HttpResponse(
        json.dumps({"status": "healthy"}),
        mimetype="application/json",
        status_code=200
    )
    return add_security_headers(response)


@app.function_name(name="test_run")
@app.route(route="test-run", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def test_run(req: func.HttpRequest) -> func.HttpResponse:
    """Manual trigger endpoint for testing."""
    correlation_id = str(uuid.uuid4())
    logger.info(f"Test run initiated with correlation ID: {correlation_id}")

    try:
        # Simulate timer request
        class MockTimer:
            past_due = False

        mdo_attack_simulation_ingest(MockTimer())

        response = func.HttpResponse(
            json.dumps({"status": "success", "message": "Ingestion completed", "correlationId": correlation_id}),
            mimetype="application/json",
            status_code=200
        )
        return add_security_headers(response)

    except Exception as e:
        logger.error(f"Test run failed with correlation ID {correlation_id}", exc_info=True)
        response = func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": "An error occurred during ingestion. Please check logs for details.",
                "correlationId": correlation_id
            }),
            mimetype="application/json",
            status_code=500
        )
        return add_security_headers(response)
