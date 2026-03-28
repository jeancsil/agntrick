# Unified Tool-Aware Architecture Design Spec

> **Status:** Draft
> **Created:** 2026-03-22
> **Author:** System Architecture Team

## Problem Statement

The agntrick ecosystem has fragmented tool configuration across multiple repositories:
- Each agent declares MCP servers independently (`mcp_servers=["web-forager", "fetch"]`)
- Agents don't know what tools other agents have access to
- System prompts are hardcoded and don't reflect actual available tools
- No runtime capability discovery mechanism exists

This leads to:
1. **Inconsistency**: Different agents have different tool access for similar tasks
2. **Maintenance burden**: Tool changes require updates in multiple places
3. **Poor discoverability**: Agents can't tell users "what can we do?"
4. **Redundant configurations**: Same tools declared repeatedly

## Proposed Solution

### Core Principle: Single Source of Truth

**agntrick-toolkit** becomes the canonical tool provider. All agents use `["toolbox"]` by default and discover capabilities at runtime.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    agntrick-toolkit (Port 8080)                 │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Tool Categories                       │   │
│  │  • web: web_search, web_fetch                           │   │
│  │  • hackernews: hacker_news_top, hacker_news_item        │   │
│  │  • document: pdf_extract_text, pandoc_convert           │   │
│  │  • data: jq_query, yq_query                             │   │
│  │  • media: ffmpeg_convert, imagemagick_convert           │   │
│  │  • search: ripgrep_search, fd_find                      │   │
│  │  • git: git_status, git_log                             │   │
│  │  • shell: run_shell (fallback)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Tool Manifest Endpoint                      │   │
│  │  GET /manifest → JSON with all tools + descriptions     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ SSE Transport
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     agntrick (Agent Framework)                   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Tool Manifest Cache                         │   │
│  │  - Fetched at startup from toolbox                      │   │
│  │  - Refreshable on demand                                │   │
│  │  - Used to generate dynamic prompts                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Agent Registry (Enhanced)                   │   │
│  │  - All agents default to mcp_servers=["toolbox"]        │   │
│  │  - Agents declare capabilities, not servers             │   │
│  │  - Cross-agent tool awareness                           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Component Design

### 1. Tool Manifest (agntrick-toolkit)

**Endpoint:** `GET /manifest`

**Response:**
```json
{
  "version": "1.0.0",
  "tools": [
    {
      "name": "web_search",
      "category": "web",
      "description": "Search the web using DuckDuckGo",
      "parameters": {
        "query": {"type": "string", "required": true},
        "max_results": {"type": "integer", "default": 5}
      },
      "examples": [
        "web_search(query='Python async best practices')"
      ]
    }
  ],
  "categories": {
    "web": {"description": "Web search and content fetching"},
    "hackernews": {"description": "Tech news from Hacker News"},
    "document": {"description": "PDF and document processing"},
    "data": {"description": "JSON/YAML/CSSV query and transformation"},
    "media": {"description": "Audio/video/image conversion"},
    "search": {"description": "File content and name search"},
    "git": {"description": "Git repository operations"}
  }
}
```

### 2. Manifest Client (agntrick)

**Location:** `src/agntrick/tools/manifest.py`

**Responsibilities:**
- Fetch manifest from toolbox server
- Cache results with TTL
- Provide query interface for agents

```python
class ToolManifest:
    """Runtime tool discovery from toolbox server."""

    def get_tools_by_category(self, category: str) -> list[ToolInfo]: ...
    def get_all_tools(self) -> list[ToolInfo]: ...
    def get_tool(self, name: str) -> ToolInfo | None: ...
    def refresh(self) -> None: ...
```

### 3. Dynamic Prompt Generation

**Location:** `src/agntrick/prompts/generator.py`

**Approach:**
- Base prompts stored in `prompts/{agent}.md`
- Tool sections injected dynamically at runtime
- Agents can request specific tool categories

```python
def generate_system_prompt(
    agent_name: str,
    tool_categories: list[str] | None = None,  # None = all tools
    manifest: ToolManifest,
) -> str:
    """Generate system prompt with tool documentation."""
    base = load_prompt(agent_name)
    tools_section = format_tools_section(manifest, tool_categories)
    return base + "\n\n" + tools_section
```

### 4. Agent Capability Declaration

**Before (current):**
```python
@AgentRegistry.register("learning", mcp_servers=["fetch", "web-forager"])
class LearningAgent(AgentBase):
    ...
```

**After (proposed):**
```python
@AgentRegistry.register(
    "learning",
    capabilities=["web_research", "content_fetching"],  # Semantic capabilities
    tool_categories=["web", "document"],  # Which toolbox categories to document
)
class LearningAgent(AgentBase):
    ...
```

### 5. Cross-Agent Tool Awareness

**New Tool:** `list_capabilities`

Allows any agent to discover what the system can do:

```python
@mcp.tool()
async def list_capabilities() -> str:
    """List all available tools and which agents can use them."""
    ...
```

## Migration Path

### Phase 1: Toolkit Consolidation ✅ (Complete)
- All tools in toolbox server
- Remove web-forager, hacker-news from individual configs

### Phase 2: Manifest System
- Add `/manifest` endpoint to toolbox
- Create `ToolManifest` client in agntrick
- Cache and refresh mechanism

### Phase 3: Dynamic Prompts
- Create prompt generator
- Update agents to use dynamic tool documentation
- Deprecate hardcoded tool lists in prompts

### Phase 4: Capability Discovery
- Add `list_capabilities` tool
- Update agent registry to track capabilities
- Enable cross-agent tool awareness

## Affected Repositories

| Repository | Changes |
|------------|---------|
| agntrick-toolkit | Add `/manifest` endpoint |
| agntrick | ToolManifest client, dynamic prompts, registry updates |
| agntrick-whatsapp | Use new prompt generation system |

## Success Criteria

1. **Single MCP Config**: All agents use `["toolbox"]` by default
2. **Runtime Discovery**: Agents can query available tools at runtime
3. **Dynamic Prompts**: Tool documentation generated from manifest
4. **Capability Awareness**: `list_capabilities` shows full system capabilities
5. **Zero Breaking Changes**: Existing agent code works without modification

## Open Questions

1. **Manifest TTL**: How often should the manifest cache refresh? (Proposed: 5 minutes)
2. **Fallback Behavior**: What happens if toolbox is unavailable? (Proposed: Use cached manifest, warn on stale)
3. **Custom Servers**: How to handle agents that need non-toolbox MCP servers? (Proposed: Allow override, but document)
