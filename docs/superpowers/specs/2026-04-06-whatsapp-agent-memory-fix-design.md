# Fix WhatsApp Agent Memory Loss

**Date**: 2026-04-06
**Status**: Approved
**Branch**: `feat/smarter-whatsapp-assistant`

---

## Problem

The assistant agent loses conversation context between turns. When the agent asks a question and the user replies "yes", the agent has no idea what they're referring to.

### Root Cause

Two issues in `src/agntrick/graph.py`:

1. **Responder truncates messages** (line 339): `_truncate_messages()` strips history to only the last `HumanMessage`, even for `chat` intent. The function was designed to isolate the executor sub-agent from poisoned state, but it's also applied to the responder's chat path.

2. **Router is blind to context** (line 215): Only receives the last message, so it can't correctly classify follow-up questions (e.g., "yes", "and in Paris?", "what about that other thing?").

### Symptom Flow

```
Turn 1: User asks "What's the weather in Tokyo?"
  → Router: receives only last message → classifies as "tool_use"
  → Executor: runs tool, returns weather data
  → Responder: formats output → "The weather in Tokyo is..."

Turn 2: User says "And in Paris?"
  → Router: receives only [HumanMessage("And in Paris?")] → no context
     → May misclassify as "chat" since it looks like a standalone question
  → If classified as "chat":
     → Responder: _truncate_messages() returns [HumanMessage("And in Paris?")]
     → LLM sees no prior conversation → "I don't understand your question"
```

---

## Design

### Change 1: Fix responder for chat intent

**File**: `src/agntrick/graph.py`, lines 338-351

Replace `_truncate_messages(state["messages"])` with `state["messages"]` for `chat` intent only. The full conversation history flows through so the responder can understand follow-ups.

Keep `_truncate_messages()` for executor invocations — that isolation is intentional and prevents failure repetition.

```python
# Before (line 339)
msgs = _truncate_messages(state["messages"])

# After
msgs = state["messages"]  # Chat needs full context for follow-ups
```

### Change 2: Give router a sliding window

**File**: `src/agntrick/graph.py`, lines 205-225

Send the last N messages (default 5) to the router instead of just the last one. This lets it understand follow-up questions while keeping the context window manageable.

```python
# Before
last_message = state["messages"][-1]
response = await model.ainvoke([SystemMessage(ROUTER_PROMPT), last_message])

# After
ROUTER_CONTEXT_WINDOW = 5
context_window = state["messages"][-ROUTER_CONTEXT_WINDOW:]
response = await model.ainvoke([SystemMessage(ROUTER_PROMPT), *context_window])
```

### Change 3: Add debug logging

Add `logger.debug()` calls in router, executor, and responder nodes showing:
- Message count and types received
- Content preview (first 100 chars per message)

This enables local debugging via `agntrick chat -v`.

### Change 4: Multi-turn integration test

**File**: `tests/test_graph.py`

Add a test that verifies multi-turn conversation context is preserved:

```python
async def test_chat_intent_remembers_previous_turn():
    """Verify the responder receives conversation history for chat intent."""
    # Turn 1: simple question
    # Turn 2: follow-up that only makes sense with context
    # Assert: agent understands the follow-up
```

---

## What We're NOT Changing

- **Executor isolation**: The executor sub-agent still uses `_truncate_messages()` and unique thread IDs. This is correct — it prevents failure poisoning.
- **Memory infrastructure**: SQLite checkpointer, thread IDs, and session management are all working correctly. No changes needed.
- **WhatsApp webhook**: Thread ID construction and checkpointer setup are correct.

---

## Testing Plan

1. **Unit test**: Multi-turn conversation test in `tests/test_graph.py`
2. **Local smoke test**: `agntrick chat "What's 2+2?" -v` then `agntrick chat "And 3+3?" -v`
3. **CI**: `make check && make test` — all existing tests must still pass

---

## Risk

Low. The changes are small and targeted:
- Change 1 removes a single function call for chat intent
- Change 2 adds a few more messages to the router LLM call (minor token increase)
- Both changes only affect the `assistant` agent's graph, not other agents

The `_truncate_messages` function docstring already says "For the responder node (chat intent), pass through all messages since it needs conversation context" — but the implementation doesn't match the docstring. This fix aligns code with intent.
