# 10ft Tall — Hybrid Web Content Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-stage hybrid web content extraction pipeline for agntrick that bypasses paywalls and anti-bot protections using Crawl4AI (local), Firecrawl (API fallback), and Archive.ph (last resort).

**Architecture:** A `WebExtractorTool` registered as a local tool on the assistant agent orchestrates a cascading pipeline: Stage 1 uses Crawl4AI as a local Python library (free, fast, headless browser via `pip install crawl4ai`), Stage 2 falls back to Firecrawl API (credit-based, high success rate), Stage 3 tries Archive.ph (free, archived snapshots). Each stage returns a `WebContentResult` with status, content, and metadata. The tool follows the existing `Tool` ABC pattern from `interfaces/base.py`. Since `Tool.invoke()` is synchronous but Crawl4AI's `AsyncWebCrawler` is async, the tool bridges with `asyncio.run()` (and a `ThreadPoolExecutor` fallback for nested event loops).

**Tech Stack:** Python 3.12+, httpx (already in deps), crawl4ai (new pip package, local library), Firecrawl REST API.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/agntrick/tools/web_extractor.py` | Create | `WebExtractorTool` — the main Tool subclass and `WebContentResult` model |
| `src/agntrick/tools/__init__.py` | Modify | Export new tool |
| `src/agntrick/agents/assistant.py` | Modify | Register `WebExtractorTool` as a local tool |
| `src/agntrick/config.py` | Modify | Add `WebExtractorConfig` dataclass |
| `tests/test_web_extractor.py` | Create | Tests for all stages |
| `.env.example` | Modify | Document new env vars |

---

### Task 1: WebContentResult Model and WebExtractorTool Skeleton

**Files:**
- Create: `src/agntrick/tools/web_extractor.py`

- [ ] **Step 1: Add crawl4ai as a dependency**

Run: `cd /Users/jeancsil/code/agents && uv add crawl4ai`

- [ ] **Step 2: Create the tool file with the result model and tool skeleton**

```python
"""Web content extraction tool with cascading fallback pipeline.

Implements a 3-stage hybrid strategy for extracting web content,
including paywalled and bot-protected sites:

Stage 1: Crawl4AI (local Python library, free, fast — handles 80% of cases)
Stage 2: Firecrawl API (credit-based, handles Cloudflare/turnstile)
Stage 3: Archive.ph (free, archived snapshots — last resort)
"""

import asyncio
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from agntrick.interfaces.base import Tool


class ExtractionStage(str, Enum):
    """Which extraction method succeeded."""

    CRAWL4AI = "crawl4ai"
    FIRECRAWL = "firecrawl"
    ARCHIVE_PH = "archive_ph"


class ExtractionStatus(str, Enum):
    """Result status."""

    SUCCESS = "success"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass
class WebContentResult:
    """Structured result from web content extraction.

    Attributes:
        url: The original URL requested.
        final_url: The URL after redirects (may differ from original).
        status: Whether extraction succeeded.
        stage: Which extraction method was used.
        content: Extracted markdown content (empty string on failure).
        title: Page title if extracted.
        error: Error message if status is not SUCCESS.
    """

    url: str
    status: ExtractionStatus
    stage: ExtractionStage | None = None
    content: str = ""
    title: str = ""
    final_url: str = ""
    error: str = ""

    def __str__(self) -> str:
        if self.status == ExtractionStatus.SUCCESS:
            header = f"# {self.title}\n\n" if self.title else ""
            meta = f"[Source: {self.stage.value} | URL: {self.final_url or self.url}]\n\n"
            return f"{meta}{header}{self.content}"
        return f"Error extracting {self.url}: {self.error}"


