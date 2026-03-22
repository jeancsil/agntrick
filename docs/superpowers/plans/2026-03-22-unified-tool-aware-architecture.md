# Unified Tool-Aware Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a unified tool-aware architecture where all agents use toolbox as the single source of truth and discover capabilities at runtime.

**Architecture:** Add manifest endpoint to toolkit, create manifest client and dynamic prompt generator in agntrick, update agent registrations to declare capabilities instead of servers.

**Tech Stack:** Python 3.12, FastMCP, Pydantic, httpx

**Note:** This project uses `from mcp.server.fastmcp import FastMCP` (from the `mcp` package), NOT the standalone `fastmcp` package.

---

## File Structure

```
agntrick-toolkit/
├── src/agntrick_toolbox/
│   ├── manifest.py          # CREATE - Tool manifest model
│   └── server.py            # MODIFY - Add /manifest endpoint
└── tests/
    └── test_manifest.py     # CREATE

agntrick/
├── src/agntrick/
│   ├── tools/
│   │   └── manifest.py      # CREATE - Manifest client
│   ├── prompts/
│   │   ├── generator.py     # CREATE - Dynamic prompt generator
│   │   └── templates/       # CREATE - Tool documentation templates
│   ├── registry.py          # MODIFY - Add capabilities tracking
│   └── agents/
│       ├── ollama.py        # MODIFY - Update registration
│       └── learning.py      # MODIFY - Update registration
└── tests/
    ├── test_manifest.py     # CREATE
    └── test_prompt_generator.py  # CREATE
```

---

## Task 1: Create Tool Manifest Model in Toolkit

**Files:**
- Create: `~/code/agntrick-toolkit/src/agntrick_toolbox/manifest.py`
- Create: `~/code/agntrick-toolkit/tests/test_manifest.py`

- [ ] **Step 1: Write the failing test for ToolInfo model**

Create `tests/test_manifest.py`:

```python
"""Tests for tool manifest."""

import pytest


class TestToolInfo:
    """Tests for ToolInfo model."""

    def test_tool_info_from_dict(self) -> None:
        """ToolInfo should be created from dict."""
        from agntrick_toolbox.manifest import ToolInfo

        data = {
            "name": "web_search",
            "category": "web",
            "description": "Search the web",
        }
        tool = ToolInfo(**data)
        assert tool.name == "web_search"
        assert tool.category == "web"
        assert tool.description == "Search the web"

    def test_tool_info_to_dict(self) -> None:
        """ToolInfo should serialize to dict."""
        from agntrick_toolbox.manifest import ToolInfo

        tool = ToolInfo(
            name="web_search",
            category="web",
            description="Search the web",
        )
        result = tool.model_dump()
        assert result["name"] == "web_search"
        assert result["category"] == "web"


class TestToolManifest:
    """Tests for ToolManifest model."""

    def test_manifest_from_tools(self) -> None:
        """ToolManifest should be created from tool list."""
        from agntrick_toolbox.manifest import ToolInfo, ToolManifest

        tools = [
            ToolInfo(name="web_search", category="web", description="Search"),
            ToolInfo(name="web_fetch", category="web", description="Fetch"),
        ]
        manifest = ToolManifest(tools=tools)
        assert len(manifest.tools) == 2
        assert manifest.version == "1.0.0"

    def test_get_tools_by_category(self) -> None:
        """ToolManifest should filter by category."""
        from agntrick_toolbox.manifest import ToolInfo, ToolManifest

        tools = [
            ToolInfo(name="web_search", category="web", description="Search"),
            ToolInfo(name="git_status", category="git", description="Status"),
        ]
        manifest = ToolManifest(tools=tools)
        web_tools = manifest.get_tools_by_category("web")
        assert len(web_tools) == 1
        assert web_tools[0].name == "web_search"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_manifest.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Create the manifest.py module**

Create `src/agntrick_toolbox/manifest.py`:

```python
"""Tool manifest models for capability discovery."""

from pydantic import BaseModel


