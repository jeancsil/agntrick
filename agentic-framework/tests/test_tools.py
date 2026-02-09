from agentic_framework.tools.example import CalculatorTool, WeatherTool
from agentic_framework.tools.web_search import WebSearchTool


def test_calculator_tool_success():
    tool = CalculatorTool()
    assert tool.invoke("2 + 2") == "4"


def test_calculator_tool_error():
    tool = CalculatorTool()
    result = tool.invoke("1 / 0")
    assert result.startswith("Error:")


def test_weather_tool():
    tool = WeatherTool()
    assert "Lisbon" in tool.invoke("Lisbon")


def test_web_search_tool_calls_tavily(monkeypatch):
    class FakeTavilyClient:
        def search(self, query):
            return {"query": query, "results": ["a"]}

    monkeypatch.setattr("agentic_framework.tools.web_search.TavilyClient", lambda: FakeTavilyClient())
    tool = WebSearchTool()
    result = tool.invoke("langchain")

    assert result["query"] == "langchain"
