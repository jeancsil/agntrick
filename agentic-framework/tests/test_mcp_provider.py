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

