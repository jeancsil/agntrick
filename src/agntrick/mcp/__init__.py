"""MCP (Model Context Protocol) as an injectable resource for agents."""

from agntrick.mcp.config import DEFAULT_MCP_SERVERS, get_mcp_servers_config
from agntrick.mcp.provider import MCPConnectionError, MCPProvider

__all__ = [
    "DEFAULT_MCP_SERVERS",
    "get_mcp_servers_config",
    "MCPConnectionError",
    "MCPProvider",
]
