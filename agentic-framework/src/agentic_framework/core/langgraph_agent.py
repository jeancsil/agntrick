from abc import abstractmethod
from typing import Any, Dict, List, Sequence, Union

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from agentic_framework.constants import DEFAULT_MODEL
from agentic_framework.interfaces.base import Agent
from agentic_framework.mcp import MCPProvider


class LangGraphMCPAgent(Agent):
    """Reusable base class for LangGraph agents with optional MCP tools."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        temperature: float = 0.1,
        mcp_provider: MCPProvider | None = None,
        initial_mcp_tools: List[Any] | None = None,
        thread_id: str = "1",
        **kwargs: Any,
    ):
        self.model = ChatOpenAI(model=model_name, temperature=temperature)
        self._mcp_provider = mcp_provider
        self._initial_mcp_tools = initial_mcp_tools
        self._thread_id = thread_id
        self._tools: List[Any] = list(self.local_tools())
        self._graph: Any | None = None

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Prompt that defines agent behavior."""

    def local_tools(self) -> Sequence[Any]:
        """Built-in tools available even without MCP."""
        return []

    async def _load_mcp_tools(self) -> List[Any]:
        if self._initial_mcp_tools is not None:
            return list(self._initial_mcp_tools)
        if self._mcp_provider is None:
            return []
        return await self._mcp_provider.get_tools()

    async def _ensure_initialized(self) -> None:
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
        if isinstance(input_data, str):
            return [HumanMessage(content=input_data)]
        return input_data

    def _default_config(self) -> Dict[str, Any]:
        return {"configurable": {"thread_id": self._thread_id}}

    async def run(
        self,
        input_data: Union[str, List[BaseMessage]],
        config: Dict[str, Any] | None = None,
    ) -> Union[str, BaseMessage]:
        await self._ensure_initialized()

        if self._graph is None:
            raise RuntimeError("Agent graph failed to initialize.")

        result = await self._graph.ainvoke(
            {"messages": self._normalize_messages(input_data)},
            config=config or self._default_config(),
        )
        return str(result["messages"][-1].content)

    def get_tools(self) -> List[Any]:
        return list(self._tools)
