from typing import Any, Dict, List, Union

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from agentic_framework.interfaces.base import Agent
from agentic_framework.mcp import MCPProvider
from agentic_framework.registry import AgentRegistry


@AgentRegistry.register("news", mcp_servers=["web-fetch"])
class NewsAgent(Agent):
    """
    A news agent using MCP server.
    """

    def __init__(
        self,
        model_name: str = "gpt-5-nano",
        temperature: float = 0.5,
        mcp_provider: MCPProvider | None = None,
        initial_mcp_tools: List[Any] | None = None,
        **kwargs,
    ):
        self.model = ChatOpenAI(model=model_name, temperature=temperature)
        self._mcp_provider = mcp_provider
        self._initial_mcp_tools = initial_mcp_tools
        self.tools = None
        self.graph = None

    async def _ensure_initialized(self):
        system_prompt = """You are a news agent with access to MCP tools.
        You MUST grab news from https://techcrunch.com/category/artificial-intelligence/ using MCP tools given to you.
        You are not allowed to ask question, make the best decision based on the user's message and return the result.
        Your goal is to provide the best and most recent news about artificial intelligence to the user so they
        can be informed about the latest trends and developments in the field.
        Stop if not able to use the MCP server.
        """

        if self.tools is None:
            if self._initial_mcp_tools is not None:
                mcp_tools = list(self._initial_mcp_tools)
            elif self._mcp_provider:
                mcp_tools = await self._mcp_provider.get_tools()
            else:
                mcp_tools = []
            self.tools = mcp_tools
            self.graph = create_agent(
                model=self.model,
                tools=self.tools,
                system_prompt=system_prompt,
                checkpointer=InMemorySaver(),
            )

    async def run(
        self,
        input_data: Union[str, List[BaseMessage]],
        config: Dict[str, Any] | None = None,
    ) -> Union[str, BaseMessage]:
        await self._ensure_initialized()

        messages: List[BaseMessage]
        if isinstance(input_data, str):
            messages = [HumanMessage(content=input_data)]
        else:
            messages = input_data

        if config is None:
            config = {"configurable": {"thread_id": "1"}}

        if self.graph:
            result = await self.graph.ainvoke({"messages": messages}, config=config)
            return str(result["messages"][-1].content)

        raise NotImplementedError("NewsAgent requires langgraph")

    def get_tools(self) -> List[Any]:
        return self.tools if self.tools is not None else []
