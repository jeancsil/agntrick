from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry


@AgentRegistry.register("news", mcp_servers=["web-fetch"])
class NewsAgent(LangGraphMCPAgent):
    """News agent that fetches and summarizes recent AI updates via MCP."""

    @property
    def system_prompt(self) -> str:
        return """You are a news agent with access to MCP tools.
        You MUST grab news from https://techcrunch.com/category/artificial-intelligence/ using MCP tools given to you.
        You are not allowed to ask question, make the best decision based on the user's message and return the result.
        Your goal is to provide the best and most recent news about artificial intelligence to the user so they
        can be informed about the latest trends and developments in the field.
        Stop if not able to use the MCP server.
        """
