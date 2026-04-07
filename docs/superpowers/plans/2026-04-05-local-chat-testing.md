# Local Chat Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `agntrick chat` CLI command that exercises the full WhatsApp message pipeline locally via FastAPI TestClient, without requiring the Go gateway, WhatsApp auth, or deployment.

**Architecture:** A new `chat_cli.py` module creates a TestClient wrapping the real FastAPI app, starts the agentic-toolkit MCP server as a subprocess, sends a message through the webhook route, prints the response, and cleans up the subprocess. A dedicated "test" tenant in `.agntrick.yaml` provides isolation from production data.

**Tech Stack:** Typer CLI, FastAPI TestClient, subprocess management, atexit/signal cleanup

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/agntrick/chat_cli.py` | Create | Core logic: MCP subprocess lifecycle, TestClient invocation, cleanup |
| `src/agntrick/cli.py` | Modify | Register `chat` command on the Typer app |
| `.agntrick.yaml` | Modify | Add "test" tenant and "test-secret" API key |
| `tests/test_chat_cli.py` | Create | Unit and integration tests for the chat command |

---

### Task 1: Add test tenant configuration to `.agntrick.yaml`

**Files:**
- Modify: `.agntrick.yaml:87-95`

- [ ] **Step 1: Add test tenant and API key to config**

Add the "test" tenant entry alongside "primary", and add a "test-secret" API key:

```yaml
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

- [ ] **Step 2: Verify config loads correctly**

Run: `cd /Users/jeancsil/code/agents && uv run python -c "from agntrick.config import get_config; c = get_config(force_reload=True); print([t.id for t in c.whatsapp.tenants]); print(c.auth.api_keys)"`
Expected: `['primary', 'test']` and `{'your-api-key-here': 'primary', 'test-secret': 'test'}`

- [ ] **Step 3: Commit**

```bash
git add .agntrick.yaml
git commit -m "feat: add test tenant config for local chat testing"
```

---

### Task 2: Create `chat_cli.py` with MCP subprocess management

**Files:**
- Create: `src/agntrick/chat_cli.py`

- [ ] **Step 1: Write failing test for MCP subprocess lifecycle**

Create `tests/test_chat_cli.py`:

```python
"""Tests for the agntrick chat CLI command."""

import os
import signal
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agntrick.chat_cli import MCPServerManager, find_test_tenant


class TestMCPServerManager:
    """Tests for MCP server subprocess lifecycle."""

    def test_start_starts_subprocess_when_toolkit_path_set(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """When AGNTRICK_TOOLKIT_PATH is set, start launches a subprocess."""
        toolkit_path = str(tmp_path / "toolkit")
        os.makedirs(toolkit_path, exist_ok=True)
        monkeypatch.setenv("AGNTRICK_TOOLKIT_PATH", toolkit_path)

        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.poll.return_value = None  # process is running

        with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            manager = MCPServerManager()
            manager.start()

            mock_popen.assert_called_once()
            assert manager.process is mock_process

    def test_start_skips_when_toolkit_path_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When AGNTRICK_TOOLKIT_PATH is not set, no subprocess is started."""
        monkeypatch.delenv("AGNTRICK_TOOLKIT_PATH", raising=False)

        manager = MCPServerManager()
        manager.start()

        assert manager.process is None

    def test_stop_kills_running_process(self) -> None:
        """stop() terminates and waits for the subprocess."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.poll.return_value = None

        manager = MCPServerManager()
        manager.process = mock_process
        manager.stop()

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=5)

    def test_stop_is_safe_when_no_process(self) -> None:
        """stop() does nothing when no process was started."""
        manager = MCPServerManager()
        manager.stop()  # should not raise

    def test_stop_kills_process_group_on_sigterm_failure(self) -> None:
        """stop() tries to kill the process group if terminate fails."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.poll.return_value = None
        mock_process.terminate.side_effect = OSError("terminate failed")

        manager = MCPServerManager()
        manager.process = mock_process

        with patch("os.killpg") as mock_killpg:
            manager.stop()
            mock_killpg.assert_called_once()

    def test_stop_force_kills_on_timeout(self) -> None:
        """stop() force-kills if process doesn't terminate in time."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.poll.return_value = None
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)

        manager = MCPServerManager()
        manager.process = mock_process
        manager.stop()

        mock_process.kill.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jeancsil/code/agents && uv run pytest tests/test_chat_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agntrick.chat_cli'`

