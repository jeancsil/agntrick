import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage

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


def test_simple_agent_run_with_string(monkeypatch):
    class FakeChain:
        async def ainvoke(self, payload):
            assert payload == {"input": "hello"}
            return SimpleNamespace(content="world")

    class FakePrompt:
        def __or__(self, model):
            return FakeChain()

    monkeypatch.setattr("agentic_framework.core.simple_agent.ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr(
        "agentic_framework.core.simple_agent.ChatPromptTemplate",
        SimpleNamespace(from_messages=lambda messages: FakePrompt()),
    )

    agent = SimpleAgent()
    result = asyncio.run(agent.run("hello"))

    assert result == "world"


def test_simple_agent_run_with_message_list_raises(monkeypatch):
    class FakePrompt:
        def __or__(self, model):
            class FakeChain:
                async def ainvoke(self, payload):
                    return SimpleNamespace(content="unused")

            return FakeChain()

    monkeypatch.setattr("agentic_framework.core.simple_agent.ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr(
        "agentic_framework.core.simple_agent.ChatPromptTemplate",
        SimpleNamespace(from_messages=lambda messages: FakePrompt()),
    )

    agent = SimpleAgent()
    with pytest.raises(NotImplementedError):
        asyncio.run(agent.run([HumanMessage(content="nope")]))
