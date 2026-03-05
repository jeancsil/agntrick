"""Groq audio transcriber using Groq API with Whisper models.

This module provides a standalone agent for transcribing audio using Groq's
OpenAI-compatible API. It supports whisper-large-v3 and whisper-large-v3-turbo
models.

Environment Variables:
    GROQ_API_KEY: Required API key for Groq authentication.
    GROQ_WHISPER_MODEL: Optional model name (default: whisper-large-v3-turbo).

Usage:
    >>> from agentic_framework.core.grok_audio_transcriber import GroqAudioTranscriber
    >>> transcriber = GroqAudioTranscriber()
    >>> transcription = await transcriber.transcribe_audio("/path/to/audio.mp3")
    >>> print(transcription)

Troubleshooting:
    - "GROQ_API_KEY not set": Set the environment variable with your Groq API key.
    - "exceeds maximum allowed size": Audio file is larger than 25MB limit.
    - "Cannot convert format": Install pydub: `uv add pydub` (requires ffmpeg).

Performance:
    - whisper-large-v3-turbo: ~30-50ms transcription time for 30s audio
    - whisper-large-v3: ~100-150ms transcription time for 30s audio
    - File size impact: Smaller files (compressed) upload faster but may lose some quality.
"""

import logging
import os
from pathlib import Path
from typing import Final

import httpx

logger = logging.getLogger(__name__)

# Supported audio formats for Whisper
_SUPPORTED_FORMATS: Final = {".wav", ".mp3", ".ogg", ".oga", ".m4a", ".webm", ".flac", ".wma"}

# Available Whisper models on Groq
_AVAILABLE_MODELS: Final = {
    "whisper-large-v3",
    "whisper-large-v3-turbo",
}

# Default model (turbo is faster and more cost-effective)
_DEFAULT_MODEL: Final = "whisper-large-v3-turbo"

# Groq API endpoint for audio transcription
_API_URL: Final = "https://api.groq.com/openai/v1/audio/transcriptions"

# Maximum file size (Groq limit: 25MB)
_MAX_SIZE_MB: Final = 25

# MP3 bitrate for conversion (128k = good balance of quality and file size)
_MP3_BITRATE: Final = "128k"


