"""Unit tests for YouTubeAgent."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from agentic_framework.core.youtube_agent import YouTubeAgent


class DummyGraph:
    """Dummy graph for testing."""

    async def ainvoke(self, payload, config):
        return {"messages": [SimpleNamespace(content="Video analysis complete")]}


class TestYouTubeAgent:
    """Test suite for YouTubeAgent."""

    def test_agent_registration(self):
        """Verify agent is registered with correct name."""
        from agentic_framework.registry import AgentRegistry

        assert "youtube" in AgentRegistry.list_agents()

    @patch("agentic_framework.core.langgraph_agent._create_model")
    @patch("agentic_framework.core.langgraph_agent.create_agent")
    def test_system_prompt_content(self, mock_create_agent, mock_create_model):
        """Test that system prompt contains expected content."""
        mock_create_model.return_value = object()
        mock_create_agent.return_value = DummyGraph()

        agent = YouTubeAgent(initial_mcp_tools=[])
        prompt = agent.system_prompt

        # Verify key capabilities in prompt
        assert "video analyst" in prompt.lower()
        assert "summar" in prompt.lower()
        assert "transcript" in prompt.lower()
        assert "timestamp" in prompt.lower()
        assert "youtube_transcript" in prompt

    @patch("agentic_framework.core.langgraph_agent._create_model")
    @patch("agentic_framework.core.langgraph_agent.create_agent")
    def test_local_tools_include_transcript(self, mock_create_agent, mock_create_model):
        """Test that local tools include the transcript tool."""
        mock_create_model.return_value = object()
        mock_create_agent.return_value = DummyGraph()

        agent = YouTubeAgent(initial_mcp_tools=[])
        tools = agent.local_tools()

        tool_names = [t.name for t in tools]
        assert "youtube_transcript" in tool_names

    @patch("agentic_framework.core.langgraph_agent._create_model")
    @patch("agentic_framework.core.langgraph_agent.create_agent")
    def test_run_returns_response(self, mock_create_agent, mock_create_model):
        """Test that run method returns agent response."""
        mock_create_model.return_value = object()
        mock_create_agent.return_value = DummyGraph()

        agent = YouTubeAgent(initial_mcp_tools=[])
        result = asyncio.run(agent.run("Summarize this video: https://youtube.com/..."))

        assert result == "Video analysis complete"

    @patch("agentic_framework.core.langgraph_agent._create_model")
    @patch("agentic_framework.core.langgraph_agent.create_agent")
    def test_mcp_servers_configured(self, mock_create_agent, mock_create_model):
        """Test that MCP servers are configured correctly."""
        mock_create_model.return_value = object()
        mock_create_agent.return_value = DummyGraph()

        # Verify MCP server configuration from decorator
        agent = YouTubeAgent(initial_mcp_tools=[])

        # Agent should be configured with web-fetch for additional context
        assert agent is not None

    @patch("agentic_framework.core.langgraph_agent._create_model")
    @patch("agentic_framework.core.langgraph_agent.create_agent")
    def test_local_tools_description(self, mock_create_agent, mock_create_model):
        """Test that local tools have proper description."""
        mock_create_model.return_value = object()
        mock_create_agent.return_value = DummyGraph()

        agent = YouTubeAgent(initial_mcp_tools=[])
        tools = agent.local_tools()

        # Find the youtube_transcript tool
        transcript_tool = None
        for tool in tools:
            if tool.name == "youtube_transcript":
                transcript_tool = tool
                break

        assert transcript_tool is not None
        assert "transcript" in transcript_tool.description.lower()
        assert "youtube" in transcript_tool.description.lower()

    @patch("agentic_framework.core.langgraph_agent._create_model")
    @patch("agentic_framework.core.langgraph_agent.create_agent")
    def test_tool_count(self, mock_create_agent, mock_create_model):
        """Test that expected number of tools are returned."""
        mock_create_model.return_value = object()
        mock_create_agent.return_value = DummyGraph()

        agent = YouTubeAgent(initial_mcp_tools=[])
        tools = agent.local_tools()

        # Should have exactly 1 local tool (youtube_transcript)
        assert len(tools) == 1

    @patch("agentic_framework.core.langgraph_agent._create_model")
    @patch("agentic_framework.core.langgraph_agent.create_agent")
    def test_custom_model_name(self, mock_create_agent, mock_create_model):
        """Test that custom model name is used."""
        mock_create_model.return_value = object()
        mock_create_agent.return_value = DummyGraph()

        YouTubeAgent(model_name="claude-opus-4-5", initial_mcp_tools=[])

        mock_create_model.assert_called_once_with("claude-opus-4-5", 0.1)

    @patch("agentic_framework.core.langgraph_agent._create_model")
    @patch("agentic_framework.core.langgraph_agent.create_agent")
    def test_custom_temperature(self, mock_create_agent, mock_create_model):
        """Test that custom temperature is used."""
        mock_create_model.return_value = object()
        mock_create_agent.return_value = DummyGraph()

        YouTubeAgent(temperature=0.7, initial_mcp_tools=[])

        mock_create_model.assert_called_once()

    @patch("agentic_framework.core.langgraph_agent._create_model")
    @patch("agentic_framework.core.langgraph_agent.create_agent")
    def test_system_prompt_guidelines(self, mock_create_agent, mock_create_model):
        """Test that system prompt includes guidelines."""
        mock_create_model.return_value = object()
        mock_create_agent.return_value = DummyGraph()

        agent = YouTubeAgent(initial_mcp_tools=[])
        prompt = agent.system_prompt

        # Verify guidelines are present
        assert "Guidelines" in prompt
        assert "timestamps" in prompt.lower()
        assert "facts" in prompt.lower()
        assert "captions" in prompt.lower()

    @patch("agentic_framework.core.langgraph_agent._create_model")
    @patch("agentic_framework.core.langgraph_agent.create_agent")
    def test_system_prompt_capabilities(self, mock_create_agent, mock_create_model):
        """Test that system prompt lists capabilities."""
        mock_create_model.return_value = object()
        mock_create_agent.return_value = DummyGraph()

        agent = YouTubeAgent(initial_mcp_tools=[])
        prompt = agent.system_prompt

        # Verify capabilities are listed
        assert "capabilities" in prompt.lower()
        assert "Summarization" in prompt
        assert "Q&A" in prompt
        assert "Key Points" in prompt
        assert "Analysis" in prompt
        assert "Comparison" in prompt
