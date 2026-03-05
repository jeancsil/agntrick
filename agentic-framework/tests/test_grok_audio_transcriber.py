"""Tests for Grok audio transcriber."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agentic_framework.core.grok_audio_transcriber import _AVAILABLE_MODELS, GroqAudioTranscriber


class TestGroqAudioTranscriberInit:
    """Tests for GroqAudioTranscriber initialization."""

    def test_init_with_explicit_api_key(self) -> None:
        """Test initialization with explicit API key."""
        transcriber = GroqAudioTranscriber(api_key="test-key")
        assert transcriber.api_key == "test-key"
        assert transcriber.is_configured

    def test_init_with_env_api_key(self) -> None:
        """Test initialization with API key from environment variable."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "env-key"}):
            transcriber = GroqAudioTranscriber()
            assert transcriber.api_key == "env-key"
            assert transcriber.is_configured

    def test_init_without_api_key(self) -> None:
        """Test initialization without API key."""
        # Remove from environment if present
        env = os.environ.copy()
        env.pop("GROQ_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            transcriber = GroqAudioTranscriber()
            assert transcriber.api_key is None
            assert not transcriber.is_configured

    def test_init_with_custom_model(self) -> None:
        """Test initialization with custom model."""
        transcriber = GroqAudioTranscriber(model="whisper-large-v3")
        assert transcriber.model == "whisper-large-v3"

    def test_init_with_default_model(self) -> None:
        """Test initialization with default model."""
        env = os.environ.copy()
        env.pop("GROQ_WHISPER_MODEL", None)
        with patch.dict(os.environ, env, clear=True):
            transcriber = GroqAudioTranscriber()
            assert transcriber.model == "whisper-large-v3-turbo"

    def test_init_with_model_from_env(self) -> None:
        """Test initialization with model from environment variable."""
        with patch.dict(os.environ, {"GROQ_WHISPER_MODEL": "whisper-large-v3"}):
            transcriber = GroqAudioTranscriber()
            assert transcriber.model == "whisper-large-v3"

    def test_create_default_factory(self) -> None:
        """Test the create_default factory method."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            transcriber = GroqAudioTranscriber.create_default()
            assert transcriber.api_key == "test-key"
            assert transcriber.is_configured

    def test_get_available_models(self) -> None:
        """Test getting available models."""
        transcriber = GroqAudioTranscriber()
        models = transcriber.get_available_models()
        assert models == _AVAILABLE_MODELS
        assert "whisper-large-v3" in models
        assert "whisper-large-v3-turbo" in models


class TestGroqAudioTranscriberValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_transcribe_empty_path(self) -> None:
        """Test handling when file path is empty."""
        transcriber = GroqAudioTranscriber(api_key="test-key")
        result = await transcriber.transcribe_audio("")

        assert result.startswith("Error:")
        assert "No audio file path" in result

    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self) -> None:
        """Test handling when audio file doesn't exist."""
        transcriber = GroqAudioTranscriber(api_key="test-key")
        result = await transcriber.transcribe_audio("/nonexistent/file.mp3")

        assert result.startswith("Error:")
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_transcribe_no_api_key(self) -> None:
        """Test handling when API key is not set."""
        env = os.environ.copy()
        env.pop("GROQ_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            transcriber = GroqAudioTranscriber()
            result = await transcriber.transcribe_audio(__file__)

        assert result.startswith("Error:")
        assert "GROQ_API_KEY" in result

    @pytest.mark.asyncio
    async def test_transcribe_large_file(self, tmp_path: Path) -> None:
        """Test handling when file size exceeds limit."""
        # Create a large file (simulated - just write enough bytes)
        large_file = tmp_path / "large.mp3"
        large_file.write_bytes(b"x" * (26 * 1024 * 1024))  # 26MB

        transcriber = GroqAudioTranscriber(api_key="test-key")
        result = await transcriber.transcribe_audio(str(large_file))

        assert result.startswith("Error:")
        assert "exceeds maximum allowed size" in result

        # Clean up
        large_file.unlink()


class TestGroqAudioTranscriberAPI:
    """Tests for Grok API interaction."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_transcribe_mp3_success(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test successful transcription of MP3 file."""
        # Create a mock MP3 file
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3\x00\x00\x00")

        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Hello, this is a test transcription"}
        mock_response.raise_for_status = MagicMock()

        # Create async mock for post
        async def mock_post(*args, **kwargs):
            return mock_response

        # Set up async context manager mock
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        transcriber = GroqAudioTranscriber(api_key="test-key")
        result = await transcriber.transcribe_audio(str(mp3_path))

        assert result == "Hello, this is a test transcription"

        # Clean up
        mp3_path.unlink()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_transcribe_with_custom_model(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test transcription with custom model."""
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Test"}
        mock_response.raise_for_status = MagicMock()

        async def mock_post(*args, **kwargs):
            return mock_response

        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        transcriber = GroqAudioTranscriber(api_key="test-key", model="whisper-large-v3")
        result = await transcriber.transcribe_audio(str(mp3_path))

        assert result == "Test"
        assert transcriber.model == "whisper-large-v3"

        mp3_path.unlink()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_transcribe_with_mime_type(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test transcription with explicit MIME type."""
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(b"RIFF\x00\x00\x00")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Test"}
        mock_response.raise_for_status = MagicMock()

        async def mock_post(*args, **kwargs):
            return mock_response

        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        transcriber = GroqAudioTranscriber(api_key="test-key")
        result = await transcriber.transcribe_audio(str(wav_path), mime_type="audio/wav")

        assert result == "Test"

        wav_path.unlink()


class TestGroqAudioTranscriberConversion:
    """Tests for audio format conversion."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("pydub.AudioSegment")
    async def test_convert_ogg_to_mp3_and_transcribe(
        self, mock_audio_segment: MagicMock, mock_client_class: MagicMock, tmp_path: Path
    ) -> None:
        """Test OGG to MP3 conversion followed by transcription."""
        # Create a mock OGG file
        ogg_path = tmp_path / "test.ogg"
        ogg_path.write_bytes(b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00")

        # Mock pydub conversion
        mock_audio = MagicMock()
        mock_audio.export = MagicMock()
        mock_audio_segment.from_file.return_value = mock_audio

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Converted and transcribed"}
        mock_response.raise_for_status = MagicMock()

        async def mock_post(*args, **kwargs):
            return mock_response

        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        transcriber = GroqAudioTranscriber(api_key="test-key")
        result = await transcriber.transcribe_audio(str(ogg_path))

        assert result == "Converted and transcribed"

        ogg_path.unlink()

    @pytest.mark.asyncio
    async def test_convert_unsupported_format_returns_error(self, tmp_path: Path) -> None:
        """Test that unsupported formats return error when pydub not available."""
        unsupported_path = tmp_path / "test.xyz"
        unsupported_path.write_bytes(b"fake audio data")

        # Mock pydub import error
        with patch.dict("sys.modules", {"pydub": None}):
            transcriber = GroqAudioTranscriber(api_key="test-key")
            result = await transcriber.transcribe_audio(str(unsupported_path))

        assert result.startswith("Error:")

        unsupported_path.unlink()


class TestGroqAudioTranscriberErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_api_http_error(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test handling when API returns HTTP error."""
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3")

        async def mock_post_error(*args, **kwargs):
            raise httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock(status_code=401))

        mock_client = MagicMock()
        mock_client.post = mock_post_error
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        transcriber = GroqAudioTranscriber(api_key="invalid-key")
        result = await transcriber.transcribe_audio(str(mp3_path))

        assert result.startswith("Error:")

        mp3_path.unlink()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_api_timeout(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test handling when API request times out."""
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3")

        async def mock_post_timeout(*args, **kwargs):
            raise httpx.TimeoutException("Request timed out")

        mock_client = MagicMock()
        mock_client.post = mock_post_timeout
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        transcriber = GroqAudioTranscriber(api_key="test-key", timeout=1.0)
        result = await transcriber.transcribe_audio(str(mp3_path))

        assert result.startswith("Error:")
        assert "timed out" in result.lower()

        mp3_path.unlink()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_network_error(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test handling when network error occurs."""
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3")

        async def mock_post_network(*args, **kwargs):
            raise httpx.RequestError("Network error")

        mock_client = MagicMock()
        mock_client.post = mock_post_network
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        transcriber = GroqAudioTranscriber(api_key="test-key")
        result = await transcriber.transcribe_audio(str(mp3_path))

        assert result.startswith("Error:")
        assert "Network" in result

        mp3_path.unlink()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_empty_transcription(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test handling when API returns empty transcription."""
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": ""}
        mock_response.raise_for_status = MagicMock()

        async def mock_post(*args, **kwargs):
            return mock_response

        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        transcriber = GroqAudioTranscriber(api_key="test-key")
        result = await transcriber.transcribe_audio(str(mp3_path))

        assert result.startswith("Error:")
        assert "Empty transcription" in result

        mp3_path.unlink()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_unexpected_response_format(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test handling when API returns unexpected response format."""
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "format"}
        mock_response.raise_for_status = MagicMock()

        async def mock_post(*args, **kwargs):
            return mock_response

        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        transcriber = GroqAudioTranscriber(api_key="test-key")
        result = await transcriber.transcribe_audio(str(mp3_path))

        assert result.startswith("Error:")
        assert "Unexpected API response format" in result

        mp3_path.unlink()
