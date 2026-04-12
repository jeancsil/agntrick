# Token-Efficient Conversation Memory

**Date:** 2026-04-12
**Status:** Draft
**Execution:** subagent-driven-development (sonnet/haiku)

## Problem

Every WhatsApp message from the same phone reuses the same thread_id
(`whatsapp:{tenant_id}:{phone}`). The LangGraph checkpointer loads all
previous messages into state on every invocation. Currently:

- Router receives up to 4K chars (~1.5K tokens) of raw messages
- Responder receives up to 8K chars (~3K tokens) of raw messages
- No summarization — messages are sent verbatim
- Total: ~4.5K tokens of conversation context per turn

For mostly single-turn conversations, this wastes tokens and slows LLM
response times.

## Goal

Reduce the conversation context from ~4.5K tokens to ~500 tokens per turn,
achieving faster LLM response times while preserving conversation context
through summarization.

## Design

### Architecture

**Current graph:**
```
Router → Executor → Responder
```

**Proposed graph:**
```
Summarize → Router → Executor → Responder
```

A new `summarize_node` runs before the router. It compresses old messages
into a running summary and stores it in state. Downstream nodes inject the
summary as context instead of raw message history.

The SQLite checkpointer remains as the full archive — summarization only
affects what's loaded into the in-memory state for the current turn.

### AgentState Extension

Add a `context` field to `AgentState`:

```python
class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str
    tool_plan: str | None
    progress: list[str]
    final_response: str | None
    context: dict[str, Any]  # NEW: running_summary, conversation_age
```

The `context` dict holds:
- `running_summary` (str): Compressed summary of older messages
- `summary_updated_at` (float): Unix timestamp of last summarization

### Summarization Node

Location: `graph.py` as a new async function `summarize_node`.

```python
async def summarize_node(
    state: AgentState,
    config: RunnableConfig,
    *,
    model: Any,
    max_tokens: int = 500,        # threshold to trigger summarization
    keep_recent: int = 2,          # messages to keep unsummarized
    summary_max_tokens: int = 128, # max tokens for summary output
    ttl_hours: int = 24,           # hours before summary is considered stale
) -> dict:
```

**Logic:**

1. Count tokens in `state["messages"]` using `count_tokens_approximately`
   from `langchain_core.messages.utils`
2. If total tokens < `max_tokens` → return `{}` (no-op, zero overhead)
3. If total tokens >= `max_tokens`:
   a. Keep last `keep_recent` messages (current user msg + last AI reply)
   b. Take everything before those as "old messages"
   c. If `state["context"]["running_summary"]` exists and is not stale:
      - Send to LLM: "Extend this summary with the new messages:
        {existing_summary}\n\nNew messages:\n{old_messages}"
   d. If no existing summary:
      - Send to LLM: "Summarize this conversation concisely:\n{old_messages}"
   e. Store result in `state["context"]["running_summary"]`
   f. Return `RemoveMessage` directives for summarized messages
4. If LLM summarization call fails → log warning, return `{}` (graceful
   degradation — proceeds with full message history)

**TTL check:** If `summary_updated_at` is > `ttl_hours` ago, clear the
summary and start fresh (handles conversation reset).

### Summary Injection

**Router node** (`router_node`):

Before sending messages to the LLM, check for a running summary:

```python
summary = state.get("context", {}).get("running_summary")
if summary:
    context_window = [
        SystemMessage(content=f"Previous conversation summary: {summary}"),
        *context_window,
    ]
```

**Responder node** (`responder_node`):

Same pattern for chat intent:

```python
summary = state.get("context", {}).get("running_summary")
if summary:
    msgs = [
        SystemMessage(content=f"Previous conversation summary: {summary}"),
        *msgs,
    ]
```

For tool_use/research/delegate intents — no change needed (responder only
receives executor output, not conversation history).

### Graph Wiring

Update `create_assistant_graph` to add the summarize node:

```python
graph = StateGraph(AgentState)
graph.add_node("summarize", _summarize)
graph.add_node("router", _router)
graph.add_node("executor", _executor)
graph.add_node("responder", _responder)
graph.set_entry_point("summarize")
graph.add_edge("summarize", "router")
graph.add_conditional_edges("router", route_decision, ...)
graph.add_edge("executor", "responder")
graph.add_edge("responder", END)
```

### Token Budgets

After summarization, the budgets can be tightened:

| Component | Current Budget | New Budget | Notes |
|-----------|---------------|------------|-------|
| Router messages | 4K chars (~1.5K tokens) | Summary (~128 tokens) + 2 msgs | Summary replaces raw history |
| Responder (chat) | 8K chars (~3K tokens) | Summary (~128 tokens) + 2 msgs | Summary replaces raw history |
| Executor | 1 msg (last HumanMessage) | No change | Already optimized |
| Summarize node | N/A | ~500 tokens in, ~128 tokens out | Only triggers when needed |

### Performance Impact

**Single-turn conversations (majority):**
- Summarize node: no-op (0ms, 0 tokens)
- Router: same as today
- No speed regression

**Multi-turn conversations (5+ messages):**
- Summarize node: 1 LLM call (~500 tokens in, ~128 out) — amortized cost
- Router: ~85% fewer input tokens → faster response
- Responder: ~90% fewer input tokens → faster response
- Net result: faster overall despite one extra summarization call

**Long conversations (20 messages):**
- Summary replaces 18 messages (~4K tokens) with ~128 tokens
- Each subsequent turn saves ~3.5K tokens on router+responder calls
- Single summarization call pays for itself immediately

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Summarization LLM call fails | Log warning, proceed with full message history |
| `context` field missing from state | Default to empty dict, no summary |
| Summary grows too large | TTL resets it; summarization compresses it |
| Checkpointer has no previous messages | Summarize node is a no-op |

### Testing Plan

| Test | What it verifies |
|------|-----------------|
| `test_summarize_node_noop_below_threshold` | < 500 tokens → returns `{}` |
| `test_summarize_node_summarizes_above_threshold` | > 500 tokens → generates summary, removes old messages |
| `test_summarize_node_extends_existing_summary` | Existing summary → extends it, doesn't recreate |
| `test_summarize_node_ttl_expires_summary` | Summary > 24h old → clears it |
| `test_summarize_node_llm_failure_graceful` | LLM fails → returns `{}`, no crash |
| `test_router_injects_summary` | Router prepends summary as SystemMessage |
| `test_responder_injects_summary` | Responder prepends summary for chat intent |
| `test_graph_full_flow_with_summarization` | Integration: 10+ messages through full graph |

### Files to Modify

| File | Change |
|------|--------|
| `src/agntrick/graph.py` | Add `summarize_node`, update `AgentState`, modify `router_node`/`responder_node` for summary injection, update `create_assistant_graph` wiring |
| `tests/test_graph.py` | Add all tests from testing plan |

### New Dependency

None. Uses existing `langchain_core.messages.utils.count_tokens_approximately`
for token counting. The summarization LLM call uses the same model instance
already configured for the agent.

### Backward Compatibility

- `AgentState` gains a `context` field with `total=False` — existing code that
  doesn't set it continues to work (defaults to missing/not present)
- Nodes that don't check for summary simply ignore it
- The graph still works if summarize_node is removed (entry point can be
  changed back to router)

### State Persistence

The `context` field is a plain dict (no reducer). LangGraph replaces non-reducer
fields on each node return. Since the checkpointer stores the full checkpoint
including non-reducer fields, `context` persists across turns. The summarize
node returns the full `context` dict each time (including existing keys), and
the checkpointer saves it for the next invocation.

## Open Questions

None — design is self-contained.
