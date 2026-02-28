import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

load_dotenv()  # Load .env before reading environment variables

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"

Provider = Literal[
    "anthropic",
    "openai",
    "ollama",
    "azure_openai",
    "google_vertexai",
    "google_genai",
    "groq",
    "mistralai",
    "cohere",
    "bedrock",
    "huggingface",
]

# Default models for each provider
DEFAULT_MODELS: dict[Provider, str] = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2",
    "azure_openai": "gpt-4o-mini",
    "google_vertexai": "gemini-2.0-flash-exp",
    "google_genai": "gemini-2.0-flash-exp",
    "groq": "llama-3.3-70b-versatile",
    "mistralai": "mistral-large-latest",
    "cohere": "command-r-plus",
    "bedrock": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "huggingface": "meta-llama/Llama-3.2-3B-Instruct",
}


def detect_provider() -> Provider:
    """Detect which LLM provider to use based on available API keys.

    Returns:
        The detected provider name. Priority order:
        1. anthropic (ANTHROPIC_API_KEY)
        2. google_vertexai (GOOGLE_VERTEX_PROJECT_ID or GOOGLE_VERTEX_CREDENTIALS)
        3. google_genai (GOOGLE_API_KEY)
        4. azure_openai (AZURE_OPENAI_API_KEY)
        5. groq (GROQ_API_KEY)
        6. mistralai (MISTRAL_API_KEY)
        7. cohere (COHERE_API_KEY)
        8. bedrock (AWS_PROFILE or AWS_ACCESS_KEY_ID)
        9. huggingface (HUGGINGFACEHUB_API_TOKEN)
        10. ollama (OLLAMA_BASE_URL or localhost:11434)
        11. openai (OPENAI_API_KEY)
        12. openai (fallback)

    Note:
        Ollama is special as it runs locally without an API key.
        It's checked via OLLAMA_BASE_URL environment variable.
    """
    # Check in order of priority
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GOOGLE_VERTEX_PROJECT_ID") or os.getenv("GOOGLE_VERTEX_CREDENTIALS"):
        return "google_vertexai"
    if os.getenv("GOOGLE_API_KEY"):
        return "google_genai"
    if os.getenv("AZURE_OPENAI_API_KEY"):
        return "azure_openai"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("MISTRAL_API_KEY"):
        return "mistralai"
    if os.getenv("COHERE_API_KEY"):
        return "cohere"
    if os.getenv("AWS_PROFILE") or os.getenv("AWS_ACCESS_KEY_ID"):
        return "bedrock"
    if os.getenv("HUGGINGFACEHUB_API_TOKEN"):
        return "huggingface"
    if os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_ENABLED"):
        return "ollama"
    # Final fallback
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "openai"


def get_default_model() -> str:
    """Get the default model name based on available provider.

    Returns:
        Default model name for the detected provider. Can be overridden
        with environment variables like ANTHROPIC_MODEL_NAME, OPENAI_MODEL_NAME, etc.
    """
    provider = detect_provider()

    # Allow override via environment variables
    env_model_names = {
        "anthropic": os.getenv("ANTHROPIC_MODEL_NAME"),
        "openai": os.getenv("OPENAI_MODEL_NAME"),
        "ollama": os.getenv("OLLAMA_MODEL_NAME"),
        "azure_openai": os.getenv("AZURE_OPENAI_MODEL_NAME"),
        "google_vertexai": os.getenv("GOOGLE_VERTEX_MODEL_NAME"),
        "google_genai": os.getenv("GOOGLE_GENAI_MODEL_NAME"),
        "groq": os.getenv("GROQ_MODEL_NAME"),
        "mistralai": os.getenv("MISTRAL_MODEL_NAME"),
        "cohere": os.getenv("COHERE_MODEL_NAME"),
        "bedrock": os.getenv("BEDROCK_MODEL_NAME"),
        "huggingface": os.getenv("HUGGINGFACE_MODEL_NAME"),
    }

    if env_model_name := env_model_names.get(provider):
        return env_model_name

    return DEFAULT_MODELS.get(provider, "gpt-4o-mini")


# Legacy constant for backward compatibility
DEFAULT_MODEL = get_default_model()


def _create_model(model_name: str, temperature: float) -> Any:
    """Create the appropriate LLM model instance based on detected provider.

    Args:
        model_name: Name of the model to use.
        temperature: Temperature setting for the model.

    Returns:
        The appropriate Chat model instance for the detected provider.
    """
    provider = detect_provider()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model_name, temperature=temperature)  # type: ignore[call-arg]

    if provider == "ollama":
        from langchain_community.chat_models import ChatOllama

        return ChatOllama(
            model=model_name,
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )

    if provider == "azure_openai":
        from langchain_openai import AzureChatOpenAI
        from pydantic.types import SecretStr

        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        return AzureChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=SecretStr(api_key) if api_key else None,
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
        )

    if provider == "google_vertexai":
        from langchain_google_vertexai import ChatVertexAI

        return ChatVertexAI(model=model_name, temperature=temperature)

    if provider == "google_genai":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model_name, temperature=temperature)

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model_name, temperature=temperature)

    if provider == "mistralai":
        from langchain_mistralai import ChatMistralAI

        return ChatMistralAI(model_name=model_name, temperature=temperature)

    if provider == "cohere":
        from langchain_cohere import ChatCohere

        return ChatCohere(model=model_name, temperature=temperature)

    if provider == "bedrock":
        from langchain_aws import ChatBedrock

        # Set AWS region via environment variable if specified
        if bedrock_region := os.getenv("BEDROCK_REGION"):
            os.environ["AWS_DEFAULT_REGION"] = bedrock_region

        return ChatBedrock(model=model_name, temperature=temperature)

    if provider == "huggingface":
        from langchain_huggingface import ChatHuggingFace

        # HuggingFace ChatModel may not support temperature in all cases
        try:
            return ChatHuggingFace(model_id=model_name, temperature=temperature)
        except Exception:
            return ChatHuggingFace(model_id=model_name)

    # Default fallback to OpenAI
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model_name, temperature=temperature)
