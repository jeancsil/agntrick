# AGENTS.md

**FOR LLM AGENTS DEVELOPING THIS FRAMEWORK.** This document defines strict rules for modifying the Agntrick codebase.

---

## PURPOSE

You are an LLM agent tasked with improving, fixing, or extending the **Agntrick** codebase. This document defines how you MUST approach this work.

---

## STRICT BEHAVIORAL RULES

### ALWAYS Rules

1. **ALWAYS** run `make check` after making any code changes.
2. **ALWAYS** run `make test` after making any code changes.
3. **ALWAYS** fix all linting errors before indicating completion.
4. **ALWAYS** fix all test failures before indicating completion.
5. **ALWAYS** maintain or improve test coverage (current: 80%).
6. **ALWAYS** follow existing code patterns in the codebase.
7. **ALWAYS** add tests for new functionality.
8. **ALWAYS** update docstrings if you change function behavior.
9. **ALWAYS** use `uv` for package management - **NO EXCEPTIONS** (not pip, not poetry, not pipenv).
10. **ALWAYS** prefer Docker for running the framework locally (see Docker section).
11. **ALWAYS** run commands from the correct directory (see Working Directory).

### NEVER Rules

1. **NEVER** skip running `make check` and `make test`.
2. **NEVER** commit changes unless explicitly requested by the user.
3. **NEVER** push changes without user confirmation.
4. **NEVER** introduce new dependencies without discussion.
5. **NEVER** delete existing tests without replacement.
6. **NEVER** change the public API without updating all affected code.
7. **NEVER** use synchronous code where async is expected.
8. **NEVER** raise exceptions from tools - return error strings instead.
9. **NEVER** edit generated files (uv.lock, etc.) directly.
10. **NEVER** ignore deprecation warnings - fix them.
11. **NEVER** use pip, pipenv, poetry, or any package manager other than `uv`.
12. **NEVER** install dependencies locally when Docker can be used instead.
13. **NEVER** add deprecated or outdated libraries as dependencies. Always verify the library is actively maintained and doesn't produce deprecation warnings.

### BEFORE Rules

1. **BEFORE** making changes: Read and understand the existing code.
2. **BEFORE** claiming done: Run `make check && make test`.
3. **BEFORE** adding features: Check if similar functionality exists.
4. **BEFORE** refactoring: Ensure tests cover the affected code.

### AFTER Rules

1. **AFTER** editing code: Run `make check` immediately.
2. **AFTER** check passes: Run `make test`.
3. **AFTER** tests pass: Summarize what was changed and why.

---

## WORKING DIRECTORY

The project root contains all source code, tests, and configuration files. Run all commands from the project root.

```bash
# Run from project root:
make check
make test
make format
make install
```

---

## DEVELOPMENT WORKFLOW

### Step 1: UNDERSTAND
Before making changes:
1. Read the relevant source files
2. Read related test files
3. Understand the existing patterns
4. Check CLAUDE.md for architectural context

### Step 2: IMPLEMENT
Make your changes:
1. Follow existing code style
2. Add type hints (this project uses strict mypy)
3. Add/update docstrings for public functions
4. Keep functions focused and small

### Step 3: VERIFY
After changes:
```bash
make check    # Linting (mypy + ruff)
make test     # Run all tests
```

### Step 4: FIX
If checks or tests fail:
1. Read the error message carefully
2. Fix the issue
3. Re-run the failing command
4. Repeat until all pass

---

## UV IS MANDATORY

**This project uses `uv` exclusively.** No other package manager is allowed.

### Why uv?
- Fast dependency resolution
- Consistent lockfile (uv.lock)
- Built-in virtual environment management
- Replaces pip, pip-tools, poetry, pipenv

### Required Commands

```bash
# Install dependencies
uv sync

# Add a dependency
uv add package-name

# Add a dev dependency
uv add --dev package-name

# Run a command in the virtual environment
uv run <command>

# Update lockfile
uv lock --upgrade-package package-name
```

### Forbidden Commands

```bash
# NEVER use these:
pip install package-name      # WRONG
pipenv install package-name   # WRONG
poetry add package-name       # WRONG
pip install -r requirements.txt  # WRONG
```

If you need a dependency, use `uv add`. No exceptions.

---

## DOCKER (PREFERRED)

**Docker is the preferred way to run and test the framework.** Avoid installing dependencies locally.

### Why Docker?
- Consistent environment across all machines
- No pollution of local Python environment
- Easy cleanup and isolation
- Matches production deployment

### Docker Commands

