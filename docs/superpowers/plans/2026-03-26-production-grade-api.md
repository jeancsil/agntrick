# Production-Grade Agntrick API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform agntrick from a CLI-only tool into a production-grade REST API with multi-tenant support, unified configuration, and WhatsApp as a channel plugin.

**Architecture:** Merge agntrick + agntrick-toolkit into a monorepo. Add FastAPI server with tenant-scoped SQLite databases. WhatsApp becomes a thin channel client connecting via API. All config centralized in one `.agntrick.yaml` file.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite (per-tenant), LangChain, LangGraph, MCP

---

## Summary of Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Repo structure | Merge core + toolkit, keep WA separate | Toolkit is tightly coupled to agents; WA should be API client |
| Config | Single YAML file | Config spread across 5+ sources currently |
| API framework | FastAPI | Async, auto-docs, already used in toolkit |
| Multi-tenant | In-process tenant_id scoping | Simpler than per-client containers |
| Database | SQLite per tenant | Complete isolation, simple backup |
| Agent config | Python registration + YAML overrides | Flexibility for advanced agents |
| WhatsApp | Channel plugin via API | Decouples from core |
| Auth | API keys | Simple, sufficient for personal/small-team |

---

## File Structure (Target State)

```
~/code/agents/                           # Main monorepo (agntrick + toolkit merged)
├── .agntrick.yaml                       # SINGLE config file
├── src/agntrick/
│   ├── __init__.py
│   ├── agent.py                         # AgentBase (modified for tenant awareness)
│   ├── registry.py                      # AgentRegistry (add per-agent config)
│   ├── config.py                        # NEW: Unified config loading
│   ├── constants.py                     # Paths, defaults
│   ├── exceptions.py
│   ├── cli.py                           # CLI (now talks to API)
│   │
│   ├── api/                             # NEW: FastAPI server
│   │   ├── __init__.py
│   │   ├── server.py                    # FastAPI app entry point
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── agents.py                # POST /agents/{name}/run
│   │   │   ├── channels.py              # WhatsApp webhook receiver
│   │   │   ├── tenants.py               # Tenant management
│   │   │   └── health.py                # /health, /ready
│   │   ├── deps.py                      # Dependencies (get_tenant, get_db)
│   │   ├── auth.py                      # API key validation
│   │   └── middleware.py                # Request logging, error handling
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py                  # Tenant-scoped Database class
│   │   ├── tenant_manager.py            # NEW: Manages tenant DBs
│   │   ├── models.py                    # ScheduledTask, Note
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── note_repository.py       # Tenant-scoped
│   │       └── task_repository.py       # Tenant-scoped
│   │
│   ├── agents/                          # Agent implementations
│   │   ├── __init__.py
│   │   ├── developer.py
│   │   ├── learning.py
│   │   ├── news.py
│   │   └── ...
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── provider.py
│   │
│   ├── tools/
│   │   └── ...
│   │
│   ├── prompts/
│   │   └── ...
│   │
│   └── llm/
│       └── ...
│
├── src/agntrick_toolbox/                # Toolkit (merged from ~/code/agntrick-toolkit)
│   ├── __init__.py
│   ├── server.py                        # MCP server
│   ├── config.py
│   └── tools/
│       └── ...
│
├── tests/
│   ├── test_api/
│   │   ├── test_agents_route.py
│   │   ├── test_channels_route.py
│   │   ├── test_auth.py
│   │   └── test_tenant_isolation.py
│   └── ...
│
├── pyproject.toml                       # Unified dependencies
└── Makefile                             # make check, make test, make serve

~/code/agntrick-whatsapp/                # Separate repo (channel plugin)
├── src/agntrick_whatsapp/
│   ├── __init__.py
│   ├── channel.py                       # WhatsApp channel (connects to API)
│   ├── config.py                        # Minimal: API URL, tenant_id, API key
│   └── qr_handler.py                    # QR code display/storage
└── pyproject.toml
```

---

## Phase 1: Foundation (API Server + Tenant Storage)

### Task 1.1: Create Unified Config Schema

**Files:**
- Modify: `src/agntrick/config.py`
- Create: `.agntrick.yaml.example` (updated)

- [ ] **Step 1: Write the failing test for unified config**

Create `tests/test_config.py`:

