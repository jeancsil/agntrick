from typing import Any, Dict, List, Union

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from agentic_framework.interfaces.base import Agent
from agentic_framework.registry import AgentRegistry

load_dotenv()


@AgentRegistry.register("travel")
class TravelAgent(Agent):
    """
    A travel agent implementation using LangGraph (React).
    """

    def __init__(self, model_name: str = "gpt-5-nano", temperature: float = 0.1):
        self.model = ChatOpenAI(model=model_name, temperature=temperature)

        self.client = MultiServerMCPClient(
            {
                "kiwi-com-flight-search": {
                    "url": "https://mcp.kiwi.com",
                    "transport": "sse",
                }
            }
        )

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

        """Garante que as ferramentas e o grafo existam antes do run."""
        if self.tools is None:
            self.tools = await self.client.get_tools()
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
        await self._ensure_initialized()  # Lazy init

        messages: List[BaseMessage]
        if isinstance(input_data, str):
            messages = [HumanMessage(content=input_data)]
        else:
            messages = input_data

        if config is None:
            config = {"configurable": {"thread_id": "1"}}

        if self.graph:
            # LangGraph returns a dictionary with 'messages'
            result = await self.graph.ainvoke({"messages": messages}, config=config)
            # The last message is the response from the agent
            last_message = result["messages"][-1]
            return str(last_message.content)

        raise NotImplementedError("TravelAgent requires langgraph")

    def get_tools(self) -> List[Any]:
        return self.tools if self.tools is not None else []
