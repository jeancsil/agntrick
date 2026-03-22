# Centralized MCP Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate all MCP servers into a single `agntrick-toolkit` service that serves multiple WhatsApp instances via SSE.

**Architecture:** Add web search/fetch and Hacker News tools directly to `agntrick-toolkit` using the same libraries that `web-forager` uses (`ddgs`, `httpx`). Remove per-instance MCP instantiation from `agntrick` and `agntrick-whatsapp`.

**Tech Stack:** Python 3.12, FastMCP (from `mcp` package), ddgs (DuckDuckGo search), httpx, beautifulsoup4

**Note:** This project uses `from mcp.server.fastmcp import FastMCP` (from the `mcp` package), NOT the standalone `fastmcp` package.

---

## File Structure

```
agntrick-toolkit/
├── src/agntrick_toolbox/
│   ├── tools/
│   │   ├── web.py          # CREATE - web_search, web_fetch
│   │   ├── hackernews.py   # CREATE - hacker_news_top, hacker_news_item
│   │   └── ...
│   └── server.py           # MODIFY - register new tools
├── tests/
│   ├── test_tools/
│   │   ├── test_web.py     # CREATE
│   │   └── test_hackernews.py # CREATE
│   └── ...
└── pyproject.toml          # MODIFY - add dependencies

agntrick/
├── src/agntrick/
│   └── mcp/
│       └── config.py       # MODIFY - remove web-forager, hacker-news
└── ...

agntrick-whatsapp/
├── src/agntrick_whatsapp/
│   └── router.py           # MODIFY - update DEFAULT_MCP_SERVERS
└── ...
```

---

## Task 1: Add Dependencies to agntrick-toolkit

**Files:**
- Modify: `~/code/agntrick-toolkit/pyproject.toml`

- [ ] **Step 1: Add new dependencies to pyproject.toml**

```toml
# In the dependencies array, add these three:
dependencies = [
    "fastmcp>=0.1.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "ddgs>=9.5.2",            # DuckDuckGo search
    "httpx>=0.28.0",          # Async HTTP client
    "beautifulsoup4>=4.12.0", # HTML parsing (compatible with Python 3.12)
]
```

- [ ] **Step 2: Sync dependencies**

Run: `cd ~/code/agntrick-toolkit && uv sync`
Expected: Dependencies installed successfully

- [ ] **Step 3: Commit**

```bash
cd ~/code/agntrick-toolkit
git add pyproject.toml uv.lock
git commit -m "chore: add ddgs, httpx, beautifulsoup4 for web tools"
```

---

## Task 2: Create Web Tools Module

**Files:**
- Create: `~/code/agntrick-toolkit/src/agntrick_toolbox/tools/web.py`
- Create: `~/code/agntrick-toolkit/tests/test_tools/test_web.py`

- [ ] **Step 0: Verify test_tools directory exists**

Run: `ls ~/code/agntrick-toolkit/tests/test_tools/__init__.py 2>/dev/null || echo "not found"`
Expected: File exists (if not, the directory was created during initial setup)

- [ ] **Step 1: Write the failing test for web_search**

Create `tests/test_tools/test_web.py`:

```python
"""Tests for web tools."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestWebSearch:
    """Tests for web_search tool."""

    @pytest.mark.asyncio
    async def test_web_search_returns_formatted_results(self) -> None:
        """web_search should return formatted search results."""
        from agntrick_toolbox.tools.web import web_search

        mock_results = [
            {"title": "Python Guide", "href": "https://example.com/python", "body": "Learn Python"},
            {"title": "Python Tutorial", "href": "https://example.com/tutorial", "body": "Best tutorial"},
        ]

        with patch("agntrick_toolbox.tools.web.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.text.return_value = iter(mock_results)
            mock_ddgs.return_value = mock_instance

            result = await web_search("python programming", max_results=2)

        assert "Python Guide" in result
        assert "https://example.com/python" in result
        assert "Learn Python" in result

    @pytest.mark.asyncio
    async def test_web_search_no_results_returns_message(self) -> None:
        """web_search should return a message when no results found."""
        from agntrick_toolbox.tools.web import web_search

        with patch("agntrick_toolbox.tools.web.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.text.return_value = iter([])
            mock_ddgs.return_value = mock_instance

            result = await web_search("zzzzzzzzzznonexistent")

        assert result == "No results found."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_tools/test_web.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Create the web.py module with web_search**

Create `src/agntrick_toolbox/tools/web.py`:

```python
"""Web search and fetch tools using proven libraries."""

import logging
from typing import Any

