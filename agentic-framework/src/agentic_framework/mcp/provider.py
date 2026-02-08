"""MCP provider: injectable MCP client and tools for agents."""

from typing import Any, Dict, List, Optional

from langchain_mcp_adapters.client import MultiServerMCPClient

from agentic_framework.mcp.config import get_mcp_servers_config


class MCPProvider:
    """
    Reusable MCP client and tool factory. Inject into any agent that needs MCP tools.

    Usage:
        # Default: all servers from config
        provider = MCPProvider()
        tools = await provider.get_tools()

        # Subset of servers (e.g. only travel-related)
        provider = MCPProvider(server_names=["kiwi-com-flight-search"])
        tools = await provider.get_tools()

        # Custom config (e.g. from env or app config)
        provider = MCPProvider(servers_config={"tinyfish": {"url": "https://agent.tinyfish.ai/mcp"}})
    """

    def __init__(
        self,
        servers_config: Dict[str, Dict[str, Any]] | None = None,
        server_names: Optional[List[str]] = None,
    ):
        """
        Args:
            servers_config: Full servers dict for MultiServerMCPClient.
                            If None, uses get_mcp_servers_config() (defaults).
            server_names: If given, use only these server keys from the effective config.
                          Ignored if servers_config is provided (use a pre-filtered config).
        """
        if servers_config is not None:
            self._config = dict(servers_config)
        else:
            self._config = get_mcp_servers_config()
            if server_names is not None:
                self._config = {k: self._config[k] for k in server_names if k in self._config}

        self._client = MultiServerMCPClient(self._config)
        self._tools_cache: Optional[List[Any]] = None

    @property
    def client(self) -> MultiServerMCPClient:
        """Access the underlying MCP client if needed."""
        return self._client

    async def get_tools(self) -> List[Any]:
        """Return LangChain tools from the configured MCP server(s). Cached after first call."""
        if self._tools_cache is None:
            self._tools_cache = await self._client.get_tools()
        return self._tools_cache
