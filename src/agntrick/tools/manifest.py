"""Tool manifest client for discovering toolbox capabilities."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class ToolInfo(BaseModel):
    """Information about a single tool."""

    name: str
    category: str
    description: str
    parameters: dict[str, Any] | None = None
    examples: list[str] | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        """Validate that tool name is not empty."""
        assert v, "Tool name cannot be empty"
        return v


class ToolManifest(BaseModel):
    """Complete tool manifest from toolbox server."""

    version: str = "1.0.0"
    tools: list[ToolInfo]

    def get_tools_by_category(self, category: str) -> list[ToolInfo]:
        """Get all tools in a category."""
        return [t for t in self.tools if t.category == category]

    def get_tool(self, name: str) -> ToolInfo | None:
        """Get a tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_categories(self) -> list[str]:
        """Get all unique categories."""
        return sorted(set(t.category for t in self.tools))


@dataclass
class CachedManifest:
    """Cached manifest with expiry."""

    manifest: ToolManifest
    fetched_at: datetime
    ttl: timedelta

    def is_fresh(self) -> bool:
        """Check if cache is still valid."""
        return datetime.now() < self.fetched_at + self.ttl


class ToolManifestClient:
    """Client for fetching and caching tool manifests."""

    DEFAULT_TTL = timedelta(minutes=5)

    def __init__(self, toolbox_url: str, ttl: timedelta | None = None) -> None:
        self.toolbox_url = toolbox_url.rstrip("/")
        self.ttl = ttl or self.DEFAULT_TTL
        self._cache: CachedManifest | None = None

    async def fetch_manifest(self) -> ToolManifest:
        """Fetch fresh manifest from toolbox server."""
        url = f"{self.toolbox_url}/sse"

        async with httpx.AsyncClient(timeout=10.0) as client:
            # For now, we'll parse the list_tools response
            # In the future, this could be a dedicated /manifest endpoint
            response = await client.get(url)
            response.raise_for_status()

            # Parse the MCP tools list
            # This is a simplified version - actual implementation
            # would call the list_tools MCP tool
            try:
                tools_data = json.loads(response.text) if response.text else []
            except json.JSONDecodeError:
                logger.warning("Failed to parse manifest response as JSON")
                return ToolManifest(tools=[])

            tools = []
            for item in tools_data if isinstance(tools_data, list) else tools_data.get("tools", []):
                if isinstance(item, dict):
                    tools.append(
                        ToolInfo(
                            name=item.get("name", ""),
                            category=item.get("category", "general"),
                            description=item.get("description", ""),
                        )
                    )

            return ToolManifest(tools=tools)

    async def get_manifest(self, force_refresh: bool = False) -> ToolManifest:
        """Get manifest, using cache if fresh."""
        if not force_refresh and self._cache and self._cache.is_fresh():
            return self._cache.manifest

        manifest = await self.fetch_manifest()
        self._cache = CachedManifest(
            manifest=manifest,
            fetched_at=datetime.now(),
            ttl=self.ttl,
        )
        return manifest

    def clear_cache(self) -> None:
        """Clear the cached manifest."""
        self._cache = None
