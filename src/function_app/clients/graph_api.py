"""Async Microsoft Graph API client with pagination and retry support."""

import asyncio
import logging
import random
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import aiohttp

from config import (
    BACKOFF_BASE_SECONDS,
    DEFAULT_RETRY_AFTER_SECONDS,
    GRAPH_API_MAX_RETRIES,
    GRAPH_BASE_URL_BETA,
    GRAPH_BASE_URL_V1,
    PAGINATION_DELAY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    TOKEN_REFRESH_BUFFER_SECONDS,
    TOKEN_URL_TEMPLATE,
    MAX_PAGES_DEFAULT,
)
from utils.security import sanitize_url_for_logging

logger = logging.getLogger(__name__)


class AsyncGraphAPIClient:
    """Async client for Microsoft Graph API with pagination and retry support.

    Handles OAuth2 client credentials authentication, automatic token refresh,
    pagination, rate limiting (429), and retry logic with exponential backoff.

    Usage:
        async with AsyncGraphAPIClient(tenant_id, client_id, secret) as client:
            async for item in client.get_paginated_data("users"):
                print(item)
    """

    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: Optional[str] = None
        self._token_expires: float = 0
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "AsyncGraphAPIClient":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        """Return the active aiohttp session, raising if not initialized."""
        if self._session is None or self._session.closed:
            raise RuntimeError(
                "Client session not initialized. Use 'async with' context manager."
            )
        return self._session

    async def _get_access_token(self, force_refresh: bool = False) -> str:
        """Get OAuth2 access token using client credentials flow.

        Caches the token and automatically refreshes it before expiration
        (with a configurable buffer defined by TOKEN_REFRESH_BUFFER_SECONDS).

        Args:
            force_refresh: If True, bypass cache and request a new token.

        Returns:
            A valid access token string.

        Raises:
            aiohttp.ClientResponseError: If the token endpoint returns an error.
        """
        if (
            not force_refresh
            and self._access_token
            and time.time() < self._token_expires - TOKEN_REFRESH_BUFFER_SECONDS
        ):
            return self._access_token

        token_url = TOKEN_URL_TEMPLATE.format(tenant_id=self.tenant_id)
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }

        async with self.session.post(token_url, data=data) as response:
            response.raise_for_status()
            token_data = await response.json()

        self._access_token = token_data["access_token"]
        self._token_expires = time.time() + token_data.get("expires_in", 3600)
        return self._access_token

    async def _make_request(
        self,
        url: str,
        retries: int = GRAPH_API_MAX_RETRIES,
        _token_retry: bool = False,
    ) -> Dict[str, Any]:
        """Make an async HTTP GET request with retry logic.

        Handles 401 (token refresh), 429 (rate limiting with Retry-After),
        and transient errors with exponential backoff + jitter.

        Args:
            url: The fully-qualified URL to request.
            retries: Maximum number of retry attempts.
            _token_retry: Internal flag to prevent recursive token refreshes.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            aiohttp.ClientResponseError: On non-retryable HTTP errors.
            RuntimeError: If all retries are exhausted.
        """
        headers = {
            "Authorization": f"Bearer {await self._get_access_token()}",
            "Content-Type": "application/json",
        }

        for attempt in range(retries):
            try:
                async with self.session.get(url, headers=headers) as response:
                    if response.status == 401 and not _token_retry:
                        logger.warning("Received 401 Unauthorized. Refreshing token...")
                        try:
                            self._access_token = None
                            self._token_expires = 0
                            return await self._make_request(
                                url, retries=retries, _token_retry=True
                            )
                        except (aiohttp.ClientError, RuntimeError):
                            logger.error("Token refresh failed after 401", exc_info=True)
                            raise

                    if response.status == 429:
                        retry_after = int(
                            response.headers.get(
                                "Retry-After", DEFAULT_RETRY_AFTER_SECONDS
                            )
                        )
                        logger.warning(
                            "Rate limited. Waiting %d seconds...", retry_after
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    if (
                        400 <= response.status < 500
                        and response.status not in (401, 429)
                    ):
                        logger.error(
                            "Non-retryable client error: %d", response.status
                        )
                        response.raise_for_status()

                    response.raise_for_status()
                    return await response.json()

            except aiohttp.ClientResponseError as e:
                # Don't retry non-retryable client errors (4xx except 401/429)
                if 400 <= e.status < 500 and e.status not in (401, 429):
                    raise
                if attempt == retries - 1:
                    raise
                wait_time = (2**attempt) * BACKOFF_BASE_SECONDS + random.uniform(0, 2)
                logger.warning(
                    "Request failed (attempt %d/%d): %s. Retrying in %.2fs...",
                    attempt + 1,
                    retries,
                    e,
                    wait_time,
                )
                await asyncio.sleep(wait_time)
            except aiohttp.ClientError as e:
                if attempt == retries - 1:
                    raise
                wait_time = (2**attempt) * BACKOFF_BASE_SECONDS + random.uniform(0, 2)
                logger.warning(
                    "Request failed (attempt %d/%d): %s. Retrying in %.2fs...",
                    attempt + 1,
                    retries,
                    e,
                    wait_time,
                )
                await asyncio.sleep(wait_time)

        raise RuntimeError(f"Failed to complete request after {retries} retries")

    async def get_paginated_data(
        self,
        endpoint: str,
        max_pages: int = MAX_PAGES_DEFAULT,
        use_beta: bool = False,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch all pages of data from a Graph API endpoint.

        Yields individual items from each page's ``value`` array, following
        ``@odata.nextLink`` for pagination.

        Args:
            endpoint: The Graph API endpoint path (without base URL).
            max_pages: Maximum number of pages to fetch (safety limit).
            use_beta: If True, use the beta API base URL instead of v1.0.

        Yields:
            Individual resource dictionaries from the ``value`` array.

        Raises:
            RuntimeError: If max_pages is exceeded.
        """
        base_url = GRAPH_BASE_URL_BETA if use_beta else GRAPH_BASE_URL_V1
        url: Optional[str] = f"{base_url}/{endpoint}"
        page_count = 0

        while url:
            page_count += 1
            if page_count > max_pages:
                raise RuntimeError(
                    f"Pagination safety limit exceeded: {max_pages} pages"
                )

            logger.info(
                "Fetching page %d: %s...", page_count, sanitize_url_for_logging(url)
            )
            data = await self._make_request(url)

            for item in data.get("value", []):
                yield item

            url = data.get("@odata.nextLink")
            if url:
                await asyncio.sleep(PAGINATION_DELAY_SECONDS)

    async def get_single_resource(
        self, endpoint: str, use_beta: bool = False,
        select: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Fetch a single resource from Graph API (no pagination).

        Useful for fetching individual resources such as user profiles
        or simulation details by ID.

        Args:
            endpoint: The Graph API endpoint path (without base URL).
            use_beta: If True, use the beta API base URL instead of v1.0.
            select: Optional list of fields to include via $select query param.

        Returns:
            Parsed JSON response as a dictionary.
        """
        base_url = GRAPH_BASE_URL_BETA if use_beta else GRAPH_BASE_URL_V1
        url = f"{base_url}/{endpoint}"
        if select:
            fields = ",".join(select)
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}$select={fields}"
        return await self._make_request(url)
