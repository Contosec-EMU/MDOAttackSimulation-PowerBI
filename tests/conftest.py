"""Shared pytest fixtures for MDO Attack Simulation tests."""

import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Mock unavailable C-extension packages before any source imports
# ---------------------------------------------------------------------------

def _ensure_mock_module(name, attrs=None):
    """Register a stub module if not importable."""
    try:
        __import__(name)
        return  # Module loaded successfully
    except (ImportError, SyntaxError, Exception):
        mod = types.ModuleType(name)
        if attrs:
            for k, v in attrs.items():
                setattr(mod, k, v)
        sys.modules[name] = mod
        # Ensure parent packages exist
        parts = name.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[:i])
            if parent not in sys.modules:
                sys.modules[parent] = types.ModuleType(parent)


# aiohttp stubs
_ensure_mock_module("aiohttp", {
    "ClientSession": MagicMock,
    "ClientTimeout": MagicMock,
    "ClientError": type("ClientError", (Exception,), {}),
    "ClientResponseError": type("ClientResponseError", (Exception,), {
        "__init__": lambda self, *a, **kw: Exception.__init__(self, kw.get("message", "")),
    }),
})

# pandas / pyarrow stubs (only needed by adls_writer, not under test here)
_ensure_mock_module("pandas", {"DataFrame": MagicMock, "to_datetime": MagicMock, "to_numeric": MagicMock})
_ensure_mock_module("pyarrow")
_ensure_mock_module("pyarrow.parquet")

# azure SDK stubs
_ensure_mock_module("azure")
_ensure_mock_module("azure.core")
_ensure_mock_module("azure.core.exceptions", {
    "ResourceExistsError": type("ResourceExistsError", (Exception,), {}),
    "ResourceNotFoundError": type("ResourceNotFoundError", (Exception,), {}),
})
_ensure_mock_module("azure.identity", {"DefaultAzureCredential": MagicMock})
_ensure_mock_module("azure.identity.aio", {"DefaultAzureCredential": MagicMock})
_ensure_mock_module("azure.storage")
_ensure_mock_module("azure.storage.filedatalake")
_ensure_mock_module("azure.storage.filedatalake.aio", {"DataLakeServiceClient": MagicMock})

# Add the function_app source directory to sys.path so imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "function_app"))


# ---------------------------------------------------------------------------
# Environment variable fixtures
# ---------------------------------------------------------------------------

VALID_ENV_VARS = {
    "TENANT_ID": "00000000-0000-0000-0000-000000000001",
    "GRAPH_CLIENT_ID": "00000000-0000-0000-0000-000000000002",
    "KEY_VAULT_URL": "https://kv-test-example.vault.azure.net",
    "STORAGE_ACCOUNT_URL": "https://stestexample.dfs.core.windows.net",
    "TIMER_SCHEDULE": "0 0 3 * * *",
    "SYNC_MODE": "full",
    "SYNC_SIMULATIONS": "true",
}


@pytest.fixture()
def env_vars(monkeypatch):
    """Set all required environment variables to valid values."""
    for key, value in VALID_ENV_VARS.items():
        monkeypatch.setenv(key, value)
    return VALID_ENV_VARS


@pytest.fixture()
def env_vars_incremental(monkeypatch, env_vars):
    """Override SYNC_MODE to 'incremental'."""
    monkeypatch.setenv("SYNC_MODE", "incremental")
    return env_vars


# ---------------------------------------------------------------------------
# Sample Graph API response data
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_repeat_offender_record():
    return {
        "attackSimulationUser": {
            "userId": "user-001",
            "displayName": "Alice Smith",
            "email": "alice@contoso.com",
        },
        "repeatOffenceCount": 3,
    }


@pytest.fixture()
def sample_simulation_user_coverage_record():
    return {
        "attackSimulationUser": {
            "userId": "user-002",
            "displayName": "Bob Jones",
            "email": "bob@contoso.com",
        },
        "simulationCount": 5,
        "latestSimulationDateTime": "2024-06-15T10:30:00Z",
        "clickCount": 2,
        "compromisedCount": 1,
    }


@pytest.fixture()
def sample_training_user_coverage_record():
    return {
        "attackSimulationUser": {
            "userId": "user-003",
            "displayName": "Carol White",
            "email": "carol@contoso.com",
        },
        "userTrainings": [
            {"trainingStatus": "completed"},
            {"trainingStatus": "inProgress"},
            {"trainingStatus": "notStarted"},
            {"trainingStatus": "assigned"},
        ],
    }


