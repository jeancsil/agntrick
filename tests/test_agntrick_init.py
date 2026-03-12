"""Tests for agntrick package - __init__ module (public API)."""

from agntrick import (
    AgentBase,
    AgentNotFoundError,
    AgentRegistry,
    AgntrickConfig,
    ConfigurationError,
    PromptNotFoundError,
    __version__,
    detect_provider,
    get_config,
    get_default_model,
)


def test_agntrick_version():
    """Test package version."""
    assert __version__ == "0.2.7"


def test_agntrick_imports():
    """Test that all public API exports are available."""
    # Core classes
    assert AgentBase is not None
    assert AgentRegistry is not None

    # Configuration
    assert AgntrickConfig is not None
    assert get_config is not None

    # LLM
    assert detect_provider is not None
    assert get_default_model is not None

    # Exceptions
    assert AgentNotFoundError is not None
    assert ConfigurationError is not None
    assert PromptNotFoundError is not None


def test_agntrick_agent_registry_available():
    """Test that AgentRegistry is functional from top-level import."""
    # Clean up first
    AgentRegistry._registry.pop("api-test-agent", None)
    AgentRegistry._mcp_servers.pop("api-test-agent", None)

    from agntrick.interfaces.base import Agent

    class TestAgent(Agent):
        async def run(self, input_data, config=None):
            return "test"

        def get_tools(self):
            return []

    @AgentRegistry.register("api-test-agent", mcp_servers=["fetch"])
    class APIAgent(TestAgent):
        pass

    try:
        assert AgentRegistry.get("api-test-agent") is APIAgent
        assert "api-test-agent" in AgentRegistry.list_agents()
    finally:
        AgentRegistry._registry.pop("api-test-agent", None)
        AgentRegistry._mcp_servers.pop("api-test-agent", None)


def test_agntrick_config_available():
    """Test that config functions work from top-level import."""
    config = get_config()
    assert config is not None
    assert isinstance(config, AgntrickConfig)
