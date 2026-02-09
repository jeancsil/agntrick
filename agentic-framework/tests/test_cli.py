import asyncio

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
    monkeypatch.setattr(cli.AgentRegistry, "get_mcp_servers", lambda name: ["tavily"])
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
