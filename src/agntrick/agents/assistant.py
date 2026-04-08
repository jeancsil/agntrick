"""Assistant Agent — default generalist orchestrator.

A senior digital assistant that handles any task by combining its own knowledge
with real-time research and delegation to specialized agents. Uses the configured
LLM provider (not hardcoded to a specific model).
"""

from typing import Any, Sequence

from agntrick.agent import AgentBase
from agntrick.graph import create_assistant_graph
from agntrick.prompts import load_prompt
from agntrick.registry import AgentRegistry
from agntrick.tools import AgentInvocationTool


@AgentRegistry.register(
    "assistant",
    mcp_servers=["toolbox"],
    tool_categories=["web", "hackernews", "document", "search", "media"],
)
class AssistantAgent(AgentBase):
    """Default generalist agent that orchestrates specialized agents and tools.

    Capabilities:
    - Answer questions across any domain
    - Research current information via web search and content fetching
    - Delegate to specialized agents (developer, learning, news, youtube, etc.)
    - Analyze, summarize, and synthesize information
    - Write, edit, and improve text, code, and documentation

    MCP Servers:
        toolbox: Centralized tool server with web search, fetch, HN, PDF tools
    """

    @property
    def system_prompt(self) -> str:
        """Return the assistant system prompt."""
        return load_prompt("assistant")

    def local_tools(self) -> Sequence[Any]:
        """Return local tools including agent invocation."""
        return [AgentInvocationTool().to_langchain_tool()]

    def _create_graph(
        self,
        model: Any,
        tools: list[Any],
        system_prompt: str,
        checkpointer: Any,
    ) -> Any:
        """Use the 3-node StateGraph with per-node model overrides."""
        node_models = self._get_node_models()
        return create_assistant_graph(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            checkpointer=checkpointer,
            progress_callback=self._progress_callback,
            router_model=node_models.get("router"),
            executor_model=node_models.get("executor"),
            responder_model=node_models.get("responder"),
        )