class GroqAudioTranscriber:
    """Standalone audio transcriber using Groq API.

    This class provides audio transcription capabilities using Groq's OpenAI-compatible
    API with Whisper models. It supports common audio formats and handles conversion
    of unsupported formats using pydub.

    The transcriber returns error messages as strings instead of raising exceptions,
    making it easy to handle errors in calling code.

    Example:
        >>> transcriber = GroqAudioTranscriber()
        >>> transcription = await transcriber.transcribe_audio("voice_message.ogg")
        >>> if transcription.startswith("Error:"):
        ...     print(f"Failed: {transcription}")
        ... else:
        ...     print(f"Transcription: {transcription}")
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        """Initialize the Groq audio transcriber.

        Args:
            api_key: Optional API key. If not provided, uses GROQ_API_KEY env var.
            model: Optional model name. If not provided, uses GROQ_WHISPER_MODEL
                  env var or defaults to whisper-large-v3-turbo.
            timeout: Request timeout in seconds (default: 60.0).
        """
        self._api_key = api_key or os.environ.get("GROQ_API_KEY")
        self._model = model or os.environ.get("GROQ_WHISPER_MODEL", _DEFAULT_MODEL)
        self._timeout = timeout

        if not self._api_key:
            logger.warning("GROQ_API_KEY not set - transcriptions will fail")

        if self._model not in _AVAILABLE_MODELS:
            logger.warning(
                f"Model '{self._model}' not in available models. Available: {', '.join(sorted(_AVAILABLE_MODELS))}"
            )

    @property
    def api_key(self) -> str | None:
        """Get the API key."""
        return self._api_key

    @property
    def model(self) -> str:
        """Get the model name."""
        return self._model

    @property
    def is_configured(self) -> bool:
        """Check if the transcriber is properly configured with an API key."""
        return bool(self._api_key)

    def _validate_path(self, audio_path: str) -> Path | None:
        """Validate and sanitize the audio file path.

        This method performs security checks on the input path to prevent
        path traversal attacks. For trusted contexts like WhatsApp, basic
        validation is sufficient.

        Args:
            audio_path: The audio file path to validate.

        Returns:
            Validated Path object, or None if validation fails.
        """
        path = Path(audio_path)

        # Resolve absolute path to prevent path traversal
        try:
            resolved_path = path.resolve(strict=True)
        except (FileNotFoundError, RuntimeError):
            # FileNotFoundError: path doesn't exist
            # RuntimeError: cyclic symbolic link
            return None

        # Check if it's a regular file (not a directory or special file)
        if not resolved_path.is_file():
            logger.warning(f"Path is not a regular file: {resolved_path}")
            return None

        return resolved_path

    def _convert_to_mp3(self, audio_path: Path) -> Path | None:
        """Convert audio file to MP3 format using pydub.

        This method converts unsupported audio formats to MP3 for compatibility
        with the Whisper API. The conversion is performed in a temporary file.

        Args:
            audio_path: Path to the audio file to convert.

        Returns:
            Path to the converted MP3 file, or None if conversion fails.
        """
        try:
            from pydub import AudioSegment  # type: ignore[import-untyped]

            logger.info(f"Converting {audio_path.suffix} to MP3 format...")
            audio = AudioSegment.from_file(str(audio_path))

            # Use mkstemp instead of NamedTemporaryFile to avoid race condition
            # The file is created, written, and only then accessible
            import tempfile as tf

            fd, temp_path = tf.mkstemp(suffix=".mp3", text=False)
            try:
                audio.export(temp_path, format="mp3", bitrate=_MP3_BITRATE)
                logger.info(f"Converted to MP3: {temp_path}")
                return Path(temp_path)
            finally:
                # Close the file descriptor but keep the file
                import os as os_module

                os_module.close(fd)

        except ImportError:
            logger.error("pydub not installed - cannot convert audio format")
            return None
        except Exception as e:
            logger.error(f"Failed to convert audio: {e}")
            return None

    async def transcribe_audio(
        self,
        audio_path: str,
        mime_type: str | None = None,
    ) -> str:
        """Transcribe audio file using Groq API.

        This method transcribes an audio file using Groq's Whisper API.
        If the file format is not supported by the API, it will be converted
        to MP3 automatically.

        Args:
            audio_path: Path to the audio file to transcribe.
            mime_type: Optional MIME type of the audio file. If not provided,
                      it will be inferred from the file extension.

        Returns:
            Transcription text or error message as string. Error messages
            always start with "Error:" prefix for easy identification.
        """
        # Validate input
        if not audio_path:
            return "Error: No audio file path provided."

        # Validate and sanitize path (security: prevent path traversal)
        path = self._validate_path(audio_path)
        if path is None:
            return f"Error: Audio file '{audio_path}' not found."

        # Check API key
        if not self._api_key:
            return "Error: GROQ_API_KEY environment variable is not set."

        # Check if format is supported, convert if needed
        converted_path = None

        if path.suffix.lower() not in _SUPPORTED_FORMATS:
            logger.info(f"Audio format {path.suffix} not supported, converting to MP3...")
            converted_path = self._convert_to_mp3(path)
            if converted_path is None:
                formats_str = ", ".join(sorted(_SUPPORTED_FORMATS))
                return f"Error: Cannot convert {path.suffix} format. Supported formats: {formats_str}"
            path = converted_path
            mime_type = "audio/mpeg"

        # Validate file size
        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > _MAX_SIZE_MB:
            return f"Error: Audio file size ({file_size_mb:.1f}MB) exceeds maximum allowed size ({_MAX_SIZE_MB}MB)."

        # Infer mime type if not provided
        if mime_type is None:
            ext = path.suffix.lower()
            mime_types = {
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
                ".ogg": "audio/ogg",
                ".oga": "audio/ogg",
                ".m4a": "audio/mp4",
                ".webm": "audio/webm",
                ".flac": "audio/flac",
                ".wma": "audio/wma",
            }
            mime_type = mime_types.get(ext, f"audio/{ext[1:]}")

        try:
            # Read audio file
            with path.open("rb") as f:
                audio_data = f.read()

            # Prepare request (OpenAI-compatible format)
            files = {"file": (path.name, audio_data, mime_type)}
            data = {
                "model": self._model,
                "response_format": "json",
            }
            headers = {"Authorization": f"Bearer {self._api_key}"}

            logger.debug(
                f"Sending transcription request: model={self._model}, file={path.name}, size={len(audio_data)} bytes"
            )

            # Send to Groq API
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    _API_URL,
                    files=files,
                    data=data,
                    headers=headers,
                )

                logger.debug(f"API response status: {response.status_code}")
                logger.debug(f"API response body: {response.text[:500]}")

                response.raise_for_status()

                # Parse response
                result = response.json()

                # Check for text field in response
                if "text" in result:
                    transcription = result["text"]
                    if transcription:
                        return str(transcription)
                    return "Error: Empty transcription received."
                else:
                    return f"Error: Unexpected API response format: {result}"

        except httpx.HTTPStatusError as e:
            return f"Error: API request failed with status {e.response.status_code}: {e.response.text}"
        except httpx.TimeoutException:
            return "Error: API request timed out."
        except httpx.RequestError as e:
            return f"Error: Network error during API request: {e}"
        except Exception as e:
            return f"Error: Failed to transcribe audio: {e}"
        finally:
            # Clean up converted temp file
            if converted_path and converted_path.exists():
                try:
                    converted_path.unlink()
                    logger.debug(f"Cleaned up temp file: {converted_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file: {e}")

    def get_available_models(self) -> set[str]:
        """Get the set of available Whisper models on Groq.

        Returns:
            Set of available model names.
        """
        return _AVAILABLE_MODELS.copy()

    @classmethod
    def create_default(cls) -> "GroqAudioTranscriber":
        """Create a transcriber with default configuration.

        This is a convenience method for creating a transcriber with
        environment variable configuration.

        Returns:
            A new GroqAudioTranscriber instance with default configuration.
        """
        return cls()
