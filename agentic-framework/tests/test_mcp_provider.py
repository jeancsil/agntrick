import asyncio

import pytest

from agentic_framework.mcp.provider import MCPConnectionError, MCPProvider


class DummySession:
    def __init__(self, name: str):
        self.name = name

    async def __aenter__(self):
        return f"session-{self.name}"

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummyClient:
    callbacks = None
    tool_interceptors = None
    tool_name_prefix = None

    def __init__(self, config):
        self.config = config
        self.get_tools_calls = 0

    async def get_tools(self):
        self.get_tools_calls += 1
        return ["cached-tool"]

    def session(self, name: str):
        return DummySession(name)


def test_mcp_provider_get_tools_caches_result(monkeypatch):
    monkeypatch.setattr("agentic_framework.mcp.provider.MultiServerMCPClient", DummyClient)

    provider = MCPProvider(servers_config={"srv": {"url": "https://example.com", "transport": "sse"}})

    first = asyncio.run(provider.get_tools())
    second = asyncio.run(provider.get_tools())

    assert first == ["cached-tool"]
    assert second == ["cached-tool"]
    assert provider.client.get_tools_calls == 1


def test_mcp_provider_tool_session_loads_tools(monkeypatch):
    monkeypatch.setattr("agentic_framework.mcp.provider.MultiServerMCPClient", DummyClient)

    async def fake_load_mcp_tools(session, callbacks, tool_interceptors, server_name, tool_name_prefix):
        return [f"tool-{server_name}"]

    monkeypatch.setattr("agentic_framework.mcp.provider.load_mcp_tools", fake_load_mcp_tools)
    provider = MCPProvider(
        servers_config={
            "srv-a": {"url": "https://a.example.com", "transport": "sse"},
            "srv-b": {"url": "https://b.example.com", "transport": "sse"},
        }
    )

    async def run_test():
        async with provider.tool_session() as tools:
            assert tools == ["tool-srv-a", "tool-srv-b"]

    asyncio.run(run_test())


def test_mcp_provider_tool_session_fail_fast_false_continues(monkeypatch):
    monkeypatch.setattr("agentic_framework.mcp.provider.MultiServerMCPClient", DummyClient)

    async def fake_load_mcp_tools(session, callbacks, tool_interceptors, server_name, tool_name_prefix):
        if server_name == "bad":
            raise RuntimeError("boom")
        return [f"tool-{server_name}"]

    monkeypatch.setattr("agentic_framework.mcp.provider.load_mcp_tools", fake_load_mcp_tools)
    provider = MCPProvider(
        servers_config={
            "ok": {"url": "https://ok.example.com", "transport": "sse"},
            "bad": {"url": "https://bad.example.com", "transport": "sse"},
        }
    )

    async def run_test():
        async with provider.tool_session(fail_fast=False) as tools:
            assert tools == ["tool-ok"]

    asyncio.run(run_test())


def test_mcp_provider_tool_session_fail_fast_true_raises(monkeypatch):
    monkeypatch.setattr("agentic_framework.mcp.provider.MultiServerMCPClient", DummyClient)

    async def fake_load_mcp_tools(session, callbacks, tool_interceptors, server_name, tool_name_prefix):
        raise RuntimeError("boom")

    monkeypatch.setattr("agentic_framework.mcp.provider.load_mcp_tools", fake_load_mcp_tools)
    provider = MCPProvider(servers_config={"bad": {"url": "https://bad.example.com", "transport": "sse"}})

    async def run_test():
        async with provider.tool_session():
            return

    with pytest.raises(MCPConnectionError):
        asyncio.run(run_test())
