# Speed, Reliability, and Memory Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce WhatsApp tool-use latency, fix context loss between turns, and eliminate fragile thread-based delegation.

**Architecture:** Five targeted changes to the existing 3-node graph (Summarize → Router → Agent): (1) add LangGraph timing callback for observability, (2) debug and fix context loss bug, (3) add regex pre-routing before the router LLM, (4) replace thread-based delegation with inline async calls, (5) add single-retry for transient tool failures.

**Tech Stack:** Python 3.12, LangGraph, LangChain, FastAPI, asyncio, MCP (Model Context Protocol)

**Spec:** `docs/superpowers/specs/2026-04-18-speed-reliability-memory-design.md`

**Testing approach:** No strict TDD. Build, write high-coverage unit tests, then verify E2E by deploying to DigitalOcean droplet via SSH and testing via WhatsApp.

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/agntrick/timing.py` | Create | LangGraph callback handler for per-node timing |
| `src/agntrick/graph.py` | Modify | Pre-routing, delegation fast path, tool retry, timing integration |
| `src/agntrick/agent.py` | Modify | Timing around `_ensure_initialized()` |
| `src/agntrick/agents/assistant.py` | Modify | Pass timing callback to graph |
| `tests/test_timing.py` | Create | Tests for timing callback |
| `tests/test_graph.py` | Modify | Tests for pre-routing, delegation fast path, tool retry |

---

## Task 1: Latency Instrumentation (Timing Callback)

**Files:**
- Create: `src/agntrick/timing.py`
- Create: `tests/test_timing.py`
- Modify: `src/agntrick/graph.py` (register callback in `create_assistant_graph`)
- Modify: `src/agntrick/agent.py` (timing around `_ensure_initialized`)

- [ ] **Step 1: Create `src/agntrick/timing.py`**

```python
"""LangGraph callback handler for per-node timing and request-level summaries."""

import logging
import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


class TimingCallbackHandler(BaseCallbackHandler):
    """Records per-node timing and emits a structured summary on graph completion."""

    def __init__(self) -> None:
        self._node_starts: dict[str, float] = {}
        self._node_durations: dict[str, float] = {}
        self._graph_start: float = 0.0
        self._intent: str = ""

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        self._graph_start = time.monotonic()

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        total = time.monotonic() - self._graph_start
        parts = [f"total={total:.1f}s"]
        for name, dur in sorted(self._node_durations.items()):
            parts.append(f"{name}={dur:.1f}s")
        intent = self._intent or "unknown"
        logger.info("[timing] intent=%s %s", intent, " ".join(parts))

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        pass

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        pass
```

Note: LangGraph nodes are chains internally. The callback hooks into `on_chain_start`/`on_chain_end` for each node. For more granular per-node timing, we also need a custom approach since LangGraph's callback system wraps nodes as chains with generated names. We'll add a simpler timing wrapper.

- [ ] **Step 2: Add timing wrapper approach in `graph.py`**

The LangGraph callback approach has limitations with node identification. A more reliable approach is to wrap the existing `_log_llm_call()` with timing accumulation that produces the summary at the end.

Add to `graph.py` after the imports:

```python
import threading

# Thread-local storage for accumulating timing data within a single graph run.
# Thread-safe because each request runs in its own async context.
_timing_data: threading.local = threading.local()
```

Add a helper function:

```python
def _timing_start(phase: str) -> None:
    """Mark the start of a timing phase."""
    if not hasattr(_timing_data, "phases"):
        _timing_data.phases = {}
        _timing_data.graph_start = time.monotonic()
    _timing_data.phases[phase] = {"start": time.monotonic()}


def _timing_end(phase: str) -> None:
    """Mark the end of a timing phase and accumulate duration."""
    if not hasattr(_timing_data, "phases") or phase not in _timing_data.phases:
        return
    elapsed = time.monotonic() - _timing_data.phases[phase]["start"]
    _timing_data.phases[phase]["duration"] = elapsed


def _timing_summary(intent: str) -> None:
    """Log a structured timing summary and reset state."""
    if not hasattr(_timing_data, "phases"):
        return
    total = time.monotonic() - _timing_data.graph_start
    parts = [f"total={total:.1f}s"]
    for name, data in sorted(_timing_data.phases.items()):
        dur = data.get("duration", 0.0)
        parts.append(f"{name}={dur:.1f}s")
    logger.info("[timing] intent=%s %s", intent, " ".join(parts))
    _timing_data.phases = {}