```python
"""Tests for unified configuration."""

import pytest
from pathlib import Path
import tempfile
import yaml


class TestUnifiedConfig:
    """Tests for unified configuration loading."""

    def test_config_loads_all_sections(self, tmp_path: Path, monkeypatch) -> None:
        """Config should load all required sections."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(yaml.dump({
            "llm": {"provider": "openai", "model": "gpt-4", "temperature": 0.5},
            "agents": {"default_agent_name": "Jarvis"},
            "mcp": {"toolbox_url": "http://localhost:8080/sse"},
            "storage": {"base_path": str(tmp_path / "data")},
            "api": {"host": "0.0.0.0", "port": 8000},
            "auth": {"api_keys": {"test-key": "tenant-1"}},
        }))

        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))
        from agntrick.config import get_config

        config = get_config(force_reload=True)

        assert config.llm.provider == "openai"
        assert config.llm.temperature == 0.5
        assert config.api.port == 8000
        assert "test-key" in config.auth.api_keys

    def test_config_per_agent_overrides(self, tmp_path: Path, monkeypatch) -> None:
        """Config should support per-agent model/temperature overrides."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(yaml.dump({
            "llm": {"temperature": 0.7},
            "agents": {
                "overrides": {
                    "developer": {"temperature": 0.1, "model": "gpt-4"},
                    "news": {"temperature": 0.9},
                }
            }
        }))

        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))
        from agntrick.config import get_config

        config = get_config(force_reload=True)

        assert config.get_agent_config("developer").temperature == 0.1
        assert config.get_agent_config("developer").model == "gpt-4"
        assert config.get_agent_config("news").temperature == 0.9
        assert config.get_agent_config("unknown").temperature == 0.7  # fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agents && uv run pytest tests/test_config.py -v`
Expected: FAIL with "AttributeError" or "ImportError"

- [ ] **Step 3: Implement unified config schema**

Replace `src/agntrick/config.py`:

```python
"""Unified configuration management for agntrick.

All configuration in a single .agntrick.yaml file with clear sections:
- llm: Provider, model, temperature defaults
- agents: Per-agent overrides, prompts
- mcp: Toolbox URL, MCP servers, timeouts
- storage: Database path, tenant settings
- api: Server host/port
- auth: API keys for tenants
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str | None = None
    model: str | None = None
    temperature: float = 0.1
    max_tokens: int | None = None


@dataclass
class AgentOverrideConfig:
    """Per-agent configuration overrides."""
    model: str | None = None
    temperature: float | None = None
    mcp_servers: list[str] | None = None
    tool_categories: list[str] | None = None


@dataclass
class AgentsConfig:
    """Agent configuration."""
    prompts_dir: str | None = None
    default_agent_name: str = "Assistant"
    system_prompt_template: str | None = None
    system_prompt_file: str | None = None
    overrides: dict[str, AgentOverrideConfig] = field(default_factory=dict)

    def get_agent_config(self, agent_name: str) -> AgentOverrideConfig:
        """Get config overrides for a specific agent."""
        return self.overrides.get(agent_name, AgentOverrideConfig())


@dataclass
class MCPConfig:
    """MCP server configuration."""
    servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    timeout: int = 60
    toolbox_url: str = "http://localhost:8080/sse"


@dataclass
class StorageConfig:
    """Storage configuration."""
    base_path: str | None = None  # Default: platformdirs.user_data_dir("agntrick")

    def get_tenant_db_path(self, tenant_id: str) -> Path:
        """Get database path for a tenant."""
        base = Path(self.base_path) if self.base_path else Path(
            __import__("platformdirs").user_data_dir("agntrick")
        )
        return base / "tenants" / tenant_id / "agntrick.db"


@dataclass
class APIConfig:
    """API server configuration."""
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False


@dataclass
class AuthConfig:
    """Authentication configuration."""
    api_keys: dict[str, str] = field(default_factory=dict)  # api_key -> tenant_id


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str | None = None
    directory: str | None = None


@dataclass
class AgntrickConfig:
    """Main configuration class for agntrick."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    api: APIConfig = field(default_factory=APIConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    _config_path: str | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "AgntrickConfig":
        """Create configuration from a dictionary."""
        llm_dict = config_dict.get("llm", {})
        agents_dict = config_dict.get("agents", {})
        mcp_dict = config_dict.get("mcp", {})
        storage_dict = config_dict.get("storage", {})
        api_dict = config_dict.get("api", {})
        auth_dict = config_dict.get("auth", {})
        logging_dict = config_dict.get("logging", {})

        # Parse agent overrides
        overrides = {}
        for name, override in agents_dict.get("overrides", {}).items():
            overrides[name] = AgentOverrideConfig(
                model=override.get("model"),
                temperature=override.get("temperature"),
                mcp_servers=override.get("mcp_servers"),
                tool_categories=override.get("tool_categories"),
            )

        return cls(
            llm=LLMConfig(**llm_dict),
            agents=AgentsConfig(
                prompts_dir=agents_dict.get("prompts_dir"),
                default_agent_name=agents_dict.get("default_agent_name", "Assistant"),
                system_prompt_template=agents_dict.get("system_prompt_template"),
                system_prompt_file=agents_dict.get("system_prompt_file"),
                overrides=overrides,
            ),
            mcp=MCPConfig(**mcp_dict),
            storage=StorageConfig(**storage_dict),
            api=APIConfig(**api_dict),
            auth=AuthConfig(
                api_keys=auth_dict.get("api_keys", {}),
            ),
            logging=LoggingConfig(**logging_dict),
        )

    def get_agent_config(self, agent_name: str) -> AgentOverrideConfig:
        """Get configuration for a specific agent."""
        return self.agents.get_agent_config(agent_name)


# Global config instance
_config: AgntrickConfig | None = None


def _find_config_file() -> Path | None:
    """Find the agntrick configuration file."""
    # Priority: env var > cwd > home
    env_config = os.getenv("AGNTRICK_CONFIG")
    if env_config:
        env_path = Path(env_config)
        if env_path.exists():
            return env_path

    local_config = Path.cwd() / ".agntrick.yaml"
    if local_config.exists():
        return local_config

    home_config = Path.home() / ".agntrick.yaml"
    if home_config.exists():
        return home_config

    return None


def get_config(force_reload: bool = False) -> AgntrickConfig:
    """Get the current configuration."""
    global _config

    if _config is not None and not force_reload:
        return _config

    config_file = _find_config_file()

    if config_file is None:
        _config = AgntrickConfig()
        return _config

    try:
        with config_file.open() as f:
            config_dict = yaml.safe_load(f) or {}

        _config = AgntrickConfig.from_dict(config_dict)
        _config._config_path = str(config_file)
        return _config

    except Exception as e:
        from agntrick.exceptions import ConfigurationError
        raise ConfigurationError(f"Failed to load configuration: {e}", str(config_file))


def reset_config() -> None:
    """Reset the cached configuration."""
    global _config
    _config = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/code/agents && uv run pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Update .agntrick.yaml.example**

Replace `.agntrick.yaml.example` with the new unified format (see file content in plan).

- [ ] **Step 6: Commit**

```bash
cd ~/code/agents
git add src/agntrick/config.py tests/test_config.py .agntrick.yaml.example
git commit -m "feat: add unified configuration schema with per-agent overrides"
```

---

### Task 1.2: Create Tenant-Scoped Database

**Files:**
- Modify: `src/agntrick/storage/database.py`
- Create: `src/agntrick/storage/tenant_manager.py`
- Create: `tests/storage/test_tenant_manager.py`

- [ ] **Step 1: Write the failing test for tenant manager**

Create `tests/storage/test_tenant_manager.py`:

```python
"""Tests for tenant-scoped database management."""

