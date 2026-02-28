from agentic_framework.interfaces.base import Agent
from agentic_framework.registry import AgentRegistry


def test_registry_discovers_core_agents():
    AgentRegistry.discover_agents()
    agents = AgentRegistry.list_agents()

    assert "simple" in agents
    assert "chef" in agents
    assert "travel" in agents
    assert "news" in agents
    assert "travel-coordinator" in agents
    assert "developer" in agents


def test_registry_register_get_and_mcp_servers():
    @AgentRegistry.register("test-agent", mcp_servers=["web-fetch"])
    class TestAgent(Agent):
        async def run(self, input_data, config=None):
            return "ok"

        def get_tools(self):
            return []

    try:
        assert AgentRegistry.get("test-agent") is TestAgent
        assert AgentRegistry.get_mcp_servers("test-agent") == ["web-fetch"]
        assert "test-agent" in AgentRegistry.list_agents()
    finally:
        AgentRegistry._registry.pop("test-agent", None)
        AgentRegistry._mcp_servers.pop("test-agent", None)


def test_registry_duplicate_registration_warns_by_default():
    """By default, duplicate registrations should log a warning but allow the override."""

    @AgentRegistry.register("dup-test", mcp_servers=None)
    class TestAgent1(Agent):
        async def run(self, input_data, config=None):
            return "ok1"

        def get_tools(self):
            return []

    @AgentRegistry.register("dup-test", mcp_servers=None)
    class TestAgent2(Agent):
        async def run(self, input_data, config=None):
            return "ok2"

        def get_tools(self):
            return []

    try:
        # Second registration should have overwritten the first
        assert AgentRegistry.get("dup-test") is TestAgent2
    finally:
        AgentRegistry._registry.pop("dup-test", None)
        AgentRegistry._mcp_servers.pop("dup-test", None)


def test_registry_duplicate_registration_strict_mode_raises():
    """In strict mode, duplicate registrations should raise an error."""
    AgentRegistry.set_strict_registration(True)

    @AgentRegistry.register("dup-strict-test", mcp_servers=None)
    class TestAgent1(Agent):
        async def run(self, input_data, config=None):
            return "ok1"

        def get_tools(self):
            return []

    try:
        # This should raise DuplicateAgentRegistrationError
        @AgentRegistry.register("dup-strict-test", mcp_servers=None)
        class TestAgent2(Agent):
            async def run(self, input_data, config=None):
                return "ok2"

            def get_tools(self):
                return []

        assert False, "Expected DuplicateAgentRegistrationError to be raised"
    except Exception as e:
        assert "DuplicateAgentRegistrationError" in str(type(e).__name__)
        assert "dup-strict-test" in str(e)
    finally:
        AgentRegistry._registry.pop("dup-strict-test", None)
        AgentRegistry._mcp_servers.pop("dup-strict-test", None)
        AgentRegistry.set_strict_registration(False)  # Reset to default


def test_registry_duplicate_registration_with_override_flag():
    """The override flag should allow duplicate registration even in strict mode."""
    AgentRegistry.set_strict_registration(True)

    @AgentRegistry.register("dup-override-test", mcp_servers=None)
    class TestAgent1(Agent):
        async def run(self, input_data, config=None):
            return "ok1"

        def get_tools(self):
            return []

    @AgentRegistry.register("dup-override-test", mcp_servers=None, override=True)
    class TestAgent2(Agent):
        async def run(self, input_data, config=None):
            return "ok2"

        def get_tools(self):
            return []

    try:
        # Should have succeeded due to override=True
        assert AgentRegistry.get("dup-override-test") is TestAgent2
    finally:
        AgentRegistry._registry.pop("dup-override-test", None)
        AgentRegistry._mcp_servers.pop("dup-override-test", None)
        AgentRegistry.set_strict_registration(False)  # Reset to default
