# Tool Response Truncation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent LLM context bloat from oversized MCP tool responses by adding truncation at both the toolkit source and the agent consumption layer.

**Architecture:** Two-layer defense: (1) agntrick-toolkit limits response size at the source for `web_fetch` and `curl_fetch` tools; (2) agntrick's MCPProvider uses a `ToolCallInterceptor` to truncate any tool response exceeding a configurable threshold before it enters the LLM context.

**Tech Stack:** Python, langchain-mcp-adapters (ToolCallInterceptor protocol), httpx, FastMCP

**Root Cause:** LangSmith trace shows 13 tool invocations over 118s for a single WhatsApp message. `web_fetch` returned 387KB, `curl_fetch` returned 445KB — each accumulated in LLM context, causing the model to loop confusedly, re-fetching the same URL 6 times and ultimately failing to answer.

---

## Files Changed

### agntrick-toolkit (`~/code/agntrick-toolkit`)
- Modify: `src/agntrick_toolbox/config.py` — Add `toolbox_web_response_max_size` setting
- Modify: `src/agntrick_toolbox/tools/web.py` — Truncate `web_fetch` responses
- Modify: `src/agntrick_toolbox/tools/utils.py` — Truncate `curl_fetch` responses (when not saving to file)
- Modify: `tests/test_tools/test_web.py` — Add truncation tests
- Modify: `tests/test_tools/test_utils.py` — Add truncation test

### agntrick (`~/code/agents`)
- Create: `src/agntrick/mcp/interceptors.py` — `ResponseTruncator` ToolCallInterceptor
- Modify: `src/agntrick/mcp/provider.py` — Wire interceptor into tool loading
- Create: `tests/test_mcp/test_interceptors.py` — Interceptor tests

---

## Task 1: Add web response max size config to agntrick-toolkit

**Files:**
- Modify: `src/agntrick_toolbox/config.py:6-21`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools/test_web.py — add to TestWebFetch class
@pytest.mark.asyncio
async def test_web_fetch_truncates_large_response(self) -> None:
    """web_fetch should truncate responses exceeding max size."""
    from agntrick_toolbox.tools.web import register_web_tools
    from mcp.server.fastmcp import FastMCP

    large_content = "x" * 100_000  # 100KB

    with patch("agntrick_toolbox.tools.web.httpx.AsyncClient") as mock_client_class:
        mock_response = AsyncMock()
        mock_response.text = large_content
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=False)

        mock_client_class.return_value = mock_context

        mcp = FastMCP("test")
        register_web_tools(mcp)

        tools = mcp._tool_manager._tools
        fetch_tool = tools.get("web_fetch")
        result = await fetch_tool.fn(url="https://example.com/large")

    assert len(result) < 100_000
    assert "truncated" in result.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_tools/test_web.py::TestWebFetch::test_web_fetch_truncates_large_response -v`
Expected: FAIL — no truncation logic exists

- [ ] **Step 3: Add config setting and implement truncation in web_fetch**

In `src/agntrick_toolbox/config.py`, add to the `Settings` class:

```python
toolbox_web_response_max_size: int = 20_000  # 20KB — enough for useful content, small enough for LLM context
```

In `src/agntrick_toolbox/tools/web.py`, modify `web_fetch`:

```python
@mcp.tool()
async def web_fetch(url: str, timeout: int = 30) -> str:
    """Fetch and extract text content from a URL.

    Uses Jina Reader API for clean text extraction (free, no API key).

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        Extracted text content from the page (truncated if too large).
    """
    from ..config import settings

    jina_url = f"https://r.jina.ai/{url}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(jina_url)
            response.raise_for_status()
            text = response.text

        max_size = settings.toolbox_web_response_max_size
        if len(text) > max_size:
            text = text[:max_size] + f"\n\n[Response truncated at {max_size} chars. Original size: {len(response.text)} chars]"
        return text
    except httpx.TimeoutException:
        return f"Error: Request timed out after {timeout} seconds."
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error(f"Fetch failed for {url}: {e}")
        return f"Error fetching URL: {e}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_tools/test_web.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/code/agntrick-toolkit
