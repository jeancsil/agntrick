# tests/test_agent_invocation.py
"""Tests for AgentInvocationTool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from agntrick.tools.agent_invocation import AgentInvocationTool


class TestAgentInvocationTool:
    """Tests for AgentInvocationTool."""

    def test_tool_name(self):
        """Tool should have correct name."""
        tool = AgentInvocationTool()
        assert tool.name == "invoke_agent"

    def test_tool_description_not_empty(self):
        """Tool should have a description."""
        tool = AgentInvocationTool()
        assert len(tool.description) > 50
        assert "agent" in tool.description.lower()

    def test_invoke_valid_agent_returns_response(self):
        """Valid agent invocation should return response."""
        tool = AgentInvocationTool()

        input_json = json.dumps({"agent_name": "developer", "prompt": "Test prompt"})

        with patch("agntrick.tools.agent_invocation.AgentRegistry") as mock_registry:
            mock_agent_cls = MagicMock()
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value="Agent response")
            mock_agent_cls.return_value = mock_agent
            mock_registry.get.return_value = mock_agent_cls
            mock_registry.list_agents.return_value = ["developer", "learning", "news", "youtube"]

            result = tool.invoke(input_json)
            assert result == "Agent response"

    def test_invoke_agent_not_found_returns_error(self):
        """Non-existent agent should return error message."""
        tool = AgentInvocationTool()

        input_json = json.dumps({"agent_name": "nonexistent", "prompt": "Test prompt"})

        with patch("agntrick.tools.agent_invocation.AgentRegistry") as mock_registry:
            mock_registry.get.return_value = None
            mock_registry.list_agents.return_value = ["developer", "learning", "news", "youtube"]

            result = tool.invoke(input_json)
            assert "not found" in result.lower()
            assert "developer" in result  # Lists available agents

    def test_invoke_invalid_json_returns_error(self):
        """Invalid JSON input should return clear error."""
        tool = AgentInvocationTool()
        result = tool.invoke("not valid json")
        assert "error" in result.lower()
        assert "json" in result.lower()

    def test_invoke_missing_agent_name_returns_error(self):
        """Missing agent_name field should return error."""
        tool = AgentInvocationTool()
        result = tool.invoke(json.dumps({"prompt": "test"}))
        assert "error" in result.lower()
        assert "agent_name" in result.lower()

    def test_invoke_missing_prompt_returns_error(self):
        """Missing prompt field should return error."""
        tool = AgentInvocationTool()
        result = tool.invoke(json.dumps({"agent_name": "developer"}))
        assert "error" in result.lower()
        assert "prompt" in result.lower()

    def test_invoke_agent_crash_returns_error_not_exception(self):
        """Agent crash should return error string, not raise."""
        tool = AgentInvocationTool()

        input_json = json.dumps({"agent_name": "developer", "prompt": "Test prompt"})

        with patch("agntrick.tools.agent_invocation.AgentRegistry") as mock_registry:
            mock_agent_cls = MagicMock()
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(side_effect=RuntimeError("Agent crashed"))
            mock_agent_cls.return_value = mock_agent
            mock_registry.get.return_value = mock_agent_cls
            mock_registry.list_agents.return_value = ["developer"]

            # Should NOT raise, should return error string
            result = tool.invoke(input_json)
            assert "error" in result.lower()

    def test_invoke_blocks_self_delegation(self):
        """Tool should block ollama from delegating to itself."""
        tool = AgentInvocationTool()

        input_json = json.dumps({"agent_name": "ollama", "prompt": "Test prompt"})

        result = tool.invoke(input_json)
        assert "cannot delegate to itself" in result.lower()

    def test_to_langchain_tool(self):
        """Tool should convert to LangChain StructuredTool."""
        from langchain_core.tools import StructuredTool

        tool = AgentInvocationTool()
        lc_tool = tool.to_langchain_tool()

        assert isinstance(lc_tool, StructuredTool)
        assert lc_tool.name == "invoke_agent"
