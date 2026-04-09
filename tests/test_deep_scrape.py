"""Tests for DeepScrapeTool — 3-stage web content extraction pipeline."""

from unittest.mock import MagicMock, patch

import httpx

from agntrick.tools.deep_scrape import (
    DeepScrapeResult,
    DeepScrapeTool,
    ExtractionStage,
    ExtractionStatus,
)


class TestDeepScrapeResult:
    """Tests for the DeepScrapeResult model."""

    def test_success_str_format(self) -> None:
        result = DeepScrapeResult(
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
        result = DeepScrapeResult(
            url="https://example.com/paywall",
            status=ExtractionStatus.BLOCKED,
            error="Content blocked by paywall.",
        )
        output = str(result)
        assert "Error" in output
        assert "blocked by paywall" in output

    def test_success_no_title(self) -> None:
        result = DeepScrapeResult(
            url="https://example.com",
            status=ExtractionStatus.SUCCESS,
            stage=ExtractionStage.FIRECRAWL,
            content="Just content.",
        )
        output = str(result)
        assert "# " not in output
        assert "Just content." in output


class TestDeepScrapeTool:
    """Tests for the DeepScrapeTool class."""

    def test_name_and_description(self) -> None:
        tool = DeepScrapeTool()
        assert tool.name == "deep_scrape"
        assert "Extract clean text" in tool.description

    def test_rejects_invalid_url(self) -> None:
        tool = DeepScrapeTool()
        result = tool.invoke("not-a-url")
        assert "Error" in result
        assert "Invalid URL" in result

    def test_rejects_non_http_url(self) -> None:
        tool = DeepScrapeTool()
        result = tool.invoke("ftp://example.com/file")
        assert "Error" in result

    def _make_crawl_result(self, markdown: str, title: str = "") -> MagicMock:
        """Create a mock CrawlResult object."""
        mock_result = MagicMock()
        mock_result.markdown = markdown
        mock_result.metadata = {"title": title} if title else {}
        return mock_result

    @patch("agntrick.tools.deep_scrape.asyncio")
    def test_stage1_crawl4ai_success(self, mock_asyncio: MagicMock) -> None:
        """Crawl4AI returns rich content — pipeline stops at Stage 1."""
        mock_asyncio.run.return_value = DeepScrapeResult(
            url="https://example.com/article",
            status=ExtractionStatus.SUCCESS,
            stage=ExtractionStage.CRAWL4AI,
            content="A" + "x" * 200,
            title="Test Article",
            final_url="https://example.com/article",
        )

        tool = DeepScrapeTool()
        result = tool.invoke("https://example.com/article")
        assert "Test Article" in result
        assert "crawl4ai" in result

    @patch("agntrick.tools.deep_scrape.asyncio")
    @patch.object(httpx, "post")
    @patch.object(httpx, "get")
    def test_stage1_fails_stage2_firecrawl_succeeds(
        self,
        mock_get: MagicMock,
        mock_post: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        """Crawl4AI fails, Firecrawl succeeds — returns content from Stage 2."""
        mock_asyncio.run.return_value = DeepScrapeResult(
            url="https://wsj.com/article",
            status=ExtractionStatus.BLOCKED,
            stage=ExtractionStage.CRAWL4AI,
            error="Insufficient content.",
        )

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

        tool = DeepScrapeTool()
        tool._firecrawl_api_key = "test-key"
        result = tool.invoke("https://wsj.com/article")
        assert "Paywalled Article" in result

    def test_stage2_firecrawl_skipped_without_key(self) -> None:
        """Firecrawl stage is skipped when no API key is set."""
        tool = DeepScrapeTool()
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
            "<html><head><title>Archived Page</title></head><body><p>" + "Content here. " * 50 + "</p></body></html>"
        )
        mock_get.return_value = mock_response

        tool = DeepScrapeTool()
        result = tool._try_archive_ph("https://example.com")
        assert result.status == ExtractionStatus.SUCCESS
        assert result.stage == ExtractionStage.ARCHIVE_PH
        assert result.title == "Archived Page"

    @patch.object(httpx, "get")
    def test_stage3_archive_ph_not_found(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        tool = DeepScrapeTool()
        result = tool._try_archive_ph("https://nonexistent.com")
        assert result.status == ExtractionStatus.NOT_FOUND

    def test_extract_text_from_html(self) -> None:
        html = "<html><head><title>Test</title></head><body><p>Hello world</p><script>var x=1;</script></body></html>"
        text = DeepScrapeTool._extract_text_from_html(html)
        assert "Hello world" in text
        assert "var x" not in text

    def test_extract_title(self) -> None:
        html = "<html><head><title>My Page Title</title></head><body></body></html>"
        title = DeepScrapeTool._extract_title(html)
        assert title == "My Page Title"

    def test_extract_title_empty(self) -> None:
        html = "<html><head></head><body></body></html>"
        title = DeepScrapeTool._extract_title(html)
        assert title == ""

    @patch("agntrick.tools.deep_scrape.asyncio")
    @patch.object(httpx, "post")
    @patch.object(httpx, "get")
    def test_full_pipeline_all_fail(
        self,
        mock_get: MagicMock,
        mock_post: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        """When all 3 stages fail, returns a combined error."""
        mock_asyncio.run.return_value = DeepScrapeResult(
            url="https://example.com/article",
            status=ExtractionStatus.ERROR,
            stage=ExtractionStage.CRAWL4AI,
            error="Crawl4AI error.",
        )
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        tool = DeepScrapeTool()
        result = tool.invoke("https://example.com/article")
        assert "All extraction stages failed" in result

    @patch("agntrick.tools.deep_scrape.asyncio")
    @patch.object(httpx, "post")
    @patch.object(httpx, "get")
    def test_whitespace_url_handling(
        self,
        mock_get: MagicMock,
        mock_post: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        mock_asyncio.run.return_value = DeepScrapeResult(
            url="https://example.com/article",
            status=ExtractionStatus.ERROR,
            stage=ExtractionStage.CRAWL4AI,
            error="failed",
        )
        mock_get.side_effect = httpx.ConnectError("fail")

        tool = DeepScrapeTool()
        result = tool.invoke("  https://example.com/article  ")
        assert "All extraction stages failed" in result or "example.com" in result