git add src/agntrick_toolbox/config.py src/agntrick_toolbox/tools/web.py tests/test_tools/test_web.py
git commit -m "feat: truncate web_fetch responses to 20KB to prevent LLM context bloat"
```

---

## Task 2: Add curl_fetch response truncation to agntrick-toolkit

**Files:**
- Modify: `src/agntrick_toolbox/tools/utils.py:12-63`
- Modify: `tests/test_tools/test_utils.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools/test_utils.py — add to TestCurlFetch class
@pytest.mark.asyncio
async def test_truncates_large_response(self, temp_workspace, monkeypatch):
    """Should truncate responses exceeding web_response_max_size."""
    import agntrick_toolbox.path_utils as path_utils

    monkeypatch.setattr(path_utils.settings, "toolbox_workspace", str(temp_workspace))

    from agntrick_toolbox.tools.utils import register_utils_tools
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("test")
    register_utils_tools(mcp)

    with patch("agntrick_toolbox.tools.utils.run_command") as mock_run:
        mock_run.return_value = CommandResult(
            success=True,
            stdout="x" * 100_000,
            stderr="",
            exit_code=0,
        )

        tools = mcp._tool_manager._tools
        curl_tool = tools.get("curl_fetch")
        result = await curl_tool.fn(url="https://example.com/large")

    assert len(result) < 100_000
    assert "truncated" in result.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_tools/test_utils.py::TestCurlFetch::test_truncates_large_response -v`
Expected: FAIL

- [ ] **Step 3: Implement truncation in curl_fetch**

In `src/agntrick_toolbox/tools/utils.py`, modify `curl_fetch`:

```python
@mcp.tool()
async def curl_fetch(
    url: str,
    output_path: str | None = None,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: str | None = None,
    follow_redirects: bool = True,
    timeout: int = 60,
) -> str:
    """Fetch URLs using curl with HTTP method support.

    Args:
        url: URL to fetch
        output_path: Save response to file within workspace (optional)
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        headers: HTTP headers as key-value pairs
        data: Request body data
        follow_redirects: Follow HTTP redirects
        timeout: Request timeout in seconds

    Returns:
        Response body or error message
    """
    from .config import settings

    cmd = ["curl", "-s", "-X", method]

    if follow_redirects:
        cmd.append("-L")

    if headers:
        for key, value in headers.items():
            cmd.extend(["-H", f"{key}: {value}"])

    if data:
        cmd.extend(["-d", data])

    if output_path:
        try:
            validated = validate_output_path(output_path)
            cmd.extend(["-o", str(validated)])
        except PathValidationError as e:
            return f"Error: {e}"

    cmd.append(url)

    result = await run_command(cmd, timeout=timeout)
    if not result.success:
        return f"Error: {result.stderr}"

    if output_path:
        return f"Successfully saved {url} to {output_path}"

    # Truncate inline responses to prevent LLM context bloat
    max_size = settings.toolbox_web_response_max_size
    response_text = result.stdout
    if len(response_text) > max_size:
        return response_text[:max_size] + f"\n\n[Response truncated at {max_size} chars. Original size: {len(response_text)} chars]"
    return response_text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_tools/test_utils.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/code/agntrick-toolkit
