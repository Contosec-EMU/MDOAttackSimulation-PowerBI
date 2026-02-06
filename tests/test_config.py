"""Tests for config.py — FunctionConfig, API endpoint definitions, and constants."""

import pytest

from config import (
    API_CONFIGS,
    EXTENDED_API_CONFIGS,
    FunctionConfig,
    APIEndpoint,
    MAX_STRING_LENGTH,
    GRAPH_BASE_URL_V1,
    GRAPH_BASE_URL_BETA,
    REQUIRED_ENV_VARS,
)


# ===================================================================
# FunctionConfig.from_environment — valid inputs
# ===================================================================

class TestFunctionConfigFromEnvironment:
    """Tests for FunctionConfig.from_environment()."""

    def test_valid_env_returns_config(self, env_vars):
        cfg = FunctionConfig.from_environment()
        assert cfg.tenant_id == env_vars["TENANT_ID"]
        assert cfg.graph_client_id == env_vars["GRAPH_CLIENT_ID"]
        assert cfg.key_vault_url == env_vars["KEY_VAULT_URL"]
        assert cfg.storage_account_url == env_vars["STORAGE_ACCOUNT_URL"]
        assert cfg.timer_schedule == env_vars["TIMER_SCHEDULE"]
        assert cfg.sync_mode == "full"
        assert cfg.sync_simulations is True

    def test_defaults_when_optional_not_set(self, monkeypatch):
        """Only required vars set — optional fields use defaults."""
        for key in REQUIRED_ENV_VARS:
            monkeypatch.setenv(key, {
                "TENANT_ID": "t1",
                "GRAPH_CLIENT_ID": "c1",
                "KEY_VAULT_URL": "https://kv.vault.azure.net",
                "STORAGE_ACCOUNT_URL": "https://st.dfs.core.windows.net",
            }[key])
        # Remove optionals
        monkeypatch.delenv("TIMER_SCHEDULE", raising=False)
        monkeypatch.delenv("SYNC_MODE", raising=False)
        monkeypatch.delenv("SYNC_SIMULATIONS", raising=False)

        cfg = FunctionConfig.from_environment()
        assert cfg.timer_schedule == "0 0 2 * * *"
        assert cfg.sync_mode == "full"
        assert cfg.sync_simulations is True

    def test_incremental_sync_mode(self, env_vars_incremental):
        cfg = FunctionConfig.from_environment()
        assert cfg.sync_mode == "incremental"

    def test_sync_simulations_false(self, monkeypatch, env_vars):
        monkeypatch.setenv("SYNC_SIMULATIONS", "false")
        cfg = FunctionConfig.from_environment()
        assert cfg.sync_simulations is False


# ===================================================================
# FunctionConfig.from_environment — invalid inputs
# ===================================================================

class TestFunctionConfigValidation:
    """Validation error paths in FunctionConfig.from_environment()."""

    def test_missing_required_var_raises(self, monkeypatch, env_vars):
        monkeypatch.delenv("TENANT_ID")
        with pytest.raises(EnvironmentError, match="TENANT_ID"):
            FunctionConfig.from_environment()

    def test_multiple_missing_vars_listed(self, monkeypatch):
        """All required vars missing → error message lists them all."""
        for var in REQUIRED_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(EnvironmentError) as exc_info:
            FunctionConfig.from_environment()
        for var in REQUIRED_ENV_VARS:
            assert var in str(exc_info.value)

    def test_invalid_sync_mode_raises(self, monkeypatch, env_vars):
        monkeypatch.setenv("SYNC_MODE", "delta")
        with pytest.raises(ValueError, match="SYNC_MODE"):
            FunctionConfig.from_environment()

    def test_storage_url_not_https_raises(self, monkeypatch, env_vars):
        monkeypatch.setenv("STORAGE_ACCOUNT_URL", "http://st.dfs.core.windows.net")
        with pytest.raises(ValueError, match="STORAGE_ACCOUNT_URL must start with https://"):
            FunctionConfig.from_environment()

    def test_key_vault_url_not_https_raises(self, monkeypatch, env_vars):
        monkeypatch.setenv("KEY_VAULT_URL", "http://kv.vault.azure.net")
        with pytest.raises(ValueError, match="KEY_VAULT_URL must start with https://"):
            FunctionConfig.from_environment()


# ===================================================================
# API_CONFIGS / EXTENDED_API_CONFIGS
# ===================================================================

class TestAPIConfigs:
    """Verify endpoint lists have expected structure."""

    def test_core_endpoints_count(self):
        assert len(API_CONFIGS) == 3

    def test_extended_endpoints_count(self):
        assert len(EXTENDED_API_CONFIGS) == 3

    def test_all_are_api_endpoint_instances(self):
        for ep in API_CONFIGS + EXTENDED_API_CONFIGS:
            assert isinstance(ep, APIEndpoint)

    def test_core_endpoint_names(self):
        names = {ep.name for ep in API_CONFIGS}
        assert names == {"repeatOffenders", "simulationUserCoverage", "trainingUserCoverage"}

    def test_extended_endpoint_names(self):
        names = {ep.name for ep in EXTENDED_API_CONFIGS}
        assert names == {"simulations", "trainings", "payloads"}

    def test_simulations_supports_incremental(self):
        sim = [ep for ep in EXTENDED_API_CONFIGS if ep.name == "simulations"][0]
        assert sim.supports_incremental is True
        assert sim.incremental_filter is not None

    def test_core_endpoints_not_incremental(self):
        for ep in API_CONFIGS:
            assert ep.supports_incremental is False


# ===================================================================
# Constants sanity checks
# ===================================================================

class TestConstants:
    def test_max_string_length_positive(self):
        assert MAX_STRING_LENGTH > 0

    def test_graph_urls_are_https(self):
        assert GRAPH_BASE_URL_V1.startswith("https://")
        assert GRAPH_BASE_URL_BETA.startswith("https://")

    def test_required_env_vars_list(self):
        assert len(REQUIRED_ENV_VARS) == 4