- [ ] **Step 3: Implement MCPServerManager and find_test_tenant**

Create `src/agntrick/chat_cli.py`:

```python
"""Local chat testing — send messages through the WhatsApp pipeline without deployment.

Uses FastAPI TestClient to exercise the real webhook route handler with a
dedicated "test" tenant. Optionally starts the agentic-toolkit MCP server
as a background subprocess for full tool testing.
"""

import logging
import os
import signal
import subprocess
from typing import TYPE_CHECKING

from agntrick.config import AgntrickConfig, WhatsAppTenantConfig, get_config

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Test tenant constants
TEST_TENANT_ID = "test"
TEST_TENANT_PHONE = "+1555000000"
TEST_API_KEY = "test-secret"
DEFAULT_TOOLBOX_PORT = 8080
MCP_STARTUP_TIMEOUT = 15  # seconds


class MCPServerManager:
    """Manages the agentic-toolkit MCP server subprocess lifecycle.

    Starts the toolkit as a background process, waits for it to be ready,
    and ensures cleanup on exit via stop(), atexit, and signal handlers.
    """

    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None
        self._toolkit_path: str | None = os.environ.get("AGNTRICK_TOOLKIT_PATH")

    def start(self) -> None:
        """Start the MCP server subprocess if toolkit path is configured."""
        if not self._toolkit_path:
            logger.info("AGNTRICK_TOOLKIT_PATH not set — running without MCP tools")
            return

        if not os.path.isdir(self._toolkit_path):
            logger.warning("AGNTRICK_TOOLKIT_PATH '%s' does not exist — skipping MCP server", self._toolkit_path)
            return

        cmd = ["uv", "run", "python", "-m", "agentic_toolkit"]
        logger.info("Starting MCP server: %s (cwd=%s)", " ".join(cmd), self._toolkit_path)

        self.process = subprocess.Popen(
            cmd,
            cwd=self._toolkit_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # new process group for clean termination
        )

        import atexit

        atexit.register(self.stop)

    def stop(self) -> None:
        """Terminate the MCP server subprocess."""
        if self.process is None:
            return

        if self.process.poll() is not None:
            return  # already dead

        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        except OSError:
            # terminate failed — try killing the process group
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
        finally:
            logger.info("MCP server subprocess stopped")
            self.process = None


def find_test_tenant(config: AgntrickConfig | None = None) -> WhatsAppTenantConfig:
    """Find the test tenant from configuration.

    Args:
        config: Optional config override. Loads from file if not provided.

    Returns:
        The test tenant configuration.

    Raises:
        SystemExit: If the test tenant is not configured.
    """
    if config is None:
        config = get_config()

    for tenant in config.whatsapp.tenants:
        if tenant.id == TEST_TENANT_ID:
            return tenant

    return WhatsAppTenantConfig(
        id=TEST_TENANT_ID,
        phone=TEST_TENANT_PHONE,
        default_agent="assistant",
        allowed_contacts=[TEST_TENANT_PHONE],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jeancsil/code/agents && uv run pytest tests/test_chat_cli.py::TestMCPServerManager -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/agntrick/chat_cli.py tests/test_chat_cli.py
git commit -m "feat: add MCPServerManager and find_test_tenant for local chat"
```

---

### Task 3: Implement the `send_chat_message` function (TestClient core)

**Files:**
- Modify: `src/agntrick/chat_cli.py`
- Modify: `tests/test_chat_cli.py`

- [ ] **Step 1: Write failing tests for send_chat_message**

Add to `tests/test_chat_cli.py`:

