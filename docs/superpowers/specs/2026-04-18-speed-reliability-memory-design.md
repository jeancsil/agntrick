# Speed, Reliability, and Memory Fix for WhatsApp Assistant

**Date**: 2026-04-18
**Status**: Draft
**Priority**: Tool use speed + reliability + context memory loss
**Constraint**: $6/month DigitalOcean droplet (1 vCPU, 1GB RAM), 2 tenants
**Previous spec**: [Sub-15s Response Architecture](2026-04-15-sub15s-response-architecture-design.md)

---

## Problem Statement

Three critical issues affecting the WhatsApp assistant:

1. **Tool use is slow** (~25s for a single web search). The previous spec removed the responder node and added direct tool calls, but the router LLM still adds 3-5s to every request, and there's no data to measure what else is slow.

2. **Context drops between turns**. In a 3-message conversation about Oscar Schmidt, the agent forgot the subject ("I don't have context of a previous conversation"). Follow-up queries like "is he alive?" fail because the agent loses who "he" refers to.

3. **Thread-based delegation is fragile and slow**. `agent_invocation.py` creates a `threading.Thread` + new event loop for every delegation. This blocks the calling event loop for up to 240s, requires a fragile httpx cache hack, and wastes memory on a 1GB droplet.

---

## Design

### 1. Latency Instrumentation

**Goal**: Establish baselines. You can't improve what you don't measure.

**Approach**: LangGraph callback handler — one new file, zero changes to node functions.

**New file: `src/agntrick/timing.py`**

`TimingCallbackHandler` class that hooks into LangGraph's callback system:
- Records start/end time for each node
- On graph completion, emits a single structured log line:
  ```
  [timing] intent=tool_use total=18.2s router=3.1s tool=5.8s llm_format=4.2s
  ```

**Change in `graph.py`**: Register the callback in `create_assistant_graph()` — pass it via `RunnableConfig` to `graph.ainvoke()`.

