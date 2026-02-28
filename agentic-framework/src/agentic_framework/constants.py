import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()  # Load .env before reading environment variables

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"

Provider = Literal["openai", "anthropic"]


def detect_provider() -> Provider:
    """Detect which LLM provider to use based on available API keys.

    Returns:
        "anthropic" if ANTHROPIC_API_KEY is set, "openai" otherwise.

    Note:
        OpenAI is the default fallback when ANTHROPIC_API_KEY is absent.
        When both keys are available, Anthropic takes precedence.
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "openai"


def get_default_model() -> str:
    """Get the default model name based on available provider.

    Returns:
        Default model name for the detected provider.

    Examples:
        - Anthropic: "claude-haiku-4-5-20251001"
        - OpenAI: "gpt-4o-mini"
    """
    provider = detect_provider()
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_MODEL_NAME", "claude-haiku-4-5-20251001")
    return os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")


# Legacy constant for backward compatibility
DEFAULT_MODEL = get_default_model()