```python
from fastapi.testclient import TestClient


class TestFindTestTenant:
    """Tests for test tenant discovery."""

    def test_finds_test_tenant_from_config(self) -> None:
        """Returns the test tenant when configured."""
        from agntrick.config import AgntrickConfig, WhatsAppConfig, WhatsAppTenantConfig

        config = AgntrickConfig(
            whatsapp=WhatsAppConfig(
                tenants=[
                    WhatsAppTenantConfig(id="primary", phone="+34000000000"),
                    WhatsAppTenantConfig(
                        id="test",
                        phone="+1555000000",
                        default_agent="assistant",
                        allowed_contacts=["+1555000000"],
                    ),
                ]
            )
        )

        tenant = find_test_tenant(config)
        assert tenant.id == "test"
        assert tenant.phone == "+1555000000"
        assert tenant.default_agent == "assistant"

    def test_returns_default_when_not_configured(self) -> None:
        """Returns a default test tenant when not found in config."""
        from agntrick.config import AgntrickConfig, WhatsAppConfig

        config = AgntrickConfig(whatsapp=WhatsAppConfig(tenants=[]))
        tenant = find_test_tenant(config)
        assert tenant.id == "test"
        assert tenant.phone == "+1555000000"


class TestSendChatMessage:
    """Tests for the TestClient-based message sending."""

    def test_sends_message_with_correct_headers_and_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sends POST to webhook route with correct API key and payload."""
        from agntrick.chat_cli import send_chat_message

        # Track what the TestClient actually sends
        captured_request: dict = {}

        # Mock the webhook route handler to capture the request
        from unittest.mock import AsyncMock

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value="Test response")
        mock_agent_class = MagicMock(return_value=mock_agent)

        monkeypatch.setattr(
            "agntrick.api.routes.whatsapp.AgentRegistry.discover_agents",
            lambda: None,
        )
        monkeypatch.setattr(
            "agntrick.api.routes.whatsapp.AgentRegistry.get",
            lambda name: mock_agent_class,
        )
        monkeypatch.setattr(
            "agntrick.api.routes.whatsapp.AgentRegistry.get_mcp_servers",
            lambda name: None,
        )
        monkeypatch.setattr(
            "agntrick.api.routes.whatsapp.AgentRegistry.get_tool_categories",
            lambda name: [],
        )

        from agntrick.config import AgntrickConfig, AuthConfig, WhatsAppConfig, WhatsAppTenantConfig

        config = AgntrickConfig(
            auth=AuthConfig(api_keys={"test-secret": "test"}),
            whatsapp=WhatsAppConfig(
                tenants=[
                    WhatsAppTenantConfig(
                        id="test",
                        phone="+1555000000",
                        default_agent="assistant",
                        allowed_contacts=["+1555000000"],
                    ),
                ]
            ),
        )

        result = send_chat_message(
            message="Hello, test!",
            config=config,
        )

        assert result["response"] == "Test response"
        assert result["tenant_id"] == "test"
        mock_agent.run.assert_called_once_with("Hello, test!")

    def test_uses_custom_agent_when_provided(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Overrides the tenant's default agent when agent_name is provided."""
        from agntrick.chat_cli import send_chat_message

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value="Chef response")
        mock_agent_class = MagicMock(return_value=mock_agent)

        monkeypatch.setattr(
            "agntrick.api.routes.whatsapp.AgentRegistry.discover_agents",
            lambda: None,
        )
        monkeypatch.setattr(
            "agntrick.api.routes.whatsapp.AgentRegistry.get",
            lambda name: mock_agent_class,
        )
        monkeypatch.setattr(
            "agntrick.api.routes.whatsapp.AgentRegistry.get_mcp_servers",
            lambda name: None,
        )
        monkeypatch.setattr(
            "agntrick.api.routes.whatsapp.AgentRegistry.get_tool_categories",
            lambda name: [],
        )

        from agntrick.config import AgntrickConfig, AuthConfig, WhatsAppConfig, WhatsAppTenantConfig

        config = AgntrickConfig(
            auth=AuthConfig(api_keys={"test-secret": "test"}),
            whatsapp=WhatsAppConfig(
                tenants=[
                    WhatsAppTenantConfig(
                        id="test",
                        phone="+1555000000",
                        default_agent="assistant",
                        allowed_contacts=["+1555000000"],
                    ),
                ]
            ),
        )

        result = send_chat_message(
            message="Recipe for pasta",
            config=config,
            agent_name="chef",
        )

        assert result["response"] == "Chef response"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jeancsil/code/agents && uv run pytest tests/test_chat_cli.py::TestSendChatMessage -v`
Expected: FAIL — `ImportError: cannot import name 'send_chat_message'`

- [ ] **Step 3: Implement send_chat_message**

