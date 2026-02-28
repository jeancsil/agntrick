import asyncio
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from agentic_framework.core.langgraph_agent import LangGraphMCPAgent


class DummyAgent(LangGraphMCPAgent):
    @property
    def system_prompt(self) -> str:
        return "dummy system prompt"

    def local_tools(self) -> list[str]:
        return ["local-tool"]


class DummyProvider:
    def __init__(self, tools: list[str]):
        self._tools = tools
        self.calls = 0

    async def get_tools(self):
        self.calls += 1
        return list(self._tools)


class DummyGraph:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, payload, config):
        self.calls.append((payload, config))
        return {"messages": [SimpleNamespace(content="ok")]}


class DummyModel:
    """A fake model that can be combined with other runnables."""

    def __init__(self):
        pass

    def __or__(self, other):
        # Return a DummyGraph when combined with create_agent
        return DummyGraph()


def test_langgraph_agent_initializes_with_local_and_initial_mcp_tools(monkeypatch):
    graph = DummyGraph()
    captured = {}

    def fake_model(*args, **kwargs):
        return DummyModel()

    monkeypatch.setattr("agentic_framework.core.langgraph_agent._create_model", fake_model)

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return graph

    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", fake_create_agent)

    agent = DummyAgent(initial_mcp_tools=["mcp-tool"], thread_id="thread-42")
    result = asyncio.run(agent.run("hello"))

    assert result == "ok"
    assert captured["tools"] == ["local-tool", "mcp-tool"]
    assert graph.calls[0][1] == {"configurable": {"thread_id": "thread-42"}}
    assert graph.calls[0][0]["messages"][0].content == "hello"
    assert agent.get_tools() == ["local-tool", "mcp-tool"]


def test_langgraph_agent_uses_provider_tools_once(monkeypatch):
    graph = DummyGraph()
    provider = DummyProvider(["mcp-a", "mcp-b"])
    captured = {}

    def fake_model(*args, **kwargs):
        return DummyModel()

    monkeypatch.setattr("agentic_framework.core.langgraph_agent._create_model", fake_model)

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return graph

    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", fake_create_agent)

    agent = DummyAgent(mcp_provider=provider)
    asyncio.run(agent.run("first"))
    asyncio.run(agent.run("second"))

    assert provider.calls == 1
    assert captured["tools"] == ["local-tool", "mcp-a", "mcp-b"]
    assert len(graph.calls) == 2


def test_langgraph_agent_run_accepts_message_list_and_custom_config(monkeypatch):
    graph = DummyGraph()

    def fake_model(*args, **kwargs):
        return DummyModel()

    monkeypatch.setattr("agentic_framework.core.langgraph_agent._create_model", fake_model)
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: graph)

    agent = DummyAgent(initial_mcp_tools=[])
    messages = [HumanMessage(content="list-input")]
    result = asyncio.run(agent.run(messages, config={"configurable": {"thread_id": "abc"}}))

    assert result == "ok"
    assert graph.calls[0][0]["messages"] == messages
    assert graph.calls[0][1] == {"configurable": {"thread_id": "abc"}}
