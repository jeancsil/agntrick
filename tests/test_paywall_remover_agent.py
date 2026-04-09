"""Tests for paywall-remover agent registration and delegation wiring."""

from agntrick.registry import AgentRegistry
from agntrick.tools.agent_invocation import DELEGATABLE_AGENTS


class TestPaywallRemoverRegistration:
    """Verify the agent is registered and delegatable."""

    def test_registered_in_registry(self) -> None:
        """Agent class is discoverable via AgentRegistry."""
        cls = AgentRegistry.get("paywall-remover")
        assert cls is not None

    def test_in_delegatable_agents(self) -> None:
        """Agent is in the DELEGATABLE_AGENTS list."""
        assert "paywall-remover" in DELEGATABLE_AGENTS

    def test_invoke_agent_description_includes_paywall(self) -> None:
        """invoke_agent tool description mentions paywall-remover."""
        from agntrick.tools.agent_invocation import AgentInvocationTool

        tool = AgentInvocationTool()
        assert "paywall-remover" in tool.description