**Change in `agent.py`**: Add timing around `_ensure_initialized()` to track cold-start costs (outside LangGraph's callback scope).

**What stays the same**: No changes to node functions, no changes to graph structure, no new dependencies.

**Verification (E2E)**:
1. Push branch, deploy to DO (`scripts/deploy.sh pull && restart`)
2. Send WhatsApp messages for each intent type (chat, tool_use, research, delegate)
3. Check logs (`scripts/deploy.sh logs`) for `[timing]` lines
4. Record baselines for all 4 intent types

---

### 2. Fix Context Loss Bug

**Goal**: Follow-up messages like "is he alive?" must resolve "he" to the previous subject.

**Root cause investigation** (debugging step before fix):

Likely culprits in order of probability:

1. **Thread ID mismatch** — if thread_id changes between requests, InMemorySaver returns empty state
2. **New agent per request** — if webhook handler creates a fresh agent instead of using pool, checkpointer state is lost
3. **`_truncate_messages()`** — for research/delegate intents, it isolates only the last HumanMessage, losing all context
4. **`_MAX_STATE_MESSAGES = 10`** — aggressive pruning, but 3 messages shouldn't trigger this
5. **Summarization over-triggering** — `_SUMMARIZE_TOKEN_THRESHOLD = 500` is low, but 3 short messages shouldn't hit it

**Fix approach**:

1. Add diagnostic logging: thread_id, message count in state, summarization trigger status for every request
2. Verify webhook handler uses pooled agent (same instance = same InMemorySaver = same thread)
3. Ensure thread_id is stable per tenant session (not per request)
4. Fix the identified root cause

**Verification (E2E)**:
1. Deploy to DO
2. Reproduce the Oscar Schmidt conversation via WhatsApp:
   - "Quem e Oscar Schmidt?"
   - "ele esta vivo?"
   - "onde voce conseguiu essa informacao?"
3. Verify agent maintains context across all 3 turns
4. Check logs for thread_id stability and state message count

---

### 3. Pre-Routing Regex Filter

**Goal**: Bypass the router LLM (~3-5s) for obvious messages.

**Design**: Regex-based pre-filter called at the start of `router_node()`. If matched, return intent + tool_plan directly. If no match, fall through to existing router LLM.

**Location**: New function `_pre_route()` in `graph.py`.

**Patterns:**

| Pattern | Intent | tool_plan | Regex (simplified) |
|---|---|---|---|
| Greetings | `chat` | `null` | `^(hi|hey|ola|bom dia|boa tarde|boa noite|good morning|good evening)\b` |
| Help/capabilities | `chat` | `null` | `^(help|what can you do|o que voce faz|ajuda)\b` |
| News queries | `tool_use` | `web_search` | `(noticia|news|o que (esta|ta) acontecendo|latest|what's happening)\b` |
| URL only (no other words) | `tool_use` | `web_fetch` | `^https?://\S+$` (message is ONLY a URL) |
| "read/extract this URL" | `tool_use` | `web_fetch` | `(read|ler|extract|fetch|open)\s+https?://` |

**Implementation**:
- List of `(compiled_regex, intent, tool_plan)` tuples
- `_pre_route(last_message_content)` checks against each pattern
- Returns `{"intent": ..., "tool_plan": ...}` on match, `None` on no match
- `router_node()` calls `_pre_route()` first; if it returns a result, skip the LLM call

**What stays the same**: Router LLM still runs for ambiguous messages. Running summary injection, budget window, and all router logic unchanged.

**Impact**: ~3-5s saved on ~40% of requests.

**Verification (E2E)**:
1. Deploy to DO
2. Send "bom dia" — should respond without a router LLM call (check logs for `[pre-route] match`)
3. Send "https://example.com" — should route directly to `web_fetch`
4. Send an ambiguous query — should still hit router LLM (check logs for `[pre-route] no match`)

---

### 4. Async Subgraphs (Replace Thread-Based Delegation)

**Goal**: Eliminate `threading.Thread` + new event loop in `agent_invocation.py`. Reduce memory usage and remove fragile httpx cache hack.

**Problem with current approach**:

```
router (3s) → agent_node → LLM decides to call invoke_agent (3s) →
  threading.Thread → new_event_loop → _clear_langchain_httpx_cache() →
  agent.run() → graph.ainvoke() → ... → thread.join(240s)
```

Three issues:
1. **2 unnecessary LLM calls**: Router classifies as "delegate", then sub-agent LLM decides to call `invoke_agent` tool, then the tool runs the actual agent
2. **Thread overhead**: New event loop + thread per delegation on a 1GB droplet
3. **Fragile httpx cache hack**: `_clear_langchain_httpx_cache()` works around event loop binding issues

**Design**: Handle delegation directly in `agent_node()`. When intent is `delegate` and `tool_plan` contains an agent name, call the agent's `run()` directly — no thread, no tool abstraction.

**New flow:**

```
router (3s) → agent_node → detect delegate intent →
  asyncio.wait_for(target_agent.run(prompt), timeout=120s)
```

**Changes in `graph.py` `agent_node()`:**
- Before the existing sub-agent creation, check if `intent == "delegate"` and `tool_plan` is in `DELEGATABLE_AGENTS`
- If yes: look up agent class from registry, instantiate (which triggers lazy MCP init on first call), call `await asyncio.wait_for(agent.run(prompt), timeout=timeout)`
- If no: fall through to existing sub-agent path (unchanged)

**Note on delegated agent initialization**: The delegated agent still needs MCP tools. On first delegation, it triggers lazy init (MCP connections, manifest fetch). Subsequent delegations to the same agent type are fast. Consider pooling delegated agents in a future iteration.

**Changes in `agent_invocation.py`:**
- `AgentInvocationTool` remains for edge cases where the LLM still tries to call it
- But the fast path no longer goes through this tool

**Memory impact**: Eliminates one thread + event loop per delegation. On 1GB droplet with 2 tenants, this matters.

**Verification (E2E)**:
1. Deploy to DO
2. Send a YouTube URL via WhatsApp — should delegate to youtube agent
3. Send a paywalled URL — should delegate to paywall-remover
4. Check logs: no `threading.Thread` or `run_in_new_loop` lines, verify response time improved
5. Verify no `_clear_langchain_httpx_cache()` calls

---

### 5. Tool Error Retry with Backoff

**Goal**: Single retry for transient MCP failures. Don't add excessive latency.

**Design**: Retry once with 1s backoff, but only for transient errors, and only if the first attempt was fast.

**Location**: In `_direct_tool_call()` for `tool_use` intent. For research/delegate, the sub-agent handles errors already.

**Logic:**

```
1. Try tool call, measure elapsed time
2. If error:
   a. Classify: is it transient?
      - Transient: TimeoutError, ConnectionError, httpx.RemoteProtocolError, HTTP 5xx
      - Non-transient: everything else (404, invalid input, auth error)
   b. If non-transient OR first attempt took >3s: return error immediately
   c. If transient AND first attempt <3s:
      - Wait 1s
      - Retry once
      - Return result or error
3. Log: [retry] tool=X attempt=1 error_type=transient retried=true
```

**Retry budget**: Total 5s maximum. If first attempt took 8s and failed, don't retry.

**What stays the same**: Tool limits per intent unchanged. Retries don't count against the limit.

**Verification (E2E)**:
1. Deploy to DO
2. Monitor logs for `[retry]` lines during normal usage
3. If a transient failure occurs naturally, verify retry happened and either succeeded or returned a clean error
4. Verify non-transient errors (e.g., invalid URL) return immediately without retry

---

## Implementation Notes

### Testing approach

No strict TDD. Build the change, verify with:
1. **Unit tests**: High coverage for new code (`timing.py`, `_pre_route()`, delegation path)
2. **E2E via DO droplet**: Push branch → deploy → WhatsApp test → check logs

Deployment commands:
```bash
# Push branch
git push -u origin feat/<branch-name>

# Deploy to DO
ssh -i ~/.ssh/droplet_jeancsil jeancsil@167.99.134.115 \
  "cd /home/jeancsil/projects/test-agntrick/agntrick && bash scripts/deploy.sh pull && bash scripts/deploy.sh restart"

# Check logs
ssh -i ~/.ssh/droplet_jeancsil jeancsil@167.99.134.115 \
  "cd /home/jeancsil/projects/test-agntrick/agntrick && bash scripts/deploy.sh logs"
```

### Task delegation

When a task is well-defined and straightforward, delegate to glm-4.7 for execution. Complex design decisions and debugging stay with the primary agent.

---

## Future Work (not this round)

These items are documented from the Anthropic "Building Effective Agents" research and the broader agent engineering community. They will be addressed in subsequent rounds.

1. **Schema-based tool args from router** — Replace `_extract_tool_args()` regex heuristics with structured JSON output from the router. Needs research on how to format router output for different models (GLM-5.1 vs Claude vs GPT-4).

2. **Provider abstraction for prompt caching** — When switching to Anthropic or OpenAI, leverage prefix caching for the system prompt + router prompt (identical across requests). Claude Code builds its entire harness around prompt caching — a high cache hit rate reduces cost and latency significantly.

3. **Parallel tool execution for research** — When the router outputs a multi-step `tool_plan` for research intent, parse steps and run independent ones concurrently via `asyncio.gather()`. Could cut research latency from 30-60s to 10-20s.

4. **Evaluator-optimizer node** — After generating a response, run a lightweight quality check (length, language match, no XML artifacts) and regenerate if needed. Current `_format_for_whatsapp()` only truncates.

5. **Streaming progress to WhatsApp** — Wire the existing `progress_callback` to send intermediate WhatsApp messages ("Searching...", "Analyzing...", "Formatting response..."). Perceived latency drops to near-zero.

6. **MCP parallel connection** — Refactor `mcp/provider.py` to use `asyncio.gather()` when connecting to multiple servers at startup, instead of sequential connections with 60s timeout each.

---

## What We Keep (unchanged)

- **Router node**: Intent classification, tool filtering, URL handling, paywall detection
- **Summarize node**: Conversation compression, TTL management
- **ToolCallLimitMiddleware**: Prevents tool spirals
- **Tool flattening**: `_make_flat_tool()` for GLM model compatibility
- **Artifact sanitization**: `_sanitize_ai_content()` for XML pseudo-tool-calls
- **Agent pool**: TenantAgentPool with LRU eviction and keep-alive
- **Direct tool calls**: `_direct_tool_call()` for `tool_use` intent
- **3-node graph**: Summarize → Router → Agent with template WhatsApp formatting
- **All model-specific workarounds**: `_safe_invoke_messages()`, `_TOOL_ARTIFACT_RE`, etc.
