"""Audio transcriber agent using GLM-ASR-2512 API."""

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence

import httpx

from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry
from agentic_framework.tools.audio_transcriber import AudioTranscriberTool

logger = logging.getLogger(__name__)


@AgentRegistry.register("audio-transcriber")
class AudioTranscriberAgent(LangGraphMCPAgent):
    """Agent that transcribes audio using GLM-ASR-2512 API.

    This agent provides audio transcription capabilities using the GLM-ASR-2512
    API from Z.AI. It supports .wav and .mp3 files with a maximum size of
    25MB and duration of 30 seconds.

    Environment Variables:
        ZAI_API_KEY: Required API key for authentication with GLM-ASR API.

    Usage:
        >>> from agentic_framework.core.audio_transcriber_agent import AudioTranscriberAgent
        >>> agent = AudioTranscriberAgent()
        >>> transcription = await agent.transcribe_audio("/path/to/audio.mp3", "audio/mpeg")
        >>> print(transcription)
    """

    @property
    def system_prompt(self) -> str:
        """System prompt for the audio transcriber agent."""
        return (
            "You are an audio transcription assistant. "
            "Transcribe the given audio file accurately and concisely. "
            "Return only the transcribed text without additional commentary."
        )

    def local_tools(self) -> Sequence[Any]:
        """Return local tools for audio transcription."""
        return [AudioTranscriberTool()]

    # Supported formats by GLM-ASR API
    _SUPPORTED_FORMATS = {".wav", ".mp3"}

    def _convert_to_mp3(self, audio_path: Path) -> Path | None:
        """Convert audio file to MP3 format using pydub.

        Args:
            audio_path: Path to the audio file to convert.

        Returns:
            Path to the converted MP3 file, or None if conversion fails.
        """
        try:
            from pydub import AudioSegment  # type: ignore[import-untyped]

            logger.info(f"Converting {audio_path.suffix} to MP3 format...")
            audio = AudioSegment.from_file(str(audio_path))

            # Create temp MP3 file
            temp_mp3 = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_mp3.close()

            audio.export(temp_mp3.name, format="mp3")
            logger.info(f"Converted to MP3: {temp_mp3.name}")
            return Path(temp_mp3.name)

        except ImportError:
            logger.error("pydub not installed - cannot convert audio format")
            return None
        except Exception as e:
            logger.error(f"Failed to convert audio: {e}")
            return None

    async def transcribe_audio(self, audio_path: str, mime_type: str | None = None) -> str:
        """Transcribe audio file using GLM-ASR-2512 API.

        Args:
            audio_path: Path to the audio file to transcribe.
            mime_type: Optional MIME type of the audio file. If not provided,
                      it will be inferred from the file extension.

        Returns:
            Transcription text or error message as string.
        """
        # Validate input
        if not audio_path:
            return "Error: No audio file path provided."

        path = Path(audio_path)

        if not path.exists():
            return f"Error: Audio file '{audio_path}' not found."

        # Get API key
        api_key = os.environ.get("ZAI_API_KEY")
        if not api_key:
            return "Error: ZAI_API_KEY environment variable is not set."

        # Check if format is supported, convert if needed
        converted_path = None

        if path.suffix.lower() not in self._SUPPORTED_FORMATS:
            logger.info(f"Audio format {path.suffix} not supported, converting to MP3...")
            converted_path = self._convert_to_mp3(path)
            if converted_path is None:
                formats_str = ", ".join(sorted(self._SUPPORTED_FORMATS))
                return f"Error: Cannot convert {path.suffix} format. Supported formats: {formats_str}"
            path = converted_path
            mime_type = "audio/mpeg"

        # Infer mime type if not provided
        if mime_type is None:
            ext = path.suffix.lower()
            mime_types = {
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
            }
            mime_type = mime_types.get(ext, f"audio/{ext[1:]}")

        try:
            # Read audio file
            with path.open("rb") as f:
                audio_data = f.read()

            # Get model from environment or use default
            model = os.environ.get("ZAI_ASR_MODEL", "GLM-ASR-2512")

            # Prepare request with model parameter (REQUIRED by API)
            files = {"file": (path.name, audio_data, mime_type)}
            data = {"model": model}
            headers = {"Authorization": f"Bearer {api_key}"}

            logger.debug(f"Sending transcription request: model={model}, file={path.name}")

            # Send to GLM-ASR API
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.z.ai/api/paas/v4/audio/transcriptions",
                    files=files,
                    data=data,
                    headers=headers,
                )

                logger.debug(f"API response status: {response.status_code}")

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
