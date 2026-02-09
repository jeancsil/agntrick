"""Core agent building blocks.

Agent modules are discovered dynamically via AgentRegistry.discover_agents().
Keep this file free of imports that instantiate concrete agents.
"""

from agentic_framework.core.langgraph_agent import LangGraphMCPAgent

__all__ = ["LangGraphMCPAgent"]