Add to `src/agntrick/chat_cli.py`:

```python
from typing import Any

from fastapi.testclient import TestClient


def send_chat_message(
    message: str,
    config: AgntrickConfig | None = None,
    agent_name: str | None = None,
    thread_id: str | None = None,
) -> dict[str, str]:
    """Send a test message through the WhatsApp webhook route via TestClient.

    Args:
        message: The message text to send.
        config: Optional config override. Loads from file if not provided.
        agent_name: Override the tenant's default agent.
        thread_id: Custom thread ID (auto-generated if not provided).

    Returns:
        Response dict with 'response' and 'tenant_id' keys.

    Raises:
        RuntimeError: If the webhook returns an error.
    """
    if config is None:
        config = get_config()

    tenant = find_test_tenant(config)
    phone = tenant.phone
    resolved_tenant_id = tenant.id

    # Override agent if specified by mutating the tenant config temporarily
    original_agent = tenant.default_agent
    if agent_name:
        tenant.default_agent = agent_name

    try:
        from agntrick.api.server import create_app

        app = create_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/channels/whatsapp/message",
            headers={"X-API-Key": TEST_API_KEY},
            json={
                "from": phone,
                "message": message,
                "tenant_id": resolved_tenant_id,
            },
        )
    finally:
        # Restore original agent
        tenant.default_agent = original_agent

    if response.status_code != 200:
        detail = response.json().get("detail", "Unknown error")
        raise RuntimeError(f"Chat request failed ({response.status_code}): {detail}")

    return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jeancsil/code/agents && uv run pytest tests/test_chat_cli.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/agntrick/chat_cli.py tests/test_chat_cli.py
git commit -m "feat: add send_chat_message with TestClient integration"
```

---

### Task 4: Implement the Typer `chat` command and register it

**Files:**
- Modify: `src/agntrick/chat_cli.py`
- Modify: `src/agntrick/cli.py`
- Modify: `tests/test_chat_cli.py`

- [ ] **Step 1: Write failing test for the CLI command**

Add to `tests/test_chat_cli.py`:

```python
from typer.testing import CliRunner


runner = CliRunner()


class TestChatCommand:
    """Tests for the 'agntrick chat' CLI command."""

    def test_chat_command_prints_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The chat command prints the agent's response."""
        from agntrick.chat_cli import chat_command

        # Mock send_chat_message to avoid real API calls
        with patch("agntrick.chat_cli.send_chat_message", return_value={"response": "Hello!", "tenant_id": "test"}):
            with patch("agntrick.chat_cli.MCPServerManager") as mock_mcp_cls:
                mock_mcp = MagicMock()
                mock_mcp_cls.return_value = mock_mcp

                result = runner.invoke(chat_command, ["Hello, test!"])
                assert result.exit_code == 0
                assert "Hello!" in result.output

    def test_chat_command_with_verbose(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The --verbose flag enables debug logging."""
        from agntrick.chat_cli import chat_command

        with patch("agntrick.chat_cli.send_chat_message", return_value={"response": "Hi", "tenant_id": "test"}):
            with patch("agntrick.chat_cli.MCPServerManager"):
                result = runner.invoke(chat_command, ["--verbose", "test message"])
                assert result.exit_code == 0
                assert "Hi" in result.output

    def test_chat_command_with_agent_override(self) -> None:
        """The --agent flag overrides the default agent."""
        from agntrick.chat_cli import chat_command

        with patch("agntrick.chat_cli.send_chat_message", return_value={"response": "Chef says hi", "tenant_id": "test"}) as mock_send:
            with patch("agntrick.chat_cli.MCPServerManager"):
                result = runner.invoke(chat_command, ["--agent", "chef", "cook something"])
                assert result.exit_code == 0
                mock_send.assert_called_once_with(
                    message="cook something",
                    agent_name="chef",
                )

    def test_chat_command_handles_error(self) -> None:
        """The command exits with code 1 when send_chat_message fails."""
        from agntrick.chat_cli import chat_command

        with patch("agntrick.chat_cli.send_chat_message", side_effect=RuntimeError("Agent not found")):
            with patch("agntrick.chat_cli.MCPServerManager"):
                result = runner.invoke(chat_command, ["test"])
                assert result.exit_code == 1
                assert "Agent not found" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jeancsil/code/agents && uv run pytest tests/test_chat_cli.py::TestChatCommand -v`
