from unittest.mock import patch

from agentic_framework.core.simple_agent import SimpleAgent


def test_simple_agent_initialization():
    with patch("agentic_framework.core.simple_agent.ChatOpenAI") as MockChatOpenAI:
        # Configure the mock
        MockChatOpenAI.return_value

        agent = SimpleAgent(model_name="gpt-4o-mini")
        assert agent is not None
        assert agent.get_tools() == []

        # Verify ChatOpenAI was initialized with correct params
        MockChatOpenAI.assert_called_once_with(model="gpt-4o-mini", temperature=0.0)