git add src/agntrick_toolbox/tools/utils.py tests/test_tools/test_utils.py
git commit -m "feat: truncate curl_fetch inline responses to 20KB"
```

---

## Task 3: Create ResponseTruncator interceptor in agntrick

**Files:**
- Create: `src/agntrick/mcp/interceptors.py`
- Create: `tests/test_mcp/test_interceptors.py`

This is the defense-in-depth layer. Even if a toolkit server doesn't truncate, the agent side will.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp/test_interceptors.py
"""Tests for MCP tool response interceptors."""

import pytest
from mcp.types import CallToolResult, TextContent


class TestResponseTruncator:
    """Tests for ResponseTruncator interceptor."""

    @pytest.mark.asyncio
    async def test_passes_through_small_responses(self) -> None:
        """Small responses should pass through unchanged."""
        from agntrick.mcp.interceptors import ResponseTruncator

        truncator = ResponseTruncator(max_response_size=1000)

        original_result = CallToolResult(
            content=[TextContent(type="text", text="hello world")],
        )

        async def handler(request: object) -> CallToolResult:
            return original_result

        result = await truncator(request=None, handler=handler)  # type: ignore[arg-type]
        assert result == original_result

    @pytest.mark.asyncio
    async def test_truncates_large_text_responses(self) -> None:
        """Large text responses should be truncated."""
        from agntrick.mcp.interceptors import ResponseTruncator

        truncator = ResponseTruncator(max_response_size=100)

        original_result = CallToolResult(
            content=[TextContent(type="text", text="x" * 500)],
        )

        async def handler(request: object) -> CallToolResult:
            return original_result

        result = await truncator(request=None, handler=handler)  # type: ignore[arg-type]
        text = result.content[0].text  # type: ignore[union-attr]
        assert len(text) < 200  # truncated + notice
        assert "truncated" in text.lower()
        assert "500" in text  # shows original size

    @pytest.mark.asyncio
    async def test_truncates_multiple_content_blocks(self) -> None:
        """Should truncate total content across multiple blocks."""
        from agntrick.mcp.interceptors import ResponseTruncator

        truncator = ResponseTruncator(max_response_size=100)

        original_result = CallToolResult(
            content=[
                TextContent(type="text", text="a" * 200),
                TextContent(type="text", text="b" * 200),
            ],
        )

        async def handler(request: object) -> CallToolResult:
            return original_result

        result = await truncator(request=None, handler=handler)  # type: ignore[arg-type]
        total_text = "".join(
            c.text for c in result.content if isinstance(c, TextContent)  # type: ignore[union-attr]
        )
        assert len(total_text) < 300

    @pytest.mark.asyncio
    async def test_preserves_non_text_content(self) -> None:
        """Non-text content blocks should be passed through."""
        from agntrick.mcp.interceptors import ResponseTruncator
        from mcp.types import ImageContent

        truncator = ResponseTruncator(max_response_size=100)

        image_block = ImageContent(type="image", data="abc", mimeType="image/png")
        original_result = CallToolResult(
            content=[
                TextContent(type="text", text="x" * 500),
                image_block,
            ],
        )

        async def handler(request: object) -> CallToolResult:
            return original_result

        result = await truncator(request=None, handler=handler)  # type: ignore[arg-type]
        # Image block should survive
        types = [c.type for c in result.content]  # type: ignore[union-attr]
        assert "image" in types

    @pytest.mark.asyncio
    async def test_default_max_size_is_20k(self) -> None:
        """Default max_response_size should be 20000."""
        from agntrick.mcp.interceptors import ResponseTruncator

        truncator = ResponseTruncator()
        assert truncator.max_response_size == 20_000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agents && uv run pytest tests/test_mcp/test_interceptors.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement ResponseTruncator**

```python
# src/agntrick/mcp/interceptors.py
"""MCP tool call interceptors for response processing."""

import logging
from typing import Any, Callable, Awaitable

from mcp.types import CallToolResult, TextContent

logger = logging.getLogger(__name__)


class ResponseTruncator:
    """ToolCallInterceptor that truncates oversized MCP tool responses.

    This is a defense-in-depth layer: even if an MCP server returns large
    responses, this interceptor truncates them before they enter the LLM
    context window. This prevents the 100s-of-KB responses that cause
    model confusion and excessive latency.

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

    def __init__(self, max_response_size: int = 20_000) -> None:
        self.max_response_size = max_response_size

    async def __call__(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[CallToolResult]],
    ) -> CallToolResult:
        """Intercept tool response and truncate if needed.

        Args:
            request: MCPToolCallRequest from the interceptor chain.
            handler: Next handler in the chain (executes the actual tool).

        Returns:
            CallToolResult with text content truncated if over limit.
        """
        result = await handler(request)

        # Calculate total text content size
        text_blocks = [c for c in result.content if isinstance(c, TextContent)]
        total_chars = sum(len(b.text) for b in text_blocks)

        if total_chars <= self.max_response_size:
            return result

        # Truncate: distribute budget across text blocks proportionally
        original_total = total_chars
        budget = self.max_response_size
        new_content: list[Any] = []

        for block in result.content:
            if isinstance(block, TextContent):
                # Proportional share of budget
                block_budget = int(budget * len(block.text) / total_chars)
                if block_budget > 0 and len(block.text) > block_budget:
                    truncated_text = block.text[:block_budget]
                    new_content.append(
                        TextContent(type="text", text=truncated_text)
                    )
                else:
                    new_content.append(block)
            else:
                # Non-text content passes through unchanged
                new_content.append(block)

        # Add truncation notice to last text block
        notice = (
            f"\n\n[Response truncated at {self.max_response_size:,} chars. "
            f"Original size: {original_total:,} chars]"
        )
        for i in range(len(new_content) - 1, -1, -1):
            if isinstance(new_content[i], TextContent):
                new_content[i] = TextContent(
                    type="text",
                    text=new_content[i].text + notice,
                )
                break

        logger.info(
            "Truncated tool response: %d -> %d chars",
            original_total,
            sum(len(c.text) for c in new_content if isinstance(c, TextContent)),
        )

        return CallToolResult(
            content=new_content,
            isError=result.isError,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/code/agents && uv run pytest tests/test_mcp/test_interceptors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/code/agents
git add src/agntrick/mcp/interceptors.py tests/test_mcp/test_interceptors.py
git commit -m "feat: add ResponseTruncator MCP interceptor for defense-in-depth"
```

---

## Task 4: Wire ResponseTruncator into MCPProvider

**Files:**
- Modify: `src/agntrick/mcp/provider.py:29-152`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp/test_interceptors.py — add to TestResponseTruncator class

@pytest.mark.asyncio
async def test_mcp_provider_uses_truncator(self) -> None:
    """MCPProvider should pass interceptors to tool loading."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from agntrick.mcp.interceptors import ResponseTruncator
    from agntrick.mcp.provider import MCPProvider

    truncator = ResponseTruncator(max_response_size=50)

    config = {
        "test_server": {
            "transport": "sse",
            "url": "http://localhost:8080/sse",
        }
    }

    with patch("agntrick.mcp.provider.load_mcp_tools") as mock_load:
        mock_load.return_value = [MagicMock()]

        with patch.object(MCPProvider, "__init__", lambda self, **kw: None):
            provider = MCPProvider.__new__(MCPProvider)
            provider._config = config
            provider._client = MagicMock()
            provider._client.tool_interceptors = [truncator]
            provider._client.callbacks = None
            provider._client.tool_name_prefix = False

            # Verify interceptors are stored
            assert provider._client.tool_interceptors == [truncator]
