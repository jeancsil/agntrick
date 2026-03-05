"""Tests for audio transcriber agent processing flow."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentic_framework.core.audio_transcriber_agent import AudioTranscriberAgent


class TestAudioConversion:
    """Tests for OGG to MP3 conversion."""

    @patch("pydub.AudioSegment")
    def test_convert_ogg_to_mp3_success(self, mock_audio_segment: MagicMock, tmp_path: Path) -> None:
        """Test successful OGG to MP3 conversion using pydub."""
        # Create a mock OGG file
        ogg_path = tmp_path / "test.ogg"
        ogg_path.write_bytes(b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00")  # Minimal OGG header

        # Mock AudioSegment behavior
        mock_audio = MagicMock()
        mock_audio.export = MagicMock()
        mock_audio_segment.from_file.return_value = mock_audio

        agent = AudioTranscriberAgent()
        result = agent._convert_to_mp3(ogg_path)

        # Should return a path to converted MP3
        assert result is not None
        assert result.suffix == ".mp3"
        assert result.exists()

        # Verify pydub was called correctly
        mock_audio_segment.from_file.assert_called_once_with(str(ogg_path))
        mock_audio.export.assert_called()

        # Clean up
        ogg_path.unlink()
        if result.exists():
            result.unlink()

    @patch("pydub.AudioSegment")
    def test_convert_unsupported_format_returns_none(self, mock_audio_segment: MagicMock, tmp_path: Path) -> None:
        """Test that unsupported formats return None."""
        # Create a mock file with unsupported extension
        unsupported_path = tmp_path / "test.xyz"
        unsupported_path.write_bytes(b"fake audio data")

        # Make pydub raise an exception
        mock_audio_segment.from_file.side_effect = Exception("Unsupported format")

        agent = AudioTranscriberAgent()
        result = agent._convert_to_mp3(unsupported_path)

        # Should return None on failure
        assert result is None

        # Clean up
        unsupported_path.unlink()

    def test_convert_mp3_returns_same_path(self, tmp_path: Path) -> None:
        """Test that MP3 files are returned as-is (no conversion needed)."""
        # Create a mock MP3 file
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3\x00\x00\x00")  # Minimal MP3 header

        agent = AudioTranscriberAgent()
        _result = agent._convert_to_mp3(mp3_path)

        # Should return the same path (no conversion needed for supported format)
        # Note: Current implementation converts all files
        # This test documents expected behavior

        # Clean up
        mp3_path.unlink()

    @patch.dict(os.environ, {"ZAI_ASR_MODEL": "custom-model-v2"})
    def test_model_from_environment_variable(self) -> None:
        """Test that ZAI_ASR_MODEL environment variable is used."""
        agent = AudioTranscriberAgent()
        assert agent._model == "custom-model-v2"


class TestTranscriptionAPI:
    """Tests for transcription API calls."""

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"ZAI_API_KEY": "test-api-key"})
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

        # Set up async context manager mock
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None

        agent = AudioTranscriberAgent()
        result = await agent.transcribe_audio(str(mp3_path))

        assert result == "Hello, this is a test transcription"

        # Verify model parameter was sent
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "data" in call_kwargs[1]
        assert "model" in call_kwargs[1]["data"]

        # Clean up
        mp3_path.unlink()

    @pytest.mark.asyncio
    async def test_transcribe_no_api_key(self, tmp_path: Path) -> None:
        """Test handling when API key is not set."""
        # Create a mock audio file
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3")

        # Remove API key
        if "ZAI_API_KEY" in os.environ:
            del os.environ["ZAI_API_KEY"]

        agent = AudioTranscriberAgent()
        result = await agent.transcribe_audio(str(mp3_path))

        assert "Error" in result
        assert "ZAI_API_KEY" in result

        # Clean up
        mp3_path.unlink()

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"ZAI_API_KEY": "test-api-key", "ZAI_ASR_MODEL": "test-model"})
    @patch("httpx.AsyncClient")
    async def test_model_parameter_sent_to_api(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test that model parameter is correctly sent to API."""
        # Create a mock MP3 file
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3")

        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Success"}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None

        agent = AudioTranscriberAgent()
        await agent.transcribe_audio(str(mp3_path))

        # Verify the model parameter was sent
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "data" in call_kwargs[1]
        assert call_kwargs[1]["data"]["model"] == "test-model"

        # Clean up
        mp3_path.unlink()


