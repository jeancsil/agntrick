from typing import Any, Dict

from tavily import TavilyClient  # type: ignore[import-untyped]

from agentic_framework.interfaces.base import Tool


class WebSearchTool(Tool):
    """WebSearch Tool that uses Tavily API."""

    def __init__(self):
        self.tavily_client = TavilyClient()

    def invoke(self, query: str) -> Dict[str, Any]:
        """Search the web for information"""
        return self.tavily_client.search(query)
