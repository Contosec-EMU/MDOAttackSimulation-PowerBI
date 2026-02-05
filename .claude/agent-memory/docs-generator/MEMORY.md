# Documentation Generator Memory

## Project Documentation Standards

### MDO Attack Simulation PowerBI Project
- **Documentation style**: Markdown-based, comprehensive yet scannable
- **Code examples**: Use bash for Azure CLI commands, PowerShell for Windows-specific tasks
- **File paths**: Always use absolute paths in final responses, but relative in documentation for portability
- **Naming conventions**: camelCase for variables in code (matching Graph API), snake_case for Python functions

## Key Documentation Patterns Used

### CLAUDE.md Structure
Created AI assistant-specific documentation with:
1. Project overview (1-2 sentences)
2. Tech stack summary table
3. Directory structure with inline comments
4. Key files section with line counts and purpose
5. Important patterns section (security, data flow, retry logic)
6. Common tasks with exact commands
7. Quick reference tables for APIs and environment variables
8. Links to related documentation

**Rationale**: AI assistants need rapid context loading. CLAUDE.md provides dense, structured information optimized for LLM consumption.

### README.md Updates
Corrected technical inaccuracies:
- Fixed output path structure from incorrect `dt=YYYY-MM-DD/data.parquet` to actual `{api_name}/{YYYY-MM-DD}/{api_name}.parquet`
- Changed validation curl from GET to POST (actual endpoint requirement)
- Added "Recent Updates" section documenting improvements (Parquet format, retry logic, security enhancements)
- Enhanced "Security Considerations" with specific features (network ACLs, input sanitization, security headers, 90-day retention)

### CONTRIBUTING.md Structure
Comprehensive contributor guide:
1. Development setup (step-by-step with OS-specific commands)
2. Project structure (directory tree with descriptions)
3. Code style guidelines (PEP 8 with project-specific conventions)
4. Testing requirements (manual, integration, checklist)
5. PR process (commit message format, review criteria)
6. Where to find help (links, common issues, support channels)

## Important Project Details Documented

### Security Features (Learned from code analysis)
- Input sanitization: All API response strings truncated at 1000 chars
- Network ACLs: Key Vault and Storage deny public access by default
- Security headers: X-Content-Type-Options, X-Frame-Options, CSP, HSTS on all HTTP responses
- Sanitized errors: HTTP responses use correlation IDs, no internal error details exposed
- 90-day log retention in Log Analytics

### Operational Features
- Retry logic: Exponential backoff with jitter (base 5s for Graph API, base 2s for storage)
- Token refresh: 60s buffer before expiration
- Pagination safety: Max 1000 pages per API endpoint
- Container auto-creation: Function creates containers if missing
- Connection pooling: HTTP session reuse for Graph API

### Common Gotchas Identified
1. Output path structure mismatch in original README
2. Test endpoint requires POST, not GET
3. B1 App Service Plan required (not Consumption) for reliability
4. Linux-only for Python functions
5. Training coverage API returns array of trainings (must aggregate counts)

## Documentation Best Practices Applied

### Clarity
- Use imperative mood for task instructions ("Update parameters" not "Updating parameters")
- Provide exact commands with placeholders clearly marked (e.g., `<your-value>`)
- Include both success and failure scenarios in troubleshooting

### Completeness
- Document all environment variables with descriptions and examples
- Include both manual testing and integration testing procedures
- Provide links to external resources (Microsoft docs, Azure Functions guides)

### Consistency
- Maintain uniform markdown heading levels across documents
- Use consistent code block language identifiers (bash, powershell, json, python)
- Apply consistent formatting for file paths, commands, and variables

### Maintainability
- Structure documentation so sections can be updated independently
- Include version numbers for dependencies and tools
- Add dates to "Recent Updates" section for historical tracking
- Use relative links between project documentation files

## Files Created/Updated

1. **C:\repos\MDOAttackSimulation_PowerBI\CLAUDE.md** (NEW) - 280 lines
2. **C:\repos\MDOAttackSimulation_PowerBI\README.md** (UPDATED) - Fixed 3 issues, added Recent Updates section
3. **C:\repos\MDOAttackSimulation_PowerBI\CONTRIBUTING.md** (NEW) - 380 lines

All files use proper markdown formatting, include practical examples, and cross-reference each other appropriately.