```bash
# Build the Docker image
make docker-build

# Run agents in Docker
bin/agent.sh developer -i "Explain the project structure"
bin/agent.sh chef -i "I have eggs and cheese"
bin/agent.sh list

# Run tests in Docker
docker compose run --rm app make test

# View logs (same location as local)
tail -f agntrick/logs/agent.log
```

### Docker Benefits
- No rebuild needed when changing Python code (mounted volumes)
- Environment variables loaded from `.env`
- Logs accessible from host machine
- Uses `uv` just like local development

---

## CODE STANDARDS

### Type Hints

This project uses strict mypy. All functions MUST have type hints:

```python
# GOOD
async def run(self, input_data: str, config: dict[str, Any] | None = None) -> str:
    ...

# BAD
async def run(self, input_data, config=None):
    ...
```

### Docstrings

Use Google-style docstrings:

```python
def process_data(data: list[str]) -> dict[str, int]:
    """Process a list of strings and return counts.

    Args:
        data: A list of strings to process.

    Returns:
        A dictionary mapping each unique string to its count.

    Raises:
        ValueError: If data is empty.
    """
```

### Error Handling in Tools

Tools MUST return error messages as strings, never raise exceptions:

```python
# GOOD
def invoke(self, input_str: str) -> str:
    try:
        result = do_something(input_str)
        return result
    except FileNotFoundError:
        return f"Error: File '{input_str}' not found."

# BAD
def invoke(self, input_str: str) -> str:
    if not os.path.exists(input_str):
        raise FileNotFoundError(f"File '{input_str}' not found")
```

### Async Patterns

Agent `run()` methods are async. Use `async def` and `await`:

```python
# GOOD
async def run(self, input_data: str) -> str:
    result = await some_async_operation()
    return result

# BAD
async def run(self, input_data: str) -> str:
    result = some_sync_operation()  # Blocks event loop
    return result
```

### Agent Registration

Always use the decorator pattern:

```python
@AgentRegistry.register("agent-name", mcp_servers=["server1"])
class MyAgent(LangGraphMCPAgent):
    ...
```

---

## TESTING REQUIREMENTS

### Test Location

Tests are in `tests/`

### Test Naming

- Test files: `test_<module>.py`
- Test functions: `test_<function>_<scenario>()`

```python
# GOOD
def test_run_with_valid_input_returns_response():
    ...

def test_invoke_with_missing_file_returns_error():
    ...

# BAD
def test_run():
    ...

def testErrorHandling():
    ...
```

### Test Patterns

Use `monkeypatch` for external dependencies:

```python
def test_web_search_returns_results(monkeypatch):
    def mock_search(query: str) -> str:
        return "Mocked results"

    monkeypatch.setattr("module.web_search", mock_search)
    tool = WebSearchTool()
    result = tool.invoke("test query")
    assert "Mocked results" in result
```

### Coverage Requirement

Minimum coverage: 60% (fail under configured in pyproject.toml)
Current coverage: 80%

New code should include tests. Aim to maintain or improve coverage.

---

## PROJECT STRUCTURE

```
agntrick/
├── gateway/                # Go WhatsApp gateway
│   ├── config.go          # YAML config parsing
│   ├── session.go        # WhatsApp session manager
│   ├── message.go        # Message handling with self-message detection
│   ├── http_client.go    # HTTP client for Python API communication
│   ├── qr.go             # QR code generation
│   └── go.mod            # Go module definition
├── src/agntrick/
│   ├── api/              # FastAPI server
│   │   ├── main.py       # FastAPI application entry point
│   │   ├── routes/       # API route handlers
│   │   ├── middleware/   # Middleware (logging, error handling, auth)
│   │   ├── models/       # Pydantic models for request/response
│   │   └── database/     # Database connection and session management
│   ├── whatsapp/         # WhatsApp integration
│   │   ├── tenant_registry.py  # Phone-to-tenant registry
│   │   ├── webhook.py    # WhatsApp webhook handlers
│   │   └── session_manager.py  # Session management utilities
│   ├── core/             # Agent implementations
│   │   ├── langgraph_agent.py   # Base class - modify carefully
│   │   ├── simple_agent.py
│   │   ├── chef_agent.py
│   │   ├── travel_agent.py
│   │   ├── news_agent.py
│   │   ├── developer_agent.py
│   │   └── travel_coordinator_agent.py
│   ├── interfaces/       # Abstract base classes
│   │   └── base.py              # Agent and Tool ABCs
│   ├── mcp/              # MCP integration
│   │   ├── config.py            # Server configurations
│   │   └── provider.py          # Connection management
│   ├── tools/            # Tool implementations
│   │   ├── codebase_explorer.py # Code navigation tools
│   │   ├── code_searcher.py     # ripgrep wrapper
│   │   ├── syntax_validator.py  # Tree-sitter validation
│   │   ├── web_search.py
│   │   └── example.py
│   ├── constants.py      # BASE_DIR, LOGS_DIR, timeouts
│   ├── registry.py       # Agent discovery and registration
│   └── cli.py            # Typer CLI interface
├── tests/                # Test suite
│   ├── test_gateway/    # Go gateway tests
│   └── test_api/        # API server tests
├── docker-compose.yml    # Docker multi-container setup
├── Dockerfile           # Multi-stage Docker build
├── pyproject.toml       # Project config, dependencies
└── uv.lock              # Lockfile (DO NOT EDIT DIRECTLY)
```

