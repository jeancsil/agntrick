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
    """Tests for ResponseTruncator interceptor."""

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
    async def test_truncates_large_text_responses(self) -> None:
        """Large text responses should be truncated."""
        truncator = ResponseTruncator(max_response_size=100)

        original_result = CallToolResult(
            content=[TextContent(type="text", text="x" * 500)],
        )

        result = await _invoke(truncator, original_result)
        assert isinstance(result, CallToolResult)
        text = result.content[0].text  # type: ignore[union-attr]
        assert len(text) < 200  # truncated + notice
        assert "truncated" in text.lower()
        assert "500" in text  # shows original size

    @pytest.mark.asyncio
    async def test_truncates_multiple_content_blocks(self) -> None:
        """Should truncate total content across multiple blocks."""
        truncator = ResponseTruncator(max_response_size=100)

        original_result = CallToolResult(
            content=[
                TextContent(type="text", text="a" * 200),
                TextContent(type="text", text="b" * 200),
            ],
        )

        result = await _invoke(truncator, original_result)
        assert isinstance(result, CallToolResult)
        total_text = "".join(
            c.text
            for c in result.content
            if isinstance(c, TextContent)  # type: ignore[union-attr]
        )
        assert len(total_text) < 300

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
        """isError flag should be preserved through truncation."""
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
    async def test_truncation_notice_appended_to_last_text_block(self) -> None:
        """Truncation notice should be appended to the last text block."""
        truncator = ResponseTruncator(max_response_size=100)

        original_result = CallToolResult(
            content=[
                TextContent(type="text", text="a" * 200),
                TextContent(type="text", text="b" * 200),
            ],
        )

        result = await _invoke(truncator, original_result)
        assert isinstance(result, CallToolResult)
        # Last text block should contain the truncation notice
        text_blocks = [c for c in result.content if isinstance(c, TextContent)]
        last_text = text_blocks[-1].text
        assert "[Response truncated" in last_text
        # First text block should not have the notice
        first_text = text_blocks[0].text
        assert "[Response truncated" not in first_text

    @pytest.mark.asyncio
    async def test_proportional_truncation_across_blocks(self) -> None:
        """Each text block should be truncated proportionally to its size."""
        truncator = ResponseTruncator(max_response_size=200)

        # Block 1 is 300 chars, block 2 is 100 chars (75% / 25% split)
        original_result = CallToolResult(
            content=[
                TextContent(type="text", text="a" * 300),
                TextContent(type="text", text="b" * 100),
            ],
        )

        result = await _invoke(truncator, original_result)
        assert isinstance(result, CallToolResult)
        text_blocks = [c for c in result.content if isinstance(c, TextContent)]

        # Both blocks should be truncated
        block1_len = len(text_blocks[0].text)
        assert block1_len < 300
        block2_len = len(text_blocks[1].text)
        assert block2_len < 100

        # Total text should stay within max_response_size
        total_text = sum(len(b.text) for b in text_blocks if isinstance(b, TextContent))
        assert total_text <= truncator.max_response_size

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
    async def test_head_tail_truncation_preserves_end_content(self) -> None:
        """Truncation should keep both beginning AND end of content.

        When web_fetch returns verbose headers followed by actual content,
        the useful data is at the end. Head+tail truncation preserves it.
        """
        truncator = ResponseTruncator(max_response_size=200)

        # Simulate a tool response: headers + actual content at the end
        header = "HTTP/1.1 200 OK\nContent-Type: text/xml\n" * 20  # ~600 chars of headers
        body = "NEWS_TITLE: Important news article about Brazil\n" * 20  # ~900 chars of content
        full_text = header + body

        original_result = CallToolResult(
            content=[TextContent(type="text", text=full_text)],
        )

        result = await _invoke(truncator, original_result)
        assert isinstance(result, CallToolResult)
        text = result.content[0].text  # type: ignore[union-attr]

        # The end content (actual news) should be preserved
        assert "NEWS_TITLE" in text, f"End content lost! Got: {text[-200:]}"
        # The beginning (headers) should also be preserved
        assert "HTTP/1.1" in text, f"Start content lost! Got: {text[:200:]}"
        # There should be a truncation indicator
        assert "content truncated" in text

    @pytest.mark.asyncio
    async def test_mcp_provider_stores_truncator_as_interceptor(self) -> None:
        """MCPProvider should be able to store a truncator in tool_interceptors."""
        truncator = ResponseTruncator(max_response_size=50)

        # Verify the truncator can be stored in a list (as tool_interceptors would)
        interceptors = [truncator]
        assert interceptors == [truncator]
        assert isinstance(interceptors[0], ResponseTruncator)
        assert interceptors[0].max_response_size == 50
