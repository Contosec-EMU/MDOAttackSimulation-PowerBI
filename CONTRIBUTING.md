# Contributing to MDO Attack Simulation PowerBI

Thank you for your interest in contributing! This guide covers development setup, architecture, and contribution standards.

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork:
   ```bash
   git clone https://github.com/<your-username>/MDOAttackSimulation_PowerBI.git
   cd MDOAttackSimulation_PowerBI
   ```
3. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

## Development Setup

### Prerequisites

- **Python 3.11** (required for Azure Functions v4)
- **Azure Functions Core Tools v4** (`npm install -g azure-functions-core-tools@4`)
- **Azure CLI** (v2.50+)

### Environment Setup

```bash
cd src/function_app
python3.11 -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes all production dependencies plus `pytest`, `pytest-cov`, `pytest-asyncio`, `ruff`, and `mypy`.

### Local Settings

Copy and edit `local.settings.json`:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "TENANT_ID": "your-tenant-id",
    "GRAPH_CLIENT_ID": "your-client-id",
    "KEY_VAULT_URL": "https://your-keyvault.vault.azure.net/",
    "STORAGE_ACCOUNT_URL": "https://your-storage.dfs.core.windows.net/"
  }
}
```

## Project Structure

```
src/function_app/
├── function_app.py              # Azure Function triggers/routes (thin orchestrator)
├── config.py                    # Constants, FunctionConfig, APIEndpoint dataclass
├── clients/
│   ├── graph_api.py             # AsyncGraphAPIClient (aiohttp, pagination, retry)
│   └── adls_writer.py           # AsyncADLSWriter (Parquet/JSON to ADLS Gen2)
├── services/
│   └── sync_state.py            # SyncStateManager (incremental sync state)
├── processors/
│   └── transformers.py          # Data processor functions (one per API endpoint)
├── utils/
│   └── security.py              # Input sanitization, security headers
├── requirements.txt             # Production dependencies
└── requirements-dev.txt         # Dev/test dependencies (includes production)

tests/
├── conftest.py                  # Shared fixtures (mock clients, sample data)
├── test_config.py               # Config loading and validation tests
├── test_security.py             # Sanitization and security header tests
├── test_processors.py           # Data transformation tests
└── test_graph_client.py         # Graph API client tests

infra/
├── main.bicep                   # Azure resource definitions (Bicep IaC)
└── main.bicepparam              # Deployment parameters
```

### Module Responsibilities

| Module | Responsibility |
|---|---|
| `function_app.py` | Defines triggers/routes, wires dependencies, orchestrates ingestion |
| `config.py` | All constants, `FunctionConfig` env loader, `APIEndpoint` dataclass |
| `clients/graph_api.py` | OAuth2 token management, paginated Graph API calls, retry with backoff |
| `clients/adls_writer.py` | Writes Parquet (curated) and JSON (raw) to ADLS Gen2, schema definitions |
| `services/sync_state.py` | Tracks last-sync timestamps for incremental mode |
| `processors/transformers.py` | Flattens/transforms Graph API responses into Power BI-ready schemas |
| `utils/security.py` | `sanitize_string()`, `add_security_headers()` |

## Running Tests

```bash
# Run all tests with coverage
python -m pytest tests/ -v --cov=src/function_app

# Run a specific test file
python -m pytest tests/test_processors.py -v

# Run tests matching a keyword
python -m pytest tests/ -k "test_sanitize" -v
```

All tests must pass before submitting a PR. Target **≥80% coverage** for new code.

## Linting & Type Checking

```bash
# Lint with ruff
ruff check src/

# Auto-fix lint issues
ruff check src/ --fix

# Type checking with mypy
mypy src/
```

Both `ruff` and `mypy` must pass cleanly. Configure overrides in `pyproject.toml` if needed.

## Code Style

### Async/Await Patterns

All I/O operations use `async`/`await`. Never use synchronous I/O in client or service code.

```python
# ✅ Correct
async def fetch_data(self, endpoint: str) -> list[dict]:
    async with self.session.get(endpoint, headers=self.headers) as resp:
        resp.raise_for_status()
        return await resp.json()

# ❌ Wrong — blocks the event loop
def fetch_data(self, endpoint: str) -> list[dict]:
    return requests.get(endpoint, headers=self.headers).json()
```

### Type Hints

Type hints are **required** on all public functions and methods.

```python
def process_repeat_offenders(raw_data: list[dict], snapshot_date: str) -> list[dict]:
    ...
```

### Logging

Use the `logging` module — no `print()` statements. Never log secrets or PII.

```python
logger = logging.getLogger(__name__)
logger.info("Processing %d records for %s", len(records), endpoint_name)
```

### Security

Always sanitize user-facing strings from external sources using `sanitize_string()` from `utils/security.py`. All HTTP responses must include security headers via `add_security_headers()`.

## Adding New API Endpoints

Follow these steps to add a new Microsoft Graph API endpoint:

### 1. Define the endpoint in `config.py`

```python
APIEndpoint(
    name="new_endpoint_name",
    url="https://graph.microsoft.com/v1.0/security/attackSimulation/newEndpoint",
    description="Description of the data",
)
```

### 2. Add a processor function in `processors/transformers.py`

```python
def process_new_endpoint(raw_data: list[dict], snapshot_date: str) -> list[dict]:
    """Transform raw Graph API response into flat records."""
    records = []
    for item in raw_data:
        records.append({
            "id": sanitize_string(item.get("id")),
            "snapshotDate": snapshot_date,
            # ... additional fields
        })
    return records
```

### 3. Add the schema in `clients/adls_writer.py`

Add an entry to `SCHEMA_DEFINITIONS` mapping the endpoint name to its PyArrow schema:

```python
"new_endpoint_name": pa.schema([
    pa.field("id", pa.string()),
    pa.field("snapshotDate", pa.string()),
    # ... additional fields matching the processor output
]),
```

### 4. Register in `PROCESSOR_MAP` in `function_app.py`

```python
PROCESSOR_MAP = {
    # ... existing entries
    "new_endpoint_name": process_new_endpoint,
}
```

### 5. Add unit tests

Create tests in `tests/test_processors.py` (or a new test file) covering:
- Happy path with representative sample data
- Empty input (`[]`)
- Missing/null fields in the API response
- Sanitization of string fields

## Pull Request Process

### Before Submitting

1. **All tests pass**: `python -m pytest tests/ -v`
2. **Linting clean**: `ruff check src/`
3. **Types check**: `mypy src/`
4. **Documentation updated** if behavior changes

### PR Description

Include:
- **What** changed and **why**
- Testing performed (unit tests, manual verification)
- Related issue numbers (e.g., `Closes #42`)

## Commit Conventions

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>: <short description>
```

| Type | Use for |
|---|---|
| `feat:` | New features or API endpoints |
| `fix:` | Bug fixes |
| `docs:` | Documentation changes |
| `chore:` | Dependency updates, CI config |
| `refactor:` | Code restructuring (no behavior change) |
| `test:` | Adding or updating tests |

Examples:
```
feat: add simulation automation endpoint ingestion
fix: handle null displayName in repeat offenders processor
docs: update CONTRIBUTING.md for modular architecture
refactor: extract Graph API client to dedicated module
```

## Getting Help

- [README.md](./README.md) — Deployment guide and architecture overview
- [Microsoft Graph Attack Simulation API](https://learn.microsoft.com/en-us/graph/api/resources/attacksimulationroot?view=graph-rest-1.0) — API reference
- Open an **issue** for bugs or questions with steps to reproduce
