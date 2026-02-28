"""Central MCP server configuration.

Single source of truth for all MCP servers. Which agent may use which servers
is defined in AgentRegistry.register(..., mcp_servers=...).
"""

from typing import Any, Dict

# All available MCP servers. Each entry must include "transport".
# Resolved at runtime via get_mcp_servers_config() (e.g. env vars for API keys).
DEFAULT_MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    "kiwi-com-flight-search": {
        "url": "https://mcp.kiwi.com",
        "transport": "sse",
    },
    "web-fetch": {
        "url": "https://remote.mcpservers.org/fetch/mcp",
        "transport": "http",
    },
}


def get_mcp_servers_config(
    override: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Return MCP server config for MultiServerMCPClient.

    Merges DEFAULT_MCP_SERVERS with optional override. Does not mutate any shared state.
    """
    base = {k: dict(v) for k, v in DEFAULT_MCP_SERVERS.items()}
    if override:
        for k, v in override.items():
            base[k] = dict(base.get(k, {}))
            base[k].update(v)
    return {k: _resolve_server_config(k, v) for k, v in base.items()}


def _resolve_server_config(server_name: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of server config with env-dependent values resolved."""
    return dict(raw)
