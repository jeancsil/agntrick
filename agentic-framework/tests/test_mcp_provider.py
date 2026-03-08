"""Tests for agntrick package - MCP provider module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agntrick.mcp.provider import MCPConnectionError, MCPProvider


class TestMCPConnectionError:
    """Test MCPConnectionError exception."""

    def test_mcp_connection_error_initialization(self):
        """Test MCPConnectionError initialization."""
        cause = Exception("connection failed")
        error = MCPConnectionError("test-server", cause)

        assert error.server_name == "test-server"
        assert error.cause == cause
        assert "Failed to connect to MCP server 'test-server'" in str(error)


class TestMCPProvider:
    """Test MCPProvider class."""

    def test_mcp_provider_initialization_with_servers_config(self):
        """Test MCPProvider initialization with servers config."""
        servers_config = {"test-server": MagicMock()}
        provider = MCPProvider(servers_config=servers_config)

        assert provider._config == servers_config

    def test_mcp_provider_client_property(self):
        """Test client property returns MultiServerMCPClient."""
        provider = MCPProvider(servers_config={"test": MagicMock()})

        assert provider.client is not None
        # Should be the same instance
        assert provider.client is provider.client

    def test_mcp_provider_initialization_with_server_names(self):
        """Test MCPProvider initialization with server names filter."""
        mock_servers_config = {
            "server1": MagicMock(),
            "server2": MagicMock(),
            "server3": MagicMock(),
        }

        provider = MCPProvider(
            servers_config=mock_servers_config,
            server_names=["server1", "server3"]
        )

        assert "server1" in provider._config
        assert "server3" in provider._config
        assert "server2" not in provider._config

    @pytest.mark.asyncio
    async def test_mcp_provider_get_tools_caches_result(self):
        """Test get_tools caches result after first call."""
        mock_client = MagicMock()
        mock_tools = [MagicMock(name="tool1"), MagicMock(name="tool2")]

        # First call returns tools
        mock_client.get_tools = AsyncMock(return_value=mock_tools)

        provider = MCPProvider(servers_config={"test": MagicMock()})
        provider._client = mock_client

        # First call
        result1 = await provider.get_tools()
        assert result1 == mock_tools

        # Second call should return cached result
        result2 = await provider.get_tools()
        assert result2 == mock_tools

        # Client.get_tools should only be called once
        mock_client.get_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_mcp_provider_tool_session_success(self):
        """Test tool_session context manager with successful connection."""
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_client.session = MagicMock(return_value=mock_session)

        provider = MCPProvider(servers_config={"test-server": MagicMock()})
        provider._client = mock_client

        with patch("agntrick.mcp.provider.load_mcp_tools") as mock_load_tools, \
             patch("agntrick.mcp.provider.AsyncExitStack") as mock_stack:
            mock_load_tools.return_value = [MagicMock()]
            mock_stack.return_value.__aenter__ = AsyncMock(return_value=MagicStack())
            mock_stack.return_value.__aexit__ = AsyncMock(return_value=None)

            async with provider.tool_session() as tools:
                assert tools is not None

    @pytest.mark.asyncio
    async def test_mcp_provider_tool_session_timeout(self):
        """Test tool_session handles timeout errors."""
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_client.session = MagicMock(return_value=mock_session)

        provider = MCPProvider(servers_config={"test-server": MagicMock()})
        provider._client = mock_client

        with pytest.raises(MCPConnectionError) as exc_info:
            async with provider.tool_session() as tools:
                pass

        assert exc_info.value.server_name == "test-server"

    @pytest.mark.asyncio
    async def test_mcp_provider_tool_session_connection_error(self):
        """Test tool_session handles connection errors."""
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("connection failed"))
        mock_client.session = MagicMock(return_value=mock_session)

        provider = MCPProvider(servers_config={"test-server": MagicMock()})
        provider._client = mock_client

        with pytest.raises(MCPConnectionError) as exc_info:
            async with provider.tool_session() as tools:
                pass

        assert exc_info.value.server_name == "test-server"

    @pytest.mark.asyncio
    async def test_mcp_provider_tool_session_fail_fast_false(self):
        """Test tool_session with fail_fast=False continues on errors."""
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("connection failed"))
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_client.session = MagicMock(return_value=mock_session)

        provider = MCPProvider(servers_config={"test-server": MagicMock()})
        provider._client = mock_client

        with patch("agntrick.mcp.provider.load_mcp_tools", return_value=[]), \
             patch("agntrick.mcp.provider.AsyncExitStack") as mock_stack, \
             patch("agntrick.mcp.provider.logging.error") as mock_log_error:
            mock_stack.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_stack.return_value.__aexit__ = AsyncMock(return_value=None)

            # Should not raise with fail_fast=False
            async with provider.tool_session(fail_fast=False) as tools:
                pass

            # Should log error
            mock_log_error.assert_called()

    @pytest.mark.asyncio
    async def test_mcp_provider_tool_session_multiple_servers(self):
        """Test tool_session with multiple servers."""
        mock_client = MagicMock()

        def mock_session_factory(name):
            session = MagicMock()
            session.__aenter__ = AsyncMock(return_value=session)
            session.__aexit__ = AsyncMock(return_value=None)
            return session

        mock_client.session = MagicMock(side_effect=mock_session_factory)

        provider = MCPProvider(servers_config={
            "server1": MagicMock(),
            "server2": MagicMock(),
            "server3": MagicMock(),
        })
        provider._client = mock_client

        with patch("agntrick.mcp.provider.load_mcp_tools", return_value=[MagicMock()]), \
             patch("agntrick.mcp.provider.AsyncExitStack") as mock_stack:
            mock_stack.return_value.__aenter__ = AsyncMock(return_value=MagicStack())
            mock_stack.return_value.__aexit__ = AsyncMock(return_value=None)

            async with provider.tool_session() as _tools:
                # Should have tools from all servers
                pass

            # Should have entered context for each server
            assert mock_client.session.call_count == 3


class MagicMockStack:
    """Mock AsyncExitStack-like object for testing."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None