import pytest
from pathlib import Path
import tempfile


class TestTenantManager:
    """Tests for tenant database isolation."""

    def test_each_tenant_gets_own_database(self, tmp_path: Path) -> None:
        """Each tenant should have a separate database file."""
        from agntrick.storage.tenant_manager import TenantManager

        manager = TenantManager(base_path=tmp_path)

        db1 = manager.get_database("tenant-1")
        db2 = manager.get_database("tenant-2")

        assert db1._db_path != db2._db_path
        assert "tenant-1" in str(db1._db_path)
        assert "tenant-2" in str(db2._db_path)

    def test_tenant_databases_are_isolated(self, tmp_path: Path) -> None:
        """Data in one tenant database should not be visible to another."""
        from agntrick.storage.tenant_manager import TenantManager
        from agntrick.storage.models import Note

        manager = TenantManager(base_path=tmp_path)

        # Save note for tenant-1
        db1 = manager.get_database("tenant-1")
        from agntrick.storage.repositories.note_repository import NoteRepository
        repo1 = NoteRepository(db1)
        note1 = Note(context_id="ctx-1", content="Tenant 1 note")
        repo1.save(note1)

        # Check tenant-2 cannot see it
        db2 = manager.get_database("tenant-2")
        repo2 = NoteRepository(db2)
        notes2 = repo2.list_all()

        assert len(notes2) == 0
        assert len(repo1.list_all()) == 1

    def test_manager_caches_database_connections(self, tmp_path: Path) -> None:
        """Manager should cache database connections per tenant."""
        from agntrick.storage.tenant_manager import TenantManager

        manager = TenantManager(base_path=tmp_path)

        db1a = manager.get_database("tenant-1")
        db1b = manager.get_database("tenant-1")

        assert db1a is db1b  # Same instance
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agents && uv run pytest tests/storage/test_tenant_manager.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Create TenantManager**

Create `src/agntrick/storage/tenant_manager.py`:

