from typing import Any, Dict, List, Union

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from agentic_framework.interfaces.base import Agent
from agentic_framework.mcp import MCPProvider
from agentic_framework.registry import AgentRegistry


@AgentRegistry.register("travel", mcp_servers=["kiwi-com-flight-search"])
class TravelAgent(Agent):
    """
    A travel agent implementation using LangGraph (React).
    MCP tools come from injectable MCPProvider (allowed servers defined in registry).
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
        self.tools = None
        self.graph = None

    async def _ensure_initialized(self):
        system_prompt = """You are a helpful travel agent.
        The user will give you the origin, destination and a date.
        Using the Kiwi MCP server, search for flights to the destination
        from the user's origin.
        Return the best flight option to the user considering the information provided.
        Do not ask questions to the user, just return the best flight option.
        If the user does not provide all the information, make assumptions,
        inform the user of the assumptions in your response.

        Safe Defaults:
        - 1 adult
        - Economy
        - Round-trip
        - Year: Current Year
        - Return date = outbound date + 5 days
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
        """
        Run the agent with the given input string.
        """
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
            last_message = result["messages"][-1]
            return str(last_message.content)

        raise NotImplementedError("TravelAgent requires langgraph")

    def get_tools(self) -> List[Any]:
        return self.tools if self.tools is not None else []
