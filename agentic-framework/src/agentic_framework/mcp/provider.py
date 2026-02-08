"""MCP provider: injectable MCP client and session-scoped tools for agents."""

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, cast

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import (
    Connection,
    SSEConnection,
    StdioConnection,
    StreamableHttpConnection,
    WebsocketConnection,
)
from langchain_mcp_adapters.tools import load_mcp_tools

from agentic_framework.mcp.config import get_mcp_servers_config


class MCPProvider:
    """
    Reusable MCP client. Use get_tools() for programmatic use, or tool_session()
    for CLI/short-lived runs so connections are closed when the context exits.
    """

    def __init__(
        self,
        servers_config: Dict[
            str,
            StdioConnection | SSEConnection | StreamableHttpConnection | WebsocketConnection,
        ]
        | None = None,
        server_names: Optional[List[str]] = None,
    ):
        if servers_config is not None:
            self._config = dict(servers_config)
        else:
            resolved = get_mcp_servers_config()
            if server_names is not None:
                self._config = {k: cast(Connection, resolved[k]) for k in server_names if k in resolved}
            else:
                self._config = cast(Dict[str, Connection], resolved)

        self._client = MultiServerMCPClient(self._config)
        self._tools_cache: Optional[List[Any]] = None

    @property
    def client(self) -> MultiServerMCPClient:
        return self._client

    async def get_tools(self) -> List[Any]:
        """Return LangChain tools from configured server(s). Cached after first call.
        Leaves connections open; use tool_session() in CLI so connections close.
        """
        if self._tools_cache is None:
            self._tools_cache = await self._client.get_tools()
        return self._tools_cache

    @asynccontextmanager
    async def tool_session(self):
        """
        Async context manager: load MCP tools with sessions that close on exit.
        Connections are opened in parallel to avoid blocking on one slow server.
        """
        import asyncio
        import logging
        from contextlib import AsyncExitStack

        # Per-server connection timeout to avoid blocking the whole agent
        CONN_TIMEOUT = 10

        async def _load_one(stack: AsyncExitStack, name: str) -> List[Any]:
            try:
                logging.debug(f"Connecting to MCP server: {name}")
                async with asyncio.timeout(CONN_TIMEOUT):
                    session = await stack.enter_async_context(self._client.session(name))
                    tools = await load_mcp_tools(
                        session,
                        callbacks=self._client.callbacks,
                        tool_interceptors=self._client.tool_interceptors,
                        server_name=name,
                        tool_name_prefix=self._client.tool_name_prefix,
                    )
                    logging.info(f"Loaded {len(tools)} tools from MCP server: {name}")
                    return tools
            except (asyncio.TimeoutError, Exception) as e:
                logging.error(f"Failed to connect to MCP server '{name}': {e}")
                return []

        async with AsyncExitStack() as stack:
            # Load all in parallel
            tasks = [_load_one(stack, name) for name in self._config]
            results = await asyncio.gather(*tasks)
            all_tools = [t for sublist in results for t in sublist]
            yield all_tools