```python
"""Tenant-scoped database management."""

import logging
from pathlib import Path
from typing import Dict

from agntrick.storage.database import Database

logger = logging.getLogger(__name__)


class TenantManager:
    """Manages tenant-scoped database connections.

    Each tenant gets its own SQLite database file for complete isolation.
    Connections are cached per tenant.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize the tenant manager.

        Args:
            base_path: Base directory for tenant databases.
                       Defaults to platformdirs.user_data_dir("agntrick")
        """
        if base_path is None:
            import platformdirs
            base_path = Path(platformdirs.user_data_dir("agntrick"))

        self._base_path = Path(base_path)
        self._databases: Dict[str, Database] = {}

    def get_database(self, tenant_id: str) -> Database:
        """Get or create a database connection for a tenant.

        Args:
            tenant_id: Unique identifier for the tenant.

        Returns:
            Database instance for the tenant.
        """
        if tenant_id not in self._databases:
            db_path = self._get_tenant_db_path(tenant_id)
            self._databases[tenant_id] = Database(db_path)
            logger.info(f"Created database for tenant {tenant_id}: {db_path}")

        return self._databases[tenant_id]

    def _get_tenant_db_path(self, tenant_id: str) -> Path:
        """Get the database path for a tenant."""
        # Sanitize tenant_id to prevent path traversal
        safe_tenant_id = "".join(c for c in tenant_id if c.isalnum() or c in "-_")
        return self._base_path / "tenants" / safe_tenant_id / "agntrick.db"

    def close_all(self) -> None:
        """Close all database connections."""
        for tenant_id, db in self._databases.items():
            try:
                db.close()
                logger.debug(f"Closed database for tenant {tenant_id}")
            except Exception as e:
                logger.warning(f"Error closing database for tenant {tenant_id}: {e}")

        self._databases.clear()

    def list_tenants(self) -> list[str]:
        """List all tenants with databases."""
        tenants_dir = self._base_path / "tenants"
        if not tenants_dir.exists():
            return []

        return [
            d.name for d in tenants_dir.iterdir()
            if d.is_dir() and (d / "agntrick.db").exists()
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/code/agents && uv run pytest tests/storage/test_tenant_manager.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/code/agents
git add src/agntrick/storage/tenant_manager.py tests/storage/test_tenant_manager.py
git commit -m "feat: add tenant-scoped database management"
```

---

### Task 1.3: Create FastAPI Server Skeleton

**Files:**
- Create: `src/agntrick/api/__init__.py`
- Create: `src/agntrick/api/server.py`
- Create: `src/agntrick/api/routes/__init__.py`
- Create: `src/agntrick/api/routes/health.py`
- Create: `src/agntrick/api/auth.py`
- Create: `src/agntrick/api/deps.py`
- Create: `tests/test_api/test_health.py`

- [ ] **Step 1: Add FastAPI and testing dependencies**

Run: `cd ~/code/agents && uv add fastapi uvicorn httpx && uv add --dev pytest-asyncio`

- [ ] **Step 2: Write the failing test for health endpoint**

Create `tests/test_api/test_health.py`:

```python
"""Tests for API health endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_returns_ok(self) -> None:
        """Health endpoint should return OK status."""
        from agntrick.api.server import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_ready_returns_ok_when_mcp_available(self, monkeypatch) -> None:
        """Ready endpoint should return OK when dependencies are available."""
        from agntrick.api.server import create_app

        # Mock MCP availability check
        monkeypatch.setenv("MCP_SKIP_HEALTH_CHECK", "true")

        app = create_app()
        client = TestClient(app)

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ~/code/agents && uv run pytest tests/test_api/test_health.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 4: Create API server**

Create `src/agntrick/api/__init__.py`:

```python
"""FastAPI-based REST API for agntrick."""

from agntrick.api.server import create_app, run_server

