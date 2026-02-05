# Contributing to MDO Attack Simulation PowerBI

Thank you for your interest in contributing to this project! This guide will help you set up your development environment and understand our coding standards.

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Code Style Guidelines](#code-style-guidelines)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Where to Find Help](#where-to-find-help)

## Development Setup

### Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.11** (required for Azure Functions v4 compatibility)
- **Azure Functions Core Tools v4** (`npm install -g azure-functions-core-tools@4 --unsafe-perm true`)
- **Azure CLI** (v2.50+) for deployment and testing
- **Git** for version control
- **VS Code** (recommended) with extensions:
  - Python (Microsoft)
  - Azure Functions (Microsoft)
  - Bicep (Microsoft)

### Local Development Environment

1. **Clone the repository**

```bash
git clone <repository-url>
cd MDOAttackSimulation_PowerBI
```

2. **Set up Python virtual environment**

```bash
cd src/function_app
python3.11 -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Create local settings file**

```bash
cp local.settings.json.example local.settings.json
```

Edit `local.settings.json` with your values:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "TENANT_ID": "your-tenant-id",
    "GRAPH_CLIENT_ID": "your-app-registration-client-id",
    "KEY_VAULT_URL": "https://your-keyvault.vault.azure.net/",
    "STORAGE_ACCOUNT_URL": "https://your-storage.dfs.core.windows.net/",
    "TIMER_SCHEDULE": "0 0 2 * * *"
  }
}
```

5. **Authenticate with Azure**

```bash
az login
az account set --subscription <your-subscription-id>
```

6. **Store test secret in Key Vault** (if using dev/test environment)

```bash
az keyvault secret set \
  --vault-name <your-keyvault> \
  --name "graph-client-secret" \
  --value "<your-client-secret>"
```

### Running Locally

1. **Start the function host**

```bash
cd src/function_app
func start
```

2. **Trigger the function manually**

Open a new terminal and run:

```bash
curl -X POST http://localhost:7071/api/test-run
```

3. **View logs**

Logs appear in the terminal where you ran `func start`. Look for:
- OAuth token acquisition
- Graph API calls and pagination
- Data processing steps
- Storage write operations

### Testing Against Azure Resources

For full integration testing, you'll need:
- A deployed Azure environment (see [README.md](./README.md) deployment section)
- An Entra ID app registration with `AttackSimulation.Read.All` permission
- Your local identity granted access to the Key Vault and Storage account

```bash
# Grant your user account access to Key Vault (for local testing)
az keyvault set-policy \
  --name <keyvault-name> \
  --upn <your-email@domain.com> \
  --secret-permissions get list

# Grant your user account access to Storage (for local testing)
az role assignment create \
  --assignee <your-email@domain.com> \
  --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg-name>/providers/Microsoft.Storage/storageAccounts/<storage-account>"
```

## Project Structure

```
MDOAttackSimulation_PowerBI/
├── infra/                      # Infrastructure as Code
│   ├── main.bicep             # Azure resource definitions
│   └── main.bicepparam        # Deployment parameters
├── src/
│   └── function_app/          # Python function code
│       ├── function_app.py    # Main application logic
│       ├── requirements.txt   # Python dependencies
│       ├── host.json         # Function runtime configuration
│       └── local.settings.json # Local development settings (gitignored)
├── .claude/                   # AI assistant agent configurations
├── README.md                  # User-facing documentation
├── CLAUDE.md                 # AI assistant project brief
└── CONTRIBUTING.md           # This file
```

## Code Style Guidelines

### Python Code Style

We follow PEP 8 with some project-specific conventions:

1. **Indentation**: 4 spaces (no tabs)
2. **Line length**: 120 characters maximum
3. **Docstrings**: Use triple quotes for all public functions and classes
4. **Type hints**: Use type hints for function parameters and return values where practical
5. **String quotes**: Use double quotes for strings, single quotes for string literals in code

### Naming Conventions

- **Functions**: `snake_case` (e.g., `process_repeat_offenders`)
- **Classes**: `PascalCase` (e.g., `GraphAPIClient`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `REQUEST_TIMEOUT_SECONDS`)
- **Variables**: `snake_case` (e.g., `snapshot_date`)

### Code Organization

- **Imports**: Grouped in order: standard library, third-party, local modules
- **Class methods**: Order: `__init__`, public methods, private methods (prefixed with `_`)
- **Functions**: Define before use, or group logically at module level

### Documentation Standards

1. **Module docstrings**: At top of file, describe purpose and major components
2. **Function docstrings**: Include description, Args, Returns, Raises sections
3. **Inline comments**: Use sparingly, explain "why" not "what"
4. **TODO comments**: Format as `# TODO(username): Description`

Example:

```python
def flatten_attack_user(user_detail: dict) -> dict:
    """Flatten attackSimulationUser nested structure with input sanitization.

    Args:
        user_detail: Nested user object from Graph API response

    Returns:
        Flattened dictionary with userId, displayName, email keys
    """
    if not user_detail:
        return {"userId": None, "displayName": None, "email": None}
    return {
        "userId": sanitize_string(user_detail.get("userId")),
        "displayName": sanitize_string(user_detail.get("displayName")),
        "email": sanitize_string(user_detail.get("email"))
    }
```

### Security Coding Practices

1. **Never commit secrets**: Use Key Vault or environment variables
2. **Sanitize inputs**: All external data (API responses, user inputs) must be sanitized
3. **Use parameterized queries**: If adding database code, use parameterized queries
4. **Validate environment variables**: Check all required variables at startup
5. **Add security headers**: All HTTP responses must include security headers
6. **Log safely**: Never log secrets or PII in plain text

### Error Handling

1. **Fail fast**: Validate inputs early, raise errors immediately
2. **Use specific exceptions**: Catch specific exception types, not bare `except:`
3. **Log with context**: Include correlation IDs, operation names, and relevant context
4. **Retry transient failures**: Use exponential backoff with jitter for network calls
5. **Return sanitized errors**: Don't expose internal error details in HTTP responses

Example:

```python
try:
    response = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()
except requests.exceptions.RequestException as e:
    if attempt == retries - 1:
        logger.error(f"Request failed after {retries} attempts: {e}", exc_info=True)
        raise
    wait_time = (2 ** attempt) * BACKOFF_BASE_SECONDS + random.uniform(0, 2)
    logger.warning(f"Request failed (attempt {attempt + 1}): {e}. Retrying in {wait_time:.2f}s...")
    time.sleep(wait_time)
```

## Testing Requirements

### Manual Testing

Before submitting a PR, manually test:

1. **Local function execution**: `func start` and trigger via `/api/test-run`
2. **Graph API authentication**: Verify token acquisition succeeds
3. **Data fetching**: Confirm all three APIs return data
4. **Data transformation**: Check processed data has correct schema
5. **Storage writes**: Verify Parquet and JSON files written to containers
6. **Error handling**: Test with invalid credentials, network failures

### Integration Testing

Test against a deployed Azure environment:

1. Deploy your changes to a test Function App
2. Trigger via HTTP endpoint
3. Verify logs in Application Insights
4. Check output files in ADLS Gen2
5. Load data in Power BI to confirm schema compatibility

### Testing Checklist

- [ ] Function runs without errors locally
- [ ] Function runs without errors in Azure
- [ ] All three APIs successfully fetched and processed
- [ ] Parquet files written to `curated/` container
- [ ] JSON files written to `raw/` container
- [ ] File paths follow `{api_name}/{YYYY-MM-DD}/{api_name}.parquet` pattern
- [ ] Logs appear in Application Insights
- [ ] No secrets logged in plain text
- [ ] HTTP endpoints return proper security headers
- [ ] Error responses don't expose internal details

## Pull Request Process

### Before Submitting

1. **Create a feature branch**: `git checkout -b feature/your-feature-name`
2. **Make your changes**: Follow code style guidelines
3. **Test thoroughly**: Complete the testing checklist above
4. **Update documentation**: Update README.md if adding features or changing behavior
5. **Write clear commit messages**: Use imperative mood ("Add feature" not "Added feature")

### Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance tasks

Example:

```
feat: Add retry logic for Graph API calls

Implement exponential backoff with jitter for handling transient
failures when calling Microsoft Graph API. This improves reliability
when the API returns 429 (rate limit) or 5xx (server error) responses.

Closes #42
```

### Submitting Your PR

1. **Push your branch**: `git push origin feature/your-feature-name`
2. **Open a pull request** on GitHub/Azure DevOps
3. **Fill out the PR template** with:
   - Description of changes
   - Testing performed
   - Screenshots (if UI changes)
   - Related issue numbers
4. **Request review** from maintainers
5. **Address feedback**: Make changes based on review comments
6. **Squash commits** if requested before merging

### PR Review Criteria

Reviewers will check:
- Code follows style guidelines
- Changes are well-tested
- Documentation is updated
- No secrets or credentials in code
- Security best practices followed
- Performance implications considered
- Backwards compatibility maintained (if applicable)

### After PR Approval

1. Maintainer will merge your PR
2. Delete your feature branch after merge
3. Pull latest changes from main branch

## Where to Find Help

### Documentation

- [README.md](./README.md) - Deployment guide and architecture overview
- [CLAUDE.md](./CLAUDE.md) - AI assistant project brief with quick reference
- [Microsoft Graph API Docs](https://learn.microsoft.com/en-us/graph/api/resources/security-attacksimulation-overview) - Attack Simulation Training API reference
- [Azure Functions Python Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python) - Python developer reference

### Common Issues

1. **Authentication failures**: Check Entra ID app permissions and admin consent
2. **Storage access denied**: Verify RBAC role assignments (Storage Blob Data Contributor)
3. **Key Vault access denied**: Verify RBAC role assignments (Key Vault Secrets User)
4. **Local function won't start**: Check Python version (must be 3.11)
5. **Module import errors**: Activate virtual environment and reinstall requirements

### Getting Support

- **Issues**: Open an issue on the repository with:
  - Clear description of the problem
  - Steps to reproduce
  - Expected vs actual behavior
  - Error messages and logs
  - Environment details (Python version, OS, etc.)

- **Questions**: For general questions about the project:
  - Check existing issues and PR discussions first
  - Review the README.md and CLAUDE.md documentation
  - Ask in the project's discussion forum (if available)

### Code Review Tips

- Be respectful and constructive in feedback
- Explain the "why" behind suggestions
- Acknowledge good code and thoughtful solutions
- Ask questions to understand intent before suggesting changes
- Focus on code quality, security, and maintainability

## Thank You!

Your contributions help make this project better for everyone. We appreciate your time and effort in following these guidelines and maintaining code quality.
