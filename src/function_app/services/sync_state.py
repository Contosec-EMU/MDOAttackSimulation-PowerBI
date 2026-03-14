"""Sync state management for incremental data processing."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import INCREMENTAL_LOOKBACK_DAYS, STATE_CONTAINER, STATE_FILE

logger = logging.getLogger(__name__)


class SyncStateManager:
    """Manages sync state for incremental processing.

    Stores last sync timestamp and processed simulation IDs in ADLS Gen2
    to enable efficient delta processing on subsequent runs.
    """

    def __init__(self, adls_writer) -> None:
        """Initialize with an AsyncADLSWriter instance.
        
        Args:
            adls_writer: AsyncADLSWriter instance for state persistence
        """
        self.adls_writer = adls_writer
        self._state: Optional[Dict[str, Any]] = None

    async def load_state(self) -> Dict[str, Any]:
        """Load sync state from ADLS Gen2 storage."""
        if self._state is not None:
            return self._state

        try:
            file_system_client = self.adls_writer.service_client.get_file_system_client(STATE_CONTAINER)
            exists = await file_system_client.exists()
            if not exists:
                logger.info(f"State container '{STATE_CONTAINER}' does not exist, will create on save")
                self._state = self._default_state()
                return self._state

            file_client = file_system_client.get_file_client(STATE_FILE)
            file_exists = await file_client.exists()
            if not file_exists:
                logger.info("No existing sync state found, starting fresh")
                self._state = self._default_state()
                return self._state

            download = await file_client.download_file()
            content = await download.readall()
            state_json = content.decode("utf-8")
            self._state = json.loads(state_json)
            logger.info(f"Loaded sync state: last_sync={self._state.get('last_sync_utc')}")
            return self._state

        except Exception as e:
            logger.warning(f"Failed to load sync state: {e}. Starting fresh.")
            self._state = self._default_state()
            return self._state

    async def save_state(self, state: Dict[str, Any]) -> None:
        """Save sync state to ADLS Gen2 storage."""
        try:
            await self.adls_writer._ensure_container_exists(STATE_CONTAINER)

            file_system_client = self.adls_writer.service_client.get_file_system_client(STATE_CONTAINER)
            file_client = file_system_client.get_file_client(STATE_FILE)

            state_json = json.dumps(state, indent=2, default=str)
            await self.adls_writer._upload_with_retry(file_client, state_json.encode("utf-8"))

            self._state = state
            logger.info(f"Saved sync state: last_sync={state.get('last_sync_utc')}")

        except Exception as e:
            logger.error(f"Failed to save sync state: {e}")
            raise

    @staticmethod
    def _default_state() -> Dict[str, Any]:
        """Return default state for fresh sync."""
        return {
            "last_sync_utc": None,
            "last_successful_sync_utc": None,
            "processed_simulation_ids": [],
            "sync_mode": "full",
            "version": "1.0",
        }

    async def get_last_sync_time(self) -> Optional[datetime]:
        """Get the last successful sync time."""
        state = await self.load_state()
        last_sync = state.get("last_successful_sync_utc")
        if last_sync:
            return datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
        return None

    async def get_lookback_date(self) -> datetime:
        """Get the date to look back to for incremental sync."""
        last_sync = await self.get_last_sync_time()
        lookback = datetime.now(timezone.utc) - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)

        if last_sync and last_sync > lookback:
            return last_sync
        return lookback

    async def update_after_sync(self, simulation_ids: Optional[List[str]] = None) -> None:
        """Update state after successful sync.
        
        Args:
            simulation_ids: List of simulation IDs processed in this run
        """
        state = await self.load_state()
        now = datetime.now(timezone.utc).isoformat()
        state["last_sync_utc"] = now
        state["last_successful_sync_utc"] = now

        if simulation_ids:
            existing_ids = set(state.get("processed_simulation_ids", []))
            new_ids = existing_ids.union(set(simulation_ids))
            # Keep only last 10000 IDs to prevent unbounded growth
            state["processed_simulation_ids"] = list(new_ids)[-10000:]

        await self.save_state(state)

    def reset(self) -> None:
        """Reset cached state to force reload on next access."""
        self._state = None
