"""
MDO Attack Simulation Training - Graph API Ingestion Function

Azure Function app that ingests Microsoft Defender for Office 365 Attack Simulation
Training data from Microsoft Graph API into ADLS Gen2 as Parquet files,
optimized for Power BI consumption.

Endpoints:
    - Timer trigger: Scheduled ingestion (default: every hour at :00)
    - GET /api/health: Health check
    - POST /api/test-run: Manual trigger for testing
    - GET /api/sync-status: View sync configuration and state
    - POST /api/reset-sync-state: Reset state to force full sync

Data Sources (9 Parquet tables):
    - repeatOffenders (v1.0)
    - simulationUserCoverage (v1.0)
    - trainingUserCoverage (v1.0)
    - simulations (beta)
    - simulationUsers (beta)
    - simulationUserEvents (beta)
    - trainings (beta)
    - payloads (beta)
    - users (v1.0)
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from config import (
    FunctionConfig,
    INCREMENTAL_LOOKBACK_DAYS,
    API_CONFIGS,
    EXTENDED_API_CONFIGS,
    APIEndpoint,
)
from clients.graph_api import AsyncGraphAPIClient
from clients.adls_writer import AsyncADLSWriter
from processors.transformers import (
    process_repeat_offenders,
    process_simulation_user_coverage,
    process_training_user_coverage,
    process_simulations,
    process_simulation_users,
    process_simulation_user_events,
    process_trainings,
    process_payloads,
    process_users,
)
from services.sync_state import SyncStateManager
from utils.security import add_security_headers

# Initialize Function App
app = func.FunctionApp()

# Configure logging
logger = logging.getLogger(__name__)

# Map processor names to functions
PROCESSOR_MAP = {
    "process_repeat_offenders": process_repeat_offenders,
    "process_simulation_user_coverage": process_simulation_user_coverage,
    "process_training_user_coverage": process_training_user_coverage,
    "process_simulations": process_simulations,
    "process_trainings": process_trainings,
    "process_payloads": process_payloads,
}


def get_key_vault_secret(vault_url: str, secret_name: str) -> str:
    """Retrieve secret from Key Vault using managed identity."""
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)
    secret = client.get_secret(secret_name)
    return secret.value


async def _process_and_write(
    graph_client: AsyncGraphAPIClient,
    adls_writer: AsyncADLSWriter,
    ep_config: APIEndpoint,
    snapshot_date: str,
    use_beta: bool = False,
    lookback_date: datetime = None,
    sync_mode: str = "full",
) -> int:
    """Fetch, process, and write data for a single API endpoint.

    Returns:
        Number of records processed
    """
    api_name = ep_config.name
    endpoint = ep_config.endpoint
    processor_name = ep_config.processor_name

    # Apply incremental filter if supported
    if (sync_mode == "incremental"
            and ep_config.supports_incremental
            and lookback_date):
        filter_template = ep_config.incremental_filter or ""
        if filter_template:
            lookback_str = lookback_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            filter_clause = filter_template.format(lookback_date=lookback_str)
            endpoint = f"{endpoint}?{filter_clause}"
            logger.info(f"Using incremental filter for {api_name}")

    # Fetch data
    raw_data: List[Dict[str, Any]] = []
    async for item in graph_client.get_paginated_data(endpoint, use_beta=use_beta):
        raw_data.append(item)
    logger.info(f"Fetched {len(raw_data)} records from {api_name}")

    if not raw_data:
        return 0

    # Process data
    processor = PROCESSOR_MAP.get(processor_name)
    if not processor:
        logger.error(f"Unknown processor: {processor_name}")
        return 0
    processed_data = processor(raw_data, snapshot_date)

    # Write to curated (Parquet) and raw (JSON) containers
    curated_path = f"{api_name}/{snapshot_date}/{api_name}.parquet"
    await adls_writer.write_parquet("curated", curated_path, processed_data, schema_name=api_name)

    raw_path = f"{api_name}/{snapshot_date}/{api_name}_raw.json"
    await adls_writer.write_json("raw", raw_path, raw_data)

    return len(processed_data)


async def _process_simulation_details(
    graph_client: AsyncGraphAPIClient,
    adls_writer: AsyncADLSWriter,
    simulation_ids: List[str],
    snapshot_date: str,
) -> int:
    """Fetch simulationUsers and events for each simulation, plus user enrichment.

    Returns:
        Total number of records processed
    """
    total = 0
    all_user_ids: set = set()
    all_sim_users: List[Dict[str, Any]] = []
    all_sim_events: List[Dict[str, Any]] = []

    for sim_id in simulation_ids:
        logger.info(f"Fetching users for simulation {sim_id}...")
        endpoint = f"security/attackSimulation/simulations/{sim_id}/report/simulationUsers"
        raw_users: List[Dict[str, Any]] = []
        try:
            async for item in graph_client.get_paginated_data(endpoint, use_beta=True):
                raw_users.append(item)
        except Exception as e:
            logger.warning(f"Failed to fetch users for simulation {sim_id}: {e}")
            continue

        if raw_users:
            sim_users = process_simulation_users(raw_users, snapshot_date, simulation_id=sim_id)
            sim_events = process_simulation_user_events(raw_users, snapshot_date, simulation_id=sim_id)
            all_sim_users.extend(sim_users)
            all_sim_events.extend(sim_events)

            # Collect user IDs for enrichment
            for user in raw_users:
                sim_user = user.get("simulationUser", {}) or {}
                uid = sim_user.get("userId")
                if uid:
                    all_user_ids.add(uid)

    # Write simulation users
    if all_sim_users:
        path = f"simulationUsers/{snapshot_date}/simulationUsers.parquet"
        await adls_writer.write_parquet("curated", path, all_sim_users, schema_name="simulationUsers")
        await adls_writer.write_json("raw", f"simulationUsers/{snapshot_date}/simulationUsers_raw.json", all_sim_users)
        total += len(all_sim_users)

    # Write simulation user events
    if all_sim_events:
        path = f"simulationUserEvents/{snapshot_date}/simulationUserEvents.parquet"
        await adls_writer.write_parquet("curated", path, all_sim_events, schema_name="simulationUserEvents")
        await adls_writer.write_json("raw", f"simulationUserEvents/{snapshot_date}/simulationUserEvents_raw.json", all_sim_events)
        total += len(all_sim_events)

    # Enrich with Entra user details
    if all_user_ids:
        total += await _enrich_users(graph_client, adls_writer, list(all_user_ids), snapshot_date)

    return total


async def _enrich_users(
    graph_client: AsyncGraphAPIClient,
    adls_writer: AsyncADLSWriter,
    user_ids: List[str],
    snapshot_date: str,
) -> int:
    """Fetch Entra ID user details for enrichment."""
    logger.info(f"Enriching {len(user_ids)} users from Entra ID...")
    raw_users: List[Dict[str, Any]] = []

    for uid in user_ids:
        try:
            user_data = await graph_client.get_single_resource(f"users/{uid}", use_beta=False)
            raw_users.append(user_data)
        except Exception as e:
            logger.warning(f"Failed to fetch user {uid}: {e}")
            raw_users.append({"id": uid, "accountEnabled": None})

    if raw_users:
        processed = process_users(raw_users, snapshot_date)
        path = f"users/{snapshot_date}/users.parquet"
        await adls_writer.write_parquet("curated", path, processed, schema_name="users")
        await adls_writer.write_json("raw", f"users/{snapshot_date}/users_raw.json", raw_users)
        return len(processed)
    return 0


async def run_ingestion_async(is_past_due: bool = False) -> Dict[str, Any]:
    """Core async ingestion logic.

    Returns:
        Dict with total_records, elapsed_seconds, sync_mode, snapshot_date
    """
    start_time = time.time()
    config = FunctionConfig.from_environment()
    snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    correlation_id = str(uuid.uuid4())

    logger.info(
        f"Starting ingestion - Snapshot: {snapshot_date}, "
        f"Mode: {config.sync_mode}, Correlation: {correlation_id}"
    )
    if is_past_due:
        logger.warning("Timer is running late!")

    client_secret = get_key_vault_secret(config.key_vault_url, "graph-client-secret")

    async with AsyncGraphAPIClient(config.tenant_id, config.graph_client_id, client_secret) as graph_client:
        async with AsyncADLSWriter(config.storage_account_url) as adls_writer:
            state_manager = SyncStateManager(adls_writer)
            lookback_date = await state_manager.get_lookback_date()

            if config.sync_mode == "incremental":
                logger.info(f"Incremental sync: looking back to {lookback_date.isoformat()}")

            total_records = 0
            processed_sim_ids: List[str] = []

            # Process core API endpoints (v1.0, always run)
            for ep_config in API_CONFIGS:
                try:
                    count = await _process_and_write(
                        graph_client, adls_writer, ep_config,
                        snapshot_date, use_beta=False,
                        lookback_date=lookback_date, sync_mode=config.sync_mode,
                    )
                    total_records += count
                except Exception as e:
                    logger.error(f"Failed to process {ep_config.name}: {e}", exc_info=True)
                    raise

            # Process extended API endpoints (beta, optional)
            if config.sync_simulations:
                for ep_config in EXTENDED_API_CONFIGS:
                    try:
                        count = await _process_and_write(
                            graph_client, adls_writer, ep_config,
                            snapshot_date, use_beta=True,
                            lookback_date=lookback_date, sync_mode=config.sync_mode,
                        )
                        total_records += count

                        # Track simulation IDs for detail fetching
                        if ep_config.name == "simulations" and count > 0:
                            async for item in graph_client.get_paginated_data(
                                ep_config.endpoint, use_beta=True
                            ):
                                sim_id = item.get("id")
                                if sim_id:
                                    processed_sim_ids.append(sim_id)

                    except Exception as e:
                        logger.warning(f"Failed to process extended endpoint {ep_config.name}: {e}")

            # Process simulation user details (if simulations were synced)
            if config.sync_simulations and processed_sim_ids:
                try:
                    detail_count = await _process_simulation_details(
                        graph_client, adls_writer, processed_sim_ids, snapshot_date
                    )
                    total_records += detail_count
                except Exception as e:
                    logger.warning(f"Failed to process simulation details: {e}")

            # Update sync state
            if config.sync_mode == "incremental":
                await state_manager.update_after_sync(processed_sim_ids)

            elapsed = time.time() - start_time
            logger.info(
                f"Ingestion complete. Records: {total_records}, "
                f"Time: {elapsed:.2f}s, Mode: {config.sync_mode}"
            )

            return {
                "total_records": total_records,
                "elapsed_seconds": elapsed,
                "sync_mode": config.sync_mode,
                "snapshot_date": snapshot_date,
                "correlation_id": correlation_id,
            }


# ============================================================================
# Azure Function Triggers and Routes
# ============================================================================

@app.timer_trigger(
    schedule="%TIMER_SCHEDULE%",
    arg_name="timer",
    run_on_startup=False,
)
async def mdo_attack_simulation_ingest(timer: func.TimerRequest) -> None:
    """Timer-triggered function to ingest MDO Attack Simulation Training data."""
    correlation_id = str(uuid.uuid4())
    logger.info(f"Timer trigger started - Correlation ID: {correlation_id}")
    await run_ingestion_async(is_past_due=timer.past_due)


@app.function_name(name="health_check")
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
async def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint."""
    response = func.HttpResponse(
        json.dumps({"status": "healthy"}),
        mimetype="application/json",
        status_code=200,
    )
    return add_security_headers(response)


