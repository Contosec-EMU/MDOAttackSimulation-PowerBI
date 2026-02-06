"""Async Azure Data Lake Storage Gen2 writer with Parquet and JSON support."""

import io
import json
import logging
import random
from typing import Any, Dict, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from azure.storage.filedatalake.aio import DataLakeServiceClient

from config import STORAGE_UPLOAD_BACKOFF_BASE, STORAGE_UPLOAD_MAX_RETRIES

logger = logging.getLogger(__name__)

# Explicit Parquet schema definitions per endpoint
SCHEMA_DEFINITIONS: Dict[str, Dict[str, str]] = {
    "repeatOffenders": {
        "snapshotDateUtc": "datetime",
        "userId": "string",
        "displayName": "string",
        "email": "string",
        "repeatOffenceCount": "int32",
    },
    "simulationUserCoverage": {
        "snapshotDateUtc": "datetime",
        "userId": "string",
        "displayName": "string",
        "email": "string",
        "simulationCount": "int32",
        "latestSimulationDateTime": "datetime",
        "clickCount": "int32",
        "compromisedCount": "int32",
    },
    "trainingUserCoverage": {
        "snapshotDateUtc": "datetime",
        "userId": "string",
        "displayName": "string",
        "email": "string",
        "assignedTrainingsCount": "int32",
        "completedTrainingsCount": "int32",
        "inProgressTrainingsCount": "int32",
        "notStartedTrainingsCount": "int32",
    },
    "simulations": {
        "snapshotDateUtc": "datetime",
        "simulationId": "string",
        "displayName": "string",
        "description": "string",
        "status": "string",
        "attackType": "string",
        "attackTechnique": "string",
        "createdDateTime": "datetime",
        "launchDateTime": "datetime",
        "completionDateTime": "datetime",
        "lastModifiedDateTime": "datetime",
        "isAutomated": "bool",
        "automationId": "string",
        "durationInDays": "int32",
        "payloadId": "string",
        "payloadDisplayName": "string",
        "reportTotalUserCount": "int32",
        "reportCompromisedCount": "int32",
        "reportClickCount": "int32",
        "reportReportedCount": "int32",
        "createdById": "string",
        "createdByDisplayName": "string",
        "createdByEmail": "string",
        "lastModifiedById": "string",
        "lastModifiedByDisplayName": "string",
        "lastModifiedByEmail": "string",
    },
    "simulationUsers": {
        "snapshotDateUtc": "datetime",
        "simulationId": "string",
        "userId": "string",
        "email": "string",
        "displayName": "string",
        "compromisedDateTime": "datetime",
        "reportedPhishDateTime": "datetime",
        "assignedTrainingsCount": "int32",
        "completedTrainingsCount": "int32",
        "inProgressTrainingsCount": "int32",
        "isCompromised": "bool",
    },
    "simulationUserEvents": {
        "snapshotDateUtc": "datetime",
        "simulationId": "string",
        "userId": "string",
        "eventName": "string",
        "eventDateTime": "datetime",
        "browser": "string",
        "ipAddress": "string",
        "osPlatformDeviceDetails": "string",
    },
    "trainings": {
        "snapshotDateUtc": "datetime",
        "trainingId": "string",
        "displayName": "string",
        "description": "string",
        "durationInMinutes": "int32",
        "source": "string",
        "type": "string",
        "availabilityStatus": "string",
        "hasEvaluation": "bool",
        "lastModifiedDateTime": "datetime",
        "createdById": "string",
        "createdByDisplayName": "string",
        "createdByEmail": "string",
        "lastModifiedById": "string",
        "lastModifiedByDisplayName": "string",
        "lastModifiedByEmail": "string",
    },
    "payloads": {
        "snapshotDateUtc": "datetime",
        "payloadId": "string",
        "displayName": "string",
        "description": "string",
        "simulationAttackType": "string",
        "platform": "string",
        "status": "string",
        "source": "string",
        "predictedCompromiseRate": "float64",
        "complexity": "string",
        "technique": "string",
        "theme": "string",
        "brand": "string",
        "industry": "string",
        "isCurrentEvent": "bool",
        "isControversial": "bool",
        "lastModifiedDateTime": "datetime",
        "createdById": "string",
        "createdByDisplayName": "string",
        "createdByEmail": "string",
        "lastModifiedById": "string",
        "lastModifiedByDisplayName": "string",
        "lastModifiedByEmail": "string",
    },
    "users": {
        "snapshotDateUtc": "datetime",
        "userId": "string",
        "displayName": "string",
        "givenName": "string",
        "surname": "string",
        "mail": "string",
        "department": "string",
        "companyName": "string",
        "city": "string",
        "country": "string",
        "jobTitle": "string",
        "accountEnabled": "bool",
    },
}


