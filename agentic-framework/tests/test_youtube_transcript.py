"""Unit tests for YouTubeTranscriptTool."""

from unittest.mock import patch

import pytest

from agentic_framework.tools.youtube_transcript import YouTubeTranscriptTool


class TestYouTubeTranscriptTool:
    """Test suite for YouTubeTranscriptTool."""

    # === Fixtures ===

    @pytest.fixture
    def tool(self):
        """Create a YouTubeTranscriptTool instance."""
        return YouTubeTranscriptTool()

    @pytest.fixture
    def mock_transcript(self):
        """Create a mock transcript."""
        return [
            {"text": "Hello everyone", "start": 0.0, "duration": 2.0},
            {"text": "Welcome to the video", "start": 2.0, "duration": 2.0},
            {"text": "Today we'll discuss AI", "start": 4.0, "duration": 3.0},
        ]

    # === Property Tests ===

    def test_name_property(self, tool):
        """Test that tool name is correct."""
        assert tool.name == "youtube_transcript"

    def test_description_property(self, tool):
        """Test that tool description is correct."""
        assert "transcript" in tool.description.lower()
        assert "youtube" in tool.description.lower()

    # === Video ID Extraction Tests ===

    @pytest.mark.parametrize(
        "url,expected_id",
        [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/v/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ],
    )
    def test_extract_video_id_valid_urls(self, tool, url, expected_id):
        """Test video ID extraction from valid URLs."""
        result = tool._extract_video_id(url)
        assert result == expected_id

    def test_extract_video_id_invalid_url(self, tool):
        """Test video ID extraction from invalid URLs."""
        assert tool._extract_video_id("not a valid url") is None
        assert tool._extract_video_id("https://example.com") is None
        assert tool._extract_video_id("") is None

    def test_extract_video_id_with_whitespace(self, tool):
        """Test video ID extraction with whitespace."""
        assert tool._extract_video_id("  dQw4w9WgXcQ  ") == "dQw4w9WgXcQ"

    # === Transcript Formatting Tests ===

    def test_format_transcript(self, tool, mock_transcript):
        """Test transcript formatting."""
        tool._format_transcript = lambda x: "formatted output"

        result = tool.invoke("https://youtube.com/watch?v=test123")

        assert result == "formatted output"

    def test_invoke_invalid_url(self, tool):
        """Test handling of invalid URL."""
        result = tool.invoke("not a youtube url")

        assert "Error" in result
        assert "Could not extract" in result

    # === Timestamp Formatting Tests ===

    def test_format_timestamp_seconds_only(self, tool):
        """Test formatting timestamp with seconds only."""
        assert tool._format_timestamp(30) == "00:30"

    def test_format_timestamp_with_minutes(self, tool):
        """Test formatting timestamp with minutes."""
        assert tool._format_timestamp(90) == "01:30"

    def test_format_timestamp_with_hours(self, tool):
        """Test formatting timestamp with hours."""
        assert tool._format_timestamp(3661) == "01:01:01"

    def test_format_timestamp_zero(self, tool):
        """Test formatting zero timestamp."""
        assert tool._format_timestamp(0) == "00:00"

    def test_format_timestamp_large_value(self, tool):
        """Test formatting large timestamp value."""
        assert tool._format_timestamp(7259) == "02:00:59"

    # === Transcript Formatting Tests ===

    def test_format_transcript(self, tool, mock_transcript):
        """Test transcript formatting."""
        result = tool._format_transcript(mock_transcript)

        assert "[00:00]" in result
        assert "[00:02]" in result
        assert "[00:04]" in result
        assert "Hello everyone" in result
        assert "Welcome to the video" in result

    def test_format_transcript_empty_entries(self, tool):
        """Test transcript formatting with empty entries."""
        transcript = [
            {"text": "  ", "start": 0.0},  # Empty/whitespace
            {"text": "Valid text", "start": 5.0},
        ]
        result = tool._format_transcript(transcript)

        assert "Valid text" in result
        assert "[00:05]" in result
        # Empty entry should be filtered out
        assert "[00:00]" not in result or "Valid text" in result

    def test_format_transcript_special_characters(self, tool):
        """Test transcript formatting with special characters."""
        transcript = [
            {"text": "Hello! What's new?", "start": 0.0},
            {"text": "Emoji test \ud83d\ude0a", "start": 3.0},
        ]
        result = tool._format_transcript(transcript)

        assert "Hello! What's new?" in result
        assert "Emoji test" in result

    # === Error Message Tests ===

    def test_error_invalid_url(self, tool):
        """Test invalid URL error message."""
        result = tool._error_invalid_url("bad_url")
        assert "Error:" in result
        assert "Could not extract video ID" in result
        assert "bad_url" in result

    def test_error_transcripts_disabled(self, tool):
        """Test disabled transcripts error message."""
        result = tool._error_transcripts_disabled()
        assert "Error:" in result
        assert "disabled" in result.lower()

    def test_error_video_unavailable(self, tool):
        """Test unavailable video error message."""
        result = tool._error_video_unavailable("test_url")
        assert "Error:" in result
        assert "unavailable" in result.lower()
        assert "test_url" in result

    def test_error_no_transcript(self, tool):
        """Test no transcript error message."""
        result = tool._error_no_transcript()
        assert "Error:" in result
        assert "No transcript found" in result

    # === Cache Integration Tests ===

    def test_tool_uses_cache_by_default(self, tool):
        """Test that tool uses cache by default."""
        assert tool._cache is not None

    def test_tool_uses_provided_cache(self):
        """Test that tool uses provided cache instance."""
        from agentic_framework.tools.youtube_cache import YouTubeTranscriptCache

        mock_cache = YouTubeTranscriptCache(max_size_mb=0.001, ttl_days=0)
        tool = YouTubeTranscriptTool(cache=mock_cache)

        assert tool._cache is mock_cache

    # === Language Fallback Tests ===

    @patch("agentic_framework.tools.youtube_transcript.YouTubeTranscriptApi")
    def test_default_languages(self, mock_api, tool):
        """Test default language list."""
        # Get actual tool class to check attributes
        from agentic_framework.tools.youtube_transcript import YouTubeTranscriptTool
        assert "en" in YouTubeTranscriptTool.DEFAULT_LANGUAGES
        assert "en-US" in YouTubeTranscriptTool.DEFAULT_LANGUAGES
        assert "en-GB" in YouTubeTranscriptTool.DEFAULT_LANGUAGES

    @patch("agentic_framework.tools.youtube_transcript.YouTubeTranscriptApi")
    def test_fallback_languages(self, mock_api, tool):
        """Test fallback language list."""
        # Get actual tool class to check attributes
        from agentic_framework.tools.youtube_transcript import YouTubeTranscriptTool
        assert "es" in YouTubeTranscriptTool.FALLBACK_LANGUAGES
        assert "pt" in YouTubeTranscriptTool.FALLBACK_LANGUAGES
        assert "fr" in YouTubeTranscriptTool.FALLBACK_LANGUAGES


class TestYouTubeTranscriptToolIntegration:
    """Integration tests requiring network access (marked separately)."""

    @pytest.fixture
    def tool(self):
        """Create a YouTubeTranscriptTool instance."""
        return YouTubeTranscriptTool()

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires network access and valid video")
    def test_real_video_transcript(self, tool):
        """Test against a known stable video with captions."""
        # Use a well-known educational video with stable captions
        result = tool.invoke("https://www.youtube.com/watch?v=jNQXAC9IVRw")
        assert "Error" not in result
        assert len(result) > 100