from bs4 import BeautifulSoup
from ddgs import DDGS
from mcp.server.fastmcp import FastMCP
import httpx

logger = logging.getLogger(__name__)


def register_web_tools(mcp: FastMCP) -> None:
    """Register web search and fetch tools."""

    @mcp.tool()
    async def web_search(query: str, max_results: int = 5) -> str:
        """Search the web using DuckDuckGo.

        Args:
            query: The search query.
            max_results: Maximum number of results (default 5, max 10).

        Returns:
            Formatted search results with titles, URLs, and snippets.
        """
        max_results = min(max_results, 10)  # Cap at 10
        results: list[dict[str, Any]] = []

        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(r)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return f"Search error: {e}"

        if not results:
            return "No results found."

        formatted = []
        for r in results:
            formatted.append(f"**{r.get('title', 'No title')}**\n{r.get('href', '')}\n{r.get('body', '')}")

        return "\n\n---\n\n".join(formatted)

    @mcp.tool()
    async def web_fetch(url: str, timeout: int = 30) -> str:
        """Fetch and extract text content from a URL.

        Uses Jina Reader API for clean text extraction (free, no API key).

        Args:
            url: The URL to fetch.
            timeout: Request timeout in seconds.

        Returns:
            Extracted text content from the page.
        """
        jina_url = f"https://r.jina.ai/{url}"

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(jina_url)
                response.raise_for_status()
                return response.text
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
Expected: PASS (2 tests)

- [ ] **Step 5: Write the failing test for web_fetch**

Add to `tests/test_tools/test_web.py`:

```python
class TestWebFetch:
    """Tests for web_fetch tool."""

    @pytest.mark.asyncio
    async def test_web_fetch_returns_content(self) -> None:
        """web_fetch should return fetched content."""
        from agntrick_toolbox.tools.web import web_fetch

        with patch("agntrick_toolbox.tools.web.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.text = "# Extracted Content\n\nThis is the page content."
            mock_response.raise_for_status = MagicMock()

            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_context.__aexit__ = AsyncMock(return_value=False)

            mock_client.return_value = mock_context

            result = await web_fetch("https://example.com/article")

        assert "Extracted Content" in result
        assert "r.jina.ai" not in result  # Should not expose internal URL

    @pytest.mark.asyncio
    async def test_web_fetch_handles_timeout(self) -> None:
        """web_fetch should handle timeout gracefully."""
        from agntrick_toolbox.tools.web import web_fetch
        import httpx

        with patch("agntrick_toolbox.tools.web.httpx.AsyncClient") as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_context.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_context

            result = await web_fetch("https://example.com/slow")

        assert "Error" in result
        assert "timed out" in result.lower()
```

- [ ] **Step 6: Run test to verify web_fetch tests pass**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_tools/test_web.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit web tools**

```bash
cd ~/code/agntrick-toolkit
git add src/agntrick_toolbox/tools/web.py tests/test_tools/test_web.py
git commit -m "feat: add web_search and web_fetch tools"
```

---

## Task 3: Create Hacker News Tools Module

**Files:**
- Create: `~/code/agntrick-toolkit/src/agntrick_toolbox/tools/hackernews.py`
- Create: `~/code/agntrick-toolkit/tests/test_tools/test_hackernews.py`

- [ ] **Step 1: Write the failing test for hacker_news_top**

Create `tests/test_tools/test_hackernews.py`:

