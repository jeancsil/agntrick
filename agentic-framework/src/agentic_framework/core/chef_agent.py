from typing import Any, Dict, List, Union, cast

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from agentic_framework.interfaces.base import Agent
from agentic_framework.mcp import MCPProvider
from agentic_framework.registry import AgentRegistry
from agentic_framework.tools.web_search import WebSearchTool


@AgentRegistry.register("chef", mcp_servers=["tavily"])
class ChefAgent(Agent):
    """
    A chef agent implementation using LangGraph (React).
    Uses MCP (tavily) when mcp_provider is injected; otherwise built-in web_search only.
    """

    def __init__(
        self,
        model_name: str = "gpt-5-nano",
        temperature: float = 0.1,
        mcp_provider: MCPProvider | None = None,
        initial_mcp_tools: List[Any] | None = None,
        **kwargs,
    ):
        self.model = ChatOpenAI(model=model_name, temperature=temperature)
        self._mcp_provider = mcp_provider
        self._initial_mcp_tools = initial_mcp_tools
        self.tools = [
            StructuredTool.from_function(
                func=WebSearchTool().invoke,
                name="web_search",
                description="Search the web for information given a query.",
            )
        ]
        self.graph = None

    async def _ensure_initialized(self):
        if self.graph is not None:
            return
        tools = list(self.tools)
        if self._initial_mcp_tools is not None:
            tools.extend(self._initial_mcp_tools)
        elif self._mcp_provider:
            tools.extend(await self._mcp_provider.get_tools())
        self._all_tools = tools
        system_prompt = """You are a personal chef.
        The user will give you a list of ingredients they have left over in their house.
        Using the web search tool, search the web for recipes
        that can be made with the ingredients they have.
        Return recipe suggestions and eventually the recipe instructions
        to the user, if requested."""
        self.graph = create_agent(
            model=self.model,
            tools=tools,
            system_prompt=system_prompt,
            checkpointer=InMemorySaver(),
        )

    async def run(
        self,
        input_data: Union[str, List[BaseMessage]],
        config: Dict[str, Any] | None = None,
    ) -> Union[str, BaseMessage]:
        """
        Run the agent with the given input string.
        """
        await self._ensure_initialized()
        if config is None:
            config = {"configurable": {"thread_id": "1"}}

        messages: List[BaseMessage]
        if isinstance(input_data, str):
            messages = [HumanMessage(content=input_data)]
        else:
            messages = input_data

        if self.graph:
            result = await self.graph.ainvoke(cast(Any, {"messages": messages}), config=cast(RunnableConfig, config))
            return str(result["messages"][-1].content)

        raise NotImplementedError("ChefAgent requires langgraph")

    def get_tools(self) -> List[Any]:
        return getattr(self, "_all_tools", self.tools)
