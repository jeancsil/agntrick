"""Tests for DeepScrapeTool — 3-stage web content extraction pipeline with DNS retry."""

from unittest.mock import MagicMock, patch

import httpx

from agntrick.tools.deep_scrape import (
    DeepScrapeResult,
    DeepScrapeTool,
    ExtractionStage,
    ExtractionStatus,
    _is_dns_error,
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


class TestIsDnsError:
    """Tests for the _is_dns_error helper."""

    def test_dns_resolution_failed(self) -> None:
        assert _is_dns_error('Firecrawl error: DNS resolution failed for hostname "g1.globo.com.br"')

    def test_tunnel_connection_failed(self) -> None:
        assert _is_dns_error(
            "Firecrawl error: Internal Server Error: Failed to scrape. "
            'The URL failed to load in the browser with error code "ERR_TUNNEL_CONNECTION_FAILED"'
        )

    def test_getaddrinfo_failed(self) -> None:
        assert _is_dns_error("httpx.ConnectError: getaddrinfo failed for host example.com")

    def test_name_or_service_not_known(self) -> None:
        assert _is_dns_error("ConnectionError: Name or service not known")

    def test_nodename_failure(self) -> None:
        assert _is_dns_error("nodename nor servname provided, or not known")

    def test_temporary_failure(self) -> None:
        assert _is_dns_error("Temporary failure in name resolution")

    def test_non_dns_error_returns_false(self) -> None:
        assert not _is_dns_error("Firecrawl returned insufficient content.")

    def test_non_dns_connection_error(self) -> None:
        assert not _is_dns_error("Connection refused")

    def test_empty_string(self) -> None:
        assert not _is_dns_error("")

    def test_case_insensitive(self) -> None:
        assert _is_dns_error("dns RESOLUTION FAILED for host")


class TestDeepScrapeTool:
    """Tests for the DeepScrapeTool class."""

    def test_name_and_description(self) -> None:
        tool = DeepScrapeTool()
        assert tool.name == "deep_scrape"
        assert "Extract clean text" in tool.description

    def test_persistent_crawler_reuse(self) -> None:
        """Verify that _get_crawler() returns the same instance across calls."""
        import asyncio

        async def check_reuse() -> None:
            tool1 = DeepScrapeTool()
            tool2 = DeepScrapeTool()

            # Both tool instances should share the same class-level crawler
            crawler1 = await tool1._get_crawler()
            crawler2 = await tool2._get_crawler()

            # Verify they're the same instance
            assert crawler1 is crawler2
            assert DeepScrapeTool._crawler is crawler1

        # Run the async test
        asyncio.run(check_reuse())

    def test_rejects_invalid_url(self) -> None:
        tool = DeepScrapeTool()
        result = tool.invoke("not-a-url")
        assert "Error" in result
        assert "Invalid URL" in result

    def test_rejects_non_http_url(self) -> None:
        tool = DeepScrapeTool()
        result = tool.invoke("ftp://example.com/file")
        assert "Error" in result

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
    @patch("agntrick.tools.deep_scrape.Firecrawl")
    @patch.object(httpx, "get")
    def test_stage1_fails_stage2_firecrawl_succeeds(
        self,
        mock_get: MagicMock,
        mock_firecrawl_cls: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        """Crawl4AI fails, Firecrawl succeeds — returns content from Stage 2."""
        mock_asyncio.run.return_value = DeepScrapeResult(
            url="https://wsj.com/article",
            status=ExtractionStatus.BLOCKED,
            stage=ExtractionStage.CRAWL4AI,
            error="Insufficient content.",
        )

        mock_app = MagicMock()
        mock_app.scrape.return_value = {
            "markdown": "Full article content " + "x" * 200,
            "metadata": {
                "title": "Paywalled Article",
                "sourceURL": "https://wsj.com/article",
            },
        }
        mock_firecrawl_cls.return_value = mock_app

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
    @patch.object(httpx, "get")
    def test_full_pipeline_all_fail(
        self,
        mock_get: MagicMock,
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
        tool._firecrawl_api_key = ""
        result = tool.invoke("https://example.com/article")
        assert "All extraction stages failed" in result

    @patch("agntrick.tools.deep_scrape.asyncio")
    @patch.object(httpx, "get")
    def test_whitespace_url_handling(
        self,
        mock_get: MagicMock,
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


class TestFirecrawlDnsRetry:
    """Tests for DNS retry logic in _try_firecrawl."""

    @patch("agntrick.tools.deep_scrape.time")
    @patch("agntrick.tools.deep_scrape.Firecrawl")
    def test_firecrawl_retries_on_dns_error_then_succeeds(
        self,
        mock_firecrawl_cls: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        """Firecrawl retries once when DNS error occurs, then succeeds."""
        mock_app = MagicMock()
        # First call raises DNS error, second succeeds
        mock_app.scrape.side_effect = [
            Exception('DNS resolution failed for hostname "g1.globo.com.br"'),
            {
                "markdown": "Recovered content " + "x" * 200,
                "metadata": {"title": "Recovered", "sourceURL": "https://g1.globo.com"},
            },
        ]
        mock_firecrawl_cls.return_value = mock_app

        tool = DeepScrapeTool()
        tool._firecrawl_api_key = "test-key"
        result = tool._try_firecrawl("https://g1.globo.com")

        assert result.status == ExtractionStatus.SUCCESS
        assert result.title == "Recovered"
        assert mock_app.scrape.call_count == 2
        mock_time.sleep.assert_called_once_with(2.0)

    @patch("agntrick.tools.deep_scrape.time")
    @patch("agntrick.tools.deep_scrape.Firecrawl")
    def test_firecrawl_retries_on_tunnel_error_then_succeeds(
        self,
        mock_firecrawl_cls: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        """Firecrawl retries once when ERR_TUNNEL_CONNECTION_FAILED occurs."""
        mock_app = MagicMock()
        mock_app.scrape.side_effect = [
            Exception('The URL failed to load with error code "ERR_TUNNEL_CONNECTION_FAILED"'),
            {
                "markdown": "Tunnel recovered " + "x" * 200,
                "metadata": {"title": "Tunnel OK", "sourceURL": "https://example.com"},
            },
        ]
        mock_firecrawl_cls.return_value = mock_app

        tool = DeepScrapeTool()
        tool._firecrawl_api_key = "test-key"
        result = tool._try_firecrawl("https://example.com")

        assert result.status == ExtractionStatus.SUCCESS
        assert result.title == "Tunnel OK"
        assert mock_app.scrape.call_count == 2

    @patch("agntrick.tools.deep_scrape.time")
    @patch("agntrick.tools.deep_scrape.Firecrawl")
    def test_firecrawl_does_not_retry_on_non_dns_error(
        self,
        mock_firecrawl_cls: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        """Firecrawl does NOT retry on non-DNS errors."""
        mock_app = MagicMock()
        mock_app.scrape.side_effect = Exception("Internal Server Error: Rate limit exceeded")
        mock_firecrawl_cls.return_value = mock_app

        tool = DeepScrapeTool()
        tool._firecrawl_api_key = "test-key"
        result = tool._try_firecrawl("https://example.com")

        assert result.status == ExtractionStatus.ERROR
        assert "Rate limit exceeded" in result.error
        assert mock_app.scrape.call_count == 1
        mock_time.sleep.assert_not_called()

    @patch("agntrick.tools.deep_scrape.time")
    @patch("agntrick.tools.deep_scrape.Firecrawl")
    def test_firecrawl_dns_retry_exhausted(
        self,
        mock_firecrawl_cls: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        """Firecrawl retries once on DNS error, then returns error if still failing."""
        mock_app = MagicMock()
        mock_app.scrape.side_effect = Exception("getaddrinfo failed for host example.com")
        mock_firecrawl_cls.return_value = mock_app

        tool = DeepScrapeTool()
        tool._firecrawl_api_key = "test-key"
        result = tool._try_firecrawl("https://example.com")

        assert result.status == ExtractionStatus.ERROR
        assert "getaddrinfo failed" in result.error
        assert mock_app.scrape.call_count == 2
        mock_time.sleep.assert_called_once_with(2.0)

    @patch("agntrick.tools.deep_scrape.time")
    @patch("agntrick.tools.deep_scrape.Firecrawl")
    def test_firecrawl_no_retry_on_blocked(
        self,
        mock_firecrawl_cls: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        """Firecrawl does NOT retry when content is blocked (insufficient content)."""
        mock_app = MagicMock()
        mock_app.scrape.return_value = {
            "markdown": "short",
            "metadata": {},
        }
        mock_firecrawl_cls.return_value = mock_app

        tool = DeepScrapeTool()
        tool._firecrawl_api_key = "test-key"
        result = tool._try_firecrawl("https://example.com")

        assert result.status == ExtractionStatus.BLOCKED
        assert mock_app.scrape.call_count == 1
        mock_time.sleep.assert_not_called()


class TestArchivePhDnsRetry:
    """Tests for DNS retry logic in _try_archive_ph."""

    @patch("agntrick.tools.deep_scrape.time")
    @patch.object(httpx, "get")
    def test_archive_ph_retries_on_dns_error_then_succeeds(
        self,
        mock_get: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        """Archive.ph retries once on DNS error, then succeeds."""
        dns_error = httpx.ConnectError("getaddrinfo failed for host archive.ph")
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.url = "https://archive.ph/abc/https://example.com"
        success_response.text = (
            "<html><head><title>Archived</title></head><body><p>" + "Content. " * 50 + "</p></body></html>"
        )

        mock_get.side_effect = [dns_error, success_response]

        tool = DeepScrapeTool()
        result = tool._try_archive_ph("https://example.com")

        assert result.status == ExtractionStatus.SUCCESS
        assert result.title == "Archived"
        assert mock_get.call_count == 2
        mock_time.sleep.assert_called_once_with(2.0)

    @patch("agntrick.tools.deep_scrape.time")
    @patch.object(httpx, "get")
    def test_archive_ph_does_not_retry_on_non_dns_error(
        self,
        mock_get: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        """Archive.ph does NOT retry on non-DNS connection errors."""
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        tool = DeepScrapeTool()
        result = tool._try_archive_ph("https://example.com")

        assert result.status == ExtractionStatus.ERROR
        assert "Connection refused" in result.error
        assert mock_get.call_count == 1
        mock_time.sleep.assert_not_called()

    @patch("agntrick.tools.deep_scrape.time")
    @patch.object(httpx, "get")
    def test_archive_ph_dns_retry_exhausted(
        self,
        mock_get: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        """Archive.ph retries once on DNS error, returns error if still failing."""
        mock_get.side_effect = httpx.ConnectError("DNS resolution failed for archive.ph")

        tool = DeepScrapeTool()
        result = tool._try_archive_ph("https://example.com")

        assert result.status == ExtractionStatus.ERROR
        assert "DNS resolution failed" in result.error
        assert mock_get.call_count == 2
        mock_time.sleep.assert_called_once_with(2.0)

    @patch("agntrick.tools.deep_scrape.time")
    @patch.object(httpx, "get")
    def test_archive_ph_no_retry_on_404(
        self,
        mock_get: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        """Archive.ph does NOT retry on 404 (not a DNS error)."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        tool = DeepScrapeTool()
        result = tool._try_archive_ph("https://example.com")

        assert result.status == ExtractionStatus.NOT_FOUND
        assert mock_get.call_count == 1
        mock_time.sleep.assert_not_called()