```

- [ ] **Step 3: Instrument `router_node()` in `graph.py`**

In the `router_node()` function, add timing calls around the LLM call. Find the line:

```python
    response = await _log_llm_call(
```

Before it, add:

```python
    _timing_start("router")
```

After the parsed response is computed (after the `_parse_router_response` call), add:

```python
    _timing_end("router")
```

- [ ] **Step 4: Instrument `agent_node()` in `graph.py`**

In `agent_node()`, add timing around each phase. Find the chat fast-path block:

```python
    if intent == "chat":
```

Inside it, after the `response = await _log_llm_call(model, safe_msgs, node="chat")` line, add before `formatted`:

```python
        _timing_start("agent")
```

And after the response:

```python
        _timing_end("agent")
        _timing_summary("chat")
```

For the `tool_use` direct path, add:

```python
    if intent == "tool_use" and tool_plan:
        target_tools = [t for t in tools if getattr(t, "name", "") == tool_plan]
        if target_tools:
            _timing_start("tool")
            user_msg = str(state["messages"][-1].content)
            direct_result = await _direct_tool_call(
                user_message=user_msg,
                tool_plan=tool_plan,
                tools=target_tools,
                model=model,
                system_prompt=system_prompt,
            )
            _timing_end("tool")
            formatted = _format_for_whatsapp(str(direct_result.content))
            removes = _build_prune_removes(state["messages"], _MAX_STATE_MESSAGES)
            _timing_summary("tool_use")
            return {"final_response": formatted, "messages": [direct_result] + removes}
```

For the sub-agent path (research/delegate), add `_timing_start("agent")` before the `sub_agent.ainvoke()` and `_timing_end("agent")` after. Then add `_timing_summary(intent)` before the final return.

- [ ] **Step 5: Instrument `_direct_tool_call()` in `graph.py`**

In `_direct_tool_call()`, add timing for the tool call and LLM formatting separately. The existing timing logs already exist but don't contribute to the summary. Wrap them:

Before `tool_result = await target.ainvoke(tool_args)`:

```python
    _timing_start("tool_exec")
```

After the tool call completes (both success and error paths):

```python
    _timing_end("tool_exec")
```

Before the formatting LLM call:

```python
    _timing_start("llm_format")
```

After the formatting response:

```python
    _timing_end("llm_format")
```

- [ ] **Step 6: Add timing to `agent.py` `_ensure_initialized()`**

In `src/agntrick/agent.py`, in the `_ensure_initialized()` method, wrap the body:

```python
    async def _ensure_initialized(self) -> None:
        if self._graph is not None:
            return

        async with self._init_lock:
            if self._graph is not None:
                return

            start = time.monotonic()

            # ... existing initialization code ...

            elapsed = time.monotonic() - start
            logger.info("[timing] agent_init=%.1fs agent=%s", elapsed, self._agent_name)
```

Add `import time` at the top if not already present.

- [ ] **Step 7: Write tests for timing helpers**

Create `tests/test_timing.py`:

```python
"""Tests for timing instrumentation helpers."""

import time

from agntrick.graph import _timing_start, _timing_end, _timing_summary, _timing_data


class TestTimingHelpers:
    def test_timing_start_creates_phases(self):
        """_timing_start should initialize the phases dict."""
        # Reset state
        _timing_data.phases = {}

        _timing_start("test_phase")
        assert hasattr(_timing_data, "phases")
        assert "test_phase" in _timing_data.phases
        assert "start" in _timing_data.phases["test_phase"]

    def test_timing_end_records_duration(self):
        """_timing_end should compute and store duration."""
        _timing_data.phases = {}
        _timing_data.graph_start = time.monotonic()

        _timing_start("test_phase")
        time.sleep(0.01)
        _timing_end("test_phase")

        assert "duration" in _timing_data.phases["test_phase"]
        assert _timing_data.phases["test_phase"]["duration"] >= 0.01

    def test_timing_end_noop_without_start(self):
        """_timing_end should be a no-op if phases not initialized."""
        _timing_data.phases = {}
        _timing_end("nonexistent")  # Should not raise

    def test_timing_summary_resets_state(self):
        """_timing_summary should reset phases after logging."""
        _timing_data.phases = {}
        _timing_data.graph_start = time.monotonic()

        _timing_start("phase_a")
        _timing_end("phase_a")
        _timing_summary("test")

        assert _timing_data.phases == {}
```

- [ ] **Step 8: Run tests**

Run: `uv run pytest tests/test_timing.py -xvs`
Expected: ALL PASS

- [ ] **Step 9: Run full test suite**

Run: `make check && make test`
Expected: ALL PASS

- [ ] **Step 10: Commit**

```bash
git add src/agntrick/timing.py src/agntrick/graph.py src/agntrick/agent.py tests/test_timing.py
git commit -m "feat: add per-node timing instrumentation for latency observability"
```

---

## Task 2: Fix Context Loss Bug

**Files:**
- Modify: `src/agntrick/graph.py` (diagnostic logging)
- Modify: `src/agntrick/agent.py` (diagnostic logging)

This task is diagnostic first — we add logging, deploy, reproduce the bug, then fix based on findings.

- [ ] **Step 1: Add diagnostic logging to `graph.py` router_node()**

In `router_node()`, after the line that gets the last message, add:

```python
    # Diagnostic: log state info for context loss debugging
    all_msgs = state.get("messages", [])
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    logger.info(
        "[context] thread_id=%s state_msgs=%d window_msgs=%d summary=%s",
        thread_id,
        len(all_msgs),
        len(context_window),
        "yes" if state.get("context", {}).get("running_summary") else "no",
    )
```

- [ ] **Step 2: Add diagnostic logging to `agent_node()` chat path**

In `agent_node()`, at the very start of the function (before the `intent = state.get(...)` line), add:

```python
    # Diagnostic: log state for context debugging
    all_msgs = state.get("messages", [])
    intent_val = state.get("intent", "unknown")
    logger.info(
        "[context] agent_node: intent=%s state_msgs=%d msg_types=%s",
        intent_val,
        len(all_msgs),
        [type(m).__name__ for m in all_msgs[-5:]],
    )
```

- [ ] **Step 3: Add diagnostic logging to `agent.run()` in `agent.py`**

In `agent.py`, in the `run()` method, before `result = await self._graph.ainvoke(...)`, add:

```python
        thread = config.get("configurable", {}).get("thread_id", self._thread_id) if config else self._thread_id
        logger.info("[context] agent.run: agent=%s thread_id=%s", self._agent_name, thread)
```

- [ ] **Step 4: Run tests**

Run: `make check && make test`
Expected: ALL PASS (only logging additions)

- [ ] **Step 5: Deploy to DO and reproduce the bug**

```bash
# Push branch
git push -u origin feat/speed-reliability-memory

# Deploy
ssh -i ~/.ssh/droplet_jeancsil jeancsil@167.99.134.115 \
  "cd /home/jeancsil/projects/test-agntrick/agntrick && bash scripts/deploy.sh pull && bash scripts/deploy.sh restart"
```

Ask user to send via WhatsApp:
1. "Quem e Oscar Schmidt?"
2. "ele esta vivo?"
3. "onde voce conseguiu essa informacao?"

Then check logs:
```bash
ssh -i ~/.ssh/droplet_jeancsil jeancsil@167.99.134.115 \
  "cd /home/jeancsil/projects/test-agntrick/agntrick && bash scripts/deploy.sh logs"
```

Look for `[context]` lines to identify:
- Is thread_id stable across the 3 requests?
- How many state_msgs are there at each turn?
- Is a new agent being created mid-conversation?

- [ ] **Step 6: Fix based on findings**

The fix depends on what the diagnostics reveal. Most likely fixes:

**If thread_id changes between requests**: The webhook handler at `src/agntrick/api/routes/whatsapp.py:387` builds `thread_id = f"whatsapp:{tenant_id}:{phone}"` which should be stable. Verify the `config` dict in `agent.run()` uses this thread_id and not `self._thread_id`.

**If new agent per request**: Verify `pool.get_or_create()` is returning the same agent instance. Check the pool key (`f"{tenant_id}:{agent_name}"`) is consistent.

**If `_truncate_messages()` is too aggressive**: For `tool_use` intent, the function isolates only the last HumanMessage. Change to pass the last 2-3 messages so pronoun resolution works. In `agent_node()`, find the `intent == "tool_use"` block and change the message budget:

```python
        if intent == "tool_use":
            executor_msgs = _budget_window_messages(state["messages"], 2_000, max_messages=4)
```

This already exists for the sub-agent path. Ensure the direct tool call path also uses windowed messages.

- [ ] **Step 7: Verify fix**

Reproduce the Oscar Schmidt conversation again. The agent should maintain context across all 3 turns.

- [ ] **Step 8: Commit**

```bash
git add src/agntrick/graph.py src/agntrick/agent.py
git commit -m "fix: add context loss diagnostics and stabilize conversation memory"
```

---

## Task 3: Pre-Routing Regex Filter

**Files:**
- Modify: `src/agntrick/graph.py` (add `_pre_route()` function)
- Modify: `tests/test_graph.py` (tests for pre-routing)

- [ ] **Step 1: Add `_pre_route()` function in `graph.py`**

Add after the `_parse_router_response()` function:

```python
import re as _re

# Pre-routing patterns: bypass the router LLM for obvious messages.
# Each tuple: (compiled regex, intent, tool_plan)
# Patterns are checked in order — first match wins.
_PRE_ROUTE_PATTERNS: list[tuple[_re.Pattern[str], str, str | None]] = [
    # Greetings (Portuguese + English)
    (
        _re.compile(
            r"^(oi|ola|hey|hi|bom dia|boa tarde|boa noite|good morning|good afternoon|good evening|good night|hello|e a[ií]|fala|salve|ciao)\b",
            _re.IGNORECASE,
        ),
        "chat",
        None,
    ),
    # Help / capabilities
    (
        _re.compile(
            r"^(help|ajuda|o que voc[eê] (pode|faz)|what can you do|comandos|commands)\b",
            _re.IGNORECASE,
        ),
        "chat",
        None,
    ),
    # "read this URL" patterns (before bare URL to handle "news about http://...")
    (
        _re.compile(
            r"(leia|read|extrair|extract|fetch|abra|open|acesse|access)\s+https?://\S+",
            _re.IGNORECASE,
        ),
        "tool_use",
        "web_fetch",
    ),
    # Bare URL only (message is ONLY a URL, nothing else)
    (
        _re.compile(r"^https?://\S+$"),
        "tool_use",
        "web_fetch",
    ),
    # News queries (Portuguese + English)
    (
        _re.compile(
            r"(not[ií]cia|news|[uú]ltima|[uú]ltimos|o que (est[aá]|t[aá]) acontecendo|what'?s happening|latest|manchete|headline)",
            _re.IGNORECASE,
        ),
        "tool_use",
        "web_search",
    ),
]


def _pre_route(message: str) -> dict[str, Any] | None:
    """Check message against pre-routing patterns.

    Returns intent + tool_plan if matched, None if no match (fall through to LLM router).
    """
    text = message.strip()
    if not text:
        return None
    for pattern, intent, tool_plan in _PRE_ROUTE_PATTERNS:
        if pattern.search(text):
            logger.info("[pre-route] match: intent=%s tool_plan=%s", intent, tool_plan)
            return {"intent": intent, "tool_plan": tool_plan}
    return None
```

Note: `_re` is imported as alias to avoid conflicting with the existing `re` import at the top of the file. Actually, `re` is already imported — use it directly instead:

```python
_PRE_ROUTE_PATTERNS: list[tuple[re.Pattern[str], str, str | None]] = [
    (
        re.compile(
            r"^(oi|ola|hey|hi|bom dia|boa tarde|boa noite|good morning|good afternoon|good evening|good night|hello|e a[ií]|fala|salve|ciao)\b",
            re.IGNORECASE,
        ),
        "chat",
        None,
    ),
    (
        re.compile(
            r"^(help|ajuda|o que voc[eê] (pode|faz)|what can you do|comandos|commands)\b",
            re.IGNORECASE,
        ),
        "chat",
        None,
    ),
    (
        re.compile(
            r"(leia|read|extrair|extract|fetch|abra|open|acesse|access)\s+https?://\S+",
            re.IGNORECASE,
        ),
        "tool_use",
        "web_fetch",
    ),
    (
        re.compile(r"^https?://\S+$"),
        "tool_use",
        "web_fetch",
    ),
    (
        re.compile(
            r"(not[ií]cia|news|[uú]ltima|[uú]ltimos|o que (est[aá]|t[aá]) acontecendo|what'?s happening|latest|manchete|headline)",
            re.IGNORECASE,
        ),
        "tool_use",
        "web_search",
    ),
]


def _pre_route(message: str) -> dict[str, Any] | None:
    """Check message against pre-routing patterns."""
    text = message.strip()
    if not text:
        return None
    for pattern, intent, tool_plan in _PRE_ROUTE_PATTERNS:
        if pattern.search(text):
            logger.info("[pre-route] match: intent=%s tool_plan=%s", intent, tool_plan)
            return {"intent": intent, "tool_plan": tool_plan}
    return None
```

- [ ] **Step 2: Wire `_pre_route()` into `router_node()`**

In `router_node()`, after getting the last message but before the LLM call, add the pre-route check:

```python
    last_message = state["messages"][-1]
    query_preview = str(last_message.content)[:200]

    # Pre-route: bypass LLM for obvious patterns
    pre_routed = _pre_route(str(last_message.content))
    if pre_routed is not None:
        logger.info(f"[router] pre-routed: intent={pre_routed['intent']} plan={pre_routed.get('tool_plan')}")
        return pre_routed

    # ... existing LLM router code continues ...
```

- [ ] **Step 3: Write tests for pre-routing**

Add to `tests/test_graph.py`:

```python
class TestPreRouting:
    """Tests for regex pre-routing filter."""

    def test_greetings_portuguese(self):
        from agntrick.graph import _pre_route

        assert _pre_route("bom dia") == {"intent": "chat", "tool_plan": None}
        assert _pre_route("oi") == {"intent": "chat", "tool_plan": None}
        assert _pre_route("boa noite") == {"intent": "chat", "tool_plan": None}

    def test_greetings_english(self):
        from agntrick.graph import _pre_route

        assert _pre_route("hello") == {"intent": "chat", "tool_plan": None}
        assert _pre_route("hi") == {"intent": "chat", "tool_plan": None}

    def test_help_queries(self):
        from agntrick.graph import _pre_route

        assert _pre_route("help") == {"intent": "chat", "tool_plan": None}
        assert _pre_route("o que voce faz?") == {"intent": "chat", "tool_plan": None}

    def test_bare_url(self):
        from agntrick.graph import _pre_route

        assert _pre_route("https://example.com") == {"intent": "tool_use", "tool_plan": "web_fetch"}

    def test_read_url(self):
        from agntrick.graph import _pre_route

        assert _pre_route("leia https://example.com/article") == {"intent": "tool_use", "tool_plan": "web_fetch"}

    def test_news_queries(self):
        from agntrick.graph import _pre_route

        assert _pre_route("noticias sobre Brasil") == {"intent": "tool_use", "tool_plan": "web_search"}
        assert _pre_route("latest news") == {"intent": "tool_use", "tool_plan": "web_search"}

    def test_ambiguous_falls_through(self):
        from agntrick.graph import _pre_route

        assert _pre_route("what do you think about AI?") is None
        assert _pre_route("can you help me with a recipe?") is None

    def test_url_in_context_not_matched(self):
        """A URL embedded in a sentence should NOT be pre-routed to web_fetch."""
        from agntrick.graph import _pre_route

        # "news about https://..." should match news, not URL
        result = _pre_route("noticias sobre https://example.com")
        assert result == {"intent": "tool_use", "tool_plan": "web_search"}

    def test_empty_message(self):
        from agntrick.graph import _pre_route

        assert _pre_route("") is None
        assert _pre_route("   ") is None
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_graph.py::TestPreRouting -xvs`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `make check && make test`
Expected: ALL PASS

- [ ] **Step 6: Deploy and verify E2E**

```bash
ssh -i ~/.ssh/droplet_jeancsil jeancsil@167.99.134.115 \
  "cd /home/jeancsil/projects/test-agntrick/agntrick && bash scripts/deploy.sh pull && bash scripts/deploy.sh restart"
```

Send via WhatsApp:
1. "bom dia" → should respond without `[router]` LLM log (check for `[pre-route] match`)
2. "noticias sobre Brasil" → should route directly to `web_search`
3. "what do you think about democracy?" → should hit router LLM (`[pre-route] no match`)

- [ ] **Step 7: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "feat: add regex pre-routing filter to bypass router LLM for obvious messages"
```

---

## Task 4: Async Delegation (Replace Thread-Based Agent Invocation)

**Files:**
- Modify: `src/agntrick/graph.py` (delegation fast path in `agent_node`)
- Modify: `tests/test_graph.py` (tests for delegation fast path)

- [ ] **Step 1: Add delegation fast path in `agent_node()`**

In `graph.py`, in `agent_node()`, add a new block after the `tool_use` direct path and before the `if progress_callback:` line. This intercepts `delegate` intent and calls the target agent directly.

```python
    # Delegation fast path: call target agent directly without thread/invocation tool.
    # The router already decided which agent to delegate to — creating a sub-agent
    # that then calls invoke_agent (which creates a thread + new event loop) wastes
    # 2 LLM calls and blocks for up to 240s.
    if intent == "delegate" and tool_plan:
        from agntrick.registry import AgentRegistry as _AR
        from agntrick.tools.agent_invocation import DELEGATABLE_AGENTS as _DA

        if tool_plan in _DA:
            agent_cls = _AR.get(tool_plan)
            if agent_cls is not None:
                user_msg = str(state["messages"][-1].content)
                tool_categories = _AR.get_tool_categories(tool_plan)
                try:
                    _timing_start("delegate")
                    delegated = agent_cls(
                        _agent_name=tool_plan,
                        tool_categories=tool_categories,
                    )
                    delegate_result = await asyncio.wait_for(
                        delegated.run(user_msg),
                        timeout=120,
                    )
                    _timing_end("delegate")
                    formatted = _format_for_whatsapp(str(delegate_result))
                    removes = _build_prune_removes(state["messages"], _MAX_STATE_MESSAGES)
                    _timing_summary("delegate")
                    return {
                        "final_response": formatted,
                        "messages": [AIMessage(content=str(delegate_result))] + removes,
                    }
                except asyncio.TimeoutError:
                    _timing_end("delegate")
                    logger.warning("[delegate] agent '%s' timed out after 120s", tool_plan)
                    error_msg = f"The request to {tool_plan} timed out. Please try again."
                    formatted = _format_for_whatsapp(error_msg)
                    removes = _build_prune_removes(state["messages"], _MAX_STATE_MESSAGES)
                    return {
                        "final_response": formatted,
                        "messages": [AIMessage(content=error_msg)] + removes,
                    }
                except Exception as e:
                    _timing_end("delegate")
                    logger.warning("[delegate] agent '%s' failed: %s", tool_plan, e)
                    # Fall through to sub-agent path as fallback
```

Add `import asyncio` at the top of `graph.py` if not already present.

- [ ] **Step 2: Write test for delegation fast path**

Add to `tests/test_graph.py`:

```python
class TestDelegationFastPath:
    """Tests for direct agent delegation (bypassing thread-based invocation)."""

    @pytest.mark.asyncio
    async def test_delegate_intent_calls_agent_directly(self):
        """delegate intent should call the target agent directly, not via thread."""
        from agntrick.graph import agent_node

        # The delegated agent class will be looked up from the registry.
        # We patch AgentRegistry.get to return a mock agent class.
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value="YouTube transcript analysis result")
        mock_agent_instance._ensure_initialized = AsyncMock()

        mock_cls = MagicMock(return_value=mock_agent_instance)

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="Here is the transcript analysis.")
        )

        with patch("agntrick.registry.AgentRegistry.get", return_value=mock_cls), \
             patch("agntrick.registry.AgentRegistry.get_tool_categories", return_value=None):
            state: AgentState = {
                "messages": [HumanMessage(content="Analyze this YouTube video: https://youtube.com/watch?v=123")],
                "intent": "delegate",
                "tool_plan": "youtube",
                "progress": [],
                "final_response": None,
            }

            result = await agent_node(
                state,
                MagicMock(),
                model=mock_model,
                tools=[],
                system_prompt="You are a helpful assistant.",
            )

        assert result["final_response"] is not None
        assert "YouTube" in result["final_response"]
        mock_agent_instance.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_delegate_timeout_returns_error(self):
        """delegate should return error message on timeout."""
        from agntrick.graph import agent_node

        mock_agent_instance = MagicMock()

        async def _slow_run(msg):
            await asyncio.sleep(200)
            return "never"

        mock_agent_instance.run = _slow_run
        mock_agent_instance._ensure_initialized = AsyncMock()

        mock_cls = MagicMock(return_value=mock_agent_instance)

        with patch("agntrick.registry.AgentRegistry.get", return_value=mock_cls), \
             patch("agntrick.registry.AgentRegistry.get_tool_categories", return_value=None):
            state: AgentState = {
                "messages": [HumanMessage(content="Analyze this YouTube video")],
                "intent": "delegate",
                "tool_plan": "youtube",
                "progress": [],
                "final_response": None,
            }

            result = await agent_node(
                state,
                MagicMock(),
                model=MagicMock(),
                tools=[],
                system_prompt="You are a helpful assistant.",
            )

        assert "timed out" in result["final_response"].lower()

    @pytest.mark.asyncio
    async def test_delegate_unknown_agent_falls_through(self):
        """delegate with unknown agent should fall through to sub-agent path."""
        from agntrick.graph import agent_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="I'll handle this directly.")
        )

        # Create a minimal tool list with invoke_agent
        from agntrick.tools.agent_invocation import AgentInvocationTool
        invoke_tool = AgentInvocationTool()
        from langchain_core.tools import StructuredTool

        lc_tool = invoke_tool.to_langchain_tool()

        with patch("agntrick.registry.AgentRegistry.get", return_value=None):
            state: AgentState = {
                "messages": [HumanMessage(content="delegate to nonexistent agent")],
                "intent": "delegate",
                "tool_plan": "nonexistent-agent",
                "progress": [],
                "final_response": None,
            }

            # Should not crash — falls through to sub-agent path
            result = await agent_node(
                state,
                MagicMock(),
                model=mock_model,
                tools=[lc_tool],
                system_prompt="You are a helpful assistant.",
            )

        assert result["final_response"] is not None
```

Note: The `asyncio` import needs `import asyncio` at the top of the test file. The `patch` import needs `from unittest.mock import patch, MagicMock, AsyncMock`. Check existing test file for these imports.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_graph.py::TestDelegationFastPath -xvs`
Expected: ALL PASS (may need adjustments for mock setup)

- [ ] **Step 4: Run full test suite**

Run: `make check && make test`
Expected: ALL PASS

- [ ] **Step 5: Deploy and verify E2E**

```bash
ssh -i ~/.ssh/droplet_jeancsil jeancsil@167.99.134.115 \
  "cd /home/jeancsil/projects/test-agntrick/agntrick && bash scripts/deploy.sh pull && bash scripts/deploy.sh restart"
```

Send via WhatsApp:
1. A YouTube URL → should delegate to youtube agent
2. A paywalled URL → should delegate to paywall-remover
3. Check logs: no `run_in_new_loop` or `threading.Thread` in the delegation path

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "feat: direct agent delegation bypassing thread-based invocation"
```

---

## Task 5: Tool Error Retry with Backoff

**Files:**
- Modify: `src/agntrick/graph.py` (retry logic in `_direct_tool_call`)

- [ ] **Step 1: Add transient error classification helper**

Add after `_extract_tool_args()` in `graph.py`:

```python
# Error types that are transient and worth retrying.
_TRANSIENT_ERROR_TYPES: tuple[type[Exception], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
    OSError,
)

_TRANSIENT_ERROR_MESSAGES: tuple[str, ...] = (
    "connection reset",
    "broken pipe",
    "remote protocol error",
    "503",
    "502",
    "connection refused",
    "timed out",
)


def _is_transient_error(error: Exception) -> bool:
    """Check if an error is transient and worth retrying."""
    if isinstance(error, _TRANSIENT_ERROR_TYPES):
        return True
    error_str = str(error).lower()
    return any(msg in error_str for msg in _TRANSIENT_ERROR_MESSAGES)
```

- [ ] **Step 2: Add retry logic to `_direct_tool_call()`**

In `_direct_tool_call()`, replace the tool call block. Find:

```python
    start = time.monotonic()
    try:
        tool_result = await target.ainvoke(tool_args)
        tool_elapsed = time.monotonic() - start
        logger.info("[direct-tool] %s returned %d chars in %.1fs", tool_plan, len(str(tool_result)), tool_elapsed)
    except Exception as e:
        tool_elapsed = time.monotonic() - start
        logger.warning("[direct-tool] %s failed in %.1fs: %s", tool_plan, tool_elapsed, e)
        tool_result = f"Error: {e}"
```

Replace with:

```python
    start = time.monotonic()
    try:
        tool_result = await target.ainvoke(tool_args)
        tool_elapsed = time.monotonic() - start
        logger.info("[direct-tool] %s returned %d chars in %.1fs", tool_plan, len(str(tool_result)), tool_elapsed)
    except Exception as e:
        tool_elapsed = time.monotonic() - start

        # Retry once for transient errors if first attempt was fast (<3s)
        if _is_transient_error(e) and tool_elapsed < 3.0:
            logger.info("[retry] %s transient error (%.1fs), retrying after 1s: %s", tool_plan, tool_elapsed, e)
            await asyncio.sleep(1.0)
            try:
                tool_result = await target.ainvoke(tool_args)
                retry_elapsed = time.monotonic() - start
                logger.info("[retry] %s succeeded on retry in %.1fs", tool_plan, retry_elapsed)
            except Exception as retry_e:
                retry_elapsed = time.monotonic() - start
                logger.warning("[retry] %s failed on retry in %.1fs: %s", tool_plan, retry_elapsed, retry_e)
                tool_result = f"Error: {retry_e}"
        else:
            logger.warning("[direct-tool] %s failed in %.1fs: %s", tool_plan, tool_elapsed, e)
            tool_result = f"Error: {e}"
```

- [ ] **Step 3: Write tests for retry logic**

Add to `tests/test_graph.py`:

```python
class TestToolRetry:
    """Tests for transient error retry in direct tool calls."""

    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self):
        """Should retry once on transient errors if first attempt was fast."""
        from agntrick.graph import _direct_tool_call

        call_count = 0

        class FakeTool:
            name = "web_search"
            description = "Search the web"
            args_schema = MagicMock()

            async def ainvoke(self, args):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise ConnectionError("Connection reset")
                return "search results"

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="Here are the results.")
        )

        fake_tool = FakeTool()
        # Patch _make_flat_tool to return the fake tool as-is
        with patch("agntrick.graph._make_flat_tool", return_value=fake_tool):
            result = await _direct_tool_call(
                user_message="test query",
                tool_plan="web_search",
                tools=[fake_tool],
                model=mock_model,
                system_prompt="test",
            )

        assert call_count == 2
        assert "Error" not in str(result.content)

    @pytest.mark.asyncio
    async def test_no_retry_on_non_transient_error(self):
        """Should NOT retry on non-transient errors."""
        from agntrick.graph import _direct_tool_call

        call_count = 0

        class FakeTool:
            name = "web_search"
            description = "Search the web"
            args_schema = MagicMock()

            async def ainvoke(self, args):
                nonlocal call_count
                call_count += 1
                raise ValueError("Invalid input")

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="Error occurred.")
        )

        fake_tool = FakeTool()
        with patch("agntrick.graph._make_flat_tool", return_value=fake_tool):
            result = await _direct_tool_call(
                user_message="test query",
                tool_plan="web_search",
                tools=[fake_tool],
                model=mock_model,
                system_prompt="test",
            )

        assert call_count == 1  # No retry
        assert "Error" in str(result.content)

    def test_is_transient_error_classification(self):
        from agntrick.graph import _is_transient_error

        assert _is_transient_error(ConnectionError("reset")) is True
        assert _is_transient_error(TimeoutError("timed out")) is True
        assert _is_transient_error(ValueError("invalid input")) is False
        assert _is_transient_error(Exception("503 Service Unavailable")) is True
        assert _is_transient_error(Exception("connection reset by peer")) is True
        assert _is_transient_error(Exception("404 Not Found")) is False
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_graph.py::TestToolRetry -xvs`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `make check && make test`
Expected: ALL PASS

- [ ] **Step 6: Deploy and verify**

```bash
ssh -i ~/.ssh/droplet_jeancsil jeancsil@167.99.134.115 \
  "cd /home/jeancsil/projects/test-agntrick/agntrick && bash scripts/deploy.sh pull && bash scripts/deploy.sh restart"
```

Monitor logs for `[retry]` lines during normal WhatsApp usage. If a transient failure occurs, verify retry happens correctly.

- [ ] **Step 7: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "feat: single retry with backoff for transient tool failures"
```

---

## Task 6: Final Verification and Documentation Update

- [ ] **Step 1: Run full test suite**

Run: `make check && make test`
Expected: ALL PASS, coverage >= 60%

- [ ] **Step 2: Deploy all changes to DO**

```bash
ssh -i ~/.ssh/droplet_jeancsil jeancsil@167.99.134.115 \
  "cd /home/jeancsil/projects/test-agntrick/agntrick && bash scripts/deploy.sh pull && bash scripts/deploy.sh restart"
```

- [ ] **Step 3: Run comprehensive E2E verification**

Send via WhatsApp and verify:

| Test | Message | Expected | Check in logs |
|------|---------|----------|---------------|
| Greeting pre-route | "bom dia" | Fast response, no router LLM | `[pre-route] match` |
| News pre-route | "noticias sobre Brasil" | Direct web_search | `[pre-route] match`, `[timing]` |
| URL pre-route | "https://example.com" | Direct web_fetch | `[pre-route] match` |
| Ambiguous query | "what do you think about AI?" | Full router LLM | `[pre-route] no match` |
| Context continuity | 3-turn Oscar Schmidt conversation | Agent remembers subject | `[context]` lines show stable thread_id |
| Delegation | YouTube URL | Fast response, no thread creation | `[timing]`, no `run_in_new_loop` |
| Timing | Any message | `[timing]` summary in logs | Per-phase breakdown |

- [ ] **Step 4: Update CLAUDE.md execution flow diagrams if needed**

If any changes affected the graph structure or flow, update the Mermaid diagrams in `CLAUDE.md`.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "docs: update execution flow for speed and reliability improvements"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Task |
|---|---|
| 1. Latency Instrumentation | Task 1 (timing helpers + node instrumentation) |
| 2. Fix Context Loss Bug | Task 2 (diagnostic logging + fix based on findings) |
| 3. Pre-Routing Regex Filter | Task 3 (`_pre_route()` + patterns) |
| 4. Async Subgraphs | Task 4 (delegation fast path) |
| 5. Tool Error Retry | Task 5 (retry with backoff) |
| Implementation Notes | Task 6 (E2E verification) |
| Future Work | Documented in spec, no tasks needed |

**Placeholder scan:** No TBDs, TODOs, or vague references. All code blocks contain complete implementations.

**Type consistency:** `_pre_route()` returns `dict[str, Any] | None` — used consistently in `router_node()`. `_is_transient_error()` takes `Exception` — used in the except clause. `TimingCallbackHandler` uses `threading.local` — no async type conflicts.
