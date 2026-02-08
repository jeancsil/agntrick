"""Central MCP server configuration.

Single source of truth for all MCP servers. Which agent may use which servers
is defined in AgentRegistry.register(..., mcp_servers=...).
"""

import os
from typing import Any, Dict

# All available MCP servers. Each entry must include "transport".
# Resolved at runtime via get_mcp_servers_config() (e.g. env vars for API keys).
DEFAULT_MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    "kiwi-com-flight-search": {
        "url": "https://mcp.kiwi.com",
        "transport": "sse",
    },
    "tinyfish": {
        "url": "https://agent.tinyfish.ai/mcp",
        "transport": "sse",
    },
    "tavily": {
        "url": "https://mcp.tavily.com/mcp",
        "transport": "sse",
    },
}


def _resolve_server_config(server_name: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of server config with env-dependent values resolved."""
    import logging

    out = dict(raw)
    if server_name == "tavily":
        key = os.environ.get("TAVILY_API_KEY")
        if not key:
            logging.warning("TAVILY_API_KEY not found in environment. Tavily MCP may fail to connect.")
        else:
            base = (raw.get("url") or "").rstrip("/")
            sep = "&" if "?" in base else "?"
            out["url"] = f"{base}{sep}tavilyApiKey={key}"
    return out


def get_mcp_servers_config(
    override: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Return MCP server config for MultiServerMCPClient.

    Merges DEFAULT_MCP_SERVERS with optional override, then resolves
    env-dependent values (e.g. TAVILY_API_KEY). Does not mutate any shared state.
    """
    base = {k: dict(v) for k, v in DEFAULT_MCP_SERVERS.items()}
    if override:
        for k, v in override.items():
            base[k] = dict(base.get(k, {}))
            base[k].update(v)
    return {k: _resolve_server_config(k, v) for k, v in base.items()}
