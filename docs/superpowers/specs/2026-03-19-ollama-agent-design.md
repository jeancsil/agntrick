# OllamaAgent Design Specification

**Date:** 2026-03-19
**Status:** Draft
**Author:** Claude (via brainstorming session)

## Overview

Redesign the OllamaAgent as a powerful local AI orchestrator running on GLM-4.7-Flash via Ollama. The agent will have full web capabilities via MCP servers and the ability to delegate to specialized agents through a new AgentInvocationTool.

## Goals

1. Create a versatile local AI companion for research, knowledge work, creative tasks, and orchestration
2. Enable agent-to-agent delegation with proper context handling
3. Ensure robust error handling with automatic recovery
4. Prevent the bug where OllamaAgent used the wrong prompt (developer prompt)

## Non-Goals

- Code editing capabilities (belongs to DeveloperAgent)
- Direct file system access outside project directory
- Persistent conversation state across delegations (each delegation is fresh)

## Architecture

### Component Overview

```
OllamaAgent
├── LocalReasoningLLM (GLM-4.7-Flash via Ollama)
├── System Prompt (Orchestrator Identity)
├── Local Tools
│   └── AgentInvocationTool
└── MCP Tools
    ├── web-forager (web search)
    ├── fetch (URL content extraction)
    └── hacker-news (tech news)
```

### Data Flow

1. User sends input to OllamaAgent
2. OllamaAgent analyzes the request using its system prompt
3. Agent decides: handle directly OR delegate to specialized agent
4. If delegating: AgentInvocationTool creates fresh session with context-rich prompt
5. Delegated agent returns result
6. OllamaAgent synthesizes and responds to user

## Components

### 1. System Prompt

**File:** `src/agntrick/prompts/ollama.md`

The prompt establishes OllamaAgent as:
- A powerful local AI assistant running on GLM-4.7-Flash
- The central orchestrator capable of delegating to specialized agents
- A versatile tool for research, knowledge work, and creative tasks

**Key Prompt Sections:**
- Identity and capabilities
- Available MCP tools (web-forager, fetch, hacker-news)
- Agent delegation protocol with context inclusion
- Decision framework (when to delegate vs handle)
- Error recovery protocol (find alternatives before reporting failure)
- Communication style guidelines

### 2. MCP Servers

| Server | Transport | Purpose |
|--------|-----------|---------|
| web-forager | stdio (uvx) | Web search for current information |
| fetch | http | Extract clean content from URLs |
| hacker-news | stdio (npx) | Tech news and discussions |

**Registration:**
```python
@AgentRegistry.register("ollama", mcp_servers=["web-forager", "fetch", "hacker-news"])
```

### 3. AgentInvocationTool

**File:** `src/agntrick/tools/agent_invocation.py`

| Property | Value |
|----------|-------|
| Name | `invoke_agent` |
| Input | JSON: `{"agent_name": string, "prompt": string, "timeout": number?}` |
| Output | Agent response as string (or error message) |

**Delegatable Agents:**
- `developer` - Code exploration and file operations
- `learning` - Educational content and tutorials
- `news` - Current news and events
- `youtube` - Video transcript analysis

**Context Handling:**
- Delegated agent starts fresh (no conversation history)
- OllamaAgent MUST include all necessary context in delegation prompt
- Prompt instructs agent to summarize relevant context when delegating

**Implementation Notes:**
- Async agent.run() called from sync tool.invoke() via `asyncio.run()`
- Never raises exceptions - always returns error strings
- Validates agent name against registry

### 4. Error Handling

| Scenario | Behavior |
|----------|----------|
| Agent not found | Return error listing valid agents, suggest alternatives |
| Agent timeout | Return partial result + offer retry or handle directly |
| Agent crashes | Catch exception, attempt task directly if possible |
| MCP unavailable | Use alternative MCP tools, fallback gracefully |
| Invalid input | Clear error message with expected format |

**Recovery Protocol (in system prompt):**
1. Try alternative approach first
2. Attempt task yourself if within capabilities
3. Only report failure after exhausting options
4. Explain what was tried and why it failed

### 5. OllamaAgent Implementation

**File:** `src/agntrick/agents/ollama.py`

Changes from current implementation:
- Load `ollama` prompt instead of `developer`
- Include AgentInvocationTool in local_tools()
- Register with expanded MCP servers

```python
@AgentRegistry.register("ollama", mcp_servers=["web-forager", "fetch", "hacker-news"])
class OllamaAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return load_prompt("ollama")  # Changed from "developer"

    def local_tools(self) -> Sequence[Any]:
        return [AgentInvocationTool().to_langchain_tool()]
```

## Testing Strategy

### Test Files

| File | Purpose |
|------|---------|
| `tests/test_ollama_agent.py` | Main agent tests |
| `tests/tools/test_agent_invocation.py` | Tool-specific tests |

### Test Cases

**OllamaAgent Tests:**
- Prompt loads `ollama.md`, not `developer.md`
- MCP tools (web-forager, fetch, hacker-news) are available
- AgentInvocationTool is in local_tools
- Regression: `assert "Principal Software Engineer" not in system_prompt`

**AgentInvocationTool Tests:**
- Valid delegation returns agent response
- Agent not found returns error with available agents
- Timeout returns partial result + notice
- Agent crash returns error string (no exception raised)
- Invalid JSON input returns clear error message

**Integration Tests:**
- End-to-end orchestration flow (mocked)
- Context is included in delegation prompts

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `src/agntrick/prompts/ollama.md` | Create | New orchestrator prompt |
| `src/agntrick/agents/ollama.py` | Modify | Use ollama prompt, add tool, expand MCPs |
| `src/agntrick/tools/agent_invocation.py` | Create | New AgentInvocationTool |
| `src/agntrick/tools/__init__.py` | Modify | Export AgentInvocationTool |
| `tests/test_ollama_agent.py` | Create | Agent tests |
| `tests/tools/test_agent_invocation.py` | Create | Tool tests |

## Success Criteria

1. OllamaAgent has its own unique prompt (not developer's)
2. Agent can search web, fetch URLs, access Hacker News
3. Agent can delegate to other agents with context-rich prompts
4. Error handling includes recovery attempts before failure
5. All tests pass with >80% coverage on new code
6. `make check && make test` passes

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| AgentInvocationTool async/sync bridging issues | Use `asyncio.run()` with proper event loop handling |
| Recursive delegation (agent calling itself) | Block "ollama" from delegatable agents list |
| Long delegation chains causing delays | Default timeout + prompt instruction to keep delegations focused |
| MCP server startup latency | Lazy loading already handled by AgentBase |
