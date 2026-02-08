"""MCP (Model Context Protocol) as an injectable resource for agents."""

from agentic_framework.mcp.config import DEFAULT_MCP_SERVERS, get_mcp_servers_config
from agentic_framework.mcp.provider import MCPProvider

__all__ = [
    "DEFAULT_MCP_SERVERS",
    "get_mcp_servers_config",
    "MCPProvider",
]