```python
"""Tests for Hacker News tools."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestHackerNewsTop:
    """Tests for hacker_news_top tool."""

    @pytest.mark.asyncio
    async def test_hacker_news_top_returns_stories(self) -> None:
        """hacker_news_top should return formatted top stories."""
        from agntrick_toolbox.tools.hackernews import hacker_news_top

        mock_story_ids = [1, 2, 3]
        mock_stories = [
            {"id": 1, "title": "First Story", "url": "https://example.com/1", "score": 100, "descendants": 50},
            {"id": 2, "title": "Second Story", "url": "https://example.com/2", "score": 80, "descendants": 30},
            {"id": 3, "title": "Third Story", "url": "https://example.com/3", "score": 60, "descendants": 20},
        ]

        with patch("agntrick_toolbox.tools.hackernews.httpx.AsyncClient") as mock_client:
            mock_context = AsyncMock()

            # Mock responses for topstories and each item
            responses = []
            ids_response = AsyncMock()
            ids_response.json = MagicMock(return_value=mock_story_ids)
            responses.append(ids_response)

            for story in mock_stories:
                story_response = AsyncMock()
                story_response.json = MagicMock(return_value=story)
                responses.append(story_response)

            mock_context.get = AsyncMock(side_effect=responses)
            mock_context.__aenter__ = AsyncMock(return_value=mock_context)
            mock_context.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_context

            result = await hacker_news_top(max_stories=3)

        assert "First Story" in result
        assert "100" in result  # score
        assert "https://example.com/1" in result

    @pytest.mark.asyncio
    async def test_hacker_news_top_handles_missing_url(self) -> None:
        """hacker_news_top should handle stories without URL (Ask HN)."""
        from agntrick_toolbox.tools.hackernews import hacker_news_top

        mock_story_ids = [1]
        mock_stories = [
            {"id": 1, "title": "Ask HN: Something", "score": 50, "descendants": 10},
        ]

        with patch("agntrick_toolbox.tools.hackernews.httpx.AsyncClient") as mock_client:
            mock_context = AsyncMock()

            responses = []
            ids_response = AsyncMock()
            ids_response.json = MagicMock(return_value=mock_story_ids)
            responses.append(ids_response)

            for story in mock_stories:
                story_response = AsyncMock()
                story_response.json = MagicMock(return_value=story)
                responses.append(story_response)

            mock_context.get = AsyncMock(side_effect=responses)
            mock_context.__aenter__ = AsyncMock(return_value=mock_context)
            mock_context.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_context

            result = await hacker_news_top(max_stories=1)

        assert "Ask HN" in result
        assert "news.ycombinator.com" in result  # Should link to HN item page
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_tools/test_hackernews.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Create the hackernews.py module**

Create `src/agntrick_toolbox/tools/hackernews.py`:

```python
"""Hacker News tools using HTTP API."""

import logging
from typing import Any

from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP
import httpx

logger = logging.getLogger(__name__)

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"


