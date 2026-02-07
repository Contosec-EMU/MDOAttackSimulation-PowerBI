# Copilot Instructions

## Architecture

This is an Azure Functions v4 (Python 3.11) data pipeline that ingests Microsoft Defender for Office 365 Attack Simulation Training data from Microsoft Graph API → ADLS Gen2 (Parquet) → Power BI / Streamlit.

**Two application components:**

- **`src/function_app/`** — Azure Function with timer + HTTP triggers. Async throughout (`aiohttp` for Graph API, Azure SDK async for storage). Produces 9 Parquet tables from Graph API data.
- **`src/dashboard/`** — Streamlit executive dashboard (Plotly charts, Fluent Design CSS). Reads the same Parquet data from ADLS Gen2. Deployed to its own App Service.

**Data flow:** Timer trigger → OAuth2 via Key Vault → paginate 9 Graph API endpoints → transform to flat dicts → write Parquet (curated/) + JSON (raw/) to ADLS Gen2, date-partitioned.

**Adding a new Graph API endpoint** requires changes in 4 places: `config.py` (APIEndpoint), `processors/transformers.py` (processor function), `clients/adls_writer.py` (PyArrow schema in SCHEMA_DEFINITIONS), and `function_app.py` (PROCESSOR_MAP registration).

## Build, Test, and Lint

All commands run from the repo root. The venv and dependencies live under `src/function_app/`.

```bash
# Setup
cd src/function_app
python3.11 -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux
pip install -r requirements-dev.txt

# Tests (run from src/function_app with PYTHONPATH set)
cd src/function_app
python -m pytest ../../tests/ -v --cov=.

# Single test file
python -m pytest ../../tests/test_processors.py -v

# Single test by keyword
python -m pytest ../../tests/ -k "test_sanitize" -v

# Lint
ruff check src/function_app/

# Type check (limited scope, ignore-missing-imports)
mypy src/function_app/config.py src/function_app/utils/ src/function_app/processors/ --ignore-missing-imports
```

Tests mock all Azure SDK and aiohttp dependencies via `conftest.py` stubs — no real Azure credentials needed.

## Key Conventions

- **All I/O is async** — never use synchronous HTTP or storage calls in client/service code.
- **Type hints required** on all public functions and methods.
- **`sanitize_string()`** must be called on all external-sourced strings (Graph API responses). Located in `utils/security.py`.
- **`add_security_headers()`** must wrap every HTTP response from the Function App.
- **Logging** — use `logging.getLogger(__name__)`, never `print()`. Never log secrets or PII.
- **Conventional Commits** — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.
- **Power BI reports** use PBIR format (`.pbip` project files). `_Measures` (not `Measures`) for the DAX measures table — `Measures` is a reserved TMDL name.
- **Infrastructure** is Bicep (`infra/main.bicep`). Parameters in `main.bicepparam` — the `.example` variant is safe to commit; the real one contains tenant-specific values.

## Graph API Details

- Core endpoints (v1.0, always run): `repeatOffenders`, `simulationUserCoverage`, `trainingUserCoverage`
- Extended endpoints (beta, `SYNC_SIMULATIONS=true`): `simulations`, `trainings`, `payloads`
- Simulation detail endpoints (beta, per-simulation): `simulationUsers`, `simulationUserEvents`, `users` (Entra ID enrichment)
- Required permissions: `AttackSimulation.Read.All` + `User.Read.All` (application, not delegated)