__all__ = ["create_app", "run_server"]
```

Create `src/agntrick/api/server.py`:

```python
"""FastAPI application factory and server."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agntrick.api.routes import health
from agntrick.config import get_config

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    config = get_config()
    logger.info(f"Starting agntrick API server on {config.api.host}:{config.api.port}")

    # Initialize tenant manager
    from agntrick.storage.tenant_manager import TenantManager
    app.state.tenant_manager = TenantManager(
        base_path=config.storage.base_path
    )

    yield

    # Cleanup
    app.state.tenant_manager.close_all()
    logger.info("Shutting down agntrick API server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Agntrick API",
        description="Production-grade API for AI agents",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure as needed
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health.router, tags=["health"])

    return app


def run_server() -> None:
    """Run the API server."""
    import uvicorn

    config = get_config()
    app = create_app()

    uvicorn.run(
        "agntrick.api.server:create_app",
        host=config.api.host,
        port=config.api.port,
        reload=config.api.debug,
        factory=True,
    )
```

Create `src/agntrick/api/routes/__init__.py`:

```python
"""API route modules."""

from agntrick.api.routes import health

__all__ = ["health"]
```

Create `src/agntrick/api/routes/health.py`:

```python
"""Health check endpoints."""

import os
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Basic health check."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check() -> dict:
    """Readiness check - verifies all dependencies are available."""
    checks = {
        "database": True,  # If we got here, DB is working
    }

    # Skip MCP check if configured
    if not os.getenv("MCP_SKIP_HEALTH_CHECK"):
        # TODO: Check MCP connectivity
        checks["mcp"] = True

    all_healthy = all(checks.values())

    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks,
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ~/code/agents && uv run pytest tests/test_api/test_health.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Add serve command to CLI**

Add to `src/agntrick/cli.py`:

```python
@app.command(name="serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
) -> None:
    """Start the REST API server."""
    from agntrick.api.server import run_server

    config = get_config()
    if host != "127.0.0.1":
        config.api.host = host
    if port != 8000:
        config.api.port = port

    console.print(f"[bold green]Starting Agntrick API server on {config.api.host}:{config.api.port}[/bold green]")
    run_server()
```

- [ ] **Step 7: Commit**

```bash
cd ~/code/agents
git add src/agntrick/api/ tests/test_api/ pyproject.toml uv.lock
git commit -m "feat: add FastAPI server skeleton with health endpoints"
```

---

### Task 1.4: Add API Authentication

**Files:**
- Create: `src/agntrick/api/auth.py`
- Create: `src/agntrick/api/deps.py`
- Create: `tests/test_api/test_auth.py`

- [ ] **Step 1: Write the failing test for auth**

Create `tests/test_api/test_auth.py`:

```python
"""Tests for API authentication."""

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException


class TestAPIAuth:
    """Tests for API key authentication."""

    def test_valid_api_key_allows_access(self, monkeypatch) -> None:
        """Valid API key should allow access to protected endpoints."""
        from agntrick.api.server import create_app
        from agntrick.config import get_config

        # Set up test API key
        monkeypatch.setenv("AGNTRICK_CONFIG", "")  # Reset config
        config = get_config(force_reload=True)
        config.auth.api_keys = {"test-key-123": "tenant-1"}

        app = create_app()
        client = TestClient(app)

        response = client.get(
            "/api/v1/agents",
            headers={"X-API-Key": "test-key-123"}
        )

        assert response.status_code != 401

    def test_invalid_api_key_returns_401(self, monkeypatch) -> None:
        """Invalid API key should return 401."""
        from agntrick.api.server import create_app
        from agntrick.config import get_config

        config = get_config(force_reload=True)
        config.auth.api_keys = {"valid-key": "tenant-1"}

        app = create_app()
        client = TestClient(app)

        response = client.get(
            "/api/v1/agents",
            headers={"X-API-Key": "invalid-key"}
        )

        assert response.status_code == 401

    def test_missing_api_key_returns_401(self) -> None:
        """Missing API key should return 401."""
        from agntrick.api.server import create_app
        from agntrick.config import get_config

        config = get_config(force_reload=True)
        config.auth.api_keys = {"valid-key": "tenant-1"}

        app = create_app()
        client = TestClient(app)

        response = client.get("/api/v1/agents")

        assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agents && uv run pytest tests/test_api/test_auth.py -v`
Expected: FAIL (no /api/v1/agents route yet)

- [ ] **Step 3: Implement authentication**

Create `src/agntrick/api/auth.py`:

```python
"""API authentication utilities."""

from fastapi import Header, HTTPException
from typing import Optional

from agntrick.config import get_config


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Verify API key and return tenant_id.

    Args:
        x_api_key: API key from X-API-Key header.

    Returns:
        tenant_id associated with the API key.

    Raises:
        HTTPException: If API key is missing or invalid.
    """
    if x_api_key is None:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header."
        )

    config = get_config()
    tenant_id = config.auth.api_keys.get(x_api_key)

    if tenant_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key."
        )

    return tenant_id
