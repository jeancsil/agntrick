import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

from agentic_framework import cli
from agentic_framework.mcp import MCPConnectionError


class FakeAgent:
    def __init__(self, initial_mcp_tools=None):
        self.initial_mcp_tools = initial_mcp_tools

    async def run(self, input_text):
        return f"handled:{input_text}:{self.initial_mcp_tools}"


class FakeSession:
    async def __aenter__(self):
        return ["mcp-tool"]

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeProvider:
    def __init__(self, server_names=None):
        self.server_names = server_names

    def tool_session(self):
        return FakeSession()


def test_execute_agent_without_mcp(monkeypatch):
    monkeypatch.setattr(cli.AgentRegistry, "get", lambda name: FakeAgent)
    monkeypatch.setattr(cli.AgentRegistry, "get_mcp_servers", lambda name: None)

    result = cli.execute_agent(agent_name="simple", input_text="hello", timeout_sec=5)
    assert result == "handled:hello:None"


def test_execute_agent_with_mcp(monkeypatch):
    monkeypatch.setattr(cli.AgentRegistry, "get", lambda name: FakeAgent)
    monkeypatch.setattr(cli.AgentRegistry, "get_mcp_servers", lambda name: ["web-fetch"])
    monkeypatch.setattr(cli, "MCPProvider", FakeProvider)

    result = cli.execute_agent(agent_name="chef", input_text="hello", timeout_sec=5)
    assert result == "handled:hello:['mcp-tool']"


def test_execute_agent_missing_agent_raises_exit(monkeypatch):
    monkeypatch.setattr(cli.AgentRegistry, "get", lambda name: None)

    with pytest.raises(typer.Exit):
        cli.execute_agent(agent_name="unknown", input_text="hello", timeout_sec=5)


def test_execute_agent_timeout_raises_timeout_error(monkeypatch):
    monkeypatch.setattr(cli.AgentRegistry, "get", lambda name: FakeAgent)
    monkeypatch.setattr(cli.AgentRegistry, "get_mcp_servers", lambda name: None)

    async def fake_wait_for(coro, timeout):
        coro.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(cli.asyncio, "wait_for", fake_wait_for)

    with pytest.raises(TimeoutError):
        cli.execute_agent(agent_name="simple", input_text="hello", timeout_sec=5)


def test_create_agent_command_handles_mcp_connection_error(monkeypatch):
    monkeypatch.setattr(cli.AgentRegistry, "get", lambda name: FakeAgent)

    def fake_execute_agent(agent_name, input_text, timeout_sec):
        raise MCPConnectionError("web-fetch", RuntimeError("down"))

    called = {"value": False}

    def fake_handle_error(error):
        called["value"] = True

    monkeypatch.setattr(cli, "execute_agent", fake_execute_agent)
    monkeypatch.setattr(cli, "_handle_mcp_connection_error", fake_handle_error)

    command = cli.create_agent_command("news")
    with pytest.raises(typer.Exit):
        command(input_text="hello", timeout_sec=5)

    assert called["value"] is True


def test_list_agents_prints_panel(monkeypatch):
    monkeypatch.setattr(cli.AgentRegistry, "list_agents", lambda: ["a", "b"])
    printed = {"value": None}

    def fake_print(content):
        printed["value"] = content

    monkeypatch.setattr(cli.console, "print", fake_print)
    cli.list_agents()

    assert printed["value"] is not None


@pytest.mark.asyncio
async def test_wait_for_shutdown_or_agent_exit_raises_when_agent_stops_early() -> None:
    async def stopped_agent() -> None:
        return None

    agent_task = asyncio.create_task(stopped_agent())

    with pytest.raises(RuntimeError, match="stopped before a shutdown signal"):
        await cli._wait_for_shutdown_or_agent_exit(agent_task, asyncio.Event())


@pytest.mark.asyncio
async def test_wait_for_shutdown_or_agent_exit_surfaces_agent_exception() -> None:
    async def failing_agent() -> None:
        raise RuntimeError("startup failed")

    agent_task = asyncio.create_task(failing_agent())

    with pytest.raises(RuntimeError, match="startup failed"):
        await cli._wait_for_shutdown_or_agent_exit(agent_task, asyncio.Event())


