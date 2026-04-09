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
class DeepScrapeResult:
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
            stage_value = self.stage.value if self.stage else "unknown"
            meta = f"[Source: {stage_value} | URL: {self.final_url or self.url}]\n\n"
            return f"{meta}{header}{self.content}"
        return f"Error extracting {self.url}: {self.error}"


class DeepScrapeTool(Tool):
    """Extract web content using a cascading fallback pipeline.

    Tries Crawl4AI first (local library, free), then Firecrawl API
    (credit-based), then Archive.ph (free archive) as a last resort.
    """

    def __init__(self) -> None:
        self._firecrawl_api_key = os.environ.get("FIRECRAWL_API_KEY", "")
        self._firecrawl_url = os.environ.get("FIRECRAWL_URL", "https://api.firecrawl.dev/v2")

    @property
    def name(self) -> str:
        return "deep_scrape"

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

    def _extract(self, url: str) -> DeepScrapeResult:
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
        return DeepScrapeResult(
            url=url,
            status=ExtractionStatus.ERROR,
            error="All extraction stages failed. Site may be down or fully paywalled.",
        )

    # --- Stage 1: Crawl4AI (Python library) ---

    def _try_crawl4ai(self, url: str) -> DeepScrapeResult:
        """Try Crawl4AI Python library (local, headless browser)."""
        try:
            return asyncio.run(self._crawl4ai_async(url))
        except ImportError:
            return DeepScrapeResult(
                url=url,
                status=ExtractionStatus.ERROR,
                stage=ExtractionStage.CRAWL4AI,
                error="crawl4ai package not installed. Run: uv add crawl4ai",
            )
        except RuntimeError:
            # Already in an event loop — use nest_asyncio or run in thread
            return self._try_crawl4ai_sync_fallback(url)
        except Exception as e:
            return DeepScrapeResult(
                url=url,
                status=ExtractionStatus.ERROR,
                stage=ExtractionStage.CRAWL4AI,
                error=str(e),
            )

    async def _crawl4ai_async(self, url: str) -> DeepScrapeResult:
        """Async Crawl4AI extraction using v0.8.x API."""
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig  # type: ignore
        from crawl4ai.content_filter_strategy import PruningContentFilter  # type: ignore
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator  # type: ignore

        md_generator = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                threshold=0.45,
                threshold_type="dynamic",
                min_word_threshold=5,
            )
        )
        run_config = CrawlerRunConfig(markdown_generator=md_generator)
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, config=run_config)
            if not result.success:
                return DeepScrapeResult(
                    url=url,
                    status=ExtractionStatus.ERROR,
                    stage=ExtractionStage.CRAWL4AI,
                    error=result.error_message or "Crawl4AI failed.",
                )
            fit = result.markdown.fit_markdown or ""
            raw = result.markdown.raw_markdown or ""
            # fit_markdown can be too aggressive on non-standard layouts — fall back
            # to raw if it pruned more than 80% of the content
            if fit and raw and len(fit) < len(raw) * 0.2:
                content = raw
            else:
                content = fit or raw
            if not content or len(content.strip()) < 100:
                return DeepScrapeResult(
                    url=url,
                    status=ExtractionStatus.BLOCKED,
                    stage=ExtractionStage.CRAWL4AI,
                    error="Crawl4AI returned insufficient content (possibly blocked).",
                )
            title = result.metadata.get("title", "") if result.metadata else ""
            return DeepScrapeResult(
                url=url,
                status=ExtractionStatus.SUCCESS,
                stage=ExtractionStage.CRAWL4AI,
                content=content,
                title=title,
                final_url=result.url,
            )

    def _try_crawl4ai_sync_fallback(self, url: str) -> DeepScrapeResult:
        """Fallback when already inside an event loop — run in a thread."""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, self._crawl4ai_async(url))
            try:
                return future.result(timeout=45)
            except Exception as e:
                return DeepScrapeResult(
                    url=url,
                    status=ExtractionStatus.ERROR,
                    stage=ExtractionStage.CRAWL4AI,
                    error=str(e),
                )

    # --- Stage 2: Firecrawl ---

    def _try_firecrawl(self, url: str) -> DeepScrapeResult:
        """Try Firecrawl API (requires FIRECRAWL_API_KEY)."""
        if not self._firecrawl_api_key:
            return DeepScrapeResult(
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
                return DeepScrapeResult(
                    url=url,
                    status=ExtractionStatus.BLOCKED,
                    stage=ExtractionStage.FIRECRAWL,
                    error="Firecrawl returned insufficient content.",
                )
            metadata = data.get("data", {}).get("metadata", {})
            return DeepScrapeResult(
                url=url,
                status=ExtractionStatus.SUCCESS,
                stage=ExtractionStage.FIRECRAWL,
                content=content,
                title=metadata.get("title", ""),
                final_url=metadata.get("sourceURL", url),
            )
        except httpx.HTTPStatusError as e:
            return DeepScrapeResult(
                url=url,
                status=ExtractionStatus.ERROR,
                stage=ExtractionStage.FIRECRAWL,
                error=f"Firecrawl API error: {e.response.status_code}",
            )
        except Exception as e:
            return DeepScrapeResult(
                url=url,
                status=ExtractionStatus.ERROR,
                stage=ExtractionStage.FIRECRAWL,
                error=str(e),
            )

    # --- Stage 3: Archive.ph ---

    def _try_archive_ph(self, url: str) -> DeepScrapeResult:
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
                return DeepScrapeResult(
                    url=url,
                    status=ExtractionStatus.NOT_FOUND,
                    stage=ExtractionStage.ARCHIVE_PH,
                    error="No archive found on archive.ph.",
                )

            text = self._extract_text_from_html(response.text)
            if not text or len(text.strip()) < 100:
                return DeepScrapeResult(
                    url=url,
                    status=ExtractionStatus.BLOCKED,
                    stage=ExtractionStage.ARCHIVE_PH,
                    error="Archive.ph returned insufficient content.",
                )

            title = self._extract_title(response.text)

            return DeepScrapeResult(
                url=url,
                status=ExtractionStatus.SUCCESS,
                stage=ExtractionStage.ARCHIVE_PH,
                content=text,
                title=title,
                final_url=str(response.url),
            )
        except Exception as e:
            return DeepScrapeResult(
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