```

Create `src/agntrick/api/deps.py`:

```python
"""FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends

from agntrick.api.auth import verify_api_key
from agntrick.storage.tenant_manager import TenantManager
from agntrick.storage.database import Database


# Type alias for tenant_id dependency
TenantId = Annotated[str, Depends(verify_api_key)]


def get_tenant_manager() -> TenantManager:
    """Get the tenant manager from app state."""
    from fastapi import Request
    from agntrick.api.server import create_app

    # This will be properly injected via app.state
    # For now, return a default instance
    from agntrick.config import get_config
    config = get_config()
    return TenantManager(base_path=config.storage.base_path)


def get_database(
    tenant_id: TenantId,
    manager: TenantManager = Depends(get_tenant_manager),
) -> Database:
    """Get database for the current tenant."""
    return manager.get_database(tenant_id)


# Type alias for database dependency
TenantDB = Annotated[Database, Depends(get_database)]
```

- [ ] **Step 4: Create agents route with auth**

Create `src/agntrick/api/routes/agents.py`:

```python
"""Agent execution endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agntrick.api.deps import TenantId, TenantDB
from agntrick.registry import AgentRegistry

router = APIRouter(prefix="/api/v1/agents", dependencies=[Depends(TenantId)])


class AgentRunRequest(BaseModel):
    """Request body for running an agent."""
    input: str
    thread_id: str | None = None


class AgentRunResponse(BaseModel):
    """Response from agent execution."""
    output: str
    agent: str


@router.get("")
async def list_agents(tenant_id: TenantId) -> list[str]:
    """List all available agents."""
    AgentRegistry.discover_agents()
    return AgentRegistry.list_agents()


@router.post("/{agent_name}/run", response_model=AgentRunResponse)
async def run_agent(
    agent_name: str,
    request: AgentRunRequest,
    tenant_id: TenantId,
    db: TenantDB,
) -> AgentRunResponse:
    """Run an agent with the given input."""
    import asyncio

    AgentRegistry.discover_agents()
    agent_cls = AgentRegistry.get(agent_name)

    if agent_cls is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    # Get agent-specific config
    from agntrick.config import get_config
    config = get_config()
    agent_config = config.get_agent_config(agent_name)

    # Create agent with tenant-scoped checkpointer
    checkpointer = db.get_checkpointer(is_async=True)
    agent = agent_cls(
        checkpointer=checkpointer,
        thread_id=request.thread_id or tenant_id,
        model_name=agent_config.model,
        temperature=agent_config.temperature or config.llm.temperature,
        _agent_name=agent_name,
    )

    # Run agent
    result = await agent.run(request.input)

    return AgentRunResponse(
        output=str(result),
        agent=agent_name,
    )
```

- [ ] **Step 5: Register agents route in server**

Update `src/agntrick/api/server.py` to include the agents router:

```python
from agntrick.api.routes import health, agents

