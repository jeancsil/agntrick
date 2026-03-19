# src/agntrick/tools/agent_invocation.py
"""Agent Invocation Tool for delegating tasks to other agents."""

import asyncio
import json
import logging
from typing import Any

from agntrick.interfaces.base import Tool
from agntrick.registry import AgentRegistry

logger = logging.getLogger(__name__)

# Agents that can be delegated to (excludes ollama to prevent recursion)
DELEGATABLE_AGENTS = ["developer", "learning", "news", "youtube"]


class AgentInvocationTool(Tool):
    """Tool to invoke other registered agents.

    This tool allows an orchestrator agent to delegate tasks to specialized
    agents. Each invocation creates a fresh agent instance with no prior
    conversation context.

    Input format (JSON string):
        {
            "agent_name": "developer",
            "prompt": "Analyze the auth module...",
            "timeout": 60  // optional, defaults to 60
        }

    Returns:
        The delegated agent's response as a string, or an error message.
    """

    @property
    def name(self) -> str:
        return "invoke_agent"

    @property
    def description(self) -> str:
        return """Invoke a specialized agent to handle a task.

The delegated agent starts with no conversation context - include all necessary
context in your prompt.

Available agents:
- developer: Code exploration, file operations, technical analysis
- learning: Educational tutorials, step-by-step guides, explanations
- news: Current news, events, breaking stories
- youtube: Video transcript extraction and analysis

Input (JSON):
{
    "agent_name": "developer",
    "prompt": "Your task with full context...",
    "timeout": 60
}

Returns the agent's response or an error message."""

    def invoke(self, input_str: str) -> str:
        """Execute agent invocation.

        Args:
            input_str: JSON string with agent_name, prompt, and optional timeout.

        Returns:
            Agent response or error message (never raises exceptions).
        """
        # Parse input
        try:
            data = json.loads(input_str)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON input. Expected format: {{'agent_name': '...', 'prompt': '...'}}. Details: {e}"

        # Validate required fields
        if "agent_name" not in data:
            return "Error: Missing required field 'agent_name'. Available agents: " + ", ".join(DELEGATABLE_AGENTS)
        if "prompt" not in data:
            return "Error: Missing required field 'prompt'."

        agent_name = data["agent_name"]
        prompt = data["prompt"]
        timeout = data.get("timeout", 60)

        # Block self-delegation
        if agent_name == "ollama":
            available = ", ".join(DELEGATABLE_AGENTS)
            return f"Error: Ollama agent cannot delegate to itself. Choose a different agent: {available}"

        # Validate agent exists
        agent_cls = AgentRegistry.get(agent_name)
        if agent_cls is None:
            registered_agents = AgentRegistry.list_agents()
            delegatable = [a for a in registered_agents if a in DELEGATABLE_AGENTS]
            return f"Error: Agent '{agent_name}' not found. Available agents: {', '.join(delegatable)}"

        # Check agent is delegatable
        if agent_name not in DELEGATABLE_AGENTS:
            return f"Error: Agent '{agent_name}' cannot be delegated to. Available: {', '.join(DELEGATABLE_AGENTS)}"

        # Invoke agent in async context
        try:
            return asyncio.run(self._invoke_agent_async(agent_cls, prompt, timeout))
        except Exception as e:
            logger.error(f"Agent invocation failed: {e}")
            return f"Error: Agent '{agent_name}' encountered an error: {e}"

    async def _invoke_agent_async(
        self,
        agent_cls: Any,
        prompt: str,
        timeout: float,
    ) -> str:
        """Invoke agent asynchronously with timeout.

        Args:
            agent_cls: The agent class to instantiate.
            prompt: The prompt to send to the agent.
            timeout: Timeout in seconds.

        Returns:
            Agent response or error message.
        """
        try:
            agent = agent_cls()
            result = await asyncio.wait_for(
                agent.run(prompt),
                timeout=timeout,
            )
            return str(result)
        except asyncio.TimeoutError:
            return f"Error: Agent timed out after {timeout} seconds. Try simplifying your request."
        except Exception as e:
            logger.error(f"Async agent invocation failed: {e}")
            raise
