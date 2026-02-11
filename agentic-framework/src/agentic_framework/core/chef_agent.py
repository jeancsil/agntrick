from typing import Any, Sequence

from langchain_core.tools import StructuredTool

from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry
from agentic_framework.tools.web_search import WebSearchTool


@AgentRegistry.register("chef", mcp_servers=["tavily"])
class ChefAgent(LangGraphMCPAgent):
    """A recipe-focused agent with local web search plus optional MCP tools."""

    @property
    def system_prompt(self) -> str:
        return """You are a personal chef.
        The user will give you a list of ingredients they have left over in their house.
        Using the web search tool, search the web for recipes
        that can be made with the ingredients they have.
        Return recipe suggestions and eventually the recipe instructions
        to the user, if requested."""

    def local_tools(self) -> Sequence[Any]:
        return [
            StructuredTool.from_function(
                func=WebSearchTool().invoke,
                name="web_search",
                description="Search the web for information given a query.",
            )
        ]
