# Fix Tool Usage Efficiency & Agent Collaboration

**Date**: 2026-04-06
**Status**: Approved
**Branch**: `feat/smarter-whatsapp-assistant`

---

## Problem

Agents waste their tool call budget retrying instead of using results they already have. When `web_search` returns good data on the first call, the model ignores it and keeps calling tools until hitting the 5-call limit, then responds "unable to retrieve content."

Agents also can't collaborate — delegated agents start with zero context and can't see previous tool results or conversation history.

### Root Cause Analysis

From production logs (g1.globo.com news request):

```
msg[0]  HumanMessage: "What are the 1st top news in g1.globo.com?"
msg[1]  web_search → 2060 chars ✓ (has g1 headlines!)
msg[3]  web_fetch  → 0 chars ✗ (empty)
msg[5]  curl_fetch → 4194 chars raw HTML
msg[7]  web_search → 1393 chars (English sources)
msg[9]  web_fetch  → 5254 chars ✓
msg[11] web_search → TOOL CALL LIMIT EXCEEDED
msg[13] "I was unable to retrieve content" ← ignores good data from msg[2]
```

Three root causes:
1. **Model ignores "stop after first tool"** — guided prompt says "DO NOT call more than 2 tools" but model makes 5+
2. **ToolCallLimitMiddleware too permissive** — `run_limit=5, exit_behavior="continue"` doesn't force stop
3. **Delegated agents get no context** — `invoke_agent` creates fresh agents with no conversation history

---

## Design

### Change 1: Intent-Specific Tool Limits + Prompt Hardening

**File**: `src/agntrick/graph.py`

#### 1a. Intent-to-limit mapping

Replace the fixed `run_limit=5` with intent-specific limits:

```python
_INTENT_TOOL_LIMITS: dict[str, int] = {
    "tool_use": 2,    # 1 primary + 1 fallback
    "research": 5,    # multi-step research
    "delegate": 1,    # just invoke the agent
}
_DEFAULT_TOOL_LIMIT = 3
```

In `executor_node`:
```python
tool_limit = _INTENT_TOOL_LIMITS.get(intent, _DEFAULT_TOOL_LIMIT)
middleware=[ToolCallLimitMiddleware(run_limit=tool_limit, exit_behavior="continue")]
```

Keep `exit_behavior="continue"` so the model gets a final chance to respond after the limit.

#### 1b. Strengthen the guided prompt for tool_use

Replace the current MANDATORY INSTRUCTION with a more aggressive version:

```python
if tool_plan and intent == "tool_use":
    guided_prompt += f"""

## MANDATORY INSTRUCTION — SINGLE TOOL CALL
The router has determined this query requires: {tool_plan}

You MUST execute exactly these steps and NO more:
1. Call the tool: {tool_plan}
2. Read the tool's response
3. IMMEDIATELY respond to the user using that data
4. DO NOT call any other tools — even if the result seems incomplete
5. If the tool returns an error, try exactly ONE alternative, then respond
6. STOP. You have data. Use it.

CRITICAL: web_search results contain snippets that ARE the answer.
Do NOT web_fetch URLs from search results — the snippets are enough.
"""
```

Key improvements:
- "SINGLE TOOL CALL" in header
- "IMMEDIATELY respond" instead of "USE IT to answer"
- Explicit rule about web_search snippets being sufficient
- Numbered steps that end with STOP

#### 1c. Strengthen research and delegate prompts

Research prompt — add evaluation step:
```python
elif tool_plan and intent == "research":
    guided_prompt += f"""

## RESEARCH PLAN
Execute this plan step by step:
{tool_plan}

Rules:
- After each tool call, evaluate: do I have enough to answer?
- If YES → respond immediately. Do NOT continue researching.
- Maximum 5 tool calls total.
- If any tool returns data, USE IT. Do NOT retry the same tool.
"""
```

Delegate prompt — add context injection instruction:
```python
elif tool_plan and intent == "delegate":
    guided_prompt += f"""

## DELEGATION
Use the invoke_agent tool with these parameters:
{tool_plan}

The agent has NO memory. Include ALL relevant context in your prompt.
Do NOT use any other tools. Just invoke the agent and return its result.
"""
```

### Change 2: Fix Agent Delegation Context Passing

**File**: `src/agntrick/tools/agent_invocation.py`

#### 2a. Accept optional `context` field

Add `context` as an optional field in the JSON input:
```python
{
    "agent_name": "developer",
    "prompt": "Analyze this news article about...",
    "context": "User asked about g1.globo.com news. web_search returned: ...",
    "timeout": 60
}
```

#### 2b. Prepend context to prompt

When `context` is provided, prepend it to the prompt before passing to the agent:
```python
if context:
    full_prompt = f"[Conversation context]\n{context}\n\n[Task]\n{prompt}"
else:
    full_prompt = prompt
```

#### 2c. Update tool description

Update the `description` property to document the `context` field and emphasize including conversation history.

### Change 3: Add LLM Call Logging

**File**: `src/agntrick/graph.py`

#### 3a. Wrap model.ainvoke calls with timing and token logging

Add a helper function:
```python
async def _log_llm_call(
    label: str,
    model: Any,
    messages: list[BaseMessage],
) -> BaseMessage:
    """Invoke model with timing and token logging."""
    import time
    start = time.monotonic()
    response = await model.ainvoke(messages)
    elapsed = time.monotonic() - start
    msg_count = len(messages)
    response_len = len(str(response.content))
    logger.info(
        "[llm] %s: %.1fs, %d msgs in, response %d chars",
        label,
        elapsed,
        msg_count,
        response_len,
    )
    return response
```

Use this in:
- `router_node` — label "router"
- `responder_node` — label "responder-chat" or "responder-tool"

The executor sub-agent's internal LLM calls are handled by LangChain's ReAct loop — those are already logged by the executor's message tracing (lines 306-319).

#### 3b. Log at INFO level

All logging uses `logger.info` so it appears in default output. Debug-level details (full message content) use `logger.debug`.

---

## What We're NOT Changing

- **Router classification logic** — works correctly
- **Tool filtering** — works correctly (right tools for each intent)
- **Responder formatting** — works correctly (just formats executor output)
- **Memory/checkpointer** — fixed in previous commit
- **MCP interceptors** — truncation works, but empty responses from `web_fetch` are a tool issue, not a framework issue
- **ToolCallLimitMiddleware exit_behavior** — keeping "continue" so the model gets a final response chance

---

## Testing Plan

1. **Unit tests**:
   - Test `_INTENT_TOOL_LIMITS` mapping
   - Test guided prompt construction for each intent
   - Test `invoke_agent` with `context` field
   - Test `_log_llm_call` helper

2. **Local smoke test**:
   ```bash
   agntrick chat "What are the top news in g1.globo.com?" -v
   # Should: call web_search once, respond with results
   # Should NOT: call web_fetch, curl_fetch, or retry

   agntrick chat "Compare React vs Vue in 2026" -v
   # Should: call web_search 2-3 times, respond
   ```

3. **CI**: `make check && make test`

---

## Risk

Low-medium. Changes are targeted:
- Prompt changes are additive (more specific instructions)
- Tool limits are configurable via the mapping dict
- `context` field is optional (backward compatible)
- LLM logging is additive (no behavior change)

The main risk is that the model (glm-5.1) may still ignore the strengthened prompt. The hard `run_limit=2` for `tool_use` provides a safety net — even if the model ignores the prompt, it physically can't make more than 2 tool calls.
