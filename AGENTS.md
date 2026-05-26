# Agents Context — report-mdo-attack-sim

## Summary
Azure data pipeline that ingests MDO Attack Simulation Training data from Microsoft Graph into ADLS Gen2 (Parquet) for Power BI. Bypasses the XDR-only reporting limitation.

## Stack
- Python 3.11
- Azure Functions v4 (timer-triggered)
- Microsoft Graph API
- Azure Data Lake Storage Gen2 (Parquet, Snappy)
- Bicep IaC
- async (`aiohttp` + Azure SDK async)

## Run / Test
```powershell
# Local dev (requires Azure Functions Core Tools)
cd src
func start

# Tests
pytest tests/

# Lint
ruff check src tests
mypy src
```

## Layout
- `src/` — function app source
- `tests/` — pytest suite
- `infra/` — Bicep templates for ADLS, Functions, Key Vault, etc.
- `scripts/` — deployment + utility scripts
- `reports/` — Power BI report (PBIX/TMDL)
- `docs/` — design + usage docs

## GitHub
- Remote: `https://github.com/Contosec-EMU/report-mdo-attack-sim.git`
- Active account: `gh auth switch --user carlossuarez-msft` (Contosec-EMU org is owned by personal account)

## Notes
- 9 data tables: simulations, users, events, trainings, payloads, etc.
- Incremental sync (7-day lookback) — ~70-80% fewer API calls after initial run
- Writer module is decoupled — can target OneLake, Azure SQL, Synapse, or Dataverse instead
- Managed Identity + Key Vault — no secrets in code
