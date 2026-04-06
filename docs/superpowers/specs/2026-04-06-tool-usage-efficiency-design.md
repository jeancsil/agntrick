# Fix Agent Tool Usage Efficiency

**Date**: 2026-04-06
**Status**: Approved
**Branch**: `feat/smarter-whatsapp-assistant`

---

## Problem

Agents waste tool call budget and ignore good data. The model makes 5+ tool calls even when the first call returned usable data, then reports "unable to retrieve content" despite having good results.

### Root Cause

From production logs (g1.globo.com news request):

```
msg[1]  web_search → 2060 chars ✓ (g1 headlines!)
msg[3]  web_fetch  → 0 chars ✗ (empty)
msg[5]  curl_fetch → 4194 chars raw HTML
msg[7]  web_search → 1393 chars (less relevant)
msg[9]  web_fetch  → 5254 chars ✓
msg[11] web_search → LIMIT EXCEEDED
msg[13] "unable to retrieve content" ← ignores msg[2]!
```

Three issues:
1. **ToolCallLimitMiddleware**: Fixed `run_limit=5` regardless of intent. `tool_use` needs 1-2 calls max.
2. **Weak guided prompt**: "USE IT to answer" is not strong enough. Model keeps calling tools.
3. **Agent delegation**: `invoke_agent` creates fresh agents with zero conversation context.

---

## Design

### Change 1: Intent-Specific Tool Limits

**File**: `src/agntrick/graph.py`

Replace fixed `run_limit=5` with intent-aware limits:

```python
_INTENT_TOOL_LIMITS: dict[str, int] = {
    "tool_use": 2,   # 1 primary + 1 fallback
    "research": 5,    # multi-step research
    "delegate": 1,    # single agent invocation
}
_DEFAULT_TOOL_LIMIT = 3
```

In `executor_node`, use the intent to determine the limit:

```python
tool_limit = _INTENT_TOOL_LIMITS.get(intent, _DEFAULT_TOOL_LIMIT)
sub_agent = create_agent(
    ...
    middleware=[ToolCallLimitMiddleware(run_limit=tool_limit, exit_behavior="continue")],
)
```

### Change 2: Rewrite Guided Prompts

**File**: `src/agntrick/graph.py`, executor_node guided prompts

For `tool_use` intent, replace the current weak prompt with an aggressive stop instruction:

```python
f"""

## TOOL USE — CALL ONCE AND RESPOND

The router has determined this query requires: {tool_plan}

EXECUTE EXACTLY THESE STEPS:
1. Call the tool: {tool_plan}
2. Read the tool's response
3. Respond to the user using the data from step 2

EXECUTE EXACTLY THESE STEPS:
1. Call the tool: {tool_plan}
2. Evaluate the tool's response:
   - Does it answer the user's question? → Respond now, STOP
   - Partial data? → You may try ONE more targeted tool to fill the gap, then respond
   - Error/empty? → Try ONE alternative tool, then respond with whatever you have
3. Respond to the user — NEVER say "unable to retrieve" if ANY tool returned data

MANDATORY RULES:
- You are allowed 1-2 tool calls maximum
- After each tool call, ask: "Can I answer the user's question now?" If yes, STOP and respond
- NEVER call more tools just to get "better" data — respond with what you have
"""
```

For `delegate` intent, add context injection instruction:

```python
f"""

## DELEGATION
Use the invoke_agent tool with these parameters:
{tool_plan}

IMPORTANT: Include ALL relevant context from the conversation in the "prompt" field.
The delegated agent has no memory — it only sees what you put in the prompt.

Do NOT use any other tools. Just invoke the agent and return its result.
"""
```

### Change 3: Fix assistant.md Conflicting Guidance

**File**: `src/agntrick/prompts/assistant.md`

Remove "Use tools proactively" (line 121) — it conflicts with "Maximum 2-3 tool calls." Add explicit stopping conditions:

```markdown
<stopping-conditions>
You MUST stop calling tools and respond to the user when:
1. The user's question can be answered with the information you have
2. You have made the maximum allowed tool calls
3. A tool returned data that addresses the user's query (even partially)
</stopping-conditions>
```

### Change 4: Add LLM Call Logging

**File**: `src/agntrick/graph.py`

Add a helper function that wraps `model.ainvoke()` to log input/output for local debugging:

```python
async def _log_llm_call(
    model: Any,
    messages: list,
    *,
    node: str,
) -> Any:
    """Log LLM call details for debugging."""
    input_msgs = len(messages)
    input_chars = sum(len(str(m.content)) for m in messages if hasattr(m, 'content'))
    logger.debug(
        "[llm] node=%s input_msgs=%d input_chars=%d",
        node, input_msgs, input_chars,
    )
    start = time.monotonic()
    response = await model.ainvoke(messages)
    elapsed = time.monotonic() - start
    output_chars = len(str(response.content)) if hasattr(response, 'content') else 0
    logger.info(
        "[llm] node=%s output_chars=%d elapsed=%.1fs",
        node, output_chars, elapsed,
    )
    return response
```

Use `_log_llm_call` in router_node and responder_node instead of direct `model.ainvoke()`.

---

## What We're NOT Changing

- **ToolCallLimitMiddleware exit_behavior**: Keeping `"continue"` — `"end"` can raise NotImplementedError with parallel tool calling
- **web_fetch empty responses**: Tool-level issue, not framework. Can address separately.
- **_truncate_messages**: Executor isolation is correct behavior
- **Memory infrastructure**: Checkpointer/session management is working correctly

---

## Testing Plan

1. **Unit tests**: Intent-specific tool limits, guided prompt construction, stopping conditions
2. **Local smoke test**: `agntrick chat "What are the top news in g1.globo.com?" -v` — should stop after 1-2 calls
3. **CI**: `make check && make test`

---

## Risk

Low. Changes are targeted:
- Tool limits: Stricter, so agents stop sooner (better UX, lower cost)
- Prompts: More aggressive about stopping (reduces tool waste)
- Logging: Additive, no behavior change
- assistant.md: Removes conflicting guidance, adds clear rules