@pytest.fixture()
def sample_simulation_record():
    return {
        "id": "sim-001",
        "displayName": "Phishing Campaign Q2",
        "description": "Quarterly phishing test",
        "status": "completed",
        "attackType": "phishing",
        "attackTechnique": "credentialHarvesting",
        "createdDateTime": "2024-01-10T08:00:00Z",
        "launchDateTime": "2024-01-15T09:00:00Z",
        "completionDateTime": "2024-02-15T09:00:00Z",
        "lastModifiedDateTime": "2024-02-15T09:05:00Z",
        "isAutomated": False,
        "automationId": None,
        "durationInDays": 30,
        "payload": {
            "id": "payload-001",
            "displayName": "Credential Harvest Payload",
        },
        "report": {
            "overview": {
                "resolvedTargetsCount": 100,
                "simulationEventsContent": {
                    "compromisedRate": 0.1,
                    "events": [
                        {"eventName": "CredentialHarvested", "count": 10},
                        {"eventName": "EmailLinkClicked", "count": 25},
                        {"eventName": "ReportedEmail", "count": 5},
                    ],
                },
            },
        },
        "createdBy": {
            "id": "admin-001",
            "displayName": "Admin User",
            "email": "admin@contoso.com",
        },
        "lastModifiedBy": {
            "id": "admin-002",
            "displayName": "Modified By User",
            "email": "modifier@contoso.com",
        },
    }


@pytest.fixture()
def sample_simulation_user_record():
    return {
        "simulationUser": {
            "userId": "user-010",
            "email": "user10@contoso.com",
            "displayName": "User Ten",
        },
        "compromisedDateTime": "2024-01-20T12:00:00Z",
        "reportedPhishDateTime": None,
        "assignedTrainingsCount": 2,
        "completedTrainingsCount": 1,
        "inProgressTrainingsCount": 1,
        "isCompromised": True,
        "simulationEvents": [
            {
                "eventName": "emailLinkClicked",
                "eventDateTime": "2024-01-20T11:55:00Z",
                "browser": "Chrome",
                "ipAddress": "10.0.0.1",
                "osPlatformDeviceDetails": "Windows 11",
            },
            {
                "eventName": "credentialSubmitted",
                "eventDateTime": "2024-01-20T12:00:00Z",
                "browser": "Chrome",
                "ipAddress": "10.0.0.1",
                "osPlatformDeviceDetails": "Windows 11",
            },
        ],
    }


@pytest.fixture()
def sample_training_record():
    return {
        "id": "training-001",
        "displayName": "Phishing Awareness 101",
        "description": "Basic phishing awareness training",
        "durationInMinutes": 30,
        "source": "tenant",
        "type": "module",
        "availabilityStatus": "available",
        "hasEvaluation": True,
        "lastModifiedDateTime": "2024-03-01T10:00:00Z",
        "createdBy": {
            "id": "admin-001",
            "displayName": "Admin User",
            "email": "admin@contoso.com",
        },
        "lastModifiedBy": None,
    }


@pytest.fixture()
def sample_payload_record():
    return {
        "id": "payload-001",
        "displayName": "Credential Harvest Payload",
        "description": "Simulated credential harvesting email",
        "simulationAttackType": "credentialHarvest",
        "platform": "email",
        "status": "ready",
        "source": "tenant",
        "predictedCompromiseRate": 0.15,
        "complexity": "medium",
        "technique": "credentialHarvesting",
        "theme": "accountActivation",
        "brand": "Microsoft",
        "industry": "technology",
        "isCurrentEvent": False,
        "isControversial": False,
        "lastModifiedDateTime": "2024-03-15T14:00:00Z",
        "createdBy": {
            "id": "admin-001",
            "displayName": "Admin",
            "email": "admin@contoso.com",
        },
        "lastModifiedBy": {
            "id": "admin-001",
            "displayName": "Admin",
            "email": "admin@contoso.com",
        },
    }


@pytest.fixture()
def sample_user_record():
    return {
        "id": "user-010",
        "displayName": "User Ten",
        "givenName": "User",
        "surname": "Ten",
        "mail": "user10@contoso.com",
        "department": "Engineering",
        "companyName": "Contoso",
        "city": "Seattle",
        "country": "US",
        "jobTitle": "Software Engineer",
        "accountEnabled": True,
    }


SNAPSHOT_DATE = "2024-06-20"


@pytest.fixture()
def snapshot_date():
    return SNAPSHOT_DATE


# ---------------------------------------------------------------------------
# Mock credentials for async clients
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_credential():
    cred = MagicMock()
    cred.close = AsyncMock()
    return cred
