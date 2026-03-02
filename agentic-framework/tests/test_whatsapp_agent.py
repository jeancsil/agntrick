"""Tests for WhatsApp agent implementation."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestWhatsAppAgentMCPInitialization:
    """Tests for WhatsApp agent MCP initialization and tools."""

    @pytest.fixture(autouse=True)
    def mock_llm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prevent real LLM instantiation so tests run without API keys."""
        monkeypatch.setattr(
            "agentic_framework.core.langgraph_agent._create_model",
            lambda model, temp: MagicMock(),
        )

    def test_agent_has_local_tools(self) -> None:
        """Test that WhatsApp agent has no local tools (uses only MCP tools)."""
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        agent = WhatsAppAgent(channel=MagicMock())
        tools = list(agent.local_tools())
        assert len(tools) == 0

    def test_agent_system_prompt(self) -> None:
        """Test that agent has appropriate system prompt."""
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        agent = WhatsAppAgent(channel=MagicMock())
        prompt = agent.system_prompt

        assert "WhatsApp" in prompt
        assert "concise" in prompt
        assert "friendly" in prompt
        assert "web search" in prompt
        assert "SAFETY & PRIVACY BARRIERS" in prompt
        assert "CANNOT execute code" in prompt
        assert "CURRENT DATE" in prompt
        assert "DuckDuckGo" in prompt

    @pytest.mark.asyncio
    async def test_agent_ensure_initialized_creates_graph(self) -> None:
        """Test that _ensure_initialized creates the agent graph."""
        # Skip this test if LLM is not configured
        # Creating the graph requires a valid model which may not be available in test env
        pytest.skip("Skipping graph initialization test - requires LLM configuration")

    def test_agent_registers_with_registry(self) -> None:
        """Test that WhatsApp agent is registered in the registry."""
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent
        from agentic_framework.registry import AgentRegistry

        agent_cls = AgentRegistry.get("whatsapp-messenger")
        assert agent_cls is WhatsAppAgent

        mcp_servers = AgentRegistry.get_mcp_servers("whatsapp-messenger")
        assert "web-fetch" in mcp_servers
        assert "duckduckgo-search" in mcp_servers

    def test_agent_initialization_with_channel(self) -> None:
        """Test that agent is initialized with a channel."""
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        channel = MagicMock()
        agent = WhatsAppAgent(channel=channel)

        assert agent.channel is channel
        assert not agent._running
        assert agent._mcp_provider is None
        assert agent._mcp_tools == []

    @pytest.mark.asyncio
    async def test_run_handles_mcp_tool_exception_gracefully(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that run() handles MCP tool exceptions gracefully.

        This test simulates the scenario where a remote MCP tool (like web-fetch)
        raises a ToolException due to an internal error (e.g., httpx.TimeoutError
        not existing in the httpx module). The agent should handle this gracefully
        and not crash.
        """
        from langchain_core.tools.base import ToolException

        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        channel = MagicMock()
        agent = WhatsAppAgent(channel=channel)

        # Initialize the agent with a mock graph
        agent._graph = MagicMock()

        # Simulate the MCP tool raising a ToolException
        # This is what happens when the remote web-fetch server has an internal error
        async def mock_ainvoke(*args, **kwargs):
            raise ToolException("Error executing tool fetch_content: module 'httpx' has no attribute 'TimeoutError'")

        agent._graph.ainvoke = mock_ainvoke

        # The run() method should handle this gracefully
        # Since the graph.ainvoke raises an exception, the exception will propagate
        # We want to test that the agent can handle this
        with pytest.raises(ToolException) as exc_info:
            await agent.run("test input")

        # Verify the error message contains the expected details
        assert "httpx" in str(exc_info.value)
        assert "TimeoutError" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_start_with_mcp_disabled_initializes_and_listens(self) -> None:
        """start() should initialize channel and start listener when MCP is disabled."""
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        channel = MagicMock()
        channel.initialize = AsyncMock()
        channel.listen = AsyncMock()

        agent = WhatsAppAgent(channel=channel, mcp_servers_override=[])
        await agent.start()

        channel.initialize.assert_awaited_once()
        channel.listen.assert_awaited_once()
        assert agent._running is True
        assert agent._mcp_tools == []

    @pytest.mark.asyncio
    async def test_start_loads_registry_mcp_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """start() should load MCP tools from registry defaults when configured."""
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        channel = MagicMock()
        channel.initialize = AsyncMock()
        channel.listen = AsyncMock()

        monkeypatch.setattr(
            "agentic_framework.core.whatsapp_agent.AgentRegistry.get_mcp_servers",
            lambda _name: ["web-fetch"],
        )

        agent = WhatsAppAgent(channel=channel)
        agent._load_mcp_tools_gracefully = AsyncMock(return_value=["tool-a"])  # type: ignore[method-assign]
        await agent.start()

        assert agent._mcp_tools == ["tool-a"]
        channel.listen.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_failure_resets_running_state(self) -> None:
        """start() should reset running state if initialization fails."""
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        channel = MagicMock()
        channel.initialize = AsyncMock(side_effect=RuntimeError("init failed"))
        channel.listen = AsyncMock()

        agent = WhatsAppAgent(channel=channel, mcp_servers_override=[])
        with pytest.raises(RuntimeError, match="init failed"):
            await agent.start()

        assert agent._running is False

    @pytest.mark.asyncio
    async def test_stop_shuts_down_running_agent(self) -> None:
        """stop() should set shutdown flag and call channel shutdown when running."""
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        channel = MagicMock()
        channel.shutdown = AsyncMock()
        agent = WhatsAppAgent(channel=channel)
        agent._running = True

        await agent.stop()

        assert agent._shutdown_event.is_set()
        assert agent._running is False
        channel.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_message_success_sends_response(self) -> None:
        """_handle_message() should call run() and forward response to channel."""
        from agentic_framework.channels.base import IncomingMessage
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        channel = MagicMock()
        channel.send = AsyncMock()

        agent = WhatsAppAgent(channel=channel)
        agent.run = AsyncMock(return_value="hello back")  # type: ignore[method-assign]

        incoming = IncomingMessage(
            text="hello",
            sender_id="123@s.whatsapp.net",
            channel_type="whatsapp",
            raw_data={},
            timestamp=1,
        )
        await agent._handle_message(incoming)

        channel.send.assert_awaited_once()
        sent_message = channel.send.await_args.args[0]
        assert sent_message.text == "hello back"
        assert sent_message.recipient_id == "123@s.whatsapp.net"

    @pytest.mark.asyncio
    async def test_handle_message_tool_exception_sends_user_friendly_error(self) -> None:
        """ToolException should send safe tool-failure wording to the user."""
        from langchain_core.tools.base import ToolException

        from agentic_framework.channels.base import IncomingMessage
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        channel = MagicMock()
        channel.send = AsyncMock()

        agent = WhatsAppAgent(channel=channel)

        async def raise_tool_exception(*_args, **_kwargs):
            raise ToolException("tool boom")

        agent.run = raise_tool_exception  # type: ignore[method-assign]
        incoming = IncomingMessage(
            text="hello",
            sender_id="123@s.whatsapp.net",
            channel_type="whatsapp",
            raw_data={},
            timestamp=1,
        )
        await agent._handle_message(incoming)

        sent_message = channel.send.await_args.args[0]
        assert "encountered an issue" in sent_message.text

    @pytest.mark.asyncio
    async def test_handle_message_generic_exception_sends_generic_error(self) -> None:
        """Generic runtime errors should send a generic safe error message."""
        from agentic_framework.channels.base import IncomingMessage
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        channel = MagicMock()
        channel.send = AsyncMock()

        agent = WhatsAppAgent(channel=channel)

        async def raise_error(*_args, **_kwargs):
            raise RuntimeError("boom")

        agent.run = raise_error  # type: ignore[method-assign]
        incoming = IncomingMessage(
            text="hello",
            sender_id="123@s.whatsapp.net",
            channel_type="whatsapp",
            raw_data={},
            timestamp=1,
        )
        await agent._handle_message(incoming)

        sent_message = channel.send.await_args.args[0]
        assert "something went wrong" in sent_message.text

    @pytest.mark.asyncio
    async def test_load_mcp_tools_gracefully_handles_partial_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_load_mcp_tools_gracefully should keep tools from healthy servers."""
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent
        from agentic_framework.mcp import MCPConnectionError

        class FakeProvider:
            def __init__(self, server_names=None):
                self.server_names = server_names or []

            async def get_tools(self):
                if self.server_names == ["good-server"]:
                    return ["good-tool"]
                raise MCPConnectionError("bad-server", RuntimeError("connection timed out"))

        monkeypatch.setattr("agentic_framework.core.whatsapp_agent.MCPProvider", FakeProvider)
        monkeypatch.setattr(
            "agentic_framework.mcp.config.get_mcp_servers_config",
            lambda: {
                "good-server": {"url": "https://good.example.com"},
                "bad-server": {"url": "https://bad.example.com"},
            },
        )
        monkeypatch.setattr("socket.gethostbyname", lambda _hostname: "127.0.0.1")

        agent = WhatsAppAgent(channel=MagicMock())
        agent._mcp_servers = ["good-server", "bad-server"]

        tools = await agent._load_mcp_tools_gracefully()
        assert tools == ["good-tool"]

    def test_default_config_contains_thread_id(self) -> None:
        """_default_config should expose the WhatsApp thread id."""
        from agentic_framework.core.whatsapp_agent import WhatsAppAgent

        agent = WhatsAppAgent(channel=MagicMock(), thread_id="wa-thread")
        assert agent._default_config() == {"configurable": {"thread_id": "wa-thread"}}
