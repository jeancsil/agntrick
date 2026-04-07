# Production WhatsApp API — Multi-Tenant Agntrick

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Model: Use `glm-4.7` for all subagent dispatches** (implementer, reviewers) unless a task specifically requires more capable reasoning — then escalate to `glm-5.1` for that task only.

**Goal:** One server runs everything. Users send WhatsApp messages to themselves, the server processes them through agents.

**Constraints:**
- Memory: ≤ 512MB RAM
- Docker: Mandatory
- Safety: Handling other people's WhatsApp accounts
- Logging: Careful about PII, configurable levels

**Overlap note:** Tasks 1.1–1.5 overlap with `docs/superpowers/plans/2026-03-26-production-grade-api.md`. If that plan has already been executed, skip to Phase 2. If executing this plan standalone, Tasks 1.1–1.5 include everything needed.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         YOUR SERVER                            │
│                                                              │
│  ┌────────────┐   ┌─────────────────────────────────────────┐   │
│  │ REST API   │   │ WhatsApp Gateway (Go)               │   │
│  │ :8000      │   │ Single process, multiple sessions       │   │
│  └────────────┘   │                                     │   │
│       ▲           │  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│       │           │  │ Session │ │ Session │ │ Session │   │
│       │           │  │ Tenant1 │ │ Tenant2 │ │ Tenant3 │   │
│       │           │  └─────────┘ └─────────┘ └─────────┘   │
│       │           │                                     │   │
│       └───────────┴─────────────────────────────────────┘   │
│                   │                                      │
│           ┌───────┴───────┐                            │
│           │ Tenant Storage │                            │
│           │ tenants/{id}/  │                            │
│           │ - agntrick.db  │                            │
│           │ - logs/*.log   │                            │
│           └───────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   ┌──────────┐         ┌──────────┐         ┌──────────┐
   │ YOU      │         │ FRIEND 1  │         │ FRIEND 2  │
   │ Phone    │         │ Phone    │         │ Phone    │
   │          │         │          │         │          │
   │ Text     │         │ Text     │         │ Text     │
   │ yourself │         │ yourself │         │ yourself │
   └──────────┘         └──────────┘         └──────────┘
```

---

## Technical Context

### Memory Strategy

**Problem:** `neonize` spawns one Go process per WhatsApp client (~100-150MB each).

**Solution:** Single Go process with multiple sessions via `whatsmeow`.

**Formula:** `Total RAM ≈ 100MB (Python) + 30MB (Go base) + (N × 10MB per session)`

| Tenants | Memory | Headroom (512MB) |
|---------|--------|------------------|
| 1 | ~140MB | ~370MB |
| 5 | ~180MB | ~330MB |
| 10 | ~230MB | ~280MB |
| 20 | ~330MB | ~180MB |

### QR Code Expiration (Critical for Task 2.2)

QR codes expire every 20-40 seconds. Use **SSE** for `/qr/{tenant_id}`:

```
Browser                          Server
   │                               │
   │──── GET /qr/personal ───────▶│
   │◀─── SSE stream opens ───────│
   │◀─── event: qr_code ──────────│ (pushed immediately)
   │◀─── event: qr_code ──────────│ (fresh QR after 20s)
   │◀─── event: connected ────────│ (after scan)
```

### Self-Message Detection (Task 2.3)

In `whatsmeow`, self-messages are detected via:
```go
v.Info.IsFromMe && v.Info.Chat == client.Store.ID
```

### SQLite Concurrency (Task 1.2)

WAL mode is already enabled in existing `database.py`. Preserve it.

### Logging Strategy

| Level | What to Log | What NOT to Log |
|-------|-------------|-----------------|
| **INFO** | Tenant IDs, agent names, "message received from tenant X" | Phone numbers, message content, API keys |
| **WARNING** | Rate limits, retries, degraded mode | Auth tokens |
| **ERROR** | Error types (sanitized), tenant ID | Stack traces with PII, full request bodies |

---

## Config File (`.agntrick.yaml`)

```yaml
llm:
  provider: openai
  model: gpt-4o-mini
  temperature: 0.8

api:
  host: 127.0.0.1
  port: 8000

storage:
  base_path: ~/.local/share/agntrick

logging:
  level: INFO
  file: logs/agntrick.log

auth:
  api_keys:
    "admin-key-123": "admin"

whatsapp:
  tenants:
    - id: personal
      phone: "+34611111111"
      default_agent: developer
      allowed_contacts: []
    - id: work
      phone: "+34622222222"
      default_agent: developer
      allowed_contacts: []
```

---

## Task Dependency Graph

```
Task 1.1 (Config) ──────┐
Task 1.2 (TenantDB) ────┤──▶ Task 1.3 (FastAPI) ──▶ Task 1.4 (Auth) ──▶ Task 1.5 (Agents route)
                        │
                        └──▶ Task 2.1 (Go gateway) ──▶ Task 2.2 (QR) ──▶ Task 2.3 (Messages) ──▶ Task 2.4 (Phone mapping)
                                                                                    │
                                                                                    ▼
                                                              Task 3.1 (Integration) ──▶ Task 3.2 (Logging) ──▶ Task 3.3 (Docker)
                                                                                                                                 │
                                                                                                                                 ▼
                                                                                                          Task 4.1 (Resilience) ──▶ Task 4.2 (Docs) ──▶ Task 4.3 (Security)
```

**Parallelizable groups:**
- Tasks 1.1 + 1.2 can run in parallel (no dependencies on each other)
- Tasks 2.1–2.3 (Go) can start after Task 1.1 (needs config schema), independent of Tasks 1.3–1.5 (Python API)
- Task 2.4 (Python) depends on both Task 2.3 and Task 1.4

---

## Phase 1: API Foundation + Tenant Storage

**Deliverable:** `agntrick serve` starts API server with tenant isolation.

### Task 1.1: Extend Config Schema with API/Auth/Storage/WhatsApp Sections

**Files:**
- Modify: `src/agntrick/config.py`
- Create: `tests/test_config.py`

**Subagent model:** `glm-4.7`

**Context:** Current `config.py` has `LLMConfig`, `LoggingConfig`, `MCPConfig`, `AgentsConfig`. Need to add `APIConfig`, `AuthConfig`, `StorageConfig`, `WhatsAppConfig` (with `WhatsAppTenantConfig`).

- [ ] **Step 1:** Add new dataclasses to `src/agntrick/config.py`:

```python
@dataclass
class APIConfig:
    """API server configuration."""
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

@dataclass
class AuthConfig:
    """Authentication configuration."""
    api_keys: dict[str, str] = field(default_factory=dict)

@dataclass
class StorageConfig:
    """Storage configuration."""
    base_path: str | None = None

    def get_tenant_db_path(self, tenant_id: str) -> Path:
        safe_id = "".join(c for c in tenant_id if c.isalnum() or c in "-_")
        base = Path(self.base_path) if self.base_path else Path.home() / ".local" / "share" / "agntrick"
        return base / "tenants" / safe_id / "agntrick.db"

@dataclass
class WhatsAppTenantConfig:
    """Per-tenant WhatsApp configuration."""
    id: str = ""
    phone: str = ""
    default_agent: str = "developer"
    allowed_contacts: list[str] = field(default_factory=list)
    system_prompt: str | None = None

@dataclass
class WhatsAppConfig:
    """WhatsApp channel configuration."""
    tenants: list[WhatsAppTenantConfig] = field(default_factory=list)

    def get_tenant_by_phone(self, phone: str) -> WhatsAppTenantConfig | None:
        for t in self.tenants:
            if t.phone == phone:
                return t
        return None
```

- [ ] **Step 2:** Add new fields to `AgntrickConfig`:

```python
@dataclass
class AgntrickConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    api: APIConfig = field(default_factory=APIConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    whatsapp: WhatsAppConfig = field(default_factory=WhatsAppConfig)

    _config_path: str | None = field(default=None, init=False, repr=False)
```

- [ ] **Step 3:** Update `AgntrickConfig.from_dict()` to parse the new sections

- [ ] **Step 4:** Create `tests/test_config.py` with tests for:
  - Config loads all sections from YAML
  - `get_tenant_by_phone()` returns correct tenant
  - `get_tenant_db_path()` returns valid path with sanitized ID
  - Missing sections get sensible defaults

- [ ] **Step 5:** Run `make check && make test` — fix any issues

---

### Task 1.2: Tenant-Scoped Database Manager

**Files:**
- Create: `src/agntrick/storage/tenant_manager.py`
- Create: `tests/storage/test_tenant_manager.py`

**Subagent model:** `glm-4.7`

- [ ] **Step 1:** Create `src/agntrick/storage/tenant_manager.py` with `TenantManager` class:
  - `get_database(tenant_id: str) -> Database` — creates/returns per-tenant SQLite DB
  - `_get_tenant_db_path(tenant_id: str) -> Path` — sanitizes ID, returns path
  - `close_all()` — closes all cached connections
  - `list_tenants() -> list[str]` — lists tenants with DB files
  - Caches connections per tenant (same instance for same tenant)

- [ ] **Step 2:** Create `tests/storage/test_tenant_manager.py` with tests:
  - Each tenant gets separate DB file
  - Data isolation between tenants
  - Connection caching (same instance returned)
  - Tenant ID sanitization (no path traversal)

- [ ] **Step 3:** Run `make check && make test`

---

### Task 1.3: FastAPI Server Skeleton

**Files:**
- Create: `src/agntrick/api/__init__.py`
- Create: `src/agntrick/api/server.py`
- Create: `src/agntrick/api/routes/__init__.py`
- Create: `src/agntrick/api/routes/health.py`
- Modify: `src/agntrick/cli.py` (add `serve` command)

**Dependencies:** `uv add fastapi uvicorn httpx`

**Subagent model:** `glm-4.7`

- [ ] **Step 1:** Add dependencies: `uv add fastapi uvicorn httpx`

- [ ] **Step 2:** Create `src/agntrick/api/server.py`:
  - `create_app() -> FastAPI` — factory with lifespan
  - Lifespan: init `TenantManager`, store in `app.state`
  - Include health router
  - CORS middleware

- [ ] **Step 3:** Create `src/agntrick/api/routes/health.py`:
  - `GET /health` → `{"status": "ok"}`
  - `GET /ready` → `{"status": "ready", "checks": {...}}`

- [ ] **Step 4:** Add `serve` command to `src/agntrick/cli.py`

- [ ] **Step 5:** Create `tests/test_api/test_health.py`:
  - `/health` returns 200
  - `/ready` returns 200

- [ ] **Step 6:** Run `make check && make test`

---

### Task 1.4: API Authentication

**Files:**
- Create: `src/agntrick/api/auth.py`
- Create: `src/agntrick/api/deps.py`
- Create: `tests/test_api/test_auth.py`

**Subagent model:** `glm-4.7`

- [ ] **Step 1:** Create `src/agntrick/api/auth.py`:
  - `verify_api_key(x_api_key: str | None) -> str` — returns `tenant_id`
  - 401 for missing or invalid key

- [ ] **Step 2:** Create `src/agntrick/api/deps.py`:
  - `TenantId` type alias (Depends on verify_api_key)
  - `get_tenant_manager()` — from app state
  - `get_database(tenant_id, manager)` — tenant-scoped DB
  - `TenantDB` type alias

- [ ] **Step 3:** Create `tests/test_api/test_auth.py`:
  - Valid key returns tenant_id
  - Invalid key returns 401
  - Missing key returns 401

- [ ] **Step 4:** Run `make check && make test`

---

### Task 1.5: Agent Execution Endpoint

**Files:**
- Create: `src/agntrick/api/routes/agents.py`
- Create: `tests/test_api/test_agents_route.py`

**Subagent model:** `glm-4.7`

- [ ] **Step 1:** Create `src/agntrick/api/routes/agents.py`:
  - `GET /api/v1/agents` — list agents (requires API key)
  - `POST /api/v1/agents/{name}/run` — run agent with tenant-scoped checkpointer
  - Request model: `{input: str, thread_id: str | None}`
  - Response model: `{output: str, agent: str}`

- [ ] **Step 2:** Register agents router in `server.py`

- [ ] **Step 3:** Create `tests/test_api/test_agents_route.py`:
  - List agents returns list
  - Run agent returns response
  - Agent not found returns 404

- [ ] **Step 4:** Run `make check && make test`

---

**Phase 1 Done:** `agntrick serve` works, agents runnable via API with tenant isolation.

---

## Phase 2: WhatsApp Gateway (Go)

**Deliverable:** Single Go process handles multiple WhatsApp sessions, talks to Python API.

**Go testing:** Go tasks use `go test ./...` instead of `make check && make test`. Python tests still use the standard `make` commands. Go code lives in `gateway/` and is NOT checked by `make check` (which runs mypy + ruff on Python only).

### Task 2.1: Go Gateway — Project Structure + Config

**Files:**
- Create: `gateway/go.mod`
- Create: `gateway/main.go`
- Create: `gateway/config.go`
- Create: `gateway/config_test.go`

**Subagent model:** `glm-4.7`

**Context:** The Go gateway is a standalone binary that reads the same `.agntrick.yaml` config file as the Python API, manages multiple WhatsApp sessions via `whatsmeow`, and forwards messages to the Python API via HTTP.

- [ ] **Step 1:** Initialize Go module:

```bash
cd gateway
go mod init github.com/agntrick/gateway
go get github.com/mdp/whatsmeow
go get github.com/mdp/whatsmeow/store/sqlstore
go get github.com/mdp/whatsmeow/proto/waE2E
go get gopkg.in/yaml.v3
```

- [ ] **Step 2:** Create `gateway/config.go` with structs that mirror the YAML config:

```go
type Config struct {
    API      APIConfig      `yaml:"api"`
    WhatsApp WhatsAppConfig `yaml:"whatsapp"`
    Storage  StorageConfig  `yaml:"storage"`
}

type APIConfig struct {
    Host string `yaml:"host"`
    Port int    `yaml:"port"`
}

type WhatsAppConfig struct {
    Tenants []TenantConfig `yaml:"tenants"`
}

type TenantConfig struct {
    ID            string   `yaml:"id"`
    Phone         string   `yaml:"phone"`
    DefaultAgent  string   `yaml:"default_agent"`
    AllowedContacts []string `yaml:"allowed_contacts"`
}

type StorageConfig struct {
    BasePath string `yaml:"base_path"`
}
```

- [ ] **Step 3:** Create `gateway/config_test.go`:
  - Test YAML parsing
  - Test missing fields get defaults

- [ ] **Step 4:** Create `gateway/main.go` skeleton:
  - Read config from `.agntrick.yaml` (same file as Python)
  - Print loaded tenants on startup
  - Graceful shutdown on SIGINT

- [ ] **Step 5:** Run `cd gateway && go test ./... && go build .`

---

### Task 2.2: Go Gateway — Session Manager + QR Code via SSE

**Files:**
- Create: `gateway/session.go`
- Create: `gateway/session_test.go`
- Create: `gateway/qr.go`
- Create: `src/agntrick/api/routes/whatsapp.py` (Python SSE endpoint)
- Create: `tests/test_api/test_whatsapp_route.py`

**Subagent model:** `glm-4.7`

**Context:** QR codes expire every 20-40 seconds. The Python API serves an SSE endpoint that the Go gateway pushes QR codes to. A simple HTML page at `/qr/{tenant_id}` consumes the SSE stream.

- [ ] **Step 1:** Create `gateway/session.go`:
  - `SessionManager` struct — manages multiple `whatsmeow` clients
  - `NewSessionManager(config, storeDir) *SessionManager`
  - `StartSession(tenantID string) error` — creates/starts a whatsmeow client
  - `StopSession(tenantID string) error`
  - Each session stores data in `{storage_path}/tenants/{tenant_id}/whatsapp_session/`
  - On QR code event: POST to Python API `POST /api/v1/whatsapp/qr/{tenant_id}` with `{image: "base64..."}`

- [ ] **Step 2:** Create `gateway/qr.go`:
  - Generate QR code PNG from whatsmeow pairing data
  - Encode to base64
  - POST to Python API for caching

- [ ] **Step 3:** Create `src/agntrick/api/routes/whatsapp.py` (Python):
  - `GET /qr/{tenant_id}` — SSE endpoint returning `text/event-stream`
  - Events: `qr_code` (base64 image), `connected` (phone number)
  - `POST /api/v1/whatsapp/qr/{tenant_id}` — internal endpoint for Go gateway to push QR codes
  - `POST /api/v1/whatsapp/status/{tenant_id}` — internal endpoint for Go gateway to report connected/disconnected
  - Simple HTML page at `/qr/{tenant_id}/page` for browser viewing

- [ ] **Step 4:** Register whatsapp router in `server.py`

- [ ] **Step 5:** Create `tests/test_api/test_whatsapp_route.py`:
  - POST QR code stores it
  - POST status updates connection state
  - (SSE testing is manual/integration — skip in unit tests)

- [ ] **Step 6:** Create `gateway/session_test.go`:
  - Test session manager creates sessions with correct paths
  - Test concurrent session access

- [ ] **Step 7:** Run `cd gateway && go test ./...` AND `make check && make test`

---

### Task 2.3: Go Gateway — Message Handling

**Files:**
- Create: `gateway/message.go`
- Create: `gateway/message_test.go`

**Subagent model:** `glm-4.7`

**Context:** Self-messages in whatsmeow are detected via `v.Info.IsFromMe && v.Info.Chat == client.Store.ID`. Messages are forwarded to the Python API via `POST /api/v1/channels/whatsapp/message` and responses are sent back to WhatsApp.

- [ ] **Step 1:** Create `gateway/message.go`:
  - `handleMessage(session *Session, msg *events.Message)` — main handler
  - Self-message detection: `IsFromMe && Chat == Store.ID`
  - Forward to Python API: `POST http://{api_host}:{api_port}/api/v1/channels/whatsapp/message`
  - Include `X-API-Key` header, `from` (phone), `message` (text), `tenant_id`
  - Send response back to WhatsApp via `session.client.SendMessage()`

- [ ] **Step 2:** Create `gateway/message_test.go`:
  - Test self-message detection logic
  - Test message forwarding format (mock HTTP)
  - Test non-self messages are ignored

- [ ] **Step 3:** Run `cd gateway && go test ./...`

---

### Task 2.4: Python — WhatsApp Webhook + Phone-to-Tenant Registry

**Files:**
- Create: `src/agntrick/whatsapp/registry.py`
- Create: `tests/test_api/test_whatsapp_registry.py`

**Subagent model:** `glm-4.7`

**Context:** When the Go gateway detects a WhatsApp connection, it reports the phone number. The Python API maps phone → tenant_id using the config file. This mapping is used when messages arrive to identify which tenant's agent to run.

- [ ] **Step 1:** Create `src/agntrick/whatsapp/registry.py`:
  - `WhatsAppRegistry` class — maps phone numbers to tenant IDs
  - `register(tenant_id, phone)` — store mapping
  - `lookup_by_phone(phone) -> str | None` — return tenant_id
  - `lookup_by_tenant(tenant_id) -> str | None` — return phone
  - Initialized from config `whatsapp.tenants` on startup

- [ ] **Step 2:** Add webhook endpoint to `src/agntrick/api/routes/whatsapp.py`:
  - `POST /api/v1/channels/whatsapp/message` — receives message from Go gateway
  - Uses `WhatsAppRegistry` to resolve tenant from phone number
  - Runs the tenant's configured `default_agent`
  - Returns agent response to Go gateway

- [ ] **Step 3:** Create `tests/test_api/test_whatsapp_registry.py`:
  - Registry maps phone → tenant from config
  - Webhook processes message and returns response
  - Unknown phone number returns appropriate error

- [ ] **Step 4:** Run `make check && make test`

---

**Phase 2 Done:** WhatsApp gateway runs, users can scan QR via web page, messages flow to API and back.

---

## Phase 3: Integration + Logging + Docker

**Deliverable:** Full system runs in Docker with proper logging.

### Task 3.1: Structured Logging with PII Sanitization

**Files:**
- Create: `src/agntrick/logging_config.py`
- Create: `tests/test_logging_config.py`

**Subagent model:** `glm-4.7`

**Context:** All log entries must include `tenant_id`. PII (phone numbers, message content, API keys) must be sanitized at INFO level and above. Log files per-component: `api.log`, `whatsapp.log`, optional per-tenant `audit.log`.

- [ ] **Step 1:** Create `src/agntrick/logging_config.py`:
  - `setup_logging(config: AgntrickConfig)` — configures structured logging
  - `PIIFilter` logging filter — redacts phone numbers, message content, API keys
  - `TenantLogAdapter` — adds `tenant_id` to every log entry
  - Supports file + console handlers
  - Log format: `"{timestamp} [{level}] {tenant_id} {module}: {message}"`

- [ ] **Step 2:** Integrate logging into:
  - `src/agntrick/api/server.py` — setup in lifespan
  - `src/agntrick/api/routes/agents.py` — log agent runs with tenant_id
  - `src/agntrick/api/routes/whatsapp.py` — log message processing

- [ ] **Step 3:** Create `tests/test_logging_config.py`:
  - PIIFilter strips phone numbers and API keys
  - TenantLogAdapter adds tenant_id field
  - Log level configurable from YAML config

- [ ] **Step 4:** Run `make check && make test`

---

### Task 3.2: Docker — Multi-Stage Build (Python API + Go Gateway)

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `.dockerignore`

**Subagent model:** `glm-4.7`

**Context:** Current Dockerfile is Python-only. Need multi-stage build: stage 1 builds Go gateway, stage 2 builds Python API, final stage combines both. Memory limit 512MB.

- [ ] **Step 1:** Update `Dockerfile` to multi-stage build:

```dockerfile
# Stage 1: Build Go gateway
FROM golang:1.22-alpine AS go-builder
WORKDIR /build/gateway
COPY gateway/ .
RUN go build -o /agntrick-gateway .

# Stage 2: Python API (extends existing)
FROM python:3.12-slim AS python-base
# ... existing Python setup ...
COPY --from=go-builder /agntrick-gateway /usr/local/bin/

# Stage 3: Runtime
FROM python-base
# Copy both Python and Go binaries
# Health check
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1
```

- [ ] **Step 2:** Update `docker-compose.yml`:
  - Single `app` service running both API + gateway
  - Command: `sh -c "agntrick-gateway & agntrick serve"`
  - Memory limit: `mem_limit: 512m`
  - Volume mount for `{storage_path}`
  - Health check references `/health` endpoint
  - Environment variables from `.env`

- [ ] **Step 3:** Update `.dockerignore` to include/exclude Go files appropriately

- [ ] **Step 4:** Test build: `docker compose build`

- [ ] **Step 5:** Test run: `docker compose up -d && curl http://localhost:8000/health`

- [ ] **Step 6:** Run `make check && make test` (Python tests unaffected by Docker changes)

---

### Task 3.3: Integration Test — End-to-End Smoke Test

**Files:**
- Create: `tests/test_integration/test_e2e_whatsapp.py`
- Create: `gateway/integration_test.sh`

**Subagent model:** `glm-4.7` (test writing is mechanical)

**Context:** This is a manual/CI smoke test, not an automated unit test. The Python test verifies the API pipeline (webhook → agent → response) works. The Go script verifies the gateway starts and connects.

- [ ] **Step 1:** Create `tests/test_integration/test_e2e_whatsapp.py`:
  - Starts FastAPI test client
  - Registers a tenant via config
  - Posts a mock WhatsApp message to the webhook
  - Verifies response comes back with agent output
  - Uses mocked agent (monkeypatch) so no LLM calls needed

- [ ] **Step 2:** Create `gateway/integration_test.sh`:
  - Builds the gateway
  - Starts with a test config
  - Verifies it can read config and report tenants
  - (Actual WhatsApp connection requires real device — manual test)

- [ ] **Step 3:** Run `make check && make test`

- [ ] **Step 4:** Run `cd gateway && go test ./...`

---

**Phase 3 Done:** Full system runs in Docker, logging is structured, integration tests pass.

---

## Phase 4: Polish + Production

**Deliverable:** Production-ready, documented system.

### Task 4.1: Error Handling + Resilience

**Files:**
- Create: `src/agntrick/api/middleware.py`
- Create: `tests/test_api/test_middleware.py`

**Subagent model:** `glm-4.7`

- [ ] **Step 1:** Create `src/agntrick/api/middleware.py`:
  - Global exception handler — catches unhandled errors, returns sanitized JSON
  - Request logging middleware — logs method, path, tenant_id, duration
  - Never expose stack traces or internal details in production

- [ ] **Step 2:** Create `src/agntrick/api/resilience.py`:
  - `RetryConfig` dataclass — max_retries, backoff_factor
  - `retry_async(func, config)` — async retry with exponential backoff
  - Used by webhook handler when calling agents

- [ ] **Step 3:** Create `tests/test_api/test_middleware.py`:
  - Unhandled exception returns 500 with sanitized message
  - Request logging includes tenant_id and duration
  - Retry succeeds after transient failure

- [ ] **Step 4:** Register middleware in `server.py`

- [ ] **Step 5:** Run `make check && make test`

---

### Task 4.2: Documentation

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Subagent model:** `glm-4.7`

- [ ] **Step 1:** Update `README.md`:
  - Add "WhatsApp Multi-Tenant" section to Available Agents table
  - Add API endpoints to Architecture section
  - Add Docker quick start
  - Add config file reference with WhatsApp section
  - Keep existing content, add new sections

- [ ] **Step 2:** Update `CLAUDE.md`:
  - Add `gateway/` to project structure
  - Add `src/agntrick/api/` to project structure
  - Add `src/agntrick/whatsapp/` to project structure
  - Note Go testing uses `cd gateway && go test ./...`
  - Add `agntrick serve` to commands reference

- [ ] **Step 3:** Run `make check` (README/CLAUDE.md changes don't affect tests)

---

### Task 4.3: Security Hardening

**Files:**
- Create: `src/agntrick/api/security.py`
- Create: `tests/test_api/test_security.py`

**Subagent model:** `glm-4.7`

- [ ] **Step 1:** Create `src/agntrick/api/security.py`:
  - `RateLimiter` — simple in-memory rate limiting per tenant_id (requests per minute)
  - `validate_tenant_id(tenant_id: str) -> str` — strict sanitization (alphanumeric + dash/underscore only, max 64 chars)
  - `sanitize_message(message: str) -> str` — strip control characters, limit length

- [ ] **Step 2:** Add rate limiting to `deps.py` — per-tenant limit on agent run endpoints

- [ ] **Step 3:** Create `tests/test_api/test_security.py`:
  - Rate limiter blocks after threshold
  - Tenant ID validation rejects path traversal attempts (`../`, null bytes, etc.)
  - Message sanitization strips control characters

- [ ] **Step 4:** Run `make check && make test`

---

**Phase 4 Done:** Production-ready with error handling, documentation, and security hardening.

---

## Quick Start (After Implementation)

```bash
# 1. Configure
cat > .agntrick.yaml << EOF
llm:
  provider: openai

whatsapp:
  tenants:
    - id: personal
      phone: "+34611111111"
      default_agent: developer
EOF

# 2. Start with Docker
docker compose up -d

# 3. Visit QR page (one-time setup)
open http://localhost:8000/qr/personal/page
# Scan with WhatsApp

# 4. Send message to yourself
# You: "developer: explain this codebase"
# Bot: [agent response]
```

---

## Verification Checklist

- [ ] `agntrick serve` starts API on port 8000
- [ ] `GET /health` returns 200
- [ ] `GET /api/v1/agents` lists agents (with API key)
- [ ] `POST /api/v1/agents/{name}/run` executes agent
- [ ] Each tenant has isolated SQLite database
- [ ] Go gateway starts, reads config, reports tenants
- [ ] QR code visible at `/qr/{tenant_id}/page` via SSE
- [ ] WhatsApp webhook receives and processes messages
- [ ] Phone → tenant mapping works
- [ ] Memory usage ≤ 512MB with 3+ tenants
- [ ] Logs contain tenant_id, no PII at INFO level
- [ ] Docker compose builds and runs with single command
- [ ] `make check && make test` passes (Python)
- [ ] `cd gateway && go test ./...` passes (Go)

---

## Rollback

- Phase 1 is additive — no changes to existing code paths (only extends config)
- Phase 2 is new code in `gateway/` — doesn't affect existing usage
- Phase 3 modifies Docker files — can `git checkout HEAD~1 -- Dockerfile docker-compose.yml`
- Can run old CLI without API server (backward compatible)
