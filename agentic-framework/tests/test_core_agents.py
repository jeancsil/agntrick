import asyncio
from types import SimpleNamespace

from agentic_framework.core.chef_agent import ChefAgent
from agentic_framework.core.news_agent import NewsAgent
from agentic_framework.core.travel_agent import TravelAgent


class DummyGraph:
    async def ainvoke(self, payload, config):
        return {"messages": [SimpleNamespace(content="done")]}


def test_chef_agent_prompt_and_mcp(monkeypatch):
    monkeypatch.setattr("agentic_framework.core.langgraph_agent._create_model", lambda model, temp: object())
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: DummyGraph())

    agent = ChefAgent(initial_mcp_tools=[])
    result = asyncio.run(agent.run("ingredients"))

    assert "personal chef" in agent.system_prompt
    assert len(agent.get_tools()) == 0  # No local tools, uses MCP instead
    assert result == "done"


def test_travel_and_news_prompts(monkeypatch):
    monkeypatch.setattr("agentic_framework.core.langgraph_agent._create_model", lambda model, temp: object())
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: DummyGraph())

    travel = TravelAgent(initial_mcp_tools=[])
    news = NewsAgent(initial_mcp_tools=[])

    travel_result = asyncio.run(travel.run("BCN to LIS"))
    news_result = asyncio.run(news.run("latest"))

    assert "travel agent" in travel.system_prompt
    assert "news agent" in news.system_prompt
    assert travel_result == "done"
    assert news_result == "done"
