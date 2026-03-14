"""Tests for clients/graph_api.py — AsyncGraphAPIClient (fully mocked HTTP)."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
import pytest_asyncio

from clients.graph_api import AsyncGraphAPIClient
from config import GRAPH_BASE_URL_BETA, GRAPH_BASE_URL_V1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_token_response(access_token="test-token-abc", expires_in=3600):
    """Create a mock token endpoint response."""
    resp = AsyncMock()
    resp.status = 200
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value={
        "access_token": access_token,
        "expires_in": expires_in,
    })
    # Async context manager support
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_graph_response(data=None, status=200, headers=None):
    """Create a mock Graph API GET response."""
    resp = AsyncMock()
    resp.status = status
    resp.headers = headers or {}
    resp.json = AsyncMock(return_value=data or {})

    if 400 <= status < 600:
        resp.raise_for_status = MagicMock(side_effect=aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=status, message="error"
        ))
    else:
        resp.raise_for_status = MagicMock()

    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    """Create an AsyncGraphAPIClient with a mocked session."""
    c = AsyncGraphAPIClient("tenant-1", "client-1", "secret-1")
    c._session = MagicMock(spec=aiohttp.ClientSession)
    c._session.closed = False
    yield c


# ---------------------------------------------------------------------------
# Token caching
# ---------------------------------------------------------------------------

class TestTokenCaching:

    @pytest.mark.asyncio
    async def test_second_call_uses_cached_token(self, client):
        """Second _get_access_token call should not hit the token endpoint again."""
        token_resp = _make_token_response("token-A")
        client._session.post = MagicMock(return_value=token_resp)

        token1 = await client._get_access_token()
        token2 = await client._get_access_token()

        assert token1 == "token-A"
        assert token2 == "token-A"
        # Token endpoint should be called exactly once
        assert client._session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_expired_token_is_refreshed(self, client):
        """Token that has expired should trigger a new request."""
        token_resp1 = _make_token_response("token-old", expires_in=3600)
        token_resp2 = _make_token_response("token-new", expires_in=3600)
        client._session.post = MagicMock(side_effect=[token_resp1, token_resp2])

        # First fetch
        await client._get_access_token()
        # Simulate expiration
        client._token_expires = time.time() - 1

        token = await client._get_access_token()
        assert token == "token-new"
        assert client._session.post.call_count == 2


# ---------------------------------------------------------------------------
# Token refresh on 401
# ---------------------------------------------------------------------------

class TestTokenRefreshOn401:

    @pytest.mark.asyncio
    async def test_401_triggers_token_refresh(self, client):
        """A 401 should force token refresh and retry the request."""
        token_resp1 = _make_token_response("token-old")
        token_resp2 = _make_token_response("token-new")
        client._session.post = MagicMock(side_effect=[token_resp1, token_resp2])

        # First GET returns 401, second succeeds
        resp_401 = _make_graph_response(status=401)
        resp_ok = _make_graph_response(data={"value": [{"id": "1"}]})
        client._session.get = MagicMock(side_effect=[resp_401, resp_ok])

        result = await client._make_request("https://graph.microsoft.com/v1.0/test")
        assert result == {"value": [{"id": "1"}]}


# ---------------------------------------------------------------------------
# Retry on 429 with Retry-After
# ---------------------------------------------------------------------------

class TestRetryOn429:

    @pytest.mark.asyncio
    async def test_429_waits_retry_after_header(self, client):
        """429 should wait the Retry-After duration and retry."""
        token_resp = _make_token_response("token-1")
        client._session.post = MagicMock(return_value=token_resp)

        resp_429 = _make_graph_response(
            status=429, headers={"Retry-After": "1"}
        )
        # Override raise_for_status for 429 — don't raise, it's handled
        resp_429.raise_for_status = MagicMock()
        resp_ok = _make_graph_response(data={"value": []})

        client._session.get = MagicMock(side_effect=[resp_429, resp_ok])

        with patch("clients.graph_api.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await client._make_request("https://graph.microsoft.com/v1.0/test")

        assert result == {"value": []}
        mock_sleep.assert_awaited_once_with(1)


# ---------------------------------------------------------------------------
# Retry with exponential backoff on transient failure
# ---------------------------------------------------------------------------

class TestRetryBackoff:

    @pytest.mark.asyncio
    async def test_retries_on_client_error(self, client):
        """Transient ClientError should trigger retry with backoff."""
        token_resp = _make_token_response("token-1")
        client._session.post = MagicMock(return_value=token_resp)

        # Fail twice, then succeed
        side_effects = [
            aiohttp.ClientError("connection reset"),
            aiohttp.ClientError("timeout"),
            _make_graph_response(data={"value": [{"id": "x"}]}),
        ]

        call_count = 0
        original_side_effects = list(side_effects)

        def get_side_effect(*args, **kwargs):
            nonlocal call_count
            effect = original_side_effects[call_count]
            call_count += 1
            if isinstance(effect, Exception):
                raise effect
            return effect

        client._session.get = MagicMock(side_effect=get_side_effect)

        with patch("clients.graph_api.asyncio.sleep", new_callable=AsyncMock):
            with patch("clients.graph_api.random.uniform", return_value=0.5):
                result = await client._make_request(
                    "https://graph.microsoft.com/v1.0/test", retries=3
                )

        assert result == {"value": [{"id": "x"}]}

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_exhausted(self, client):
        """All retries fail → should raise."""
        token_resp = _make_token_response("token-1")
        client._session.post = MagicMock(return_value=token_resp)

        def always_fail(*args, **kwargs):
            raise aiohttp.ClientError("persistent failure")

        client._session.get = MagicMock(side_effect=always_fail)

        with patch("clients.graph_api.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(aiohttp.ClientError):
                await client._make_request(
                    "https://graph.microsoft.com/v1.0/test", retries=2
                )


# ---------------------------------------------------------------------------
# Pagination follows @odata.nextLink
# ---------------------------------------------------------------------------

class TestPagination:

    @pytest.mark.asyncio
    async def test_follows_odata_next_link(self, client):
        """Paginated responses should follow @odata.nextLink."""
        token_resp = _make_token_response("token-1")
        client._session.post = MagicMock(return_value=token_resp)

        page1 = _make_graph_response(data={
            "value": [{"id": "1"}, {"id": "2"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/test?$skip=2",
        })
        page2 = _make_graph_response(data={
            "value": [{"id": "3"}],
        })
        client._session.get = MagicMock(side_effect=[page1, page2])

        items = []
        with patch("clients.graph_api.asyncio.sleep", new_callable=AsyncMock):
            async for item in client.get_paginated_data("test", max_pages=10):
                items.append(item)

        assert len(items) == 3
        assert [i["id"] for i in items] == ["1", "2", "3"]

    @pytest.mark.asyncio
    async def test_single_page_no_next_link(self, client):
        """No @odata.nextLink → only one page fetched."""
        token_resp = _make_token_response("token-1")
        client._session.post = MagicMock(return_value=token_resp)

        page = _make_graph_response(data={"value": [{"id": "a"}]})
        client._session.get = MagicMock(return_value=page)

        items = []
        async for item in client.get_paginated_data("test"):
            items.append(item)

        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_max_pages_safety_limit(self, client):
        """Exceeding max_pages should raise RuntimeError."""
        token_resp = _make_token_response("token-1")
        client._session.post = MagicMock(return_value=token_resp)

        # Every page has a nextLink → infinite loop
        endless_page = _make_graph_response(data={
            "value": [{"id": "x"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/test?$skip=1",
        })
        client._session.get = MagicMock(return_value=endless_page)

        with patch("clients.graph_api.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="safety limit"):
                items = []
                async for item in client.get_paginated_data("test", max_pages=3):
                    items.append(item)


# ---------------------------------------------------------------------------
# get_single_resource
# ---------------------------------------------------------------------------

class TestGetSingleResource:

    @pytest.mark.asyncio
    async def test_returns_data(self, client):
        token_resp = _make_token_response("token-1")
        client._session.post = MagicMock(return_value=token_resp)

        data = {"id": "sim-1", "displayName": "Test Simulation"}
        resp = _make_graph_response(data=data)
        client._session.get = MagicMock(return_value=resp)

        result = await client.get_single_resource("security/attackSimulation/simulations/sim-1")
        assert result["id"] == "sim-1"

    @pytest.mark.asyncio
    async def test_uses_v1_url_by_default(self, client):
        token_resp = _make_token_response("token-1")
        client._session.post = MagicMock(return_value=token_resp)

        resp = _make_graph_response(data={"id": "1"})
        client._session.get = MagicMock(return_value=resp)

        await client.get_single_resource("users/me")
        call_url = client._session.get.call_args[0][0]
        assert call_url.startswith(GRAPH_BASE_URL_V1)


# ---------------------------------------------------------------------------
# use_beta flag
# ---------------------------------------------------------------------------

class TestUseBeta:

    @pytest.mark.asyncio
    async def test_use_beta_paginated(self, client):
        token_resp = _make_token_response("token-1")
        client._session.post = MagicMock(return_value=token_resp)

        resp = _make_graph_response(data={"value": [{"id": "b1"}]})
        client._session.get = MagicMock(return_value=resp)

        items = []
        async for item in client.get_paginated_data("test/endpoint", use_beta=True):
            items.append(item)

        call_url = client._session.get.call_args[0][0]
        assert call_url.startswith(GRAPH_BASE_URL_BETA)

    @pytest.mark.asyncio
    async def test_use_beta_single_resource(self, client):
        token_resp = _make_token_response("token-1")
        client._session.post = MagicMock(return_value=token_resp)

        resp = _make_graph_response(data={"id": "1"})
        client._session.get = MagicMock(return_value=resp)

        await client.get_single_resource("test/endpoint", use_beta=True)
        call_url = client._session.get.call_args[0][0]
        assert call_url.startswith(GRAPH_BASE_URL_BETA)
