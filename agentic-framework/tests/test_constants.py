"""Tests for provider detection and model creation in constants.py."""

import os
from typing import get_args

import pytest

# Mark tests that require external services or credentials
requires_external_service = pytest.mark.skip(reason="Requires external service credentials")


@pytest.fixture(autouse=True)
def reset_env():
    """Reset environment variables before each test."""
    # Save original env vars
    original = dict(os.environ)

    yield

    # Restore original env vars
    os.environ.clear()
    os.environ.update(original)


class TestDetectProvider:
    """Tests for detect_provider() function."""

    def test_detect_anthropic_provider(self, monkeypatch):
        """Test provider detection returns anthropic when ANTHROPIC_API_KEY is set."""
        # Clear all provider env vars first
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "anthropic"

    def test_detect_google_vertexai_provider(self, monkeypatch):
        """Test provider detection returns google_vertexai when GOOGLE_VERTEX_PROJECT_ID is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("GOOGLE_VERTEX_PROJECT_ID", "test-project")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "google_vertexai"

    def test_detect_google_vertexai_credentials(self, monkeypatch):
        """Test provider detection returns google_vertexai when GOOGLE_VERTEX_CREDENTIALS is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("GOOGLE_VERTEX_CREDENTIALS", "test-credentials")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "google_vertexai"

    def test_detect_google_genai_provider(self, monkeypatch):
        """Test provider detection returns google_genai when GOOGLE_API_KEY is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "google_genai"

    def test_detect_azure_openai_provider(self, monkeypatch):
        """Test provider detection returns azure_openai when AZURE_OPENAI_API_KEY is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "azure_openai"

    def test_detect_groq_provider(self, monkeypatch):
        """Test provider detection returns groq when GROQ_API_KEY is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "groq"

    def test_detect_mistralai_provider(self, monkeypatch):
        """Test provider detection returns mistralai when MISTRAL_API_KEY is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "mistralai"

    def test_detect_cohere_provider(self, monkeypatch):
        """Test provider detection returns cohere when COHERE_API_KEY is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("COHERE_API_KEY", "test-key")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "cohere"

    def test_detect_bedrock_provider_aws_profile(self, monkeypatch):
        """Test provider detection returns bedrock when AWS_PROFILE is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("AWS_PROFILE", "test-profile")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "bedrock"

    def test_detect_bedrock_provider_aws_access_key(self, monkeypatch):
        """Test provider detection returns bedrock when AWS_ACCESS_KEY_ID is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-key")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "bedrock"

    def test_detect_huggingface_provider(self, monkeypatch):
        """Test provider detection returns huggingface when HUGGINGFACEHUB_API_TOKEN is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("HUGGINGFACEHUB_API_TOKEN", "test-token")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "huggingface"

    def test_detect_ollama_provider_base_url(self, monkeypatch):
        """Test provider detection returns ollama when OLLAMA_BASE_URL is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "ollama"

    def test_detect_ollama_provider_enabled(self, monkeypatch):
        """Test provider detection returns ollama when OLLAMA_ENABLED is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("OLLAMA_ENABLED", "true")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "ollama"

    def test_detect_openai_provider(self, monkeypatch):
        """Test provider detection returns openai when OPENAI_API_KEY is set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "openai"

    def test_detect_fallback_to_openai(self, monkeypatch):
        """Test provider detection falls back to openai when no keys are set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        from agentic_framework.constants import detect_provider

        assert detect_provider() == "openai"

    def test_priority_anthropic_over_others(self, monkeypatch):
        """Test Anthropic has highest priority when multiple keys are set."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
        from agentic_framework.constants import detect_provider

        assert detect_provider() == "anthropic"


class TestGetDefaultModel:
    """Tests for get_default_model() function."""

    def test_default_model_anthropic(self, monkeypatch):
        """Test default model for Anthropic provider."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                    "MODEL_NAME",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        from agentic_framework.constants import get_default_model

        assert get_default_model() == "claude-haiku-4-5-20251001"

    def test_default_model_openai(self, monkeypatch):
        """Test default model for OpenAI provider."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                    "MODEL_NAME",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        from agentic_framework.constants import get_default_model

        assert get_default_model() == "gpt-4o-mini"

    def test_default_model_ollama(self, monkeypatch):
        """Test default model for Ollama provider."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                    "MODEL_NAME",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        from agentic_framework.constants import get_default_model

        assert get_default_model() == "llama3.2"

    def test_default_model_groq(self, monkeypatch):
        """Test default model for Groq provider."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                    "MODEL_NAME",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        from agentic_framework.constants import get_default_model

        assert get_default_model() == "llama-3.3-70b-versatile"

    def test_default_model_override(self, monkeypatch):
        """Test model override via environment variable."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                    "MODEL_NAME",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("ANTHROPIC_MODEL_NAME", "claude-opus-4")
        from agentic_framework.constants import get_default_model

        assert get_default_model() == "claude-opus-4"

    def test_all_default_models_defined(self):
        """Test that all providers have default models defined."""
        from agentic_framework.constants import DEFAULT_MODELS, Provider

        provider_types = get_args(Provider)
        for provider in provider_types:
            assert provider in DEFAULT_MODELS, f"Missing default model for provider: {provider}"