## GO TESTING

When working on the Go gateway, use the following commands:

```bash
cd gateway && go test ./...          # Run all Go tests
cd gateway && go test -v ./...       # Verbose Go test output
cd gateway && go fmt ./...           # Format Go code
cd gateway && go vet ./...           # Lint Go code
```

## COMMANDS REFERENCE

```bash
# From project root:
make check          # Run mypy + ruff (linting)
make test           # Run pytest with coverage
make format         # Auto-format with ruff
make install        # Install dependencies
make clean          # Remove caches and artifacts

# Run the CLI:
agntrick list
agntrick info developer
agntrick developer -i "input"

# Start FastAPI server (multi-tenant WhatsApp support):
agntrick serve

# Gateway-specific commands:
make gateway-build   # Build Go gateway
make gateway-test   # Test Go gateway
```

---

## GIT HOOKS

This project has a pre-push hook that runs `make check`.

If the hook fails:
1. Run `make -C .. check` to see errors
2. Fix all errors
3. Try pushing again

---

## COMMANDS REFERENCE

```bash
# From project root:
make check      # Run mypy + ruff (linting)
make test       # Run pytest with coverage
make format     # Auto-format with ruff
make install    # Install dependencies
make clean      # Remove caches and artifacts

# Run the CLI:
agntrick list
agntrick info developer
agntrick developer -i "input"

# Start FastAPI server (multi-tenant WhatsApp support):
agntrick serve
```

---

## COMMON TASKS

### Adding a New Agent

1. Create file in `src/agntrick/agents/my_agent.py`
2. Subclass `AgentBase` (alias for `LangGraphMCPAgent`)
3. Add `@AgentRegistry.register()` decorator
4. Define `system_prompt` property
5. Override `local_tools()` if needed
6. Add tests in `tests/test_my_agent.py`
7. Run `make check && make test`

### Adding a New Tool

1. Create file in `src/agntrick/tools/my_tool.py`
2. Subclass `Tool` from `interfaces.base`
3. Implement `name`, `description`, `invoke()`
4. Export from `tools/__init__.py`
5. Add tests in `tests/test_my_tool.py`
6. Run `make check && make test`

### Adding a New MCP Server

1. Add configuration in `mcp/config.py`
2. Update `DEFAULT_MCP_SERVERS` dict
3. Document API key requirements if any
4. Test connection manually
5. Update relevant agent registrations

### Fixing a Bug

1. Write a failing test that reproduces the bug
2. Run `make test` to confirm failure
3. Fix the code
4. Run `make check && make test`
5. Confirm test now passes

---

## DEPENDENCIES

### Adding Dependencies

```bash
uv add package-name
```

### Adding Dev Dependencies

```bash
uv add --dev package-name
```

### Updating Dependencies

```bash
uv lock --upgrade-package package-name
```

---

## FINAL CHECKLIST

Before saying a task is complete:

- [ ] Code follows project style
- [ ] Type hints are complete
- [ ] Docstrings are updated
- [ ] `make check` passes with no errors
- [ ] `make test` passes with no failures
- [ ] Coverage maintained or improved
- [ ] No new warnings introduced
- [ ] README.md is updated if public API or agents/tools changed

## KEEPING README.md IN SYNC

**README.md must stay in sync with framework changes.**

Update README.md when you:
- Add a new agent (add to Available Agents table)
- Add a new tool (add to Available Tools table)
- Add a new MCP server (add to Available MCP Servers table)
- Change public API (update Architecture section if needed)
- Modify agent capabilities (update agent descriptions)

**Do NOT:**
- Leave outdated information in README.md
- Document features that no longer exist
- Skip updating relevant sections

---

## WHEN IN DOUBT

1. Read existing code for patterns
2. Run `make check` early and often
3. Ask the user for clarification
4. Don't guess - verify
