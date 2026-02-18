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


class MCPConnectionError(Exception):
    """Raised when an MCP server fails to connect."""

    def __init__(self, server_name: str, cause: Exception):
        self.server_name = server_name
        self.cause = cause
        super().__init__(f"Failed to connect to MCP server '{server_name}': {cause}")


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
    async def tool_session(self, fail_fast: bool = True) -> Any:
        """
        Async context manager: load MCP tools with sessions that close on exit.

        IMPORTANT: Connections are opened sequentially. While slightly slower than
        parallel, this avoids "Attempted to exit cancel scope in a different task"
        errors from anyio (used by mcp) which requires task identity for cleanup.
        """
        import asyncio
        import logging
        from contextlib import AsyncExitStack

        CONN_TIMEOUT = 15
        all_tools = []

        # We use a stack to track entered contexts for reliable cleanup
        async with AsyncExitStack() as stack:
            for name in self._config:
                try:
                    logging.debug(f"Connecting to MCP server: {name}")
                    async with asyncio.timeout(CONN_TIMEOUT):
                        # We enter the context manager in the SAME task that will exit it
                        session = await stack.enter_async_context(self._client.session(name))

                        tools = await load_mcp_tools(
                            session,
                            callbacks=self._client.callbacks,
                            tool_interceptors=self._client.tool_interceptors,
                            server_name=name,
                            tool_name_prefix=self._client.tool_name_prefix,
                        )
                        logging.info(f"Loaded {len(tools)} tools from MCP server: {name}")
                        all_tools.extend(tools)
                except (asyncio.TimeoutError, TimeoutError) as e:
                    err = TimeoutError(f"Connection timed out after {CONN_TIMEOUT}s")
                    if fail_fast:
                        raise MCPConnectionError(name, err) from e
                    logging.error(f"Failed to connect to MCP server '{name}': {err}")
                except Exception as e:
                    if fail_fast:
                        logging.debug(f"MCP connection failed for '{name}'", exc_info=True)
                        raise MCPConnectionError(name, e) from e
                    logging.error(f"Failed to connect to MCP server '{name}': {e}")

            # Once all (or some) tools are loaded, yield them to the agent
            try:
                yield all_tools
            finally:
                # During stack exit, some servers (like those with misconfigured http transport)
                # might return 405 on DELETE or have other cleanup issues.
                # We want to ensure one server's cleanup failure doesn't mask the agent's result.
                # AsyncExitStack already handles this by aggregation, but let's be aware.
                logging.debug("Exiting MCP tool session stack")
