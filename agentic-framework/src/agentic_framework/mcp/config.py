"""Central MCP server configuration.

Agents can use a subset of these servers by name when constructing
an MCPProvider or when calling get_tools(server_names=...).
"""

from typing import Any, Dict

# Default MCP servers available to any agent that uses MCPProvider.
# Add or override via get_mcp_servers_config() (e.g. from env or file).
DEFAULT_MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    "kiwi-com-flight-search": {
        "url": "https://mcp.kiwi.com",
        "transport": "sse",
    },
    "tinyfish": {
        "url": "https://agent.tinyfish.ai/mcp",
    },
}


def get_mcp_servers_config(
    override: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Return MCP server config, optionally merged with overrides.

    Args:
        override: Optional dict of server name -> config to merge
                  (overrides DEFAULT_MCP_SERVERS for same keys).

    Returns:
        Merged config suitable for MultiServerMCPClient(servers).
    """
    config = dict(DEFAULT_MCP_SERVERS)
    if override:
        config.update(override)
    return config