def register_hackernews_tools(mcp: FastMCP) -> None:
    """Register Hacker News tools."""

    @mcp.tool()
    async def hacker_news_top(max_stories: int = 10) -> str:
        """Get top stories from Hacker News.

        Args:
            max_stories: Maximum number of stories to return (default 10, max 30).

        Returns:
            Formatted list of top stories with titles, URLs, and points.
        """
        max_stories = min(max_stories, 30)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Get top story IDs
                response = await client.get(f"{HN_API_BASE}/topstories.json")
                story_ids = response.json()[:max_stories]

                # Fetch each story
                stories: list[dict[str, Any]] = []
                for story_id in story_ids:
                    story_resp = await client.get(f"{HN_API_BASE}/item/{story_id}.json")
                    story = story_resp.json()
                    if story:
                        stories.append(story)

                if not stories:
                    return "No stories found."

                formatted = []
                for story in stories:
                    title = story.get("title", "No title")
                    url = story.get("url") or f"https://news.ycombinator.com/item?id={story.get('id')}"
                    score = story.get("score", 0)
                    comments = story.get("descendants", 0)

                    formatted.append(
                        f"**{title}**\n"
                        f"URL: {url}\n"
                        f"Points: {score} | Comments: {comments}"
                    )

                return "\n\n---\n\n".join(formatted)

        except Exception as e:
            logger.error(f"Failed to fetch HN stories: {e}")
            return f"Error fetching stories: {e}"

    @mcp.tool()
    async def hacker_news_item(item_id: int) -> str:
        """Get details of a specific Hacker News item.

        Args:
            item_id: The Hacker News item ID.

        Returns:
            Item details including title, URL, text, author, and points.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{HN_API_BASE}/item/{item_id}.json")
                item = response.json()

                if not item:
                    return f"Item {item_id} not found."

                result = f"**{item.get('title', 'No title')}**\n"
                result += f"By: {item.get('by', 'unknown')} | Points: {item.get('score', 0)}\n"

                if item.get("url"):
                    result += f"URL: {item['url']}\n"

                if item.get("text"):
                    # Strip HTML tags from text
                    soup = BeautifulSoup(item["text"], "html.parser")
                    clean_text = soup.get_text()
                    result += f"\n{clean_text}"

                return result

        except Exception as e:
            logger.error(f"Failed to fetch HN item {item_id}: {e}")
            return f"Error fetching item: {e}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_tools/test_hackernews.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Write test for hacker_news_item**

Add to `tests/test_tools/test_hackernews.py`:

```python
class TestHackerNewsItem:
    """Tests for hacker_news_item tool."""

    @pytest.mark.asyncio
    async def test_hacker_news_item_returns_details(self) -> None:
        """hacker_news_item should return item details."""
        from agntrick_toolbox.tools.hackernews import hacker_news_item

        mock_item = {
            "id": 12345,
            "title": "Test Story",
            "by": "testuser",
            "score": 42,
            "url": "https://example.com/test",
            "text": "<p>This is <b>bold</b> text.</p>",
        }

        with patch("agntrick_toolbox.tools.hackernews.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = MagicMock(return_value=mock_item)

            mock_context = AsyncMock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_context.__aenter__ = AsyncMock(return_value=mock_context)
            mock_context.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_context

            result = await hacker_news_item(12345)

        assert "Test Story" in result
        assert "testuser" in result
        assert "42" in result
        assert "https://example.com/test" in result
        # HTML should be stripped
        assert "<p>" not in result
        assert "<b>" not in result

    @pytest.mark.asyncio
    async def test_hacker_news_item_handles_not_found(self) -> None:
        """hacker_news_item should handle missing items."""
        from agntrick_toolbox.tools.hackernews import hacker_news_item

        with patch("agntrick_toolbox.tools.hackernews.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = MagicMock(return_value=None)

            mock_context = AsyncMock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_context.__aenter__ = AsyncMock(return_value=mock_context)
            mock_context.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_context

            result = await hacker_news_item(99999999)

        assert "not found" in result.lower()
```

- [ ] **Step 6: Run all hackernews tests**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_tools/test_hackernews.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit hackernews tools**

```bash
cd ~/code/agntrick-toolkit
git add src/agntrick_toolbox/tools/hackernews.py tests/test_tools/test_hackernews.py
git commit -m "feat: add hacker_news_top and hacker_news_item tools"
```

---

## Task 4: Register New Tools in Server

**Files:**
- Modify: `~/code/agntrick-toolkit/src/agntrick_toolbox/server.py`

- [ ] **Step 1: Add imports and registration calls**

In `server.py`, add imports after the existing tool imports (after `from .tools.utils import register_utils_tools`):

```python
from .tools.hackernews import register_hackernews_tools
from .tools.web import register_web_tools
```

Add registration calls after `register_shell_tool(mcp)`:

```python
register_web_tools(mcp)  # web_search, web_fetch
register_hackernews_tools(mcp)  # hacker_news_top, hacker_news_item
```

Update `list_tools()` function to include new tools (add after the "Shell fallback" entry):

```python
# Web tools
{"name": "web_search", "category": "web", "description": "Search the web using DuckDuckGo"},
{"name": "web_fetch", "category": "web", "description": "Fetch and extract text from URLs"},
# Hacker News tools
{"name": "hacker_news_top", "category": "hackernews", "description": "Get top stories from Hacker News"},
{"name": "hacker_news_item", "category": "hackernews", "description": "Get details of a specific HN item"},
```

- [ ] **Step 2: Run linting and tests**

Run: `cd ~/code/agntrick-toolkit && uv run ruff check src/ && uv run mypy src/`
Expected: No errors

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
cd ~/code/agntrick-toolkit
git add src/agntrick_toolbox/server.py
git commit -m "feat: register web and hackernews tools in server"
```

---

## Task 5: Update agntrick MCP Configuration

**Files:**
- Modify: `~/code/agents/src/agntrick/mcp/config.py`

- [ ] **Step 1: Remove web-forager and hacker-news from DEFAULT_MCP_SERVERS**

Edit `config.py` to remove the stdio-based servers:

```python
DEFAULT_MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    "kiwi-com-flight-search": {
        "url": "https://mcp.kiwi.com",
        "transport": "sse",
    },
    "fetch": {
        "url": "https://remote.mcpservers.org/fetch/mcp",
        "transport": "http",
    },
    "toolbox": {
        "url": "http://localhost:8080/sse",
        "transport": "sse",
    },
    # Removed: web-forager (now in toolbox as web_search, web_fetch)
    # Removed: hacker-news (now in toolbox as hacker_news_*)
}
```

- [ ] **Step 2: Run agntrick tests**

Run: `cd ~/code/agents && make check && make test`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
cd ~/code/agents
git add src/agntrick/mcp/config.py
git commit -m "refactor: remove web-forager and hacker-news from MCP config

These tools are now available in agntrick-toolkit:
- web-forager -> toolbox: web_search, web_fetch
- hacker-news -> toolbox: hacker_news_top, hacker_news_item"
```

---

## Task 6: Update agntrick-whatsapp Default MCP Servers

**Files:**
- Modify: `~/code/agntrick-whatsapp/src/agntrick_whatsapp/router.py`

- [ ] **Step 1: Update DEFAULT_MCP_SERVERS**

Find line ~33 and change:

```python
# OLD:
DEFAULT_MCP_SERVERS = ["web-forager", "fetch", "toolbox"]

# NEW:
DEFAULT_MCP_SERVERS = ["toolbox"]  # All tools now in toolbox
```

- [ ] **Step 2: Update DEFAULT_SYSTEM_PROMPT (optional but recommended)**

Update the system prompt to reflect the new tool names. Find the "Your Capabilities" section and update:

```python
DEFAULT_SYSTEM_PROMPT = f"""You are {DEFAULT_AGENT_NAME}, a helpful AI assistant on WhatsApp.

