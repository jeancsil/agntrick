"""Agntrick: An AI agent framework for building AI-powered applications.

This library provides a flexible framework for creating agents with tool
integration, MCP (Model Context Protocol) support, and LLM provider
abstraction.

Example usage:
    ```python
    from agntrick import AgentRegistry

    # Discover all available agents
    AgentRegistry.discover_agents()

    # List available agents
    for agent_name in AgentRegistry.list_agents():
        print(agent_name)

    # Get an agent class
    AgentClass = AgentRegistry.get("developer")

    # Create and run the agent
    agent = AgentClass()
    response = await agent.run("Explain this codebase")
    ```

CLI usage:
    ```bash
    # List all available agents
    agntrick list

    # Run an agent with input
    agntrick run developer -i "Explain this codebase"

    # Get information about an agent
    agntrick info developer

    # Show current configuration
    agntrick config
    ```

## Public API

### Core Classes
- AgentBase: Base class for creating agents
- AgentRegistry: Agent discovery and registration

### Configuration
- get_config(): Get the current configuration
- AgntrickConfig: Main configuration class

### LLM
- detect_provider(): Detect the LLM provider to use
- get_default_model(): Get the default model name
- Provider: Literal type for LLM providers

### Exceptions
- AgentNotFoundError: Raised when an agent is not found
- ConfigurationError: Raised when configuration is invalid
- PromptNotFoundError: Raised when a prompt file is not found
"""

from agntrick.agent import AgentBase
from agntrick.agents import (
    DeveloperAgent,
    GithubPrReviewerAgent,
    LearningAgent,
    NewsAgent,
    YouTubeAgent,
)
from agntrick.config import AgntrickConfig, get_config
from agntrick.exceptions import (
    AgentNotFoundError,
    ConfigurationError,
    PromptNotFoundError,
)
from agntrick.llm import Provider, _create_model, detect_provider, get_default_model
from agntrick.registry import AgentRegistry

__version__ = "0.2.7"

__all__ = [
    # Core
    "AgentBase",
    "AgentRegistry",
    # Agents
    "DeveloperAgent",
    "GithubPrReviewerAgent",
    "LearningAgent",
    "NewsAgent",
    "YouTubeAgent",
    # Configuration
    "AgntrickConfig",
    "get_config",
    # LLM
    "Provider",
    "_create_model",
    "detect_provider",
    "get_default_model",
    # Exceptions
    "AgentNotFoundError",
    "ConfigurationError",
    "PromptNotFoundError",
    # Version
    "__version__",
]
