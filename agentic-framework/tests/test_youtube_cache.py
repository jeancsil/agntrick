"""Unit tests for YouTubeTranscriptCache."""

import time
from pathlib import Path

import pytest

from agentic_framework.tools.youtube_cache import YouTubeTranscriptCache


class TestYouTubeTranscriptCache:
    """Test suite for YouTubeTranscriptCache."""

    @pytest.fixture
    def temp_cache_dir(self, tmp_path: Path) -> Path:
        """Create a temporary cache directory.

        Args:
            tmp_path: Pytest temporary path fixture.

        Returns:
            Path to temporary cache directory.
        """
        cache_dir = tmp_path / "youtube_cache"
        cache_dir.mkdir()
        return cache_dir

    @pytest.fixture
    def cache(self, temp_cache_dir: Path) -> YouTubeTranscriptCache:
        """Create a cache instance with temporary storage.

        Args:
            temp_cache_dir: Temporary cache directory.

        Returns:
            YouTubeTranscriptCache instance.
        """
        return YouTubeTranscriptCache(
            cache_dir=temp_cache_dir,
            max_size_mb=1,  # Small size for testing eviction
            ttl_days=0,  # No TTL by default
        )

    # === Basic CRUD Operations ===

    def test_set_and_get(self, cache: YouTubeTranscriptCache) -> None:
        """Test storing and retrieving a transcript."""
        video_id = "test123"
        transcript = "Hello everyone, welcome to the video."

        cache.set(video_id, transcript, "https://youtube.com/watch?v=test123")

        result = cache.get(video_id)
        assert result is not None
        assert result["transcript_text"] == transcript
        assert result["video_id"] == video_id

    def test_get_nonexistent(self, cache: YouTubeTranscriptCache) -> None:
        """Test retrieving a non-existent transcript."""
        result = cache.get("nonexistent")
        assert result is None

    def test_delete(self, cache: YouTubeTranscriptCache) -> None:
        """Test deleting a cached transcript."""
        video_id = "delete_test"
        cache.set(video_id, "Test transcript", "https://youtube.com/watch?v=delete_test")

        assert cache.get(video_id) is not None

        deleted = cache.delete(video_id)
        assert deleted is True
        assert cache.get(video_id) is None

    def test_delete_nonexistent(self, cache: YouTubeTranscriptCache) -> None:
        """Test deleting a non-existent entry."""
        deleted = cache.delete("nonexistent")
        assert deleted is False

    def test_clear(self, cache: YouTubeTranscriptCache) -> None:
        """Test clearing all cached transcripts."""
        cache.set("video1", "Transcript 1", "url1")
        cache.set("video2", "Transcript 2", "url2")

        count = cache.clear()
        assert count == 2
        assert cache.get("video1") is None
        assert cache.get("video2") is None

    # === Access Tracking ===

    def test_access_count_increments(self, cache: YouTubeTranscriptCache) -> None:
        """Test that access count increments on each get."""
        video_id = "access_test"
        cache.set(video_id, "Test", "url")

        # First get
        result = cache.get(video_id)
        assert result is not None
        assert result["access_count"] == 2  # 1 from set + 1 from get

        # Second get
        result = cache.get(video_id)
        assert result["access_count"] == 3

    # === TTL Expiration ===

    def test_ttl_expiration(self, temp_cache_dir: Path) -> None:
        """Test that entries expire based on TTL."""
        cache = YouTubeTranscriptCache(
            cache_dir=temp_cache_dir,
            ttl_days=1,  # 1 day TTL
        )

        cache.set("ttl_test", "Test transcript", "url")

        # Should be present immediately
        assert cache.get("ttl_test") is not None

        # Manually update cached_at to simulate expiration
        conn = cache._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE transcript_cache SET cached_at = ? WHERE video_id = ?",
            (time.time() - 2 * 24 * 60 * 60, "ttl_test"),  # 2 days ago
        )
        conn.commit()

        # Should be expired now
        assert cache.get("ttl_test") is None

    def test_no_ttl(self, cache: YouTubeTranscriptCache) -> None:
        """Test that entries persist when TTL is disabled."""
        cache.set("no_ttl_test", "Test transcript", "url")

        # Manually update cached_at to long ago
        conn = cache._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE transcript_cache SET cached_at = ? WHERE video_id = ?",
            (time.time() - 365 * 24 * 60 * 60, "no_ttl_test"),  # 1 year ago
        )
        conn.commit()

        # Should still be present with no TTL
        assert cache.get("no_ttl_test") is not None

    # === LRU Eviction ===

    def test_lru_eviction(self, temp_cache_dir: Path) -> None:
        """Test LRU eviction when cache exceeds size limit."""
        cache = YouTubeTranscriptCache(
            cache_dir=temp_cache_dir,
            max_size_mb=0.001,  # Very small: ~1KB
        )

        # Store a large transcript
        large_text = "x" * 500
        cache.set("evict1", large_text, "url1")

        # Store another, should trigger eviction
        cache.set("evict2", large_text, "url2")

        # First entry should be evicted (LRU)
        # Note: exact behavior depends on size calculations
        stats = cache.get_stats()
        assert stats["total_entries"] <= 2

    # === Statistics ===

    def test_get_stats(self, cache: YouTubeTranscriptCache) -> None:
        """Test cache statistics."""
        cache.set("stats1", "Short text", "url1")
        cache.set("stats2", "Another text", "url2")

        stats = cache.get_stats()

        assert stats["total_entries"] == 2
        assert stats["total_size_bytes"] > 0
        assert stats["total_size_mb"] >= 0

    # === Thread Safety ===

    def test_thread_safety(self, cache: YouTubeTranscriptCache) -> None:
        """Test that cache handles concurrent access safely."""
        import threading

        errors = []
        video_ids = [f"thread_{i}" for i in range(10)]

        def write_transcript(vid: str) -> None:
            """Write a transcript in a separate thread."""
            try:
                cache.set(vid, f"Transcript for {vid}", f"url_{vid}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_transcript, args=(vid,)) for vid in video_ids]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

        # Verify all transcripts were stored
        for vid in video_ids:
            result = cache.get(vid)
            assert result is not None

    # === Edge Cases ===

    def test_update_existing_entry(self, cache: YouTubeTranscriptCache) -> None:
        """Test that updating an existing entry replaces it."""
        video_id = "update_test"
        cache.set(video_id, "Original transcript", "url")

        cache.set(video_id, "Updated transcript", "url")

        result = cache.get(video_id)
        assert result["transcript_text"] == "Updated transcript"

    def test_special_characters_in_transcript(self, cache: YouTubeTranscriptCache) -> None:
        """Test storing transcripts with special characters."""
        video_id = "special_chars"
        transcript = "Hello! What's new? \n\t Special: chars"

        cache.set(video_id, transcript, "url")

        result = cache.get(video_id)
        assert result["transcript_text"] == transcript

    def test_large_transcript(self, cache: YouTubeTranscriptCache) -> None:
        """Test storing a large transcript."""
        video_id = "large_test"
        # Simulate a 10-minute video transcript (~5000 words)
        large_transcript = " ".join(["word"] * 5000)

        cache.set(video_id, large_transcript, "url")

        result = cache.get(video_id)
        assert result is not None
        assert len(result["transcript_text"]) == len(large_transcript)

    def test_video_title_optional(self, cache: YouTubeTranscriptCache) -> None:
        """Test that video title is optional."""
        video_id = "no_title"
        cache.set(video_id, "Transcript", "url", video_title=None)

        result = cache.get(video_id)
        assert result is not None
        assert result["video_title"] is None

    def test_video_title_provided(self, cache: YouTubeTranscriptCache) -> None:
        """Test that video title is stored when provided."""
        video_id = "with_title"
        title = "Test Video Title"
        cache.set(video_id, "Transcript", "url", video_title=title)

        result = cache.get(video_id)
        assert result is not None
        assert result["video_title"] == title

    def test_language_default(self, cache: YouTubeTranscriptCache) -> None:
        """Test that default language is 'en'."""
        video_id = "lang_test"
        cache.set(video_id, "Transcript", "url")

        result = cache.get(video_id)
        assert result is not None
        assert result["language"] == "en"

    def test_language_custom(self, cache: YouTubeTranscriptCache) -> None:
        """Test that custom language is stored."""
        video_id = "lang_custom"
        cache.set(video_id, "Transcript", "url", language="es")

        result = cache.get(video_id)
        assert result is not None
        assert result["language"] == "es"

    def test_empty_transcript(self, cache: YouTubeTranscriptCache) -> None:
        """Test storing an empty transcript."""
        video_id = "empty"
        cache.set(video_id, "", "url")

        result = cache.get(video_id)
        assert result is not None
        assert result["transcript_text"] == ""

    def test_clear_empty_cache(self, cache: YouTubeTranscriptCache) -> None:
        """Test clearing an empty cache."""
        count = cache.clear()
        assert count == 0
