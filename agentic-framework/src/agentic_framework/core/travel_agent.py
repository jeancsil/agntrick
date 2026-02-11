from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry


@AgentRegistry.register("travel", mcp_servers=["kiwi-com-flight-search"])
class TravelAgent(LangGraphMCPAgent):
    """Travel assistant that relies on flight-search MCP tools."""

    @property
    def system_prompt(self) -> str:
        return """You are a helpful travel agent.
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