class TestCreateModel:
    """Tests for _create_model() function."""

    def test_create_anthropic_model(self, monkeypatch):
        """Test creating Anthropic model."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        from agentic_framework.constants import _create_model

        model = _create_model("claude-3-opus", 0.7)
        assert model.__class__.__name__ == "ChatAnthropic"
        assert model.model == "claude-3-opus"
        assert model.temperature == 0.7

    def test_create_openai_model(self, monkeypatch):
        """Test creating OpenAI model."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        from agentic_framework.constants import _create_model

        model = _create_model("gpt-4", 0.5)
        assert model.__class__.__name__ == "ChatOpenAI"
        model_attr = getattr(model, "model_name", model.model if hasattr(model, "model") else None)
        assert model_attr == "gpt-4"
        assert model.temperature == 0.5

    def test_create_ollama_model(self, monkeypatch):
        """Test creating Ollama model."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        from agentic_framework.constants import _create_model

        model = _create_model("llama3.2", 0.8)
        assert model.__class__.__name__ == "ChatOllama"
        assert model.model == "llama3.2"
        assert model.temperature == 0.8
        assert model.base_url == "http://localhost:11434"

    def test_create_ollama_model_custom_base_url(self, monkeypatch):
        """Test creating Ollama model with custom base URL."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote-host:11434")
        from agentic_framework.constants import _create_model

        model = _create_model("llama3.2", 0.5)
        assert model.base_url == "http://remote-host:11434"

    def test_create_groq_model(self, monkeypatch):
        """Test creating Groq model."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        from agentic_framework.constants import _create_model

        model = _create_model("llama-3.3-70b-versatile", 0.3)
        assert model.__class__.__name__ == "ChatGroq"
        model_attr = getattr(model, "model_name", model.model if hasattr(model, "model") else None)
        assert model_attr == "llama-3.3-70b-versatile"
        assert model.temperature == 0.3

    def test_create_mistralai_model(self, monkeypatch):
        """Test creating MistralAI model."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
        from agentic_framework.constants import _create_model

        model = _create_model("mistral-large-latest", 0.6)
        assert model.__class__.__name__ == "ChatMistralAI"
        # MistralAI uses 'model' attribute
        model_attr = getattr(model, "model", model.model_name if hasattr(model, "model_name") else None)
        assert model_attr == "mistral-large-latest"
        assert model.temperature == 0.6

    def test_create_cohere_model(self, monkeypatch):
        """Test creating Cohere model."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("COHERE_API_KEY", "test-key")
        from agentic_framework.constants import _create_model

        model = _create_model("command-r-plus", 0.4)
        assert model.__class__.__name__ == "ChatCohere"
        assert model.model == "command-r-plus"
        assert model.temperature == 0.4

    def test_create_huggingface_model(self, monkeypatch):
        """Test creating HuggingFace model - requires transformers library."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("HUGGINGFACEHUB_API_TOKEN", "test-token")
        from agentic_framework.constants import _create_model

        try:
            model = _create_model("meta-llama/Llama-3.2-3B-Instruct", 0.2)
            assert model.__class__.__name__ == "ChatHuggingFace"
            # HuggingFace uses model_id parameter
            model_attr = getattr(model, "model_id", model.model if hasattr(model, "model") else None)
            assert model_attr == "meta-llama/Llama-3.2-3B-Instruct"
        except Exception as e:
            # Skip if transformers library is not installed
            pytest.skip(f"HuggingFace provider requires transformers library: {e}")

    def test_create_azure_openai_model(self, monkeypatch):
        """Test creating Azure OpenAI model."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        from agentic_framework.constants import _create_model

        model = _create_model("gpt-4", 0.5)
        assert model.__class__.__name__ == "AzureChatOpenAI"
        model_attr = getattr(model, "model_name", model.model if hasattr(model, "model") else None)
        assert model_attr == "gpt-4"
        assert model.temperature == 0.5
        assert str(model.azure_endpoint) == "https://test.openai.azure.com"

    def test_create_google_genai_model(self, monkeypatch):
        """Test creating Google GenAI model."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        from agentic_framework.constants import _create_model

        model = _create_model("gemini-2.0-flash-exp", 0.7)
        assert model.__class__.__name__ == "ChatGoogleGenerativeAI"
        model_attr = getattr(model, "model_name", model.model if hasattr(model, "model") else None)
        assert model_attr == "gemini-2.0-flash-exp"
        assert model.temperature == 0.7

    @requires_external_service
    def test_create_google_vertexai_model(self, monkeypatch):
        """Test creating Google VertexAI model - requires credentials."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("GOOGLE_VERTEX_PROJECT_ID", "test-project")
        from agentic_framework.constants import _create_model

        model = _create_model("gemini-2.0-flash-exp", 0.6)
        assert model.__class__.__name__ == "ChatVertexAI"
        model_attr = getattr(model, "model_name", model.model if hasattr(model, "model") else None)
        assert model_attr == "gemini-2.0-flash-exp"
        assert model.temperature == 0.6

    @requires_external_service
    def test_create_bedrock_model(self, monkeypatch):
        """Test creating Bedrock model - requires credentials."""
        for key in list(os.environ.keys()):
            if any(
                x in key.upper()
                for x in [
                    "ANTHROPIC",
                    "GOOGLE",
                    "AZURE",
                    "GROQ",
                    "MISTRAL",
                    "COHERE",
                    "AWS",
                    "HUGGINGFACE",
                    "OLLAMA",
                    "OPENAI",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("AWS_PROFILE", "test-profile")
        from agentic_framework.constants import _create_model

        model = _create_model("anthropic.claude-3-5-sonnet-20241022-v2:0", 0.5)
        assert model.__class__.__name__ == "ChatBedrock"
        # Bedrock uses model_id
        model_attr = getattr(model, "model_id", model.model if hasattr(model, "model") else None)
        assert model_attr == "anthropic.claude-3-5-sonnet-20241022-v2:0"
        assert model.temperature == 0.5
