"""
Configuration module for MDO Attack Simulation Training ingestion function.

Centralizes all constants, environment-based configuration, and API endpoint
definitions used across the function app. Extracted from function_app.py for
maintainability and testability.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Token & request constants
# ---------------------------------------------------------------------------
TOKEN_REFRESH_BUFFER_SECONDS: int = 60
REQUEST_TIMEOUT_SECONDS: int = 30
DEFAULT_RETRY_AFTER_SECONDS: int = 60
BACKOFF_BASE_SECONDS: int = 5
PAGINATION_DELAY_SECONDS: float = 0.5

# ---------------------------------------------------------------------------
# Pagination & data limits
# ---------------------------------------------------------------------------
MAX_PAGES_DEFAULT: int = 1000
MAX_STRING_LENGTH: int = 1000

# ---------------------------------------------------------------------------
# Incremental sync constants
# ---------------------------------------------------------------------------
INCREMENTAL_LOOKBACK_DAYS: int = 7
STATE_CONTAINER: str = "state"
STATE_FILE: str = "sync_state.json"

# ---------------------------------------------------------------------------
# Required environment variables
# ---------------------------------------------------------------------------
REQUIRED_ENV_VARS: List[str] = [
    "TENANT_ID",
    "GRAPH_CLIENT_ID",
    "KEY_VAULT_URL",
    "STORAGE_ACCOUNT_URL",
]

# ---------------------------------------------------------------------------
# Retry constants (previously hard-coded in class methods)
# ---------------------------------------------------------------------------
GRAPH_API_MAX_RETRIES: int = 3
STORAGE_UPLOAD_MAX_RETRIES: int = 3
STORAGE_UPLOAD_BACKOFF_BASE: int = 2

# ---------------------------------------------------------------------------
# Microsoft Graph API URLs
# ---------------------------------------------------------------------------
GRAPH_BASE_URL_V1: str = "https://graph.microsoft.com/v1.0"
GRAPH_BASE_URL_BETA: str = "https://graph.microsoft.com/beta"
TOKEN_URL_TEMPLATE: str = (
    "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
)


# ---------------------------------------------------------------------------
# API endpoint configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class APIEndpoint:
    """Describes a single Graph API endpoint to ingest."""

    name: str
    endpoint: str
    processor_name: str
    supports_incremental: bool = False
    incremental_filter: Optional[str] = None
    max_records: Optional[int] = None


# Core endpoints – always executed regardless of sync mode.
API_CONFIGS: List[APIEndpoint] = [
    APIEndpoint(
        name="repeatOffenders",
        endpoint="reports/security/getAttackSimulationRepeatOffenders",
        processor_name="process_repeat_offenders",
        supports_incremental=False,
    ),
    APIEndpoint(
        name="simulationUserCoverage",
        endpoint="reports/security/getAttackSimulationSimulationUserCoverage",
        processor_name="process_simulation_user_coverage",
        supports_incremental=False,
    ),
    APIEndpoint(
        name="trainingUserCoverage",
        endpoint="reports/security/getAttackSimulationTrainingUserCoverage",
        processor_name="process_training_user_coverage",
        supports_incremental=False,
    ),
]

# Extended endpoints – only executed when SYNC_SIMULATIONS is enabled.
EXTENDED_API_CONFIGS: List[APIEndpoint] = [
    APIEndpoint(
        name="simulations",
        endpoint="security/attackSimulation/simulations",
        processor_name="process_simulations",
        supports_incremental=True,
        incremental_filter=(
            "$filter=status eq 'running' or "
            "lastModifiedDateTime ge {lookback_date}"
        ),
    ),
    APIEndpoint(
        name="trainings",
        endpoint="security/attackSimulation/trainings",
        processor_name="process_trainings",
        supports_incremental=False,
    ),
    APIEndpoint(
        name="payloads",
        endpoint="security/attackSimulation/payloads?$filter=source eq 'global'&$top=200",
        processor_name="process_payloads",
        supports_incremental=False,
        max_records=500,
    ),
]


# ---------------------------------------------------------------------------
# Central function configuration (populated from environment variables)
# ---------------------------------------------------------------------------
@dataclass
class FunctionConfig:
    """Central configuration for the function app."""

    tenant_id: str
    graph_client_id: str
    key_vault_url: str
    storage_account_url: str
    timer_schedule: str = "0 0 * * * *"
    sync_mode: str = "full"
    sync_simulations: bool = True
    incremental_lookback_days: int = INCREMENTAL_LOOKBACK_DAYS
    max_pages: int = MAX_PAGES_DEFAULT

    @classmethod
    def from_environment(cls) -> "FunctionConfig":
        """Create config from environment variables with validation.

        Raises:
            EnvironmentError: If any required variable is missing.
            ValueError: If a variable has an invalid value.
        """
        missing = [var for var in REQUIRED_ENV_VARS if var not in os.environ]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        storage_url = os.environ["STORAGE_ACCOUNT_URL"]
        if not storage_url.startswith("https://"):
            raise ValueError("STORAGE_ACCOUNT_URL must start with https://")

        kv_url = os.environ["KEY_VAULT_URL"]
        if not kv_url.startswith("https://"):
            raise ValueError("KEY_VAULT_URL must start with https://")

        sync_mode = os.environ.get("SYNC_MODE", "full").lower()
        if sync_mode not in ("full", "incremental"):
            raise ValueError(
                f"SYNC_MODE must be 'full' or 'incremental', got: {sync_mode}"
            )

        return cls(
            tenant_id=os.environ["TENANT_ID"],
            graph_client_id=os.environ["GRAPH_CLIENT_ID"],
            key_vault_url=kv_url,
            storage_account_url=storage_url,
            timer_schedule=os.environ.get("TIMER_SCHEDULE", "0 0 * * * *"),
            sync_mode=sync_mode,
            sync_simulations=(
                os.environ.get("SYNC_SIMULATIONS", "true").lower() == "true"
            ),
        )
