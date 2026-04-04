"""MCP tool call interceptors for response processing."""

import logging
from collections.abc import Awaitable, Callable
from typing import Union

from langchain_core.messages import ToolMessage
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.types import CallToolResult, TextContent

logger = logging.getLogger(__name__)

# Default maximum response size in characters (~5K tokens).
# Enough for useful content without bloating the LLM context window.
DEFAULT_MAX_RESPONSE_SIZE = 20_000

# The result type from the handler chain.  We only intercept
# ``CallToolResult`` (the raw MCP response).  ``ToolMessage`` and
# ``Command`` are LangGraph-level wrappers that are already shaped by
# higher-level interceptors, so we pass them through untouched.
try:
    from langgraph.types import Command  # noqa: F401

    _HandlerResult = Union[CallToolResult, ToolMessage, Command]  # type: ignore[misc]
except ImportError:
    _HandlerResult = Union[CallToolResult, ToolMessage]  # type: ignore[misc]


class ResponseTruncator:
    """ToolCallInterceptor that truncates oversized MCP tool responses.

    This is a defense-in-depth layer: even if an MCP server returns large
    responses, this interceptor truncates them before they enter the LLM
    context window. This prevents the 100s-of-KB responses that cause
    model confusion and excessive latency.

    Implements the ``ToolCallInterceptor`` protocol from
    ``langchain_mcp_adapters.interceptors``.

    Args:
        max_response_size: Maximum characters for text content in a single
            tool response. Defaults to 20000 (~5K tokens, enough for useful
            content without bloating context).

    Example:
        >>> truncator = ResponseTruncator(max_response_size=20_000)
        >>> provider = MCPProvider(
        ...     server_names=["toolbox"],
        ...     tool_interceptors=[truncator],
        ... )
    """

    def __init__(self, max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE) -> None:
        self.max_response_size = max_response_size

    async def __call__(
        self,
        request: MCPToolCallRequest,
        handler: Callable[[MCPToolCallRequest], Awaitable[_HandlerResult]],
    ) -> _HandlerResult:
        """Intercept tool response and truncate if needed.

        Only truncates ``CallToolResult`` responses.  ``ToolMessage`` and
        ``Command`` results are passed through unchanged.

        Args:
            request: MCPToolCallRequest from the interceptor chain.
            handler: Next handler in the chain (executes the actual tool).

        Returns:
            CallToolResult with text content truncated if over limit,
            or the original result if it is not a CallToolResult.
        """
        result = await handler(request)

        # Only intercept raw MCP CallToolResult — pass through
        # LangGraph-level wrappers unchanged.
        if not isinstance(result, CallToolResult):
            return result

        return self._truncate(result)

    def _truncate(self, result: CallToolResult) -> CallToolResult:
        """Truncate text content in a CallToolResult if it exceeds the limit."""
        # Calculate total text content size
        text_blocks = [c for c in result.content if isinstance(c, TextContent)]
        total_chars = sum(len(b.text) for b in text_blocks)

        if total_chars <= self.max_response_size:
            return result

        # Truncate: distribute budget across text blocks proportionally.
        # Reserve space for the truncation notice so the final result
        # stays within budget.
        notice = f"\n\n[Response truncated at {self.max_response_size:,} chars. Original size: {total_chars:,} chars]"
        budget = self.max_response_size - len(notice)
        new_content: list[object] = []

        for block in result.content:
            if isinstance(block, TextContent):
                # Proportional share of budget
                block_budget = int(budget * len(block.text) / total_chars)
                if block_budget > 0 and len(block.text) > block_budget:
                    truncated_text = block.text[:block_budget]
                    new_content.append(TextContent(type="text", text=truncated_text))
                else:
                    new_content.append(block)
            else:
                # Non-text content passes through unchanged
                new_content.append(block)

        # Add truncation notice to last text block
        for i in range(len(new_content) - 1, -1, -1):
            if isinstance(new_content[i], TextContent):
                existing = new_content[i]
                assert isinstance(existing, TextContent)
                new_content[i] = TextContent(
                    type="text",
                    text=existing.text + notice,
                )
                break

        new_total = sum(len(c.text) for c in new_content if isinstance(c, TextContent))
        logger.info(
            "Truncated tool response: %s -> %s chars",
            total_chars,
            new_total,
        )

        return CallToolResult(
            content=new_content,  # type: ignore[arg-type]
            isError=result.isError,
        )