# ... in create_app():
app.include_router(agents.router, tags=["agents"])
```

- [ ] **Step 6: Run auth tests**

Run: `cd ~/code/agents && uv run pytest tests/test_api/test_auth.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
cd ~/code/agents
git add src/agntrick/api/ tests/test_api/
git commit -m "feat: add API key authentication and agents endpoint"
```

---

## Phase 2: WhatsApp Channel Plugin

> **NOTE:** This phase works on the **separate** `~/code/agntrick-whatsapp` repository.
> All file paths below are relative to `~/code/agntrick-whatsapp` unless noted.
> Run commands from that directory.

### Task 2.1: Add Required Dependencies

**Files:**
- Modify: `~/code/agntrick-whatsapp/pyproject.toml`

- [ ] **Step 1: Add httpx dependency**

Run: `cd ~/code/agntrick-whatsapp && uv add httpx`

- [ ] **Step 2: Add pytest-asyncio for async tests**

Run: `cd ~/code/agntrick-whatsapp && uv add --dev pytest-asyncio`

- [ ] **Step 3: Commit**

```bash
cd ~/code/agntrick-whatsapp
git add pyproject.toml uv.lock
git commit -m "chore: add httpx and pytest-asyncio dependencies"
```

---

### Task 2.2: Create WhatsApp Channel Client

**Files:**
- Create: `~/code/agntrick-whatsapp/src/agntrick_whatsapp/channel_client.py`
- Create: `~/code/agntrick-whatsapp/tests/test_channel_client.py`

This task creates a thin client that:
1. Connects to WhatsApp via neonize (existing)
2. Forwards incoming messages to the agntrick API
3. Sends responses back to WhatsApp

- [ ] **Step 1: Write the failing test for channel client**

Create `~/code/agntrick-whatsapp/tests/test_channel_client.py`:

```python
"""Tests for WhatsApp channel client."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestChannelClient:
    """Tests for WhatsApp channel client."""

    @pytest.mark.asyncio
    async def test_process_message_calls_api(self) -> None:
        """Incoming message should be forwarded to API."""
        from agntrick_whatsapp.channel_client import ChannelClient

        client = ChannelClient(
            api_url="http://localhost:8000",
            api_key="test-key",
            tenant_id="tenant-1",
            default_agent="developer",
        )

        with patch("httpx.AsyncClient") as mock_http:
            mock_response = AsyncMock()
            mock_response.json = MagicMock(return_value={
                "output": "Agent response",
                "agent": "developer"
            })
            mock_response.raise_for_status = MagicMock()

            mock_context = AsyncMock()
            mock_context.post = AsyncMock(return_value=mock_response)
            mock_context.__aenter__ = AsyncMock(return_value=mock_context)
            mock_context.__aexit__ = AsyncMock(return_value=False)
            mock_http.return_value = mock_context

            result = await client.process_message("Hello, agent!")

            assert result == "Agent response"
            mock_context.post.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agntrick-whatsapp && uv run pytest tests/test_channel_client.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement channel client**

Create `~/code/agntrick-whatsapp/src/agntrick_whatsapp/channel_client.py`:

```python
"""WhatsApp channel client that connects to the agntrick API."""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ChannelClientConfig:
    """Configuration for channel client."""
    api_url: str = "http://localhost:8000"
    api_key: str = ""
    tenant_id: str = ""
    default_agent: str = "developer"


class ChannelClient:
    """Client that forwards WhatsApp messages to the agntrick API.

    This replaces the direct agent invocation with API calls,
    making WhatsApp a thin channel plugin.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        tenant_id: str,
        default_agent: str = "developer",
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._default_agent = default_agent

    async def process_message(
        self,
        message: str,
        agent: str | None = None,
        thread_id: str | None = None,
    ) -> str:
        """Process an incoming message via the API.

        Args:
            message: The message text.
            agent: Optional agent name override.
            thread_id: Optional conversation thread ID.

        Returns:
            The agent's response.
        """
        agent_name = agent or self._default_agent

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self._api_url}/api/v1/agents/{agent_name}/run",
                headers={"X-API-Key": self._api_key},
                json={
                    "input": message,
                    "thread_id": thread_id,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["output"]

    async def list_available_agents(self) -> list[str]:
        """List available agents from the API."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self._api_url}/api/v1/agents",
                headers={"X-API-Key": self._api_key},
            )
            response.raise_for_status()
            return response.json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/code/agntrick-whatsapp && uv run pytest tests/test_channel_client.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Update WhatsApp config to use API**

Update `src/agntrick_whatsapp/config.py` to add API configuration:

```python
@dataclass
class APIConfig:
    """API connection configuration."""
    url: str = "http://localhost:8000"
    api_key: str = ""
    tenant_id: str = ""
```

- [ ] **Step 6: Commit**

```bash
cd ~/code/agntrick-whatsapp
git add src/agntrick_whatsapp/channel_client.py src/agntrick_whatsapp/config.py tests/test_channel_client.py
git commit -m "feat: add WhatsApp channel client that connects to API"
```

---

### Task 2.2: Add WhatsApp Webhook Receiver to API

**Files:**
- Create: `src/agntrick/api/routes/channels.py`
- Create: `tests/test_api/test_channels.py`

- [ ] **Step 1: Write the failing test for webhook**

Create `tests/test_api/test_channels.py`:

```python
"""Tests for channel webhook endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestChannelWebhooks:
    """Tests for WhatsApp webhook receiver."""

    def test_whatsapp_webhook_receives_message(self, monkeypatch) -> None:
        """Webhook should receive and process WhatsApp messages."""
        from agntrick.api.server import create_app
        from agntrick.config import get_config

        config = get_config(force_reload=True)
        config.auth.api_keys = {"wa-key": "tenant-wa"}

        app = create_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/channels/whatsapp/message",
            headers={"X-API-Key": "wa-key"},
            json={
                "from": "+1234567890",
                "message": "Hello, agent!",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )

        assert response.status_code == 200
        assert "response" in response.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agents && uv run pytest tests/test_api/test_channels.py -v`
Expected: FAIL with 404

- [ ] **Step 3: Implement webhook endpoint**

Create `src/agntrick/api/routes/channels.py`:

```python
"""Channel webhook endpoints."""

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from agntrick.api.deps import TenantId

router = APIRouter(prefix="/api/v1/channels", tags=["channels"])


class WhatsAppMessage(BaseModel):
    """Incoming WhatsApp message."""
    from_number: str
    message: str
    timestamp: str
    message_id: Optional[str] = None
    thread_id: Optional[str] = None


class WhatsAppResponse(BaseModel):
    """Response to WhatsApp message."""
    response: str
    agent: str
    thread_id: str


@router.post("/whatsapp/message", response_model=WhatsAppResponse)
async def receive_whatsapp_message(
    msg: WhatsAppMessage,
    tenant_id: TenantId,
    background_tasks: BackgroundTasks,
) -> WhatsAppResponse:
    """Receive and process a WhatsApp message.

    This endpoint is called by the WhatsApp channel client
    when a new message is received.
    """
    import asyncio
    from agntrick.registry import AgentRegistry
    from agntrick.config import get_config
    from agntrick.storage.tenant_manager import TenantManager

    AgentRegistry.discover_agents()

    # Get default agent for WhatsApp
    config = get_config()
    # TODO: Get from channel config
    agent_name = "developer"

    # Get tenant database
    manager = TenantManager(base_path=config.storage.base_path)
    db = manager.get_database(tenant_id)

    # Create thread_id from phone number
    thread_id = msg.thread_id or f"wa:{msg.from_number}"

    # Run agent
    agent_cls = AgentRegistry.get(agent_name)
    if agent_cls is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    agent_config = config.get_agent_config(agent_name)
    checkpointer = db.get_checkpointer(is_async=True)
    agent = agent_cls(
        checkpointer=checkpointer,
        thread_id=thread_id,
        model_name=agent_config.model,
        temperature=agent_config.temperature or config.llm.temperature,
        _agent_name=agent_name,
    )

    result = await agent.run(msg.message)

    return WhatsAppResponse(
        response=str(result),
        agent=agent_name,
        thread_id=thread_id,
    )
```

- [ ] **Step 4: Register channels route**

Update `src/agntrick/api/server.py`:

```python
from agntrick.api.routes import health, agents, channels

# In create_app():
app.include_router(channels.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ~/code/agents && uv run pytest tests/test_api/test_channels.py -v`
Expected: PASS (1 test)

- [ ] **Step 6: Commit**

```bash
cd ~/code/agents
git add src/agntrick/api/routes/channels.py tests/test_api/test_channels.py
git commit -m "feat: add WhatsApp webhook receiver endpoint"
```

---

## Phase 3: Merge Toolkit into Monorepo

### Task 3.1: Copy Toolkit into Main Repo

**Files:**
- Copy: `~/code/agntrick-toolkit/src/agntrick_toolbox/` → `~/code/agents/src/agntrick_toolbox/`
- Copy: `~/code/agntrick-toolkit/tests/` → `~/code/agents/tests/toolbox/`
- Modify: `pyproject.toml`

- [ ] **Step 1: Copy toolkit source**

```bash
cp -r ~/code/agntrick-toolkit/src/agntrick_toolbox ~/code/agents/src/
```

- [ ] **Step 2: Copy toolkit tests**

```bash
mkdir -p ~/code/agents/tests/toolbox
cp -r ~/code/agntrick-toolkit/tests/* ~/code/agents/tests/toolbox/
```

- [ ] **Step 3: Merge dependencies**

Add toolkit dependencies to `~/code/agents/pyproject.toml`:

```toml
# Add to dependencies:
"ddgs>=9.5.2",
"beautifulsoup4>=4.12.0",
```

- [ ] **Step 4: Run all tests**

```bash
cd ~/code/agents
uv sync
make check
make test
```

- [ ] **Step 5: Commit**

```bash
cd ~/code/agents
git add src/agntrick_toolbox/ tests/toolbox/ pyproject.toml uv.lock
git commit -m "feat: merge agntrick-toolkit into monorepo"
```

---

## Phase 4: Documentation and Cleanup

### Task 4.1: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README with new architecture**

Update README.md to document:
- New API server (`agntrick serve`)
- Unified config format
- Multi-tenant support
- WhatsApp as channel plugin

- [ ] **Step 2: Update CLAUDE.md**

Update CLAUDE.md with new project structure and development workflow.

- [ ] **Step 3: Commit**

```bash
cd ~/code/agents
git add README.md CLAUDE.md
git commit -m "docs: update documentation for production-grade API"
```

---

## Verification Checklist

After completing all tasks:

- [ ] `agntrick serve` starts FastAPI server on port 8000
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `GET /api/v1/agents` lists all agents (requires API key)
- [ ] `POST /api/v1/agents/{name}/run` executes an agent (requires API key)
- [ ] Each tenant has isolated SQLite database
- [ ] WhatsApp channel client can connect to API
- [ ] All tests pass: `make check && make test`
- [ ] Coverage maintained at 80%+

---

## Rollback Instructions

If issues arise:

1. **Revert API changes:**
   ```bash
   cd ~/code/agents
   git revert HEAD~N  # Revert N commits for API work
   ```

2. **Restore separate toolkit:**
   ```bash
   rm -rf ~/code/agents/src/agntrick_toolbox
   rm -rf ~/code/agents/tests/toolbox
   git checkout HEAD~1 -- pyproject.toml
   ```

3. **Restore original config:**
   ```bash
   git checkout HEAD~M -- src/agntrick/config.py
   ```
