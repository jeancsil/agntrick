# Sub-15s WhatsApp Response Architecture

**Date**: 2026-04-15
**Status**: Draft
**Target**: All WhatsApp responses under 15 seconds
**Constraint**: $6/month DigitalOcean droplet (1 vCPU, 1GB RAM)

---

## Problem Statement

WhatsApp assistant responses are too slow. Production logs show:

| Query type | Before fixes | After recent fixes | Target |
|-----------|-------------|-------------------|--------|
| Simple chat | ~22s | ~10s | <15s |
| Tool use (1 tool) | ~37s | ~25s | <15s |
| Research (3-5 tools) | unknown | ~15-50s (est.) | <30s |
| Delegation | unknown | ~25-170s (est.) | <30s |

**Root cause**: Every WhatsApp message triggers per-request resource creation (agent, MCP connections, checkpointer, sub-agent) plus 3-4 sequential LLM API calls at 3-7s each.

---

## Evidence

From production log traces on DO droplet (2026-04-14, 19:27 - 20:10 UTC):

### Tool use query ("Barcelona score") — 25.2s breakdown:
```
MCP connection + 19 tools loaded:        ~1s
Router LLM (glm-5.1):                    ~3s  (classify intent + tool_plan)
Executor sub-agent:                      ~14s  (LLM decide 3s + tool 5s + LLM respond 6s)
Responder LLM (glm-5.1):                 ~7s  (format for WhatsApp)
──────────────────────────────────────────────
Total API response:                      ~25s
```

### 12 bottlenecks identified by architecture team:

| # | Bottleneck | Impact | Layer |
|---|-----------|--------|-------|
| 1 | New agent per request | ~8-10s | Init |
| 2 | New MCP connections per request | ~1-2s | Connection |
| 3 | New AsyncSqliteSaver per request | ~0.5-1s | Init |
| 4 | New sub-agent per executor call | ~3-4s | Execution |
| 5 | Tool flattening per execution | ~0.5-1s | Execution |
| 6 | Tool manifest HTTP fetch | ~0.5s | Init |
| 7 | Agent discovery per request | ~0.3s | Init |
| 8 | Tool filtering per execution | ~0.2s | Execution |
| 9 | Sequential MCP connections | variable | Connection |
| 10 | Research: LLM roundtrip explosion | +5-10s per tool | Execution |
| 11 | Delegation: full agent re-init | +25-170s | Execution |
| 12 | Responder LLM for formatting | ~7s | Execution |

---

## Design

### 1. Remove Responder Node (save ~7s)

Replace the responder LLM call with template-based formatting.

**Current responder** (graph.py:745-815):
- LLM call to format for WhatsApp (~7s)
- Truncates to 4096 chars
- Strips tool artifacts
- Matches user language
- Adds markdown

**Proposed `_format_for_whatsapp()` function**:
- Truncate to 4096 chars (string slicing)
- Strip XML tool artifacts via existing `_sanitize_ai_content()` regex
- Strip raw JSON blocks via regex
- No LLM needed — the executor/agent already generates human-readable text

**Risk**: Language matching and "make it concise" are lost. Mitigation: include "respond concisely in the user's language" in the agent's system prompt.

**Impact**: Saves ~7s per request (1 LLM call eliminated).

### 2. Merge Executor + Formatting into Agent Node

Replace the executor sub-agent + responder with a single unified agent node.

**Current flow**:
```
Router → Executor (sub-agent with InMemorySaver) → Responder (LLM)
```

**Proposed flow**:
```
Router → Agent (with tools + WhatsApp instructions in prompt) → _format_for_whatsapp()
```

The agent node uses the existing `create_agent()` with:
- Router's intent + tool_plan injected into system prompt
- Tool filtering from router's classification
- `ToolCallLimitMiddleware` for safety
- WhatsApp formatting instructions in the system prompt (not a separate LLM call)

**For chat intent**: Agent responds directly with no tools (1 LLM call).
**For tool_use**: Agent calls tool, then responds (2 LLM calls + tool execution).
**For research**: Agent calls tools sequentially with middleware limit (N+1 LLM calls).
**For delegate**: Agent calls `invoke_agent` (1 LLM call + delegation).

### 3. Agent Pool per Tenant (save ~8-10s)

Create agents once and reuse them across requests instead of creating new agents per message.

**Current** (whatsapp.py:422-427):
```python
# Every request creates a new agent
async with provider.tool_session() as mcp_tools:
    agent = agent_cls(initial_mcp_tools=mcp_tools, **agent_kwargs)
    result = await agent.run(message)
# Connections closed, agent discarded
```

**Proposed `TenantAgentPool`**:
```python
class TenantAgentPool:
    """One agent per tenant, reused across requests."""

    def __init__(self):
        self._agents: dict[str, AgentBase] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, tenant_id: str, phone: str, **kwargs) -> AgentBase:
        key = f"{tenant_id}:{kwargs.get('_agent_name', 'assistant')}"
        if key in self._agents:
            return self._agents[key]
        async with self._lock:
            if key not in self._agents:
                agent = await self._create(tenant_id, phone, **kwargs)
                self._agents[key] = agent
            return self._agents[key]
```

**Key details**:
- Agent created on first request for a tenant, reused thereafter
- MCP connections stay open (no `tool_session()` — use persistent `get_tools()`)
- Thread ID changes per request (agent.run with different thread_id)
- Checkpointer changes per request (passed to graph.ainvoke via config)
- On memory pressure: evict least-recently-used agents

**Risk**: Stale MCP connections. Mitigation: health check + reconnect on failure.
**Risk**: Memory usage on 1GB droplet. Mitigation: LRU eviction with max pool size.