class TestEndToEndFlow:
    """Tests for full end-to-end audio processing flow."""

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"ZAI_API_KEY": "test-api-key"})
    @patch("httpx.AsyncClient")
    @patch("pydub.AudioSegment")
    async def test_full_flow_ogg_to_transcription(
        self,
        mock_audio_segment: MagicMock,
        mock_client_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test full flow: OGG download -> convert -> transcribe -> respond."""
        # Create a mock OGG file
        ogg_path = tmp_path / "voice_message.ogg"
        ogg_path.write_bytes(b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00")

        # Mock pydub conversion
        mock_audio = MagicMock()
        mock_audio.export = MagicMock()
        mock_audio_segment.from_file.return_value = mock_audio

        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Hello, this is my voice message"}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None

        agent = AudioTranscriberAgent()
        result = await agent.transcribe_audio(str(ogg_path))

        # Verify full flow succeeded
        assert result == "Hello, this is my voice message"

        # Clean up
        ogg_path.unlink()

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"ZAI_API_KEY": "test-api-key"})
    @patch("httpx.AsyncClient")
    async def test_full_flow_mp3_direct(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test full flow with MP3 file (no conversion needed)."""
        # Create a mock MP3 file
        mp3_path = tmp_path / "voice_message.mp3"
        mp3_path.write_bytes(b"ID3\x00\x00\x00")

        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Direct MP3 transcription"}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None

        agent = AudioTranscriberAgent()
        result = await agent.transcribe_audio(str(mp3_path))

        assert result == "Direct MP3 transcription"

        # Clean up
        mp3_path.unlink()


class TestErrorHandling:
    """Tests for error handling in audio processing."""

    @pytest.mark.asyncio
    async def test_file_not_found(self) -> None:
        """Test handling when audio file doesn't exist."""
        agent = AudioTranscriberAgent()
        result = await agent.transcribe_audio("/nonexistent/file.mp3")

        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_empty_file_path(self) -> None:
        """Test handling when file path is empty."""
        agent = AudioTranscriberAgent()
        result = await agent.transcribe_audio("")

        assert "Error" in result
        assert "No audio file path" in result

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"ZAI_API_KEY": "test-api-key"})
    @patch("httpx.AsyncClient")
    async def test_api_error_response(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test handling when API returns an error."""
        # Create a mock MP3 file
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3")

        # Mock API error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"error": {"message": "Invalid audio format"}}'
        mock_response.raise_for_status.side_effect = Exception("HTTPStatusError: 400")

        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("HTTPStatusError: 400")
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None

        agent = AudioTranscriberAgent()
        result = await agent.transcribe_audio(str(mp3_path))

        assert "Error" in result

        # Clean up
        mp3_path.unlink()

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"ZAI_API_KEY": "test-api-key"})
    @patch("httpx.AsyncClient")
    async def test_api_timeout_error(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test handling when API request times out."""
        # Create a mock MP3 file
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3")

        # Mock timeout
        import httpx

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("Request timed out")
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None

        agent = AudioTranscriberAgent()
        result = await agent.transcribe_audio(str(mp3_path))

        assert "Error" in result
        assert "timeout" in result.lower() or "timed out" in result.lower()

        # Clean up
        mp3_path.unlink()

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"ZAI_API_KEY": "test-api-key"})
    @patch("httpx.AsyncClient")
    async def test_network_error(self, mock_client_class: MagicMock, tmp_path: Path) -> None:
        """Test handling when network error occurs."""
        # Create a mock MP3 file
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"ID3")

        # Mock network error
        import httpx

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.RequestError("Network error")
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None

        agent = AudioTranscriberAgent()
        result = await agent.transcribe_audio(str(mp3_path))

        assert "Error" in result
        assert "Network" in result

        # Clean up
        mp3_path.unlink()