def test_whatsapp_reset_session_removes_directories(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage_dir = tmp_path / "whatsapp-storage"
    storage_dir.mkdir()
    session_file = storage_dir / "session.bin"
    session_file.write_text("session", encoding="utf-8")
    session_dir = storage_dir / "media"
    session_dir.mkdir()
    (session_dir / "photo.jpg").write_text("img", encoding="utf-8")
    dedup_db = storage_dir / "processed_messages.db"
    dedup_db.write_text("keep", encoding="utf-8")

    fake_config = SimpleNamespace(
        get_storage_path=lambda: storage_dir,
        privacy=SimpleNamespace(allowed_contact="+34 666 666 666", log_filtered_messages=False),
        model=None,
        mcp_servers=None,
        features=SimpleNamespace(typing_indicators=True),
        audio_transcriber=SimpleNamespace(model="whisper-large-v3-turbo", timeout=60.0, config_file=None),
    )

    monkeypatch.setattr(cli, "load_config", lambda path: fake_config)
    monkeypatch.setattr(cli.console, "print", lambda *args, **kwargs: None)

    cli.whatsapp_command(
        config_path="unused",
        allowed_contact=None,
        storage=None,
        mcp_servers=None,
        reset_session=True,
        verbose=False,
    )

    assert not session_file.exists()
    assert not session_dir.exists()
    assert dedup_db.exists()


def test_print_chained_causes_prints_all_causes(monkeypatch: pytest.MonkeyPatch) -> None:
    printed: list[str] = []
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))

    root = RuntimeError("root")
    middle = ValueError("middle")
    leaf = KeyError("leaf")
    root.__cause__ = middle
    middle.__cause__ = leaf

    cli._print_chained_causes(root)

    assert any("middle" in message for message in printed)
    assert any("leaf" in message for message in printed)


def test_handle_mcp_connection_error_prints_subexceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    printed: list[str] = []
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))

    grouped = ExceptionGroup("group", [RuntimeError("a"), RuntimeError("b")])
    error = MCPConnectionError("web-fetch", grouped)

    cli._handle_mcp_connection_error(error)

    assert any("sub-exception 1" in message for message in printed)
    assert any("sub-exception 2" in message for message in printed)
    assert any("web-fetch requires a valid remote URL" in message for message in printed)


def test_agent_info_missing_agent_raises_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.AgentRegistry, "get", lambda _: None)
    monkeypatch.setattr(cli.console, "print", lambda *_args, **_kwargs: None)

    with pytest.raises(typer.Exit):
        cli.agent_info("missing")


def test_agent_info_prints_details_and_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    printed: list[str] = []

    class ToolObj:
        name = "search"
        description = "Search tool"

    class InfoAgent:
        def __init__(self, initial_mcp_tools=None) -> None:
            self.initial_mcp_tools = initial_mcp_tools

        @property
        def system_prompt(self) -> str:
            return "prompt"

        def get_tools(self) -> list[ToolObj]:
            return [ToolObj()]

    monkeypatch.setattr(cli.AgentRegistry, "get", lambda _: InfoAgent)
    monkeypatch.setattr(cli.AgentRegistry, "get_mcp_servers", lambda _: ["web-fetch"])
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))

    cli.agent_info("developer")

    assert any("Agent Details" in message for message in printed)
    assert any("web-fetch" in message for message in printed)
    assert any("prompt" in message for message in printed)
    assert any("search" in message for message in printed)


def test_agent_info_handles_instantiation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    printed: list[str] = []

    class BrokenAgent:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(cli.AgentRegistry, "get", lambda _: BrokenAgent)
    monkeypatch.setattr(cli.AgentRegistry, "get_mcp_servers", lambda _: [])
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))

    cli.agent_info("developer")

    assert any("Could not instantiate agent" in message for message in printed)
    assert any("Could not instantiate agent to list tools" in message for message in printed)


