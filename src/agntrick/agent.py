"""Base agent class for agntrick.

This module provides AgentBase, the main class for creating agents
with MCP tool integration and LLM provider abstraction.
"""

import asyncio
from abc import abstractmethod
from typing import Any, Dict, List, Sequence, Union

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from agntrick.config import get_config
from agntrick.interfaces.base import Agent
from agntrick.llm import _create_model, get_default_model
from agntrick.mcp import MCPProvider


class AgentBase(Agent):
    """Reusable base class for LangGraph agents with optional MCP tools.

    This class provides the foundation for creating agents in agntrick. It
    handles LLM model creation, MCP tool integration, and graph initialization.

    Attributes:
        model: The LLM model instance.
        _mcp_provider: Optional MCP provider for external tool access.
        _initial_mcp_tools: Optional pre-loaded MCP tools.
        _thread_id: Thread ID for conversation memory.
        _tools: List of available tools (local + MCP).
        _graph: The agent graph, initialized lazily.

    Example:
        ```python
        from agntrick import AgentBase, AgentRegistry

        @AgentRegistry.register("my-agent")
        class MyAgent(AgentBase):
            @property
            def system_prompt(self) -> str:
                return "You are a helpful assistant."

            def local_tools(self) -> Sequence[Any]:
                return []  # Add local tools here
        ```
    """

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
        mcp_provider: MCPProvider | None = None,
        initial_mcp_tools: List[Any] | None = None,
        thread_id: str = "1",
        **kwargs: Any,
    ):
        """Initialize the agent.

        Args:
            model_name: Optional model name. If not provided, uses default from config.
            temperature: Optional temperature setting. If not provided, uses default from config.
            mcp_provider: Optional MCP provider for external tool access.
            initial_mcp_tools: Optional pre-loaded MCP tools.
            thread_id: Thread ID for conversation memory.
            **kwargs: Additional arguments (for future compatibility).
        """
        config = get_config()

        if model_name is None:
            model_name = config.llm.model or get_default_model()

        if temperature is None:
            temperature = config.llm.temperature

        self.model = _create_model(model_name, temperature)
        self._mcp_provider = mcp_provider
        self._initial_mcp_tools = initial_mcp_tools
        self._thread_id = thread_id
        self._tools: List[Any] = list(self.local_tools())
        self._graph: Any | None = None
        self._init_lock = asyncio.Lock()

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Prompt that defines agent behavior.

        Returns:
            The system prompt string.
        """

    def local_tools(self) -> Sequence[Any]:
        """Built-in tools available even without MCP.

        Returns:
            A sequence of local tool instances.
        """
        return []

    async def _load_mcp_tools(self) -> List[Any]:
        """Load MCP tools from the provider.

        Returns:
            A list of MCP tools, or empty list if no provider.
        """
        if self._initial_mcp_tools is not None:
            return list(self._initial_mcp_tools)
        if self._mcp_provider is None:
            return []
        return await self._mcp_provider.get_tools()

    async def _ensure_initialized(self) -> None:
        """Ensure the agent graph is initialized.

        Lazily initializes the graph and loads MCP tools on first use.
        """
        if self._graph is not None:
            return

        async with self._init_lock:
            # Double-checked locking
            if self._graph is not None:
                return

            self._tools.extend(await self._load_mcp_tools())
            self._graph = create_agent(
                model=self.model,
                tools=self._tools,
                system_prompt=self.system_prompt,
                checkpointer=InMemorySaver(),
            )

    def _normalize_messages(self, input_data: Union[str, List[BaseMessage]]) -> List[BaseMessage]:
        """Normalize input data to a list of BaseMessage.

        Args:
            input_data: Either a string or a list of BaseMessage.

        Returns:
            A list of BaseMessage objects.
        """
        if isinstance(input_data, str):
            return [HumanMessage(content=input_data)]
        return input_data

    def _default_config(self) -> Dict[str, Any]:
        """Get the default configuration for the agent graph.

        Returns:
            A dictionary with the thread_id configuration.
        """
        return {"configurable": {"thread_id": self._thread_id}}

    async def run(
        self,
        input_data: Union[str, List[BaseMessage]],
        config: Dict[str, Any] | None = None,
    ) -> Union[str, BaseMessage]:
        """Run the agent with the given input.

        Args:
            input_data: The input for the agent, either a string or a list of messages.
            config: Optional configuration for the agent run.

        Returns:
            The agent's response as a string or BaseMessage.

        Raises:
            RuntimeError: If the agent graph fails to initialize.
        """
        await self._ensure_initialized()

        if self._graph is None:
            raise RuntimeError("Agent graph failed to initialize.")

        result = await self._graph.ainvoke(
            {"messages": self._normalize_messages(input_data)},
            config=config or self._default_config(),
        )
        return str(result["messages"][-1].content)

    def get_tools(self) -> List[Any]:
        """Get the list of available tools.

        Returns:
            A copy of the tools list to prevent external modification.
        """
        return list(self._tools)