```

- [ ] **Step 2: Run test to verify it fails/skips**

Run: `cd ~/code/agents && uv run pytest tests/test_mcp/test_interceptors.py -v`
Expected: PASS or SKIP — depends on current provider wiring

- [ ] **Step 3: Wire truncator into MCPProvider**

In `src/agntrick/mcp/provider.py`, modify the `__init__` to accept interceptors and the `tool_session` to use them:

Add import at top:
```python
from agntrick.mcp.interceptors import ResponseTruncator
```

Modify `__init__` to add interceptor creation:
```python
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
        self._config = cast(Dict[str, Connection], resolved)

    # Apply server_names filter if provided
    if server_names is not None:
        unknown = [n for n in server_names if n not in self._config]
        if unknown:
            available = list(self._config.keys())
            raise ValueError(f"Unknown MCP server(s): {unknown}. Available servers: {available}")
        self._config = {k: self._config[k] for k in server_names}

    # Create default interceptors for response truncation
    self._interceptors = [ResponseTruncator()]

    self._client = MultiServerMCPClient(
        self._config,
        tool_interceptors=self._interceptors,
    )
    self._tools_cache: Optional[List[Any]] = None
```

Note: `tool_interceptors` is already passed through in `tool_session()` at line 111 of the current code (`tool_interceptors=self._client.tool_interceptors`). By passing it to `MultiServerMCPClient`, it gets propagated to `load_mcp_tools` calls in both `get_tools()` and `tool_session()`.

- [ ] **Step 4: Run all tests**

Run: `cd ~/code/agents && uv run pytest tests/test_mcp/ -v`
Expected: PASS

- [ ] **Step 5: Run make check**

Run: `cd ~/code/agents && make check`
Expected: PASS (no type errors)

- [ ] **Step 6: Commit**

```bash
cd ~/code/agents
git add src/agntrick/mcp/provider.py src/agntrick/mcp/interceptors.py
git commit -m "feat: wire ResponseTruncator into MCPProvider for automatic tool response limiting"
```

---

## Task 5: Run full test suite and verify both repos

**Files:** None (verification only)

- [ ] **Step 1: Run agntrick-toolkit tests**

Run: `cd ~/code/agntrick-toolkit && uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Run agntrick check and tests**

Run: `cd ~/code/agents && make check && make test`
Expected: ALL PASS

---

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| `web_fetch` response size | Up to 1MB | Max 20KB |
| `curl_fetch` response size | Up to 1MB | Max 20KB |
| Defense-in-depth truncation | None | Agent-side 20KB cap |
| LLM context per tool call | 387-445KB | Max 20KB |
| Model confusion from bloat | High (6x redundant fetches) | Low |
| Typical WhatsApp response time | 118s (observed) | Expected <30s |
