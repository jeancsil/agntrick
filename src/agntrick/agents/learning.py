"""Learning/Tutorial agent for creating step-by-step educational content.

This module provides an agent specialized in creating tutorials,
explaining concepts, and providing educational content with web research.
"""

from typing import Any, Sequence

from agntrick.agent import AgentBase
from agntrick.prompts import load_prompt
from agntrick.registry import AgentRegistry


@AgentRegistry.register("learning", mcp_servers=["fetch", "web-forager"])
class LearningAgent(AgentBase):
    """Agent specialized in creating tutorials and educational content.

    This agent uses web search and content fetching to create comprehensive,
    step-by-step tutorials and explanations on any topic.

    Capabilities:
    - Creates structured tutorials with clear steps
    - Explains complex concepts in simple terms
    - Provides examples and code snippets
    - Researches current best practices via web search

    Args:
        model_name: The name of LLM model to use.
        temperature: The temperature for LLM responses.
        initial_mcp_tools: Optional pre-loaded MCP tools.
        thread_id: The thread ID for conversation memory.

    Example:
        >>> agent = LearningAgent()
        >>> response = await agent.run("Explain Docker containers with a tutorial")
    """

    @property
    def system_prompt(self) -> str:
        """System prompt for the learning agent."""
        from datetime import datetime

        date_context = f"Current date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"

        return date_context + load_prompt("learning")

    def local_tools(self) -> Sequence[Any]:
        """Learning agent uses only MCP tools for web research."""
        return []
