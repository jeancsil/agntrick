from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry


@AgentRegistry.register("chef", mcp_servers=["web-fetch"])
class ChefAgent(LangGraphMCPAgent):
    """A recipe-focused agent with MCP web search capabilities."""

    @property
    def system_prompt(self) -> str:
        return """You are a personal chef.
        The user will give you a list of ingredients they have left over in their house.
        Using the web search tool (web_fetch_search), search the web for recipes
        that can be made with the ingredients they have.
        Return recipe suggestions and eventually the recipe instructions
        to the user, if requested."""
