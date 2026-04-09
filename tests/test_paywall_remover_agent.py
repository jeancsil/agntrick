"""Tests for paywall-remover agent registration and delegation wiring."""

from agntrick.graph import _INTENT_TOOLS
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


class TestDeepScrapeRemovedFromGraph:
    """Verify web_extract/deep_scrape are NOT in intent tools (replaced by delegation)."""

    def test_web_extract_not_in_tool_use(self) -> None:
        assert "web_extract" not in _INTENT_TOOLS["tool_use"]

    def test_web_extract_not_in_research(self) -> None:
        assert "web_extract" not in _INTENT_TOOLS["research"]

    def test_deep_scrape_not_in_tool_use(self) -> None:
        assert "deep_scrape" not in _INTENT_TOOLS["tool_use"]

    def test_deep_scrape_not_in_research(self) -> None:
        assert "deep_scrape" not in _INTENT_TOOLS["research"]
