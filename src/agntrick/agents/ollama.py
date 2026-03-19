"""Ollama Agent using local GLM-4.7-Flash model.

This agent uses LocalReasoningLLM to connect to a local Ollama server
running GLM-4.7-Flash with thinking tags automatically stripped from responses.
"""

from typing import Any, Sequence

from agntrick.agent import AgentBase
from agntrick.llm.local_reasoning import get_local_developer_model
from agntrick.prompts import load_prompt
from agntrick.registry import AgentRegistry


@AgentRegistry.register("ollama", mcp_servers=["fetch"])
class OllamaAgent(AgentBase):
    """Agent using local GLM-4.7-Flash model via Ollama.

    This agent connects to a local Ollama server at http://127.0.0.1:8080
    using the GLM-4.7-Flash model. The LocalReasoningLLM automatically
    strips <reasoning>...</reasoning> tags from model responses.

    MCP Servers:
        fetch: Extract clean text from URLs

    Server Configuration:
        Make sure your Ollama server is running with:
        ollama serve --port 8080

    Usage:
        agntrick ollama -i "Your question here"
    """

    def __init__(self) -> None:
        """Initialize OllamaAgent with local GLM-4.7-Flash model."""
        # Store custom model before calling parent init
        self._custom_model = get_local_developer_model()
        # Parent sets self.model, so we provide a property to return our custom one
        super().__init__()

    @property
    def system_prompt(self) -> str:
        """Return the system prompt for the Ollama agent."""
        return load_prompt("developer")

    def local_tools(self) -> Sequence[Any]:
        """Return list of local tools (none for this base implementation)."""
        return []

    @property
    def model(self) -> Any:
        """Return the custom LocalReasoningLLM model.

        Overrides parent's model to use LocalReasoningLLM that strips
        <reasoning>...</reasoning> tags from responses.
        """
        return self._custom_model

    @model.setter
    def model(self, value: Any) -> None:
        """No-op setter to allow parent's __init__ to set self.model."""
        pass