## Your Capabilities
- Conversational chat and Q&A
- **Web Search**: Use `web_search` to search DuckDuckGo
- **Web Fetch**: Use `web_fetch` to read web page content
- **Hacker News**: Use `hacker_news_top` and `hacker_news_item` for tech news
- **Document Processing**: PDF text extraction, document conversion (pandoc)
- **Media Processing**: Audio/video conversion (ffmpeg), image manipulation (ImageMagick)
- **Data Processing**: JSON/YAML query (jq, yq), CSV operations
- **File Operations**: Search files (ripgrep, fd), git operations
- **Invoke specialized agents** for specific tasks (use the invoke_agent tool)
...
"""
```

- [ ] **Step 3: Run tests**

Run: `cd ~/code/agntrick-whatsapp && uv run ruff check src/ && uv run mypy src/`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
cd ~/code/agntrick-whatsapp
git add src/agntrick_whatsapp/router.py
git commit -m "refactor: update default MCP servers to use only toolbox

All tools are now consolidated in agntrick-toolkit:
- web-forager -> toolbox: web_search, web_fetch
- hacker-news -> toolbox: hacker_news_*"
```

---

## Task 7: Integration Testing

**Files:**
- None (manual testing)

- [ ] **Step 1: Start the toolkit server**

Run: `cd ~/code/agntrick-toolkit && uv run toolbox-server`
Expected: Server starts on port 8080, logs show "Starting agntrick-toolbox on port 8080"

- [ ] **Step 2: Verify health endpoint**

Run: `curl http://localhost:8080/health` (or check server logs for startup confirmation)
Expected: Returns "OK" or server logs show successful startup

- [ ] **Step 3: Test tools via agntrick CLI**

In another terminal:
```bash
cd ~/code/agents
uv run agntrick developer -i "Search for Python async best practices"
```
Expected: Uses `web_search` from toolbox, returns results

- [ ] **Step 3: Test with WhatsApp (if available)**

Start one WhatsApp instance and verify it connects to toolbox.

---

## Task 8: Final Commit and Cleanup

- [ ] **Step 1: Run all test suites**

```bash
cd ~/code/agntrick-toolkit && uv run pytest tests/ -v
cd ~/code/agents && make check && make test
cd ~/code/agntrick-whatsapp && uv run pytest tests/ -v
```

Expected: All pass

- [ ] **Step 2: Create summary commit**

```bash
cd ~/code/agents
git add docs/superpowers/plans/2026-03-22-centralized-mcp-architecture.md
git commit -m "docs: add centralized MCP architecture implementation plan"
```

---

## Verification Checklist

After completing all tasks:

- [ ] `agntrick-toolkit` has 4 new tools: `web_search`, `web_fetch`, `hacker_news_top`, `hacker_news_item`
- [ ] `agntrick/mcp/config.py` no longer references `web-forager` or `hacker-news`
- [ ] `agntrick-whatsapp` defaults to `["toolbox"]` only
- [ ] All tests pass in all 3 repositories
- [ ] Memory footprint of toolkit is ~150-200MB (verify with `docker stats`)
- [ ] Two WhatsApp instances can connect to the same toolbox server

---

## Rollback Instructions

If issues arise:

1. **Revert agntrick-toolkit (if new tools cause problems):**
   ```bash
   cd ~/code/agntrick-toolkit
   # Revert all toolkit commits from this plan
   git log --oneline -5  # Find the commits to revert
   git revert <commit-hash>  # Revert server.py registration
   git revert <commit-hash>  # Revert hackernews.py
   git revert <commit-hash>  # Revert web.py
   git revert <commit-hash>  # Revert pyproject.toml
   ```

2. **Revert agntrick config:**
   ```bash
   cd ~/code/agents
   git revert HEAD~1  # Reverts the config.py change
   ```

3. **Revert agntrick-whatsapp:**
   ```bash
   cd ~/code/agntrick-whatsapp
   git revert HEAD~1  # Reverts the router.py change
   ```

4. **Alternative: Keep old MCP servers as fallback** - The removed `web-forager` and `hacker-news` entries can be restored to `agntrick/mcp/config.py` if toolkit tools have issues.
