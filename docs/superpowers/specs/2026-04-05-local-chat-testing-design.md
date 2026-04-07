# Local Chat Testing — Design Spec

**Date:** 2026-04-05
**Status:** Draft
**Branch:** feat/smarter-whatsapp-assistant

## Problem

Testing the WhatsApp assistant requires deploying to Digital Ocean and sending real WhatsApp messages. This makes the feedback loop slow and blocks the AI agent (Claude/Copilot) from verifying its own changes.

## Goal

A CLI command that exercises the full WhatsApp message pipeline locally — auth, tenant routing, agent execution, MCP tools, persistent memory — without the Go gateway, WhatsApp auth, or deployment.

## Usage

```bash
# One-off message (fresh conversation)
agntrick chat "What's the weather in São Paulo?"

# Continue an existing thread
agntrick chat "Tell me more" --thread-id "whatsapp:test:+1555000000"

# Specify a different agent
agntrick chat "Hello" --agent assistant

# Verbose output (tool calls, routing decisions)
agntrick chat "Search for HN top stories" --verbose
```

## Architecture

```
agntrick chat "message"
    │
    ▼
┌──────────────────────────────────────┐
│  chat_cli.py                         │
│                                      │
│  1. Load config                      │
│  2. Start MCP server (subprocess)    │
│  3. Create TestClient(app)           │
│  4. POST /api/v1/channels/           │
│     whatsapp/message                 │
│     Headers: X-API-Key: test-secret  │
│     Body: {from, message, tenant_id} │
│  5. Print response                   │
│  6. Kill MCP server subprocess       │
└──────────────────────────────────────┘
    │                   │
    ▼                   ▼
  Real webhook       Real MCP tools
  route handler      (web search, HN,
  (auth, tenant        fetch, etc.)
   lookup, agent
   init, graph)
```

### Why TestClient?

FastAPI's `TestClient` wraps the ASGI app in-process. It calls the real route handlers, middleware, dependency injection, and lifespan events — without starting an HTTP server. This means:

- **Same code path** as production: the `whatsapp_webhook` function in `routes/whatsapp.py` runs exactly as it does when called by the Go gateway.
- **Fast startup** — no server boot, no port binding.
- **No network** — no port conflicts, no firewall issues.
- **Clean shutdown** — TestClient cleans up after the request.

## Test Tenant

A dedicated "test" tenant isolates test data from production:

```yaml
# .agntrick.yaml addition
whatsapp:
  tenants:
    - id: "primary"
      phone: "+34123456789"
      default_agent: "assistant"
    - id: "test"
      phone: "+1555000000"
      default_agent: "assistant"
      allowed_contacts: ["+1555000000"]

auth:
  api_keys:
    "your-api-key-here": "primary"
    "test-secret": "test"
```

- **Phone:** `+1555000000` — a clearly fake number that won't collide with real data.
- **Agent:** Defaults to "assistant" but configurable via `--agent`.
- **Storage:** Separate SQLite DB at `~/.local/share/agntrick/tenants/test/agntrick.db`.
- **Thread ID:** `whatsapp:test:+1555000000` (auto-generated) or custom via `--thread-id`.

## MCP Server Auto-Start

The CLI starts the agentic-toolkit MCP server as a background process before sending the message:

1. Read `AGNTRICK_TOOLKIT_PATH` env var for the toolkit repo path.
2. Start the toolkit server as a subprocess.
3. Poll `localhost:8080/sse` until it responds (max 15s).
4. Send the message via TestClient.
5. On completion or error, terminate the subprocess.

**Environment variables:**
- `AGNTRICK_TOOLKIT_PATH` — absolute path to the agentic-toolkit repo (required when MCP tools are needed).

**Cleanup guarantees:**
- `atexit` handler kills the subprocess.
- Signal handlers for SIGINT/SIGTERM trigger cleanup.
- Subprocess is started in a new process group for clean termination.

**Graceful degradation:**
- If `AGNTRICK_TOOLKIT_PATH` is not set, print a warning and run without MCP tools (the agent still works, just without web search etc.).
- If the MCP server fails to start within the timeout, print an error and exit.

## CLI Command Design

**File:** `src/agntrick/chat_cli.py`

```python
@app.command(name="chat")
def chat(
    message: str = typer.Argument(..., help="Message to send to the agent."),
    thread_id: str | None = typer.Option(None, "--thread-id", "-t", help="Thread ID to continue."),
    agent: str | None = typer.Option(None, "--agent", "-a", help="Agent name (default: from tenant config)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show tool calls and routing."),
) -> None:
    """Send a test message through the WhatsApp pipeline locally."""
```

**Flow:**

1. Load config, find "test" tenant.
2. Start MCP server subprocess (if `AGNTRICK_TOOLKIT_PATH` is set).
3. Override the tenant's `default_agent` if `--agent` is provided.
4. Create `TestClient(create_app())`.
5. `POST /api/v1/channels/whatsapp/message` with `X-API-Key: test-secret`.
6. Print the response to stdout.
7. Kill MCP subprocess.

**Output format:**

```
$ agntrick chat "What's the weather in São Paulo?"

Agent: assistant
Thread: whatsapp:test:+1555000000

Currently in São Paulo, the weather is 28°C and sunny.

[Completed in 12.3s]
```

With `--verbose`:

```
$ agntrick chat -v "What's the weather in São Paulo?"

Agent: assistant
Thread: whatsapp:test:+1555000000

[router] → tool_use
[executor] Calling: web_search("weather São Paulo today")
[executor] Got results (2.1s)
[responder] Formatting response

Currently in São Paulo, the weather is 28°C and sunny.

[Completed in 12.3s]
```

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/agntrick/chat_cli.py` | Create | Chat command logic (MCP start, TestClient, cleanup) |
| `src/agntrick/cli.py` | Modify | Register `chat` command |
| `.agntrick.yaml` | Modify | Add test tenant and test API key |
| `tests/test_chat_cli.py` | Create | Tests for the chat command |

## Testing

### Unit Tests

- `test_chat_cli_sends_message_through_test_client` — verify TestClient is called with correct headers and body.
- `test_chat_cli_uses_test_tenant` — verify the test tenant config is used.
- `test_chat_cli_custom_agent` — verify `--agent` overrides the default.
- `test_chat_cli_custom_thread_id` — verify `--thread-id` is passed through.
- `test_chat_cli_mcp_server_auto_start` — verify subprocess is started when `AGNTRICK_TOOLKIT_PATH` is set.
- `test_chat_cli_mcp_server_cleanup` — verify subprocess is killed on completion and on error.
- `test_chat_cli_no_toolkit_path_warning` — verify graceful degradation when env var is unset.

### Integration Tests

- `test_chat_cli_full_pipeline` — send a real message through TestClient with a mocked LLM, verify the response comes back through the full webhook route.

## Constraints

- **No mocks in the pipeline.** The TestClient hits the real route handler. Only the LLM response may be mocked in tests to avoid API costs.
- **No Go gateway dependency.** The Go gateway and WhatsApp auth are completely out of the picture.
- **No network dependency for the core flow.** TestClient is in-process. Only MCP tools (web search, etc.) require network.
- **Safe cleanup.** The MCP server process must always be terminated, even on error or SIGINT.
