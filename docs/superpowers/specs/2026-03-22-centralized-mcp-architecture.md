# Centralized MCP Architecture Design

**Date:** 2026-03-22
**Status:** Draft
**Author:** Claude (AI)
**Target Audience:** Mid-level Software Engineer

---

## Problem Statement

Currently, each `agntrick-whatsapp` instance creates its own MCP connections:
- 2 WhatsApp instances = 2× MCP connections = 2× memory usage
- stdio-based MCP servers (web-forager, hacker-news) spawn separate processes per client
- This is inefficient and won't scale on a 1GB droplet

## Goal

Consolidate all MCP servers into a single `agntrick-toolkit` service that:
1. Runs as a single SSE server on port 8080
2. Serves multiple WhatsApp instances
3. Uses minimal memory (~150-200MB)
4. Removes MCP instantiation code from `agntrick` and `agntrick-whatsapp`

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    agntrick-toolkit                          │
│              (Single Docker Container)                        │
│                                                               │
│   FastMCP SSE Server (:8080)                                  │
│   ┌─────────────────────────────────────────────────────────┐│
│   │ EXISTING TOOLS (keep as-is):                            ││
│   │ • pdf_extract_text, pandoc_convert                      ││
│   │ • ffmpeg_convert, imagemagick_convert                   ││
│   │ • jq_query, yq_query                                    ││
│   │ • ripgrep_search, fd_find                               ││
│   │ • git_status, git_log                                   ││
│   │ • curl_fetch, wget_download                             ││
│   │ • run_shell                                             ││
│   │                                                         ││
│   │ NEW TOOLS:                                              ││
│   │ • web_search        - DuckDuckGo search                 ││
│   │ • web_fetch         - Jina Reader API                   ││
│   │ • hacker_news_top   - Top HN stories                    ││
│   │ • hacker_news_item  - Get HN story details              ││
│   └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                           ▲
                           │ HTTP/SSE
          ┌────────────────┴────────────────┐
          │                                 │
   WhatsApp #1                        WhatsApp #2
   (agntrick-whatsapp)                (agntrick-whatsapp)
   Connects to toolkit:8080           Connects to toolkit:8080
```

---

## Libraries to Use (All Actively Maintained)

| Library | Version | Purpose | PyPI Downloads |
|---------|---------|---------|----------------|
| `ddgs` | >=9.5.2 | DuckDuckGo search | High, maintained |
| `httpx` | >=0.28.0 | Async HTTP client | Very high, maintained |
| `beautifulsoup4` | >=4.11.0 | HTML parsing | Very high, maintained |
| `fastmcp` | >=2.3.4 | MCP server framework | Already in toolkit |

**Note:** We use Jina Reader API for web fetching (free, no API key, just prefix URL with `r.jina.ai`).

---

## Implementation Plan

### Phase 1: Add New Tools to agntrick-toolkit

**File:** `~/code/agntrick-toolkit/src/agntrick_toolbox/tools/web.py`

```python
"""Web search and fetch tools using proven libraries."""

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

from mcp.server.fastmcp import FastMCP


def register_web_tools(mcp: FastMCP) -> None:
    """Register web search and fetch tools."""

    @mcp.tool()
    async def web_search(query: str, max_results: int = 5) -> str:
        """Search the web using DuckDuckGo.

        Args:
            query: The search query.
            max_results: Maximum number of results (default 5).

        Returns:
            Formatted search results with titles, URLs, and snippets.
        """
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(
                    f"**{r['title']}**\n{r['href']}\n{r['body']}\n"
                )
        return "\n---\n".join(results) if results else "No results found."

    @mcp.tool()
    async def web_fetch(url: str) -> str:
        """Fetch and extract text content from a URL.

        Uses Jina Reader API for clean text extraction.

        Args:
            url: The URL to fetch.

        Returns:
            Extracted text content from the page.
        """
        jina_url = f"https://r.jina.ai/{url}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(jina_url)
            response.raise_for_status()
            return response.text
```

**File:** `~/code/agntrick-toolkit/src/agntrick_toolbox/tools/hackernews.py`

```python
"""Hacker News tools using HTTP API."""

import httpx
from mcp.server.fastmcp import FastMCP

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"


def register_hackernews_tools(mcp: FastMCP) -> None:
    """Register Hacker News tools."""

    @mcp.tool()
    async def hacker_news_top(max_stories: int = 10) -> str:
        """Get top stories from Hacker News.

        Args:
            max_stories: Maximum number of stories to return (default 10).

        Returns:
            Formatted list of top stories with titles, URLs, and points.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get top story IDs
            response = await client.get(f"{HN_API_BASE}/topstories.json")
            story_ids = response.json()[:max_stories]

            # Fetch each story
            stories = []
            for story_id in story_ids:
                story_resp = await client.get(f"{HN_API_BASE}/item/{story_id}.json")
                story = story_resp.json()
                if story:
                    stories.append(
                        f"**{story.get('title', 'No title')}**\n"
                        f"URL: {story.get('url', f'https://news.ycombinator.com/item?id={story_id}')}\n"
                        f"Points: {story.get('score', 0)} | Comments: {story.get('descendants', 0)}"
                    )

            return "\n\n---\n\n".join(stories)

    @mcp.tool()
    async def hacker_news_item(item_id: int) -> str:
        """Get details of a specific Hacker News item.

        Args:
            item_id: The Hacker News item ID.

        Returns:
            Item details including title, URL, text, author, and points.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{HN_API_BASE}/item/{item_id}.json")
            item = response.json()

            if not item:
                return f"Item {item_id} not found."

            result = f"**{item.get('title', 'No title')}**\n"
            result += f"By: {item.get('by', 'unknown')} | Points: {item.get('score', 0)}\n"
            if item.get('url'):
                result += f"URL: {item['url']}\n"
            if item.get('text'):
                # Strip HTML tags from text
                from bs4 import BeautifulSoup
                clean_text = BeautifulSoup(item['text'], 'html.parser').get_text()
                result += f"\n{clean_text}"

            return result