Expected: FAIL — `ImportError: cannot import name 'chat_command'`

- [ ] **Step 3: Implement the chat_command Typer app**

Add to `src/agntrick/chat_cli.py`:

```python
import time

import typer
from rich.console import Console

console = Console()


def chat_command_wrapper(
    message: str = typer.Argument(..., help="Message to send to the agent."),
    thread_id: str | None = typer.Option(None, "--thread-id", "-t", help="Thread ID to continue."),
    agent_name: str | None = typer.Option(None, "--agent", "-a", help="Agent name (default: from tenant config)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug output."),
) -> None:
    """Send a test message through the WhatsApp pipeline locally."""
    if verbose:
        configure_chat_logging("DEBUG")
    else:
        configure_chat_logging("WARNING")

    mcp_manager = MCPServerManager()
    try:
        mcp_manager.start()

        tenant = find_test_tenant()
        effective_agent = agent_name or tenant.default_agent
        thread = thread_id or f"whatsapp:{TEST_TENANT_ID}:{TEST_TENANT_PHONE}"

        console.print(f"[bold blue]Agent:[/bold blue] {effective_agent}")
        console.print(f"[bold blue]Thread:[/bold blue] {thread}")
        console.print()

        start_time = time.time()
        result = send_chat_message(
            message=message,
            agent_name=agent_name,
        )
        elapsed = time.time() - start_time

        console.print(result["response"])
        console.print()
        console.print(f"[dim][Completed in {elapsed:.1f}s][/dim]")

    except Exception as error:
        console.print(f"[bold red]Error:[/bold red] {error}")
        raise typer.Exit(code=1)
    finally:
        mcp_manager.stop()


# Expose as a standalone Typer app for registration in cli.py
chat_app = typer.Typer()
chat_app.command(name="chat")(chat_command_wrapper)


def configure_chat_logging(level: str) -> None:
    """Configure logging for the chat command."""
    logging.basicConfig(level=level, format="%(name)s - %(message)s", force=True)
```

Note: `chat_command` is exported as `chat_command_wrapper` — the tests import it as `chat_command` so we need to add an alias. Update the import in the test file accordingly, or rename. The function name in the module is `chat_command_wrapper`. The tests should import it as:

```python
from agntrick.chat_cli import chat_command_wrapper as chat_command
```

Update the test imports accordingly. Then register in `cli.py`.

- [ ] **Step 4: Register chat command in cli.py**

Add to `src/agntrick/cli.py` after the `serve` command and before `@app.callback`:

```python
# Register the chat command from chat_cli module
from agntrick.chat_cli import chat_app

app.add_typer(chat_app, name="chat")
```

Wait — `app.add_typer` would make it `agntrick chat chat`. We need a different approach. Since `chat_app` is a Typer with a single command named "chat", we can just register the callback function directly:

In `src/agntrick/cli.py`, add before the `@app.callback` decorator:

```python
from agntrick.chat_cli import chat_command_wrapper

app.command(name="chat")(chat_command_wrapper)
```

This registers `agntrick chat "message"` directly on the main Typer app.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/jeancsil/code/agents && uv run pytest tests/test_chat_cli.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run make check**

Run: `cd /Users/jeancsil/code/agents && make check`
Expected: No linting or type errors

- [ ] **Step 7: Commit**

```bash
git add src/agntrick/chat_cli.py src/agntrick/cli.py tests/test_chat_cli.py
git commit -m "feat: add 'agntrick chat' CLI command for local testing"
```

---

### Task 5: Run full test suite and verify CLI works end-to-end

**Files:**
- No new files

- [ ] **Step 1: Run make check && make test**

Run: `cd /Users/jeancsil/code/agents && make check && make test`
Expected: All checks and tests pass

- [ ] **Step 2: Verify CLI registration**

Run: `cd /Users/jeancsil/code/agents && uv run agntrick --help`
Expected: Output shows `chat` as an available command

- [ ] **Step 3: Final commit if any fixes needed**

If any issues were found and fixed:

```bash
git add -A
git commit -m "fix: address test/lint issues from local chat testing"
```
