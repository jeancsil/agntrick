# Architecture Diagrams Design

**Date**: 2026-04-07
**Status**: Approved

## Goal

Add Mermaid diagrams to AGENTS.md that visualize the execution flow of the agntrick framework, highlight synchronous blocking calls, and stay in sync via a behavioral rule.

## Scope

- Two Mermaid diagrams added to AGENTS.md
- One blocking calls table
- One behavioral rule addition
- No new files — everything goes into AGENTS.md

## Design

### Diagram 1: End-to-End Execution Flow

A `flowchart TD` with three color-coded subgraphs:

- **Entry Points** (blue): CLI (`agntrick run/chat`), API (WhatsApp webhook via Go Gateway), Chat (TestClient)
- **Agent Layer** (green): Registry lookup → Agent instantiation → Lazy initialization (tool manifest fetch → MCP tool loading → graph creation)
- **Output** (gray): Response returned to user

Red-highlighted nodes for blocking calls:
- `_fetch_tool_manifest()` — HTTP call with circuit breaker
- `agent_invocation.run_in_new_loop()` — blocking thread + new event loop
- Sequential MCP connection — `for name in config: await stack.enter_async_context(...)`

### Diagram 2: Graph Detail (3-Node StateGraph)

A `flowchart LR` showing the internal routing:

1. **Router** — classifies into `chat | tool_use | research | delegate`
2. **Conditional edge**:
   - `chat` → Responder directly
   - `tool_use | research | delegate` → Executor
3. **Executor** sub-elements:
   - Tool filtering by intent
   - Sub-agent creation (`create_agent`) — annotated as **recursive** (triggers a full End-to-End flow via agent_invocation, which re-enters the same lifecycle)
   - Tool call limits (2/5/1 per intent)
   - MCP output flattening
   - Artifact sanitization
4. **Executor feedback loop** — dotted line back to Router after tool execution, representing the ReAct loop: after tools execute, the agent may re-classify whether it's done or needs more tools
5. **Responder** — formats for WhatsApp
6. **END**

Red-highlighted: `create_agent()` sync factory (intentional, fast). Dotted lines: feedback loop and recursion hint.

### Blocking Calls Table

| Location | Pattern | Impact | Intentional? |
|---|---|---|---|
| `tools/agent_invocation.py` | `thread.join()` + new event loop | Blocks up to 60s on delegation | Necessary (needs isolated loop) |
| `mcp/provider.py` | Sequential `await stack.enter_async_context()` | N*M startup delay | Yes (avoids anyio cleanup bugs) |
| `graph.py` | `create_agent()` sync factory | Negligible (in-memory only) | Yes (fast) |
| `agent.py` | `_fetch_tool_manifest()` HTTP | 5s+ if toolbox slow | Circuit breaker mitigates |

### Behavioral Rule

Added to "Behavioral Rules" section in AGENTS.md:

> - **When modifying** `agent.py`, `graph.py`, `mcp/provider.py`, `tools/manifest.py`, `api/routes/`, or `whatsapp/webhook.py`: verify the "Execution Flow" Mermaid diagrams still reflect the current code.

## Placement in AGENTS.md

Diagrams replace the existing "## Key Architecture Concepts" section with a new "## Execution Flow" section containing both diagrams, the blocking calls table, and updated architecture text.

The behavioral rule is appended to the existing "## Behavioral Rules" section.

## Maintenance

- Single source of truth: AGENTS.md only
- Behavioral rule ensures agents check diagrams when modifying core flow files
- No automated tests for diagram accuracy (behavioral rule is sufficient per user preference)
