from typing import Any, Dict, List, Union, cast

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
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

    async def run(
        self,
        input_data: Union[str, List[BaseMessage]],
        config: Dict[str, Any] | None = None,
    ) -> Union[str, BaseMessage]:
        """
        Run the agent with the given input string.
        """
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
        return self.tools
