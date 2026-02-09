from agentic_framework.interfaces.base import Agent
from agentic_framework.registry import AgentRegistry


def test_registry_discovers_core_agents():
    AgentRegistry.discover_agents()
    agents = AgentRegistry.list_agents()

    assert "simple" in agents
    assert "chef" in agents
    assert "travel" in agents
    assert "news" in agents


def test_registry_register_get_and_mcp_servers():
    @AgentRegistry.register("test-agent", mcp_servers=["tavily", "web-fetch"])
    class TestAgent(Agent):
        async def run(self, input_data, config=None):
            return "ok"

        def get_tools(self):
            return []

    try:
        assert AgentRegistry.get("test-agent") is TestAgent
        assert AgentRegistry.get_mcp_servers("test-agent") == ["tavily", "web-fetch"]
        assert "test-agent" in AgentRegistry.list_agents()
    finally:
        AgentRegistry._registry.pop("test-agent", None)
        AgentRegistry._mcp_servers.pop("test-agent", None)