def test_load_config_missing_file_raises_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    printed: list[str] = []
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))

    with pytest.raises(typer.Exit):
        cli.load_config(str(tmp_path / "missing.yaml"))

    assert any("Config file not found" in message for message in printed)


def test_load_config_yaml_error_raises_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("foo: [", encoding="utf-8")
    monkeypatch.setattr(cli.console, "print", lambda *_args, **_kwargs: None)

    with pytest.raises(typer.Exit):
        cli.load_config(str(config_file))


def test_load_config_prints_allowed_contact_hint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("privacy: {}", encoding="utf-8")
    printed: list[str] = []
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))
    monkeypatch.setattr(
        cli.WhatsAppAgentConfig,
        "model_validate",
        lambda _value: (_ for _ in ()).throw(ValueError("allowed_contact is required")),
    )

    with pytest.raises(typer.Exit):
        cli.load_config(str(config_file))

    assert any("allowed_contact" in message for message in printed)


def test_create_agent_command_success_prints_result(monkeypatch: pytest.MonkeyPatch) -> None:
    printed: list[str] = []
    monkeypatch.setattr(cli.AgentRegistry, "get", lambda _: object())
    monkeypatch.setattr(cli, "execute_agent", lambda **_kwargs: "ok")
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))

    command = cli.create_agent_command("simple")
    command(input_text="hello", timeout_sec=3)

    assert any("Running agent" in message for message in printed)
    assert any("Result from simple" in message for message in printed)


def test_create_agent_command_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.AgentRegistry, "get", lambda _: object())
    monkeypatch.setattr(cli, "execute_agent", lambda **_kwargs: (_ for _ in ()).throw(TimeoutError("slow")))
    monkeypatch.setattr(cli.console, "print", lambda *_args, **_kwargs: None)

    command = cli.create_agent_command("simple")
    with pytest.raises(typer.Exit):
        command(input_text="hello", timeout_sec=3)


def test_create_agent_command_handles_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    printed: list[str] = []
    monkeypatch.setattr(cli.AgentRegistry, "get", lambda _: object())

    def raise_error(**_kwargs):
        root = RuntimeError("inner")
        error = RuntimeError("outer")
        error.__cause__ = root
        raise error

    monkeypatch.setattr(cli, "execute_agent", raise_error)
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))
    monkeypatch.setattr(cli.logging.getLogger(), "isEnabledFor", lambda _level: False)

    command = cli.create_agent_command("simple")
    with pytest.raises(typer.Exit):
        command(input_text="hello", timeout_sec=3)

    assert any("Run with --verbose" in message for message in printed)


def test_main_prints_hint_without_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    printed: list[str] = []
    monkeypatch.setattr(cli, "configure_logging", lambda _verbose: None)
    monkeypatch.setattr(cli.logging, "info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))

    cli.main(SimpleNamespace(invoked_subcommand=None), verbose=False)

    assert any("No command provided" in message for message in printed)


def test_whatsapp_command_surfaces_startup_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    printed: list[str] = []

    class FailingAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def start(self) -> None:
            raise RuntimeError("startup failed")

        async def stop(self) -> None:
            return None

    fake_config = SimpleNamespace(
        get_storage_path=lambda: tmp_path,
        privacy=SimpleNamespace(allowed_contact="+34 666 666 666", log_filtered_messages=False),
        model=None,
        mcp_servers=None,
        features=SimpleNamespace(typing_indicators=True),
        audio_transcriber=SimpleNamespace(model="whisper-large-v3-turbo", timeout=60.0, config_file=None),
    )

    monkeypatch.setattr(cli, "load_config", lambda _path: fake_config)
    monkeypatch.setattr(cli, "WhatsAppChannel", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "WhatsAppRouterAgent", lambda **_kwargs: FailingAgent())
    monkeypatch.setattr(cli.AgentRegistry, "get_mcp_servers", lambda _name: [])
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))

    with pytest.raises(typer.Exit):
        cli.whatsapp_command(
            config_path="unused",
            allowed_contact=None,
            storage=None,
            mcp_servers=None,
            reset_session=False,
            verbose=False,
        )

    assert any("startup failed" in message for message in printed)
