import asyncio
from types import SimpleNamespace

from agentic_framework.core.travel_coordinator_agent import TravelCoordinatorAgent


class DummyGraph:
    def __init__(self, label: str, calls: list[tuple[str, dict, dict]]):
        self.label = label
        self.calls = calls

    async def ainvoke(self, payload, config):
        self.calls.append((self.label, payload, config))
        outputs = {
            "flight": "FLIGHT_REPORT",
            "city": "CITY_REPORT",
            "review": "FINAL_BRIEF",
        }
        return {"messages": [SimpleNamespace(content=outputs[self.label])]}


def test_travel_coordinator_orchestrates_three_specialists(monkeypatch):
    calls: list[tuple[str, dict, dict]] = []

    monkeypatch.setattr("agentic_framework.core.langgraph_agent.ChatOpenAI", lambda **kwargs: object())

    def fake_create_agent(**kwargs):
        system_prompt = kwargs["system_prompt"]
        if "flight specialist" in system_prompt:
            return DummyGraph("flight", calls)
        if "destination intelligence specialist" in system_prompt:
            return DummyGraph("city", calls)
        return DummyGraph("review", calls)

    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", fake_create_agent)

    agent = TravelCoordinatorAgent(initial_mcp_tools=["kiwi-tool", "web-fetch-tool"])
    result = asyncio.run(
        agent.run(
            "I need a 5-day trip from Lisbon to Berlin in May",
            config={"configurable": {"thread_id": "trip-42"}},
        )
    )

    assert result == "FINAL_BRIEF"
    assert [entry[0] for entry in calls] == ["flight", "city", "review"]
    assert "FLIGHT_REPORT" in calls[1][1]["messages"][0].content
    assert "CITY_REPORT" in calls[2][1]["messages"][0].content
    assert calls[0][2]["configurable"]["thread_id"] == "trip-42:flight"
    assert calls[1][2]["configurable"]["thread_id"] == "trip-42:city"
    assert calls[2][2]["configurable"]["thread_id"] == "trip-42:review"


def test_travel_coordinator_get_tools_aggregates_from_specialists(monkeypatch):
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr(
        "agentic_framework.core.langgraph_agent.create_agent",
        lambda **kwargs: DummyGraph("review", []),
    )

    agent = TravelCoordinatorAgent(initial_mcp_tools=["kiwi-tool", "web-fetch-tool"])
    asyncio.run(agent.run("Plan Lisbon to Porto."))

    tools = agent.get_tools()
    assert tools.count("kiwi-tool") == 3
    assert tools.count("web-fetch-tool") == 3