class ToolInfo(BaseModel):
    """Information about a single tool."""

    name: str
    category: str
    description: str
    parameters: dict | None = None
    examples: list[str] | None = None


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_manifest.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/code/agntrick-toolkit
git add src/agntrick_toolbox/manifest.py tests/test_manifest.py
git commit -m "feat: add ToolManifest model for capability discovery"
```

---

## Task 2: Add Manifest Endpoint to Toolkit Server

**Files:**
- Modify: `~/code/agntrick-toolkit/src/agntrick_toolbox/server.py`
- Modify: `~/code/agntrick-toolkit/tests/test_manifest.py`

- [ ] **Step 1: Write the failing test for manifest endpoint**

Add to `tests/test_manifest.py`:

```python
class TestManifestEndpoint:
    """Tests for manifest MCP tool."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_manifest(self) -> None:
        """list_tools should return a valid manifest."""
        from agntrick_toolbox.server import mcp

        tools = mcp._tool_manager._tools
        list_tools = tools.get("list_tools")
        assert list_tools is not None

        result = await list_tools.fn()
        import json
        manifest = json.loads(result)

        assert "tools" in manifest or isinstance(manifest, list)
        # Should include the new web tools
        tool_names = [t["name"] if isinstance(t, dict) else t for t in (manifest if isinstance(manifest, list) else manifest.get("tools", []))]
        assert "web_search" in tool_names
        assert "hacker_news_top" in tool_names
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_manifest.py::TestManifestEndpoint -v`
Expected: Should pass (list_tools already exists, verify it returns correct format)

- [ ] **Step 3: Update list_tools to return manifest format**

The existing `list_tools()` function returns a JSON array. We need to ensure it returns the tool name, category, and description. Check the current implementation and verify it matches the expected format.

Read `server.py` to verify the current `list_tools()` implementation includes all required fields.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/code/agntrick-toolkit && uv run pytest tests/test_manifest.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/code/agntrick-toolkit
git add tests/test_manifest.py
git commit -m "test: add tests for manifest endpoint format"
```

---

## Task 3: Create Manifest Client in agntrick

**Files:**
- Create: `~/code/agents/src/agntrick/tools/manifest.py`
- Create: `~/code/agents/tests/test_tools/test_manifest.py`

- [ ] **Step 1: Write the failing test for ToolManifestClient**

Create `tests/test_tools/test_manifest.py`:

```python
"""Tests for tool manifest client."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestToolManifestClient:
    """Tests for ToolManifestClient."""

    @pytest.mark.asyncio
    async def test_fetch_manifest_from_toolbox(self) -> None:
        """Client should fetch manifest from toolbox server."""
        from agntrick.tools.manifest import ToolManifestClient

        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={
            "version": "1.0.0",
            "tools": [
                {"name": "web_search", "category": "web", "description": "Search"},
            ]
        })

        with patch("agntrick.tools.manifest.httpx.AsyncClient") as mock_client:
            mock_context = AsyncMock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_context.__aenter__ = AsyncMock(return_value=mock_context)
            mock_context.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_context

            client = ToolManifestClient("http://localhost:8080")
            manifest = await client.fetch_manifest()

        assert manifest is not None
        assert len(manifest.tools) == 1
        assert manifest.tools[0].name == "web_search"

    @pytest.mark.asyncio
    async def test_get_cached_manifest(self) -> None:
        """Client should cache manifest."""
        from agntrick.tools.manifest import ToolManifestClient

        client = ToolManifestClient("http://localhost:8080")

        # Mock the first fetch
        with patch.object(client, "fetch_manifest", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = MagicMock(tools=[])
            await client.get_manifest()
            assert mock_fetch.call_count == 1

            # Second call should use cache
            await client.get_manifest()
            assert mock_fetch.call_count == 1  # Not called again
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/code/agents && uv run pytest tests/test_tools/test_manifest.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Create the manifest client module**

Create `src/agntrick/tools/manifest.py`:

```python
"""Tool manifest client for discovering toolbox capabilities."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ToolInfo(BaseModel):
    """Information about a single tool."""

    name: str
    category: str
    description: str
    parameters: dict[str, Any] | None = None
    examples: list[str] | None = None


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
            import json
            tools_data = json.loads(response.text) if response.text else []

            tools = []
            for item in tools_data if isinstance(tools_data, list) else tools_data.get("tools", []):
                if isinstance(item, dict):
                    tools.append(ToolInfo(
                        name=item.get("name", ""),
                        category=item.get("category", "general"),
                        description=item.get("description", ""),
                    ))

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/code/agents && uv run pytest tests/test_tools/test_manifest.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/code/agents
git add src/agntrick/tools/manifest.py tests/test_tools/test_manifest.py
git commit -m "feat: add ToolManifestClient for capability discovery"
```

---

## Task 4: Create Dynamic Prompt Generator

**Files:**
- Create: `~/code/agents/src/agntrick/prompts/generator.py`
- Create: `~/code/agents/src/agntrick/prompts/templates/tools.md`
- Create: `~/code/agents/tests/test_prompts/test_generator.py`

- [ ] **Step 1: Create the tools documentation template**

Create `src/agntrick/prompts/templates/tools.md`:

```markdown
## AVAILABLE TOOLS

The following tools are available via the toolbox MCP server:

{% for category in categories %}
### {{ category.title() }} Tools
{% for tool in tools_by_category[category] %}
- **{{ tool.name }}** - {{ tool.description }}
{% endfor %}

{% endfor %}

## USAGE NOTES

- All tools are accessed via the toolbox MCP server
- Use tools proactively when they would help complete the task
- If unsure which tool to use, describe what you need and the system will help
```

- [ ] **Step 2: Write the failing test for prompt generator**

Create `tests/test_prompts/test_generator.py`:

```python
"""Tests for dynamic prompt generator."""

import pytest
from unittest.mock import MagicMock


class TestGenerateToolsSection:
    """Tests for generate_tools_section."""

    def test_generates_markdown_for_tools(self) -> None:
        """Should generate markdown documentation for tools."""
        from agntrick.prompts.generator import generate_tools_section
        from agntrick.tools.manifest import ToolInfo, ToolManifest

        manifest = ToolManifest(tools=[
            ToolInfo(name="web_search", category="web", description="Search the web"),
            ToolInfo(name="web_fetch", category="web", description="Fetch URL content"),
            ToolInfo(name="git_status", category="git", description="Get git status"),
        ])

        result = generate_tools_section(manifest)

        assert "AVAILABLE TOOLS" in result
        assert "web_search" in result
        assert "web_fetch" in result
        assert "git_status" in result

    def test_filters_by_categories(self) -> None:
        """Should filter tools by category when specified."""
        from agntrick.prompts.generator import generate_tools_section
        from agntrick.tools.manifest import ToolInfo, ToolManifest

        manifest = ToolManifest(tools=[
            ToolInfo(name="web_search", category="web", description="Search"),
            ToolInfo(name="git_status", category="git", description="Status"),
        ])

        result = generate_tools_section(manifest, categories=["web"])

        assert "web_search" in result
        assert "git_status" not in result


class TestGenerateSystemPrompt:
    """Tests for generate_system_prompt."""

    def test_combines_base_with_tools(self) -> None:
        """Should combine base prompt with tools section."""
        from agntrick.prompts.generator import generate_system_prompt
        from agntrick.tools.manifest import ToolInfo, ToolManifest

        manifest = ToolManifest(tools=[
            ToolInfo(name="web_search", category="web", description="Search"),
        ])

        result = generate_system_prompt(
            agent_name="learning",
            manifest=manifest,
            categories=["web"],
        )

        assert "expert educator" in result.lower()  # From base prompt
        assert "web_search" in result  # From tools section
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ~/code/agents && uv run pytest tests/test_prompts/test_generator.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 4: Create the prompt generator module**

Create `src/agntrick/prompts/generator.py`:

```python
"""Dynamic prompt generation with tool documentation."""

import logging
from pathlib import Path
from typing import Any

from agntrick.prompts import load_prompt
from agntrick.tools.manifest import ToolManifest

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def generate_tools_section(
    manifest: ToolManifest,
    categories: list[str] | None = None,
) -> str:
    """Generate markdown documentation for tools.

    Args:
        manifest: Tool manifest with all available tools.
        categories: Optional filter for specific categories. None = all.

    Returns:
        Markdown string documenting the tools.
    """
    if categories:
        tools = []
        for cat in categories:
            tools.extend(manifest.get_tools_by_category(cat))
    else:
        tools = manifest.tools

    if not tools:
        return ""

    # Group by category
    tools_by_category: dict[str, list[Any]] = {}
    for tool in tools:
        if tool.category not in tools_by_category:
            tools_by_category[tool.category] = []
        tools_by_category[tool.category].append(tool)

    # Generate markdown
    lines = ["## AVAILABLE TOOLS\n"]
    lines.append("The following tools are available via the toolbox MCP server:\n")

    for category in sorted(tools_by_category.keys()):
        lines.append(f"\n### {category.title()} Tools\n")
        for tool in tools_by_category[category]:
            lines.append(f"- **{tool.name}** - {tool.description}")

    lines.append("\n\n## USAGE NOTES\n")
    lines.append("- All tools are accessed via the toolbox MCP server\n")
    lines.append("- Use tools proactively when they would help complete the task\n")
    lines.append("- If unsure which tool to use, describe what you need\n")

    return "\n".join(lines)


def generate_system_prompt(
    agent_name: str,
    manifest: ToolManifest,
    categories: list[str] | None = None,
) -> str:
    """Generate system prompt with tool documentation.

    Args:
        agent_name: Name of the agent (for base prompt).
        manifest: Tool manifest with all available tools.
        categories: Optional filter for specific tool categories.

    Returns:
        Complete system prompt with tool documentation.
    """
    base_prompt = load_prompt(agent_name)
    tools_section = generate_tools_section(manifest, categories)

    if tools_section:
        return f"{base_prompt}\n\n{tools_section}"

    return base_prompt
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ~/code/agents && uv run pytest tests/test_prompts/test_generator.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
cd ~/code/agents
git add src/agntrick/prompts/generator.py src/agntrick/prompts/templates/ tests/test_prompts/test_generator.py
git commit -m "feat: add dynamic prompt generator with tool documentation"
```

---

## Task 5: Update Agent Registrations

**Files:**
- Modify: `~/code/agents/src/agntrick/agents/ollama.py`
- Modify: `~/code/agents/src/agntrick/agents/learning.py`
- Modify: `~/code/agents/src/agntrick/registry.py`

- [ ] **Step 1: Update ollama agent registration**

Edit `src/agntrick/agents/ollama.py`:

Change line 18:
```python
# OLD:
@AgentRegistry.register("ollama", mcp_servers=["web-forager", "fetch", "hacker-news"])

# NEW:
@AgentRegistry.register("ollama", mcp_servers=["toolbox"])
```

Update docstring to remove old MCP server references:
```python
"""Agent using local GLM-4.7-Flash model via Ollama.

A versatile local AI orchestrator that can:
- Search the web and fetch content via toolbox MCP tools
- Delegate to specialized agents (developer, learning, news, youtube)
- Handle research, writing, and analysis tasks directly

MCP Servers:
    toolbox: Centralized tool server with web search, fetch, and more

Server Configuration:
    Make sure toolbox is running:
    cd agntrick-toolkit && uv run toolbox-server

Usage:
    agntrick ollama -i "Your question here"
"""
```

- [ ] **Step 2: Update learning agent registration**

Edit `src/agntrick/agents/learning.py`:

Change line 14:
```python
# OLD:
@AgentRegistry.register("learning", mcp_servers=["fetch", "web-forager"])

# NEW:
@AgentRegistry.register("learning", mcp_servers=["toolbox"])
```

Update docstring:
```python
"""Agent specialized in creating tutorials and educational content.

This agent uses toolbox MCP tools for web research and content fetching
to create comprehensive, step-by-step tutorials.

Capabilities:
- Creates structured tutorials with clear steps
- Explains complex concepts in simple terms
- Provides examples and code snippets
- Researches current best practices via toolbox tools
"""
```

- [ ] **Step 3: Run tests to verify no regressions**

Run: `cd ~/code/agents && make check && make test`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
cd ~/code/agents
git add src/agntrick/agents/ollama.py src/agntrick/agents/learning.py
git commit -m "refactor: update agent registrations to use toolbox

- ollama: Change from [web-forager, fetch, hacker-news] to [toolbox]
- learning: Change from [fetch, web-forager] to [toolbox]
- Update docstrings to reflect new architecture"
```

---

## Task 6: Update Agent Prompts

**Files:**
- Modify: `~/code/agents/src/agntrick/prompts/ollama.md`

- [ ] **Step 1: Update ollama.md prompt**

Edit `src/agntrick/prompts/ollama.md`:

Remove old MCP server documentation and update to reflect toolbox:

```markdown
# Ollama Agent System Prompt

You are a versatile AI assistant running locally via Ollama.
You can delegate tasks to specialized agents and use MCP tools.

## Your Capabilities

- Conversational chat and Q&A
- Web search via DuckDuckGo (web_search tool)
- Web content fetching (web_fetch tool)
- Hacker News access (hacker_news_top, hacker_news_item tools)
- Invoke specialized agents for specific tasks

## Available Tools

All tools are available via the **toolbox** MCP server:

### Web Tools
- **web_search** - Search the web using DuckDuckGo
- **web_fetch** - Fetch and extract text from URLs

### Hacker News Tools
- **hacker_news_top** - Get top stories from Hacker News
- **hacker_news_item** - Get details of a specific HN item

### Document Tools
- **pdf_extract_text** - Extract text from PDFs
- **pandoc_convert** - Convert document formats

## Invoking Specialized Agents

You have the `invoke_agent` tool which allows you to delegate tasks:

| For this... | Use this agent |
|-------------|----------------|
| Coding, debugging | developer |
| News & current events | news |
| Learning topics | learning |
| YouTube operations | youtube |
| GitHub PR reviews | github-pr-reviewer |

**IMPORTANT:** Actually use `invoke_agent` when appropriate - don't just suggest it.

## Communication Style

- Be concise and helpful
- Use your tools proactively
- When uncertain, search for current information
- Celebrate the user's progress
```

- [ ] **Step 2: Run tests to verify no regressions**

Run: `cd ~/code/agents && make test`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
cd ~/code/agents
git add src/agntrick/prompts/ollama.md
git commit -m "docs: update ollama prompt to reflect toolbox architecture"
```

---

## Task 7: Integration Testing

**Files:**
- None (manual testing)

- [ ] **Step 1: Start the toolbox server**

Run: `cd ~/code/agntrick-toolkit && uv run toolbox-server`
Expected: Server starts on port 8080

- [ ] **Step 2: Verify manifest is accessible**

In another terminal:
```bash
cd ~/code/agents
uv run python -c "
import asyncio
from agntrick.tools.manifest import ToolManifestClient

async def test():
    client = ToolManifestClient('http://localhost:8080')
    manifest = await client.get_manifest()
    print(f'Tools: {len(manifest.tools)}')
    print(f'Categories: {manifest.get_categories()}')

asyncio.run(test())
"
```

- [ ] **Step 3: Test agent with toolbox**

```bash
cd ~/code/agents
uv run agntrick ollama -i "What tools do you have access to?"
```

---

## Task 8: Final Verification and Cleanup

- [ ] **Step 1: Run all test suites**

```bash
cd ~/code/agntrick-toolkit && uv run pytest tests/ -v
cd ~/code/agents && make check && make test
```

Expected: All pass

- [ ] **Step 2: Create summary commit**

```bash
cd ~/code/agents
git add docs/superpowers/specs/2026-03-22-unified-tool-aware-architecture.md
git add docs/superpowers/plans/2026-03-22-unified-tool-aware-architecture.md
git commit -m "docs: add unified tool-aware architecture spec and plan"
```

---

## Verification Checklist

After completing all tasks:

- [ ] agntrick-toolkit has manifest model
- [ ] agntrick has ToolManifestClient
- [ ] agntrick has dynamic prompt generator
- [ ] All agents use `["toolbox"]` as MCP servers
- [ ] All prompts updated to reflect toolbox architecture
- [ ] All tests pass in all repositories

---

## Rollback Instructions

If issues arise:

1. **Revert agntrick agent changes:**
   ```bash
   cd ~/code/agents
   git revert HEAD~3  # Reverts the last 3 commits
   ```

2. **Revert manifest client:**
   ```bash
   cd ~/code/agents
   git revert HEAD~1
   ```

3. **Alternative: Keep old MCP servers as fallback** - The `toolbox` entry can coexist with other servers in the config.