### 4. MCP Connection Reuse (save ~1-2s)

Keep MCP connections alive across requests instead of reconnecting per message.

**Current**: `tool_session()` opens connections in async context manager, closes on exit.
**Proposed**: Use `get_tools()` which keeps connections open, with background health check.

```python
# In TenantAgentPool._create()
provider = MCPProvider(server_names=allowed_mcp)
mcp_tools = await provider.get_tools()  # Persistent connection
agent = agent_cls(mcp_provider=provider, initial_mcp_tools=mcp_tools, **kwargs)
```

**Health check**: Periodic background task pings toolbox `/health` endpoint. If unhealthy, evict agent from pool (next request recreates with fresh connection).

### 5. AsyncSqliteSaver Pool (save ~0.5s)

Reuse database connections instead of creating new `AsyncSqliteSaver` per request.

**Current**: `AsyncSqliteSaver.from_conn_string()` per request.
**Proposed**: One `AsyncSqliteSaver` per tenant database, kept in the agent pool.

The checkpointer is passed to `graph.ainvoke(config)` — it doesn't need to be in the agent constructor. Store it alongside the agent in the pool.

### 6. Move Agent Discovery to Startup (save ~0.3s)

**Current**: `AgentRegistry.discover_agents()` called per request (whatsapp.py:381).
**Proposed**: Call once at FastAPI app startup via lifespan handler.

---

## Revised Graph Architecture

```
Before (4 nodes):
  Summarize → Router → Executor → Responder
                3s       14s         7s     = 25s (tool_use)

After (3 nodes):
  Summarize → Router → Agent → _format_for_whatsapp()
                3s      12s        0s      = 15s (tool_use)
```

### Graph definition changes:

```python
def create_assistant_graph(model, tools, system_prompt, ...):
    graph = StateGraph(AgentState)
    graph.add_node("summarize", _summarize)
    graph.add_node("router", _router)
    graph.add_node("agent", _agent)  # unified executor + responder
    graph.set_entry_point("summarize")
    graph.add_edge("summarize", "router")
    graph.add_conditional_edges("router", route_decision, {
        "agent": "agent",       # tool_use, research, delegate
        "respond": END,         # chat — router can respond directly for chat
    })
    graph.add_edge("agent", END)
    return graph.compile(checkpointer=checkpointer)
```

### Chat intent fast path:

For "chat" intent, the router can respond directly without the agent node. The router already has the user's messages — it just needs to generate a response instead of classifying intent.

This is a merge of the old router + responder for chat: 1 LLM call instead of 2.

```
Chat:    Summarize → Router(responds directly)  = 1 LLM call = ~5s
Tool:    Summarize → Router → Agent            = 2 LLM calls + tool = ~15s
```

---

## Expected Performance

### Simple chat (e.g., "What can you do?")
```
MCP (reused):          ~0s
Router-respond (glm-5.1): ~5s  (classify + respond in single call)
Template format:          ~0s
──────────────────────────────
Total:                    ~5s
```

### Tool use (e.g., "Barcelona score")
```
MCP (reused):          ~0s
Router (glm-5.1):       ~3s  (classify intent + tool_plan)
Agent decide (glm-5.1):  ~3s  (call tool)
Tool execution:          ~5s  (web_search)
Agent respond (glm-5.1): ~4s  (generate response)
Template format:          ~0s
──────────────────────────────
Total:                   ~15s
```

### Research (3 tools)
```
Router:                          ~3s
Agent (3 tool calls + responses): ~18s
Template format:                  ~0s
──────────────────────────────────
Total:                           ~21s
```

### Delegation
```
Router:                  ~3s
Agent invoke_agent:      ~3s  (LLM call)
Delegated agent (pooled): varies (but no re-init overhead)
Template format:          ~0s
──────────────────────────────
Total:                   ~25s+ (depends on delegated agent)
```

---

## Implementation Sequence

### Phase 1: Remove Responder (2-3 days)
- Implement `_format_for_whatsapp()` template function
- Modify `create_assistant_graph` to 3-node graph
- Add WhatsApp formatting instructions to agent system prompt
- Update tests

### Phase 2: Agent Pool (2-3 days)
- Implement `TenantAgentPool` class
- Modify `whatsapp_webhook` to use pool
- Move `AgentRegistry.discover_agents()` to FastAPI startup
- Add pool size limits and LRU eviction
- Update tests

### Phase 3: MCP + DB Connection Reuse (1-2 days)
- Replace `tool_session()` with persistent `get_tools()` in pool
- Store `AsyncSqliteSaver` in pool alongside agent
- Add background health check for MCP connections
- Update tests

### Phase 4: Chat Fast Path (1 day)
- Modify router to respond directly for "chat" intent
- Skip agent node entirely for simple conversations
- Update tests

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Stale MCP connections | Background health check, evict+recreate on failure |
| Memory pressure on 1GB RAM | LRU eviction, max pool size (e.g., 10 agents) |
| Lost language matching | Include "respond in user's language" in system prompt |
| Lost "make it concise" | Include "keep response under 4096 chars, be concise" in prompt |
| Agent state leaking between requests | Use different thread_id per request, verify checkpointer isolation |
| Template formatting produces ugly output | Log when truncation occurs, monitor quality |

---

## What We Keep

- **Router node**: Intent classification, tool filtering, URL handling, paywall detection
- **Summarize node**: Conversation compression, TTL management
- **ToolCallLimitMiddleware**: Prevents tool spirals
- **Tool flattening**: `_make_flat_tool()` for GLM model compatibility
- **Artifact sanitization**: `_sanitize_ai_content()` for XML pseudo-tool-calls
- **All existing safety features**: Intent-based limits, guided prompts, error handling