```

**File:** Update `~/code/agntrick-toolkit/src/agntrick_toolbox/server.py`

```python
# Add imports
from .tools.web import register_web_tools
from .tools.hackernews import register_hackernews_tools

# Register new tools (add after existing registrations)
register_web_tools(mcp)        # NEW: web_search, web_fetch
register_hackernews_tools(mcp) # NEW: hacker_news_top, hacker_news_item
```

**File:** Update `~/code/agntrick-toolkit/pyproject.toml`

```toml
dependencies = [
    "fastmcp>=0.1.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "ddgs>=9.5.2",           # NEW: DuckDuckGo search
    "httpx>=0.28.0",         # NEW: Async HTTP client
    "beautifulsoup4>=4.11.0", # NEW: HTML parsing
]
```

---

### Phase 2: Update agntrick MCP Configuration

**File:** `~/code/agents/src/agntrick/mcp/config.py`

Remove the individual MCP servers and keep only the toolkit:

```python
DEFAULT_MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    "toolbox": {
        "url": "http://localhost:8080/sse",
        "transport": "sse",
    },
    # Remote servers (no local resources)
    "kiwi-com-flight-search": {
        "url": "https://mcp.kiwi.com",
        "transport": "sse",
    },
    "fetch": {
        "url": "https://remote.mcpservers.org/fetch/mcp",
        "transport": "http",
    },
}
# Remove: web-forager, hacker-news (now in toolkit)
```

---

### Phase 3: Update agntrick-whatsapp

**File:** `~/code/agntrick-whatsapp/src/agntrick_whatsapp/router.py`

Update the default MCP servers:

```python
# OLD:
DEFAULT_MCP_SERVERS = ["web-forager", "fetch", "toolbox"]

# NEW:
DEFAULT_MCP_SERVERS = ["toolbox"]  # All tools now in one server
```

---

### Phase 4: Docker Configuration

**File:** `~/code/agntrick-toolkit/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for document/media tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    pandoc \
    ffmpeg \
    imagemagick \
    ripgrep \
    fd-find \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir .

# Copy source
COPY src/ src/

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run server
CMD ["python", "-m", "agntrick_toolbox.server"]
```

**File:** `~/code/agntrick-toolkit/docker-compose.yaml`

```yaml
services:
  toolbox:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./workspace:/workspace
    environment:
      - TOOLBOX_WORKSPACE=/workspace
      - TOOLBOX_PORT=8080
      - TOOLBOX_LOG_LEVEL=INFO
      - TOOLBOX_SHELL_ENABLED=false
    restart: unless-stopped
    mem_limit: 300m
    cpus: 1.0
```

---

### Phase 5: Testing Checklist

1. **Unit Tests** (in `agntrick-toolkit/tests/`)
   - [ ] `test_web.py` - Test web_search and web_fetch
   - [ ] `test_hackernews.py` - Test hacker_news_top and hacker_news_item

2. **Integration Tests**
   - [ ] Start toolkit server: `toolbox-server`
   - [ ] Connect from agntrick CLI: `agntrick developer -i "search for python"`
   - [ ] Connect from WhatsApp bot

3. **Memory Test**
   - [ ] Run toolkit container with `mem_limit: 300m`
   - [ ] Verify it stays under 200MB with normal load
   - [ ] Test with 2 concurrent WhatsApp instances

---

## File Changes Summary

| Repository | File | Action |
|------------|------|--------|
| agntrick-toolkit | `src/agntrick_toolbox/tools/web.py` | **CREATE** |
| agntrick-toolkit | `src/agntrick_toolbox/tools/hackernews.py` | **CREATE** |
| agntrick-toolkit | `src/agntrick_toolbox/server.py` | **MODIFY** |
| agntrick-toolkit | `pyproject.toml` | **MODIFY** |
| agntrick-toolkit | `Dockerfile` | **MODIFY** |
| agntrick-toolkit | `docker-compose.yaml` | **MODIFY** |
| agntrick | `src/agntrick/mcp/config.py` | **MODIFY** |
| agntrick-whatsapp | `src/agntrick_whatsapp/router.py` | **MODIFY** |

---

## Memory Estimation

| Component | Memory |
|-----------|--------|
| Python runtime | ~30MB |
| FastMCP server | ~20MB |
| Existing toolbox tools | ~50MB |
| New web tools (ddgs, httpx) | ~30MB |
| Hacker News tools | ~10MB |
| **Total** | **~140-200MB** |

Fits comfortably in 1GB droplet with room for WhatsApp instances.

---

## Rollback Plan

If issues arise:
1. Revert `agntrick/mcp/config.py` to restore original MCP servers
2. Revert `agntrick-whatsapp/router.py` DEFAULT_MCP_SERVERS
3. Toolkit changes are additive - no breaking changes

---

## Questions for Implementation

Before starting, verify:
1. Is `kiwi-com-flight-search` still needed? (it's remote, no impact on memory)
2. Is `fetch` remote server still needed? (toolkit now has `web_fetch`)
3. Should we deprecate the old MCP servers or keep them as fallbacks?
