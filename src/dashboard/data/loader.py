"""ADLS Gen2 Parquet data loader with Streamlit caching."""

from __future__ import annotations

import io
import logging
import os

import pandas as pd
import streamlit as st
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

logger = logging.getLogger(__name__)

STORAGE_ACCOUNT_URL: str = os.environ.get(
    "STORAGE_ACCOUNT_URL", "https://YOURSTORAGEACCOUNT.dfs.core.windows.net"
)
CONTAINER_NAME: str = os.environ.get("CONTAINER_NAME", "curated")

# Column schemas for empty fallback DataFrames
TABLE_SCHEMAS: dict[str, dict[str, str]] = {
    "repeatOffenders": {
        "snapshotDateUtc": "datetime64[ns]",
        "userId": "str",
        "displayName": "str",
        "email": "str",
        "repeatOffenceCount": "Int64",
    },
    "simulationUserCoverage": {
        "snapshotDateUtc": "datetime64[ns]",
        "userId": "str",
        "displayName": "str",
        "email": "str",
        "simulationCount": "Int64",
        "latestSimulationDateTime": "datetime64[ns]",
        "clickCount": "Int64",
        "compromisedCount": "Int64",
    },
    "trainingUserCoverage": {
        "snapshotDateUtc": "datetime64[ns]",
        "userId": "str",
        "displayName": "str",
        "email": "str",
        "assignedTrainingsCount": "Int64",
        "completedTrainingsCount": "Int64",
        "inProgressTrainingsCount": "Int64",
        "notStartedTrainingsCount": "Int64",
    },
    "simulations": {
        "snapshotDateUtc": "datetime64[ns]",
        "simulationId": "str",
        "displayName": "str",
        "description": "str",
        "status": "str",
        "attackType": "str",
        "attackTechnique": "str",
        "createdDateTime": "datetime64[ns]",
        "launchDateTime": "datetime64[ns]",
        "completionDateTime": "datetime64[ns]",
        "lastModifiedDateTime": "datetime64[ns]",
        "isAutomated": "bool",
        "automationId": "str",
        "durationInDays": "Int64",
        "payloadId": "str",
        "payloadDisplayName": "str",
        "reportTotalUserCount": "Int64",
        "reportCompromisedCount": "Int64",
        "reportClickCount": "Int64",
        "reportReportedCount": "Int64",
        "createdById": "str",
        "createdByDisplayName": "str",
        "createdByEmail": "str",
        "lastModifiedById": "str",
        "lastModifiedByDisplayName": "str",
        "lastModifiedByEmail": "str",
    },
    "simulationUsers": {
        "snapshotDateUtc": "datetime64[ns]",
        "simulationId": "str",
        "userId": "str",
        "email": "str",
        "displayName": "str",
        "compromisedDateTime": "datetime64[ns]",
        "reportedPhishDateTime": "datetime64[ns]",
        "assignedTrainingsCount": "Int64",
        "completedTrainingsCount": "Int64",
        "inProgressTrainingsCount": "Int64",
        "isCompromised": "bool",
    },
    "simulationUserEvents": {
        "snapshotDateUtc": "datetime64[ns]",
        "simulationId": "str",
        "userId": "str",
        "eventName": "str",
        "eventDateTime": "datetime64[ns]",
        "browser": "str",
        "ipAddress": "str",
        "osPlatformDeviceDetails": "str",
    },
    "trainings": {
        "snapshotDateUtc": "datetime64[ns]",
        "trainingId": "str",
        "displayName": "str",
        "description": "str",
        "durationInMinutes": "Int64",
        "source": "str",
        "type": "str",
        "availabilityStatus": "str",
        "hasEvaluation": "bool",
        "lastModifiedDateTime": "datetime64[ns]",
        "createdById": "str",
        "createdByDisplayName": "str",
        "createdByEmail": "str",
        "lastModifiedById": "str",
        "lastModifiedByDisplayName": "str",
        "lastModifiedByEmail": "str",
    },
    "payloads": {
        "snapshotDateUtc": "datetime64[ns]",
        "payloadId": "str",
        "displayName": "str",
        "description": "str",
        "simulationAttackType": "str",
        "platform": "str",
        "status": "str",
        "source": "str",
        "predictedCompromiseRate": "float64",
        "complexity": "str",
        "technique": "str",
        "theme": "str",
        "brand": "str",
        "industry": "str",
        "isCurrentEvent": "bool",
        "isControversial": "bool",
        "lastModifiedDateTime": "datetime64[ns]",
        "createdById": "str",
        "createdByDisplayName": "str",
        "createdByEmail": "str",
        "lastModifiedById": "str",
        "lastModifiedByDisplayName": "str",
        "lastModifiedByEmail": "str",
    },
    "users": {
        "snapshotDateUtc": "datetime64[ns]",
        "userId": "str",
        "displayName": "str",
        "givenName": "str",
        "surname": "str",
        "mail": "str",
        "department": "str",
        "companyName": "str",
        "city": "str",
        "country": "str",
        "jobTitle": "str",
        "accountEnabled": "bool",
    },
}


def _empty_df(table_name: str) -> pd.DataFrame:
    """Return an empty DataFrame with the correct schema for a table."""
    schema = TABLE_SCHEMAS.get(table_name, {})
    df = pd.DataFrame({col: pd.Series(dtype=dtype) for col, dtype in schema.items()})
    return df


# Track load errors so pages can display actionable messages
_load_errors: dict[str, str] = {}


def _record_load_error(table_name: str, exc: Exception) -> None:
    """Store a human-readable error for a table so pages can show it."""
    _load_errors[table_name] = f"{type(exc).__name__}: {exc}"


def get_load_error(table_name: str) -> str | None:
    """Return the last load error for a table, or None if it loaded OK."""
    return _load_errors.get(table_name)


def _get_service_client() -> DataLakeServiceClient:
    """Create an ADLS Gen2 service client using DefaultAzureCredential."""
    credential = DefaultAzureCredential()
    return DataLakeServiceClient(account_url=STORAGE_ACCOUNT_URL, credential=credential)


@st.cache_data(ttl=3600, show_spinner="Loading data from storage...")
def load_table(table_name: str) -> pd.DataFrame:
    """Load the latest Parquet file for a table from ADLS Gen2.

    Returns an empty DataFrame with the correct schema if the table
    folder doesn't exist or contains no files.
    """
    try:
        client = _get_service_client()
        fs_client = client.get_file_system_client(CONTAINER_NAME)

        # List files in the table folder, sorted by last modified desc
        paths = list(fs_client.get_paths(path=table_name, recursive=True))
        parquet_files = [
            p for p in paths if p.name.endswith(".parquet") and not p.is_directory
        ]

        if not parquet_files:
            logger.info("No parquet files found for table '%s'", table_name)
            return _empty_df(table_name)

        # Pick the most recently modified file
        latest = max(parquet_files, key=lambda p: p.last_modified)

        # Download and read
        file_client = fs_client.get_file_client(latest.name)
        download = file_client.download_file()
        data = download.readall()

        return pd.read_parquet(io.BytesIO(data))

    except Exception as exc:
        logger.error("Failed to load table '%s': %s: %s", table_name, type(exc).__name__, exc)
        _record_load_error(table_name, exc)
        return _empty_df(table_name)


@st.cache_data(ttl=3600, show_spinner="Loading all tables...")
def load_all_tables() -> dict[str, pd.DataFrame]:
    """Load all 9 tables and return as a dictionary."""
    return {name: load_table(name) for name in TABLE_SCHEMAS}