@app.function_name(name="test_run")
@app.route(route="test-run", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def test_run(req: func.HttpRequest) -> func.HttpResponse:
    """Manual trigger endpoint for testing."""
    correlation_id = str(uuid.uuid4())
    logger.info(f"Test run initiated - Correlation ID: {correlation_id}")

    try:
        result = await run_ingestion_async(is_past_due=False)
        response = func.HttpResponse(
            json.dumps({
                "status": "success",
                "message": "Ingestion completed",
                "correlationId": correlation_id,
                "details": result,
            }),
            mimetype="application/json",
            status_code=200,
        )
        return add_security_headers(response)
    except Exception:
        logger.error(f"Test run failed - Correlation ID: {correlation_id}", exc_info=True)
        response = func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": "An error occurred during ingestion. Check logs for details.",
                "correlationId": correlation_id,
            }),
            mimetype="application/json",
            status_code=500,
        )
        return add_security_headers(response)


@app.function_name(name="sync_status")
@app.route(route="sync-status", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
async def sync_status(req: func.HttpRequest) -> func.HttpResponse:
    """Get current sync configuration and state."""
    try:
        config = FunctionConfig.from_environment()
        result: Dict[str, Any] = {
            "configuration": {
                "sync_mode": config.sync_mode,
                "sync_simulations": config.sync_simulations,
                "incremental_lookback_days": INCREMENTAL_LOOKBACK_DAYS,
                "timer_schedule": config.timer_schedule,
            },
            "state": None,
            "endpoints": {
                "core": [c.name for c in API_CONFIGS],
                "extended": [c.name for c in EXTENDED_API_CONFIGS],
            },
        }

        async with AsyncADLSWriter(config.storage_account_url) as adls_writer:
            state_manager = SyncStateManager(adls_writer)
            state = await state_manager.load_state()
            lookback = await state_manager.get_lookback_date()
            result["state"] = {
                "last_sync_utc": state.get("last_sync_utc"),
                "last_successful_sync_utc": state.get("last_successful_sync_utc"),
                "tracked_simulation_count": len(state.get("processed_simulation_ids", [])),
                "lookback_date": lookback.isoformat(),
                "version": state.get("version"),
            }

        response = func.HttpResponse(
            json.dumps(result, indent=2, default=str),
            mimetype="application/json",
            status_code=200,
        )
        return add_security_headers(response)

    except Exception as e:
        logger.error(f"Sync status check failed: {e}", exc_info=True)
        response = func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to retrieve sync status."}),
            mimetype="application/json",
            status_code=500,
        )
        return add_security_headers(response)


@app.function_name(name="reset_sync_state")
@app.route(route="reset-sync-state", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def reset_sync_state(req: func.HttpRequest) -> func.HttpResponse:
    """Reset sync state to force a full sync on next run."""
    try:
        config = FunctionConfig.from_environment()
        async with AsyncADLSWriter(config.storage_account_url) as adls_writer:
            state_manager = SyncStateManager(adls_writer)
            default_state = state_manager._default_state()
            await state_manager.save_state(default_state)

        response = func.HttpResponse(
            json.dumps({
                "status": "success",
                "message": "Sync state reset. Next run will perform a full sync.",
                "new_state": default_state,
            }, indent=2),
            mimetype="application/json",
            status_code=200,
        )
        return add_security_headers(response)

    except Exception as e:
        logger.error(f"Failed to reset sync state: {e}", exc_info=True)
        response = func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to reset sync state."}),
            mimetype="application/json",
            status_code=500,
        )
        return add_security_headers(response)