class WebExtractorTool(Tool):
    """Extract web content using a cascading fallback pipeline.

    Tries Crawl4AI first (local library, free), then Firecrawl API
    (credit-based), then Archive.ph (free archive) as a last resort.
    """

    def __init__(self) -> None:
        self._firecrawl_api_key = os.environ.get("FIRECRAWL_API_KEY", "")
        self._firecrawl_url = os.environ.get(
            "FIRECRAWL_URL", "https://api.firecrawl.dev/v1"
        )

    @property
    def name(self) -> str:
        return "web_extract"

    @property
    def description(self) -> str:
        return (
            "Extract clean text content from a web page URL, including paywalled "
            "and bot-protected sites. Returns markdown-formatted content. "
            "Input: a single URL string."
        )

    def invoke(self, input_str: str) -> str:
        """Extract content from the given URL using the cascading pipeline."""
        url = input_str.strip()
        if not url.startswith(("http://", "https://")):
            return f"Error: Invalid URL — must start with http:// or https://. Got: {url}"

        result = self._extract(url)
        return str(result)

    def _extract(self, url: str) -> WebContentResult:
        """Run the 3-stage extraction pipeline."""
        # Stage 1: Crawl4AI (local library, free)
        result = self._try_crawl4ai(url)
        if result.status == ExtractionStatus.SUCCESS:
            return result

        # Stage 2: Firecrawl (API, credit-based)
        result = self._try_firecrawl(url)
        if result.status == ExtractionStatus.SUCCESS:
            return result

        # Stage 3: Archive.ph (free, last resort)
        result = self._try_archive_ph(url)
        if result.status == ExtractionStatus.SUCCESS:
            return result

        # All stages failed — return last error
        return WebContentResult(
            url=url,
            status=ExtractionStatus.ERROR,
            error="All extraction stages failed. Site may be down or fully paywalled.",
        )

    # --- Stage 1: Crawl4AI (Python library) ---

    def _try_crawl4ai(self, url: str) -> WebContentResult:
        """Try Crawl4AI Python library (local, headless browser)."""
        try:
            return asyncio.run(self._crawl4ai_async(url))
        except ImportError:
            return WebContentResult(
                url=url,
                status=ExtractionStatus.ERROR,
                stage=ExtractionStage.CRAWL4AI,
                error="crawl4ai package not installed. Run: uv add crawl4ai",
            )
        except RuntimeError:
            # Already in an event loop — use nest_asyncio or run in thread
            return self._try_crawl4ai_sync_fallback(url)
        except Exception as e:
            return WebContentResult(
                url=url,
                status=ExtractionStatus.ERROR,
                stage=ExtractionStage.CRAWL4AI,
                error=str(e),
            )

    async def _crawl4ai_async(self, url: str) -> WebContentResult:
        """Async Crawl4AI extraction."""
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
        from crawl4ai.content_filter_strategy import PruningContentFilter

        run_config = CrawlerRunConfig(
            content_filter=PruningContentFilter(),
        )
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, config=run_config)
            content = result.markdown or ""
            if not content or len(content.strip()) < 100:
                return WebContentResult(
                    url=url,
                    status=ExtractionStatus.BLOCKED,
                    stage=ExtractionStage.CRAWL4AI,
                    error="Crawl4AI returned insufficient content (possibly blocked).",
                )
            title = result.metadata.get("title", "") if result.metadata else ""
            return WebContentResult(
                url=url,
                status=ExtractionStatus.SUCCESS,
                stage=ExtractionStage.CRAWL4AI,
                content=content,
                title=title,
                final_url=url,
            )

    def _try_crawl4ai_sync_fallback(self, url: str) -> WebContentResult:
        """Fallback when already inside an event loop — run in a thread."""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, self._crawl4ai_async(url))
            try:
                return future.result(timeout=45)
            except Exception as e:
                return WebContentResult(
                    url=url,
                    status=ExtractionStatus.ERROR,
                    stage=ExtractionStage.CRAWL4AI,
                    error=str(e),
                )

    # --- Stage 2: Firecrawl ---

    def _try_firecrawl(self, url: str) -> WebContentResult:
        """Try Firecrawl API (requires FIRECRAWL_API_KEY)."""
        if not self._firecrawl_api_key:
            return WebContentResult(
                url=url,
                status=ExtractionStatus.ERROR,
                stage=ExtractionStage.FIRECRAWL,
                error="FIRECRAWL_API_KEY not set — skipping Firecrawl stage.",
            )
        try:
            response = httpx.post(
                f"{self._firecrawl_url}/scrape",
                headers={
                    "Authorization": f"Bearer {self._firecrawl_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "url": url,
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                },
                timeout=45.0,
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("data", {}).get("markdown", "")
            if not content or len(content.strip()) < 100:
                return WebContentResult(
                    url=url,
                    status=ExtractionStatus.BLOCKED,
                    stage=ExtractionStage.FIRECRAWL,
                    error="Firecrawl returned insufficient content.",
                )
            metadata = data.get("data", {}).get("metadata", {})
            return WebContentResult(
                url=url,
                status=ExtractionStatus.SUCCESS,
                stage=ExtractionStage.FIRECRAWL,
                content=content,
                title=metadata.get("title", ""),
                final_url=metadata.get("sourceURL", url),
            )
        except httpx.HTTPStatusError as e:
            return WebContentResult(
                url=url,
                status=ExtractionStatus.ERROR,
                stage=ExtractionStage.FIRECRAWL,
                error=f"Firecrawl API error: {e.response.status_code}",
            )
        except Exception as e:
            return WebContentResult(
                url=url,
                status=ExtractionStatus.ERROR,
                stage=ExtractionStage.FIRECRAWL,
                error=str(e),
            )

    # --- Stage 3: Archive.ph ---

    def _try_archive_ph(self, url: str) -> WebContentResult:
        """Try Archive.ph for an archived snapshot."""
        try:
            check_url = f"https://archive.ph/newest/{url}"
            response = httpx.get(
                check_url,
                follow_redirects=True,
                timeout=20.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 "
                        "Safari/537.36"
                    ),
                },
            )
            if response.status_code != 200:
                return WebContentResult(
                    url=url,
                    status=ExtractionStatus.NOT_FOUND,
                    stage=ExtractionStage.ARCHIVE_PH,
                    error="No archive found on archive.ph.",
                )

            text = self._extract_text_from_html(response.text)
            if not text or len(text.strip()) < 100:
                return WebContentResult(
                    url=url,
                    status=ExtractionStatus.BLOCKED,
                    stage=ExtractionStage.ARCHIVE_PH,
                    error="Archive.ph returned insufficient content.",
                )

            title = self._extract_title(response.text)

            return WebContentResult(
                url=url,
                status=ExtractionStatus.SUCCESS,
                stage=ExtractionStage.ARCHIVE_PH,
                content=text,
                title=title,
                final_url=str(response.url),
            )
        except Exception as e:
            return WebContentResult(
                url=url,
                status=ExtractionStatus.ERROR,
                stage=ExtractionStage.ARCHIVE_PH,
                error=str(e),
            )

    @staticmethod
    def _extract_text_from_html(html: str) -> str:
        """Extract readable text from HTML using a simple heuristic."""
        # Remove script and style blocks
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Decode common HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'")
        text = text.replace("&nbsp;", " ")
        return text

    @staticmethod
    def _extract_title(html: str) -> str:
        """Extract <title> content from HTML."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
```

- [ ] **Step 3: Run type check to verify the skeleton compiles**

Run: `cd /Users/jeancsil/code/agents && uv run mypy src/agntrick/tools/web_extractor.py --ignore-missing-imports`
Expected: No errors

---

### Task 2: Register the Tool in Package Exports

**Files:**
- Modify: `src/agntrick/tools/__init__.py`

- [ ] **Step 1: Add import and export for WebExtractorTool**

Add to `src/agntrick/tools/__init__.py`:

After the existing imports, add:
```python
from .web_extractor import WebContentResult, WebExtractorTool, ExtractionStage, ExtractionStatus
```

In `__all__`, add:
```python
    "WebExtractorTool",
    "WebContentResult",
    "ExtractionStage",
    "ExtractionStatus",
```

- [ ] **Step 2: Verify imports work**

Run: `cd /Users/jeancsil/code/agents && uv run python -c "from agntrick.tools import WebExtractorTool; t = WebExtractorTool(); print(t.name)"`
Expected: `web_extract`

---

### Task 3: Add WebExtractorConfig to Configuration

**Files:**
- Modify: `src/agntrick/config.py`

- [ ] **Step 1: Add the WebExtractorConfig dataclass**

Add after the `MCPConfig` dataclass (after line 87):

```python
@dataclass
class WebExtractorConfig:
    """Web content extraction configuration."""

    firecrawl_api_key: str = ""
    firecrawl_url: str = "https://api.firecrawl.dev/v1"
    archive_ph_enabled: bool = True
```

- [ ] **Step 2: Add the field to AgntrickConfig**

Add to the `AgntrickConfig` dataclass (after `agent_models` field, around line 168):

```python
    web_extractor: WebExtractorConfig = field(default_factory=WebExtractorConfig)
```

- [ ] **Step 3: Parse the config in `from_dict`**

Add to `AgntrickConfig.from_dict()` (after the `agent_models_config` creation, before the `return cls(...)` call):

```python
        we_dict = config_dict.get("web_extractor", {})
        web_extractor_config = WebExtractorConfig(**we_dict)
```

And add `web_extractor=web_extractor_config,` to the `return cls(...)` call.

- [ ] **Step 4: Run make check**

Run: `cd /Users/jeancsil/code/agents && make check`
Expected: mypy and ruff pass

---

### Task 4: Wire WebExtractorTool into AssistantAgent

**Files:**
- Modify: `src/agntrick/agents/assistant.py`

- [ ] **Step 1: Import and add the tool to local_tools**

Change the import section at the top of `src/agntrick/agents/assistant.py`:

```python
from agntrick.agent import AgentBase
from agntrick.graph import create_assistant_graph
from agntrick.prompts import load_prompt
from agntrick.registry import AgentRegistry
from agntrick.tools import AgentInvocationTool, WebExtractorTool
```

Update `local_tools`:

```python
    def local_tools(self) -> Sequence[Any]:
        """Return local tools including agent invocation and web extraction."""
        return [
            AgentInvocationTool().to_langchain_tool(),
            WebExtractorTool().to_langchain_tool(),
        ]
```

- [ ] **Step 2: Run make check**

Run: `cd /Users/jeancsil/code/agents && make check`
Expected: mypy and ruff pass

---

### Task 5: Update .env.example

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add new environment variables**

Append to `.env.example`:

```bash
# Web Content Extraction (10ft Tall)
# Crawl4AI — local Python library (pip install crawl4ai), no env config needed
# Firecrawl — API key for credit-based extraction fallback
FIRECRAWL_API_KEY=
# Firecrawl — custom API base URL (default: https://api.firecrawl.dev/v1)
FIRECRAWL_URL=https://api.firecrawl.dev/v1
```

---

### Task 6: Write Tests

**Files:**
- Create: `tests/test_web_extractor.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for WebExtractorTool — 3-stage web content extraction pipeline."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agntrick.tools.web_extractor import (
    ExtractionStage,
    ExtractionStatus,
    WebContentResult,
    WebExtractorTool,
)


class TestWebContentResult:
    """Tests for the WebContentResult model."""

    def test_success_str_format(self) -> None:
        result = WebContentResult(
            url="https://example.com/article",
            status=ExtractionStatus.SUCCESS,
            stage=ExtractionStage.CRAWL4AI,
            content="Article body text here.",
            title="Test Article",
            final_url="https://example.com/article",
        )
        output = str(result)
        assert "Test Article" in output
        assert "Article body text here." in output
        assert "crawl4ai" in output

    def test_error_str_format(self) -> None:
        result = WebContentResult(
            url="https://example.com/paywall",
            status=ExtractionStatus.BLOCKED,
            error="Content blocked by paywall.",
        )
        output = str(result)
        assert "Error" in output
        assert "blocked by paywall" in output

    def test_success_no_title(self) -> None:
        result = WebContentResult(
            url="https://example.com",
            status=ExtractionStatus.SUCCESS,
            stage=ExtractionStage.FIRECRAWL,
            content="Just content.",
        )
        output = str(result)
        assert "# " not in output
        assert "Just content." in output


class TestWebExtractorTool:
    """Tests for the WebExtractorTool class."""

    def test_name_and_description(self) -> None:
        tool = WebExtractorTool()
        assert tool.name == "web_extract"
        assert "Extract clean text" in tool.description

    def test_rejects_invalid_url(self) -> None:
        tool = WebExtractorTool()
        result = tool.invoke("not-a-url")
        assert "Error" in result
        assert "Invalid URL" in result

    def test_rejects_non_http_url(self) -> None:
        tool = WebExtractorTool()
        result = tool.invoke("ftp://example.com/file")
        assert "Error" in result

    def _make_crawl_result(self, markdown: str, title: str = "") -> MagicMock:
        """Create a mock CrawlResult object."""
        mock_result = MagicMock()
        mock_result.markdown = markdown
        mock_result.metadata = {"title": title} if title else {}
        return mock_result

    @patch("agntrick.tools.web_extractor.asyncio")
    def test_stage1_crawl4ai_success(self, mock_asyncio: MagicMock) -> None:
        """Crawl4AI returns rich content — pipeline stops at Stage 1."""
        mock_result = self._make_crawl_result(
            "A" + "x" * 200, title="Test Article"
        )
        # asyncio.run returns the result from _crawl4ai_async
        mock_asyncio.run.return_value = WebContentResult(
            url="https://example.com/article",
            status=ExtractionStatus.SUCCESS,
            stage=ExtractionStage.CRAWL4AI,
            content="A" + "x" * 200,
            title="Test Article",
            final_url="https://example.com/article",
        )

        tool = WebExtractorTool()
        result = tool.invoke("https://example.com/article")
        assert "Test Article" in result
        assert "crawl4ai" in result

    @patch("agntrick.tools.web_extractor.asyncio")
    @patch.object(httpx, "post")
    @patch.object(httpx, "get")
    def test_stage1_fails_stage2_firecrawl_succeeds(
        self,
        mock_get: MagicMock,
        mock_post: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        """Crawl4AI fails, Firecrawl succeeds — returns content from Stage 2."""
        # Crawl4AI returns blocked
        mock_asyncio.run.return_value = WebContentResult(
            url="https://wsj.com/article",
            status=ExtractionStatus.BLOCKED,
            stage=ExtractionStage.CRAWL4AI,
            error="Insufficient content.",
        )

        # Firecrawl succeeds
        firecrawl_response = MagicMock()
        firecrawl_response.status_code = 200
        firecrawl_response.raise_for_status = MagicMock()
        firecrawl_response.json.return_value = {
            "data": {
                "markdown": "Full article content " + "x" * 200,
                "metadata": {
                    "title": "Paywalled Article",
                    "sourceURL": "https://wsj.com/article",
                },
            }
        }
        mock_post.return_value = firecrawl_response

        tool = WebExtractorTool()
        tool._firecrawl_api_key = "test-key"
        result = tool.invoke("https://wsj.com/article")
        assert "Paywalled Article" in result

    def test_stage2_firecrawl_skipped_without_key(self) -> None:
        """Firecrawl stage is skipped when no API key is set."""
        tool = WebExtractorTool()
        tool._firecrawl_api_key = ""
        result = tool._try_firecrawl("https://example.com")
        assert result.status == ExtractionStatus.ERROR
        assert "FIRECRAWL_API_KEY" in result.error

    @patch.object(httpx, "get")
    def test_stage3_archive_ph_success(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "https://archive.ph/abc123/https://example.com"
        mock_response.text = (
            "<html><head><title>Archived Page</title></head>"
            "<body><p>" + "Content here. " * 50 + "</p></body></html>"
        )
        mock_get.return_value = mock_response

        tool = WebExtractorTool()
        result = tool._try_archive_ph("https://example.com")
        assert result.status == ExtractionStatus.SUCCESS
        assert result.stage == ExtractionStage.ARCHIVE_PH
        assert result.title == "Archived Page"

    @patch.object(httpx, "get")
    def test_stage3_archive_ph_not_found(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        tool = WebExtractorTool()
        result = tool._try_archive_ph("https://nonexistent.com")
        assert result.status == ExtractionStatus.NOT_FOUND

    def test_extract_text_from_html(self) -> None:
        html = (
            "<html><head><title>Test</title></head>"
            "<body><p>Hello world</p><script>var x=1;</script></body></html>"
        )
        text = WebExtractorTool._extract_text_from_html(html)
        assert "Hello world" in text
        assert "var x" not in text

    def test_extract_title(self) -> None:
        html = "<html><head><title>My Page Title</title></head><body></body></html>"
        title = WebExtractorTool._extract_title(html)
        assert title == "My Page Title"

    def test_extract_title_empty(self) -> None:
        html = "<html><head></head><body></body></html>"
        title = WebExtractorTool._extract_title(html)
        assert title == ""

    @patch("agntrick.tools.web_extractor.asyncio")
    @patch.object(httpx, "post")
    @patch.object(httpx, "get")
    def test_full_pipeline_all_fail(
        self,
        mock_get: MagicMock,
        mock_post: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        """When all 3 stages fail, returns a combined error."""
        # Crawl4AI fails
        mock_asyncio.run.return_value = WebContentResult(
            url="https://example.com/article",
            status=ExtractionStatus.ERROR,
            stage=ExtractionStage.CRAWL4AI,
            error="Crawl4AI error.",
        )
        # Firecrawl fails (no API key)
        # Archive.ph fails
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        tool = WebExtractorTool()
        result = tool.invoke("https://example.com/article")
        assert "All extraction stages failed" in result

    @patch("agntrick.tools.web_extractor.asyncio")
    @patch.object(httpx, "post")
    @patch.object(httpx, "get")
    def test_whitespace_url_handling(
        self,
        mock_get: MagicMock,
        mock_post: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        mock_asyncio.run.return_value = WebContentResult(
            url="https://example.com/article",
            status=ExtractionStatus.ERROR,
            stage=ExtractionStage.CRAWL4AI,
            error="failed",
        )
        mock_get.side_effect = httpx.ConnectError("fail")

        tool = WebExtractorTool()
        result = tool.invoke("  https://example.com/article  ")
        # Should still attempt extraction after strip
        assert "All extraction stages failed" in result or "example.com" in result
```

- [ ] **Step 2: Run the tests**

Run: `cd /Users/jeancsil/code/agents && uv run pytest tests/test_web_extractor.py -v`
Expected: All tests pass

---

### Task 7: Run Full Verification

- [ ] **Step 1: Run make check && make test**

Run: `cd /Users/jeancsil/code/agents && make check && make test`
Expected: All checks pass, all tests pass

- [ ] **Step 2: Commit**

```bash
git add src/agntrick/tools/web_extractor.py src/agntrick/tools/__init__.py src/agntrick/config.py src/agntrick/agents/assistant.py tests/test_web_extractor.py .env.example
git commit -m "feat: add 10ft-tall hybrid web content extraction pipeline

Implements a 3-stage cascading extraction tool (WebExtractorTool):
- Stage 1: Crawl4AI (local Docker, free)
- Stage 2: Firecrawl API (credit-based fallback)
- Stage 3: Archive.ph (free archived snapshots)

Registered as a local tool on the assistant agent."
```