class AsyncADLSWriter:
    """Async writer for Azure Data Lake Storage Gen2.

    Supports writing JSON (raw archival) and Parquet (optimized for Power BI)
    with retry logic and explicit schema definitions.

    Usage:
        async with AsyncADLSWriter("https://account.dfs.core.windows.net") as writer:
            await writer.write_parquet("curated", "path/file.parquet", data, "tableName")
    """

    def __init__(self, account_url: str, credential=None) -> None:
        self._account_url = self._normalize_url(account_url)
        self._credential = credential
        self._service_client: Optional[DataLakeServiceClient] = None

    @staticmethod
    def _normalize_url(account_url: str) -> str:
        account_url = account_url.rstrip("/")
        if not account_url.startswith("https://"):
            account_url = f"https://{account_url}"
        if ".dfs.core.windows.net" not in account_url:
            account_name = account_url.replace("https://", "").split(".")[0]
            account_url = f"https://{account_name}.dfs.core.windows.net"
        return account_url

    async def __aenter__(self) -> "AsyncADLSWriter":
        if self._credential is None:
            self._credential = AsyncDefaultAzureCredential()
        self._service_client = DataLakeServiceClient(
            account_url=self._account_url,
            credential=self._credential,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._service_client:
            await self._service_client.close()
        if hasattr(self._credential, "close"):
            await self._credential.close()

    @property
    def service_client(self) -> DataLakeServiceClient:
        if self._service_client is None:
            raise RuntimeError("Writer not initialized. Use 'async with' context manager.")
        return self._service_client

    async def _ensure_container_exists(self, container: str) -> None:
        """Verify container exists, create if not."""
        try:
            file_system_client = self.service_client.get_file_system_client(container)
            exists = await file_system_client.exists()
            if not exists:
                logger.info(f"Creating container: {container}")
                await file_system_client.create_file_system()
        except ResourceExistsError:
            pass  # Container already exists, safe to continue
        except Exception as e:
            logger.error(f"Failed to verify/create container {container}: {e}")
            raise

    async def _upload_with_retry(self, file_client, data: bytes, max_retries: int = STORAGE_UPLOAD_MAX_RETRIES) -> None:
        """Upload data with retry logic for transient failures."""
        import asyncio
        for attempt in range(max_retries):
            try:
                await file_client.upload_data(data, overwrite=True)
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = (2 ** attempt) * STORAGE_UPLOAD_BACKOFF_BASE + random.uniform(0, 1)
                logger.warning(f"Upload failed (attempt {attempt + 1}): {e}. Retrying in {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)

    async def write_json(self, container: str, path: str, data: List[Dict[str, Any]]) -> int:
        """Write JSON data to ADLS Gen2."""
        if not data:
            logger.warning(f"No data to write to {container}/{path}")
            return 0

        await self._ensure_container_exists(container)
        json_bytes = json.dumps(data, indent=2, default=str).encode("utf-8")

        file_system_client = self.service_client.get_file_system_client(container)
        file_client = file_system_client.get_file_client(path)
        await self._upload_with_retry(file_client, json_bytes)

        logger.info(f"Written {len(data)} records to {container}/{path}")
        return len(data)

    async def write_parquet(
        self,
        container: str,
        path: str,
        data: List[Dict[str, Any]],
        schema_name: Optional[str] = None,
    ) -> int:
        """Write data as Parquet to ADLS Gen2, optimized for Power BI.

        Args:
            container: Storage container name
            path: File path within container
            data: List of record dictionaries
            schema_name: Name of the table for explicit schema application
        """
        if not data:
            logger.warning(f"No data to write to {container}/{path}")
            return 0

        df = pd.DataFrame(data)

        if schema_name and schema_name in SCHEMA_DEFINITIONS:
            df = self._apply_explicit_schema(df, schema_name)
        else:
            df = self._optimize_schema_for_powerbi(df)

        parquet_buffer = io.BytesIO()
        df.to_parquet(
            parquet_buffer,
            engine="pyarrow",
            compression="snappy",
            index=False,
            use_deprecated_int96_timestamps=False,
            coerce_timestamps="ms",
            allow_truncated_timestamps=True,
        )
        parquet_bytes = parquet_buffer.getvalue()

        await self._ensure_container_exists(container)
        file_system_client = self.service_client.get_file_system_client(container)
        file_client = file_system_client.get_file_client(path)
        await self._upload_with_retry(file_client, parquet_bytes)

        logger.info(f"Written {len(data)} records to {container}/{path} (Parquet, {len(parquet_bytes):,} bytes)")
        return len(data)

    @staticmethod
    def _apply_explicit_schema(df: pd.DataFrame, schema_name: str) -> pd.DataFrame:
        """Apply explicit schema definition for a known table."""
        schema = SCHEMA_DEFINITIONS[schema_name]
        for col, dtype in schema.items():
            if col not in df.columns:
                continue
            try:
                if dtype == "datetime":
                    df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
                elif dtype == "int32":
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int32")
                elif dtype == "float64":
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                elif dtype == "bool":
                    df[col] = df[col].astype("boolean")
                elif dtype == "string":
                    df[col] = df[col].astype("string")
            except Exception as e:
                logger.warning(f"Schema conversion failed for {col} ({dtype}): {e}")
        return df

    @staticmethod
    def _optimize_schema_for_powerbi(df: pd.DataFrame) -> pd.DataFrame:
        """Fallback schema optimization using column name heuristics."""
        for col in df.columns:
            if "date" in col.lower() or "datetime" in col.lower():
                if df[col].dtype == "object":
                    try:
                        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
                    except Exception as e:
                        logger.warning(f"Could not convert {col} to datetime: {e}")
            elif "count" in col.lower() or col.endswith("Count"):
                if df[col].dtype == "object" or df[col].dtype == "float64":
                    try:
                        df[col] = df[col].fillna(0).astype("int32")
                    except Exception as e:
                        logger.warning(f"Could not convert {col} to int32: {e}")
            elif df[col].dtype == "object":
                try:
                    df[col] = df[col].astype("string")
                except Exception as e:
                    logger.warning(f"Could not convert {col} to string: {e}")
        return df
