from typing import Any, Dict, List, Union

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from agentic_framework.interfaces.base import Agent
from agentic_framework.registry import AgentRegistry
from agentic_framework.tools.web_search import WebSearchTool

load_dotenv()


@AgentRegistry.register("chef")
class ChefAgent(Agent):
    """
    A chef agent implementation using LangGraph (React).
    """

    def __init__(self, model_name: str = "gpt-5-nano", temperature: float = 0.1):
        self.model = ChatOpenAI(model=model_name, temperature=temperature)

        self.tools = [
            StructuredTool.from_function(
                func=WebSearchTool().invoke,
                name="web_search",
                description="Search the web for information given a query.",
            )
        ]

        system_prompt = """You are a personal chef. 
        The user will give you a list of ingredients they have left over in their house.
        Using the web search tool, search the web for recipes
        that can be made with the ingredients they have.
        Return recipe suggestions and eventually the recipe instructions
        to the user, if requested."""

        self.graph = create_agent(
            model=self.model,
            tools=self.tools,
            system_prompt=system_prompt,
            checkpointer=InMemorySaver(),
        )

    # def web_search(self, query: str) -> Dict[str, Any]:
    #     """Search the web for information"""
    #     return self.tavily_client.search(query)

    def run(self, input_data: Union[str, List[BaseMessage]], config: Dict[str, Any] = None) -> Union[str, BaseMessage]:
        """
        Run the agent with the given input string.
        """
        if isinstance(input_data, str):
            messages = [HumanMessage(content=input_data)]
        else:
            messages = input_data

        if config is None:
            config = {"configurable": {"thread_id": "1"}}

        if self.graph:
            # LangGraph returns a dictionary with 'messages'
            result = self.graph.invoke({"messages": messages}, config=config)
            # The last message is the response from the agent
            last_message = result["messages"][-1]
            return str(last_message.content)

        raise NotImplementedError("ChefAgent requires langgraph")

    def get_tools(self) -> List[Any]:
        return self.tools
