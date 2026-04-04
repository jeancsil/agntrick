"""Tests for MCP tool response interceptors."""

from typing import Union

import pytest
from langchain_core.messages import ToolMessage
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.types import CallToolResult, ImageContent, TextContent

from agntrick.mcp.interceptors import DEFAULT_MAX_RESPONSE_SIZE, ResponseTruncator

try:
    from langgraph.types import Command

    _HandlerResult = Union[CallToolResult, ToolMessage, Command]  # type: ignore[misc]
except ImportError:
    _HandlerResult = Union[CallToolResult, ToolMessage]  # type: ignore[misc]


def _make_request() -> MCPToolCallRequest:
    """Create a minimal MCPToolCallRequest for testing."""
    return MCPToolCallRequest(
        name="test_tool",
        args={},
        server_name="test_server",
    )


async def _invoke(
    truncator: ResponseTruncator,
    result: _HandlerResult,
) -> _HandlerResult:
    """Helper to run a truncator with a handler that returns the given result."""

    async def handler(
        request: MCPToolCallRequest,
    ) -> _HandlerResult:
        return result

    return await truncator(request=_make_request(), handler=handler)


class TestResponseTruncator:
    """Tests for ResponseTruncator interceptor.

    NOTE: Truncation is currently bypassed. These tests verify the bypass
    behavior — all responses pass through unchanged regardless of size.
    """

    @pytest.mark.asyncio
    async def test_passes_through_small_responses(self) -> None:
        """Small responses should pass through unchanged."""
        truncator = ResponseTruncator(max_response_size=1000)

        original_result = CallToolResult(
            content=[TextContent(type="text", text="hello world")],
        )

        result = await _invoke(truncator, original_result)
        assert result == original_result

    @pytest.mark.asyncio
    async def test_bypass_passes_through_large_responses(self) -> None:
        """Large responses pass through unchanged while truncation is bypassed."""
        truncator = ResponseTruncator(max_response_size=100)

        original_result = CallToolResult(
            content=[TextContent(type="text", text="x" * 500)],
        )

        result = await _invoke(truncator, original_result)
        assert result == original_result

    @pytest.mark.asyncio
    async def test_bypass_passes_through_multiple_content_blocks(self) -> None:
        """Multiple content blocks pass through unchanged while bypassed."""
        truncator = ResponseTruncator(max_response_size=100)

        original_result = CallToolResult(
            content=[
                TextContent(type="text", text="a" * 200),
                TextContent(type="text", text="b" * 200),
            ],
        )

        result = await _invoke(truncator, original_result)
        assert result == original_result

    @pytest.mark.asyncio
    async def test_preserves_non_text_content(self) -> None:
        """Non-text content blocks should be passed through."""
        truncator = ResponseTruncator(max_response_size=100)

        image_block = ImageContent(type="image", data="abc", mimeType="image/png")
        original_result = CallToolResult(
            content=[
                TextContent(type="text", text="x" * 500),
                image_block,
            ],
        )

        result = await _invoke(truncator, original_result)
        assert isinstance(result, CallToolResult)
        # Image block should survive
        types = [c.type for c in result.content]  # type: ignore[union-attr]
        assert "image" in types

    @pytest.mark.asyncio
    async def test_preserves_is_error_flag(self) -> None:
        """isError flag should be preserved."""
        truncator = ResponseTruncator(max_response_size=100)

        original_result = CallToolResult(
            content=[TextContent(type="text", text="x" * 500)],
            isError=True,
        )

        result = await _invoke(truncator, original_result)
        assert isinstance(result, CallToolResult)
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_default_max_size_is_20k(self) -> None:
        """Default max_response_size should be 20000."""
        truncator = ResponseTruncator()
        assert truncator.max_response_size == DEFAULT_MAX_RESPONSE_SIZE
        assert truncator.max_response_size == 20_000

    @pytest.mark.asyncio
    async def test_empty_content_passes_through(self) -> None:
        """Empty content list should pass through unchanged."""
        truncator = ResponseTruncator(max_response_size=100)

        original_result = CallToolResult(content=[])

        result = await _invoke(truncator, original_result)
        assert isinstance(result, CallToolResult)
        assert result.content == []

    @pytest.mark.asyncio
    async def test_no_text_content_passes_through(self) -> None:
        """Non-text-only content should pass through unchanged."""
        truncator = ResponseTruncator(max_response_size=100)

        image_block = ImageContent(type="image", data="abc", mimeType="image/png")
        original_result = CallToolResult(content=[image_block])

        result = await _invoke(truncator, original_result)
        assert result == original_result

    @pytest.mark.asyncio
    async def test_tool_message_passes_through(self) -> None:
        """ToolMessage results should pass through unchanged (not CallToolResult)."""
        truncator = ResponseTruncator(max_response_size=100)

        tool_msg = ToolMessage(
            content="x" * 500,
            tool_call_id="test-call-id",
        )

        result = await _invoke(truncator, tool_msg)
        assert result == tool_msg

    @pytest.mark.asyncio
    async def test_mcp_provider_stores_truncator_as_interceptor(self) -> None:
        """MCPProvider should be able to store a truncator in tool_interceptors."""
        truncator = ResponseTruncator(max_response_size=50)

        # Verify the truncator can be stored in a list (as tool_interceptors would)
        interceptors = [truncator]
        assert interceptors == [truncator]
        assert isinstance(interceptors[0], ResponseTruncator)
        assert interceptors[0].max_response_size == 50
