from typing import Any, Dict, cast

from tavily import TavilyClient  # type: ignore[import-untyped]

from agentic_framework.interfaces.base import Tool


class WebSearchTool(Tool):
    """WebSearch Tool that uses Tavily API."""

    def __init__(self) -> None:
        self.tavily_client = TavilyClient()

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for information using Tavily API."

    def invoke(self, query: str) -> Dict[str, Any]:
        """Search the web for information"""
        result = self.tavily_client.search(query)
        return cast(Dict[str, Any], result)
