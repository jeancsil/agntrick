# Token-Efficient Conversation Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a summarization node to the 3-node StateGraph that compresses old conversation messages into a running summary, reducing token usage from ~4.5K to ~500 tokens per turn.

**Architecture:** Insert a `summarize_node` before the router in the graph. It uses `count_tokens_approximately` to check message history size. When history exceeds a token threshold, it calls the LLM to compress old messages into a running summary stored in `state["context"]`. Router and responder nodes inject the summary as a SystemMessage prefix. For single-turn conversations, the node is a no-op with zero overhead.

**Tech Stack:** Python 3.12, LangGraph StateGraph, `langchain_core.messages.utils.count_tokens_approximately`, existing LLM provider abstraction.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/agntrick/graph.py` | Core graph — `AgentState`, `summarize_node`, `router_node`, `responder_node`, `create_assistant_graph` |
| `tests/test_graph.py` | All tests for summarization node, summary injection, TTL, graceful degradation |

Only two files change. All work is in `graph.py` and `test_graph.py`.

---

### Task 1: Add `context` field to `AgentState`

**Files:**
- Modify: `src/agntrick/graph.py:276-284` (the `AgentState` TypedDict)
- Modify: `tests/test_graph.py:88-100` (the `TestAgentState` class)

- [ ] **Step 1: Add failing test for context field**

Add to `tests/test_graph.py` in the `TestAgentState` class:

```python
def test_state_accepts_context_field(self) -> None:
    """AgentState should accept an optional context dict."""
    state: AgentState = {
        "messages": [],
        "intent": "chat",
        "tool_plan": None,
        "progress": [],
        "final_response": None,
        "context": {"running_summary": "User asked about F1.", "summary_updated_at": 1712900000.0},
    }
    assert state["context"]["running_summary"] == "User asked about F1."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph.py::TestAgentState::test_state_accepts_context_field -v`
Expected: FAIL — `AgentState` does not yet have a `context` field (may still pass since TypedDict is total=False, but confirms test compiles).

- [ ] **Step 3: Add `context` field to `AgentState`**

In `src/agntrick/graph.py`, update the `AgentState` TypedDict (around line 276):

```python
class AgentState(TypedDict, total=False):
    """State flowing through the 3-node graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    intent: str
    tool_plan: str | None
    progress: list[str]
    final_response: str | None
    context: dict[str, Any]
```

Add `import time` at the top if not already present (it is — line 9). The `Any` type is already imported from `typing`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph.py::TestAgentState -v`
Expected: PASS — all `TestAgentState` tests pass including new one.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/test_graph.py -v`
Expected: All existing tests pass (no behavioral change yet).

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "feat: add context field to AgentState for conversation summary storage"
```

---

### Task 2: Implement `summarize_node` — no-op path

**Files:**
- Modify: `src/agntrick/graph.py` (add new function after `_build_prune_removes`, around line 184)
- Modify: `tests/test_graph.py` (add new test class)

- [ ] **Step 1: Write failing test for no-op behavior**

Add to `tests/test_graph.py` — new class after `TestBuildPruneRemoves`:

```python
class TestSummarizeNode:
    """Tests for summarize_node — conversation history compression."""

    @pytest.mark.asyncio
    async def test_noop_below_threshold(self) -> None:
        """Messages under token threshold should return empty dict (no-op)."""
        from agntrick.graph import summarize_node

        mock_model = AsyncMock()
        state: AgentState = {
            "messages": [HumanMessage(content="hello")],
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        result = await summarize_node(state, {}, model=mock_model)

        # No-op: model should NOT be called, empty dict returned
        mock_model.ainvoke.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_noop_with_empty_messages(self) -> None:
        """Empty messages should return empty dict (no-op)."""
        from agntrick.graph import summarize_node

        mock_model = AsyncMock()
        state: AgentState = {
            "messages": [],
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        result = await summarize_node(state, {}, model=mock_model)
        mock_model.ainvoke.assert_not_called()
        assert result == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph.py::TestSummarizeNode::test_noop_below_threshold -v`
Expected: FAIL — `ImportError: cannot import name 'summarize_node' from 'agntrick.graph'`

- [ ] **Step 3: Implement `summarize_node` with no-op path only**

Add to `src/agntrick/graph.py` after `_build_prune_removes` (after line 183). Add the import at the top of the file:

```python
from langchain_core.messages.utils import count_tokens_approximately
```

Then add the function:

```python
# Token threshold above which summarization is triggered.
_SUMMARIZE_TOKEN_THRESHOLD = 500

# Number of most-recent messages to keep unsummarized.
_SUMMARIZE_KEEP_RECENT = 2

# Maximum tokens for the summary output.
_SUMMARY_MAX_TOKENS = 128

# Hours after which a running summary is considered stale and cleared.
_SUMMARY_TTL_HOURS = 24


async def summarize_node(
    state: AgentState,
    config: RunnableConfig,
    *,
    model: Any,
    max_tokens: int = _SUMMARIZE_TOKEN_THRESHOLD,
    keep_recent: int = _SUMMARIZE_KEEP_RECENT,
    summary_max_tokens: int = _SUMMARY_MAX_TOKENS,
    ttl_hours: int = _SUMMARY_TTL_HOURS,
) -> dict:
    """Compress old conversation messages into a running summary.

    Checks token count of messages in state. If below threshold, returns
    empty dict (no-op). If above, uses the LLM to summarize older messages
    into a compact running summary stored in ``state["context"]``.

    Args:
        state: Current graph state with messages and optional context.
        config: LangGraph runnable config.
        model: LLM model for summarization.
        max_tokens: Token threshold to trigger summarization.
        keep_recent: Number of recent messages to keep unsummarized.
        summary_max_tokens: Max tokens for the summary LLM output.
        ttl_hours: Hours before a summary is considered stale.

    Returns:
        Dict with updated context and optional RemoveMessage directives.
        Empty dict if no summarization needed (no-op).
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    token_count = count_tokens_approximately(messages)
    if token_count < max_tokens:
        return {}

    # Will be implemented in Task 3 (summarization logic)
    return {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph.py::TestSummarizeNode -v`
Expected: PASS — both no-op tests pass.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest tests/test_graph.py -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "feat: add summarize_node with no-op path for short conversations"
```

---

### Task 3: Implement `summarize_node` — summarization logic

**Files:**
- Modify: `src/agntrick/graph.py` (complete the `summarize_node` function body)
- Modify: `tests/test_graph.py` (add summarization tests)

- [ ] **Step 1: Write failing test for summarization**

Add to `tests/test_graph.py` in `TestSummarizeNode`:

```python
    @pytest.mark.asyncio
    async def test_summarizes_above_threshold(self) -> None:
        """Messages above threshold should be summarized and old ones removed."""
        from agntrick.graph import summarize_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="User asked about F1 news and weather in Tokyo.")
        )

        # Build messages with IDs so RemoveMessage can target them
        msgs = [
            HumanMessage(content="What's the F1 news?" + " detail" * 200, id="msg-0"),
            AIMessage(content="Here are the F1 results..." + " detail" * 200, id="msg-1"),
            HumanMessage(content="And the weather in Tokyo?" + " detail" * 200, id="msg-2"),
            AIMessage(content="Tokyo is 22°C sunny." + " detail" * 200, id="msg-3"),
            HumanMessage(content="What about Paris?", id="msg-4"),
        ]

        state: AgentState = {
            "messages": msgs,
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        result = await summarize_node(state, {}, model=mock_model, max_tokens=10, keep_recent=2)

        # Model should have been called to summarize
        mock_model.ainvoke.assert_called_once()

        # Should return RemoveMessage for old messages (all except last 2)
        removes = [m for m in result.get("messages", []) if isinstance(m, RemoveMessage)]
        assert len(removes) == 3, f"Expected 3 RemoveMessage (msg-0,1,2), got {len(removes)}"
        removed_ids = {r.id for r in removes}
        assert "msg-0" in removed_ids
        assert "msg-1" in removed_ids
        assert "msg-2" in removed_ids

        # Context should have running_summary
        assert "context" in result
        assert "running_summary" in result["context"]
        assert "F1" in result["context"]["running_summary"]
        assert "summary_updated_at" in result["context"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph.py::TestSummarizeNode::test_summarizes_above_threshold -v`
Expected: FAIL — summarize_node returns `{}` for all cases (not implemented yet).

- [ ] **Step 3: Implement summarization logic**

Replace the placeholder `return {}` at the end of `summarize_node` in `src/agntrick/graph.py`:

```python
    # Split messages: old ones to summarize vs recent to keep
    split_index = max(0, len(messages) - keep_recent)
    old_messages = messages[:split_index]
    recent_messages = messages[split_index:]

    if not old_messages:
        return {}

    # Build summarization prompt
    existing_summary = state.get("context", {}).get("running_summary")
    summary_age = state.get("context", {}).get("summary_updated_at", 0.0)

    # TTL check: clear stale summary
    if existing_summary and (time.time() - summary_age) > ttl_hours * 3600:
        logger.info("[summarize] TTL expired, clearing stale summary")
        existing_summary = None

    # Build the prompt to LLM
    old_content = "\n".join(
        f"{type(m).__name__}: {str(m.content)[:500]}" for m in old_messages
    )

    if existing_summary:
        prompt = (
            f"Extend this conversation summary with the new messages below. "
            f"Keep it concise (max {summary_max_tokens} tokens).\n\n"
            f"Existing summary: {existing_summary}\n\n"
            f"New messages:\n{old_content}"
        )
    else:
        prompt = (
            f"Summarize this conversation concisely (max {summary_max_tokens} tokens). "
            f"Focus on topics, user preferences, and key facts.\n\n"
            f"Messages:\n{old_content}"
        )

    # Call LLM for summarization
    try:
        response = await model.ainvoke([HumanMessage(content=prompt)])
        new_summary = str(response.content).strip()
    except Exception as e:
        logger.warning("[summarize] LLM summarization failed: %s", e)
        return {}

    # Build RemoveMessage directives for old messages
    removes = [
        RemoveMessage(id=m.id)
        for m in old_messages
        if m.id is not None
    ]

    logger.info(
        "[summarize] compressed %d messages (%d tokens) into %d-char summary",
        len(old_messages),
        token_count,
        len(new_summary),
    )

    return {
        "messages": removes,
        "context": {
            "running_summary": new_summary,
            "summary_updated_at": time.time(),
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph.py::TestSummarizeNode::test_summarizes_above_threshold -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "feat: implement summarize_node summarization with RemoveMessage cleanup"
```

---

### Task 4: Add remaining `summarize_node` tests

**Files:**
- Modify: `tests/test_graph.py` (add tests to `TestSummarizeNode`)

- [ ] **Step 1: Write failing tests for extending summary, TTL, and error handling**

Add to `tests/test_graph.py` in `TestSummarizeNode`:

```python
    @pytest.mark.asyncio
    async def test_extends_existing_summary(self) -> None:
        """Should extend an existing summary rather than recreate from scratch."""
        from agntrick.graph import summarize_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="Extended: User also asked about chess.")
        )

        msgs = [
            HumanMessage(content="Tell me about chess openings" + " detail" * 200, id="old-0"),
            AIMessage(content="Here are chess openings..." + " detail" * 200, id="old-1"),
            HumanMessage(content="New question"),
        ]

        state: AgentState = {
            "messages": msgs,
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
            "context": {
                "running_summary": "User asked about F1 news.",
                "summary_updated_at": time.time(),
            },
        }

        result = await summarize_node(state, {}, model=mock_model, max_tokens=10, keep_recent=1)

        # The prompt sent to LLM should mention the existing summary
        call_args = mock_model.ainvoke.call_args[0][0]
        prompt_text = str(call_args[0].content)
        assert "F1 news" in prompt_text, "Prompt should include existing summary"
        assert "Extend" in prompt_text, "Prompt should ask to extend, not recreate"

        assert "chess" in result["context"]["running_summary"]

    @pytest.mark.asyncio
    async def test_ttl_expires_stale_summary(self) -> None:
        """Summary older than TTL should be cleared, summarization starts fresh."""
        from agntrick.graph import summarize_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="Fresh summary about chess.")
        )

        msgs = [
            HumanMessage(content="Chess question" + " detail" * 200, id="m-0"),
            AIMessage(content="Chess answer" + " detail" * 200, id="m-1"),
            HumanMessage(content="New question"),
        ]

        # Summary is 48 hours old (TTL default is 24h)
        stale_time = time.time() - (48 * 3600)

        state: AgentState = {
            "messages": msgs,
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
            "context": {
                "running_summary": "Stale summary about old topics.",
                "summary_updated_at": stale_time,
            },
        }

        result = await summarize_node(state, {}, model=mock_model, max_tokens=10, keep_recent=1)

        # The prompt should NOT mention the stale summary
        call_args = mock_model.ainvoke.call_args[0][0]
        prompt_text = str(call_args[0].content)
        assert "Stale summary" not in prompt_text, "Stale summary should not be used"
        assert "Summarize" in prompt_text, "Should start fresh with 'Summarize'"

    @pytest.mark.asyncio
    async def test_llm_failure_graceful_degradation(self) -> None:
        """When summarization LLM fails, should return empty dict (no crash)."""
        from agntrick.graph import summarize_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(side_effect=RuntimeError("API timeout"))

        msgs = [
            HumanMessage(content="Long message" + " detail" * 200, id="m-0"),
            AIMessage(content="Long response" + " detail" * 200, id="m-1"),
            HumanMessage(content="New question"),
        ]

        state: AgentState = {
            "messages": msgs,
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        # Should NOT raise — graceful degradation
        result = await summarize_node(state, {}, model=mock_model, max_tokens=10, keep_recent=1)
        assert result == {}, "Should return empty dict on LLM failure"

    @pytest.mark.asyncio
    async def test_context_missing_defaults_to_empty(self) -> None:
        """Missing context field should default to empty dict gracefully."""
        from agntrick.graph import summarize_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="Summary of the conversation.")
        )

        msgs = [
            HumanMessage(content="Big message" + " detail" * 200, id="m-0"),
            AIMessage(content="Big answer" + " detail" * 200, id="m-1"),
            HumanMessage(content="New question"),
        ]

        # No context field at all
        state: AgentState = {
            "messages": msgs,
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        result = await summarize_node(state, {}, model=mock_model, max_tokens=10, keep_recent=1)
        assert "context" in result
        assert "running_summary" in result["context"]
```

Add `import time` at the top of `tests/test_graph.py` if not already there. It's not — add it.

- [ ] **Step 2: Run all new tests**

Run: `uv run pytest tests/test_graph.py::TestSummarizeNode -v`
Expected: All 6 tests in `TestSummarizeNode` pass.

- [ ] **Step 3: Run full suite**

Run: `uv run pytest tests/test_graph.py -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_graph.py
git commit -m "test: add summarize_node tests for TTL, extension, error handling"
```

---

### Task 5: Inject summary into `router_node`

**Files:**
- Modify: `src/agntrick/graph.py:402-427` (the `router_node` function)
- Modify: `tests/test_graph.py` (add test to `TestRouterNode`)

- [ ] **Step 1: Write failing test for router summary injection**

Add to `tests/test_graph.py` in `TestRouterNode`:

```python
    @pytest.mark.asyncio
    async def test_router_injects_summary_as_context(self) -> None:
        """Router should prepend summary as SystemMessage when context has one."""
        from agntrick.graph import router_node

        captured_messages: list[list[BaseMessage]] = []

        async def capture_invoke(messages: list[BaseMessage]) -> AIMessage:
            captured_messages.append(messages)
            return AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}')

        mock_model = AsyncMock()
        mock_model.ainvoke = capture_invoke

        state: AgentState = {
            "messages": [HumanMessage(content="follow up question")],
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
            "context": {
                "running_summary": "User previously asked about F1 news and got results.",
                "summary_updated_at": time.time(),
            },
        }

        await router_node(state, {}, model=mock_model)

        sent = captured_messages[0]
        # Should contain a SystemMessage with the summary
        system_msgs = [m for m in sent if isinstance(m, SystemMessage)]
        summary_msgs = [m for m in system_msgs if "Previous conversation summary" in str(m.content)]
        assert len(summary_msgs) == 1, f"Expected 1 summary SystemMessage, got {len(summary_msgs)}"
        assert "F1 news" in str(summary_msgs[0].content)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph.py::TestRouterNode::test_router_injects_summary_as_context -v`
Expected: FAIL — router doesn't inject summary yet.

- [ ] **Step 3: Implement summary injection in `router_node`**

In `src/agntrick/graph.py`, update `router_node` (around line 402). Add summary injection after the `context_window` is computed:

```python
async def router_node(state: AgentState, config: RunnableConfig, *, model: Any) -> dict:
    """Classify intent and decide strategy. Single fast LLM call."""
    # Send a budget-based window of recent messages so the router can understand
    # follow-up questions (e.g. "yes", "and in Paris?") that need context.
    context_window = _budget_window_messages(state["messages"], _ROUTER_CONTEXT_BUDGET)
    last_message = state["messages"][-1]
    query_preview = str(last_message.content)[:200]
    logger.info(
        "[router] input: %s messages in window, last: %s",
        len(context_window),
        query_preview,
    )

    # Inject running summary as context prefix if available
    summary = state.get("context", {}).get("running_summary")
    if summary:
        context_window = [
            SystemMessage(content=f"Previous conversation summary: {summary}"),
            *context_window,
        ]

    response = await _log_llm_call(
        model,
        [SystemMessage(content=ROUTER_PROMPT), *context_window],
        node="router",
    )
    parsed = _parse_router_response(response.content)
    intent = parsed.get("intent", "chat")
    tool_plan = parsed.get("tool_plan")
    logger.info(f"[router] output: intent={intent}, plan={str(tool_plan)[:200] if tool_plan else 'None'}")
    return {
        "intent": intent,
        "tool_plan": tool_plan,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph.py::TestRouterNode -v`
Expected: PASS — all router tests pass including new one.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest tests/test_graph.py -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "feat: inject conversation summary into router node as context"
```

---

### Task 6: Inject summary into `responder_node` for chat intent

**Files:**
- Modify: `src/agntrick/graph.py:573-634` (the `responder_node` function)
- Modify: `tests/test_graph.py` (add test to `TestResponderChatWindow`)

- [ ] **Step 1: Write failing test for responder summary injection**

Add to `tests/test_graph.py` in `TestResponderChatWindow`:

```python
    @pytest.mark.asyncio
    async def test_chat_intent_injects_summary(self) -> None:
        """Responder for chat should prepend summary when available."""
        from agntrick.graph import responder_node

        captured_messages: list[list[BaseMessage]] = []

        async def capture_invoke(messages: list[BaseMessage]) -> AIMessage:
            captured_messages.append(messages)
            return AIMessage(content="Response")

        mock_model = AsyncMock()
        mock_model.ainvoke = capture_invoke

        state: AgentState = {
            "messages": [
                HumanMessage(content="And what about Paris?"),
            ],
            "intent": "chat",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
            "context": {
                "running_summary": "User asked about F1 and Tokyo weather.",
                "summary_updated_at": time.time(),
            },
        }

        await responder_node(state, {}, model=mock_model)

        sent = captured_messages[0]
        system_msgs = [m for m in sent if isinstance(m, SystemMessage)]
        summary_msgs = [m for m in system_msgs if "Previous conversation summary" in str(m.content)]
        assert len(summary_msgs) == 1, f"Expected 1 summary SystemMessage, got {len(summary_msgs)}"
        assert "F1" in str(summary_msgs[0].content)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph.py::TestResponderChatWindow::test_chat_intent_injects_summary -v`
Expected: FAIL — responder doesn't inject summary yet.

- [ ] **Step 3: Implement summary injection in `responder_node`**

In `src/agntrick/graph.py`, update the chat intent branch of `responder_node`. The key change is after `msgs = _budget_window_messages(...)` — inject the summary:

```python
    if state.get("intent") == "chat":
        msgs = _budget_window_messages(state["messages"], _RESPONDER_CHAT_BUDGET)
        logger.debug(
            "[responder] chat intent: %d messages, types=%s",
            len(msgs),
            [type(m).__name__ for m in msgs],
        )

        # Inject running summary as context if available
        summary = state.get("context", {}).get("running_summary")
        if summary:
            msgs = [
                SystemMessage(content=f"Previous conversation summary: {summary}"),
                *msgs,
            ]

        safe_msgs = _safe_invoke_messages(RESPONDER_PROMPT, msgs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph.py::TestResponderChatWindow::test_chat_intent_injects_summary -v`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest tests/test_graph.py -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "feat: inject conversation summary into responder node for chat intent"
```

---

### Task 7: Wire `summarize_node` into the graph

**Files:**
- Modify: `src/agntrick/graph.py:644-702` (the `create_assistant_graph` function)
- Modify: `tests/test_graph.py` (update integration tests)

- [ ] **Step 1: Write failing test for graph with summarize node**

Add to `tests/test_graph.py` in `TestGraphIntegration`:

```python
    @pytest.mark.asyncio
    async def test_graph_has_summarize_node(self) -> None:
        """Graph should compile with summarize as the entry point."""
        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}'),
                AIMessage(content="Hello!"),
            ]
        )

        graph = create_assistant_graph(
            model=mock_model,
            tools=[],
            system_prompt="You are a test assistant.",
        )

        # Graph should compile and have ainvoke
        assert graph is not None

        # Invoke should work end-to-end (summarize no-op → router → responder)
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="Hi")]},
            config={"configurable": {"thread_id": "test-summarize-node"}},
        )
        assert result.get("final_response") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph.py::TestGraphIntegration::test_graph_has_summarize_node -v`
Expected: May pass already since graph compiles — but the summarize node isn't wired in yet, so this confirms the wiring change doesn't break things.

- [ ] **Step 3: Wire summarize_node into `create_assistant_graph`**

In `src/agntrick/graph.py`, update `create_assistant_graph` to add the summarize node and change the entry point:

```python
def create_assistant_graph(
    model: Any,
    tools: Sequence[Any],
    system_prompt: str,
    checkpointer: Any | None = None,
    progress_callback: ProgressCallback = None,
    router_model: Any | None = None,
    executor_model: Any | None = None,
    responder_model: Any | None = None,
) -> Any:
    """Create the 3-node assistant StateGraph.

    Args:
        model: Primary LLM model instance (used for executor if executor_model not set).
        tools: Sequence of tools available to the executor.
        system_prompt: Base system prompt for the agent.
        checkpointer: Optional checkpointer for persistent memory.
        progress_callback: Optional async callback for progress updates.
        router_model: Optional model override for the router node.
        executor_model: Optional model override for the executor node.
        responder_model: Optional model override for the responder node.

    Returns:
        Compiled StateGraph ready for ainvoke().
    """
    _router_model = router_model or model
    _executor_model = executor_model or model
    _responder_model = responder_model or model

    async def _summarize(state: AgentState, config: RunnableConfig) -> dict:
        return await summarize_node(state, config, model=model)

    async def _router(state: AgentState, config: RunnableConfig) -> dict:
        return await router_node(state, config, model=_router_model)

    async def _executor(state: AgentState, config: RunnableConfig) -> dict:
        return await executor_node(
            state,
            config,
            model=_executor_model,
            tools=tools,
            system_prompt=system_prompt,
            progress_callback=progress_callback,
        )

    async def _responder(state: AgentState, config: RunnableConfig) -> dict:
        return await responder_node(state, config, model=_responder_model)

    graph = StateGraph(AgentState)
    graph.add_node("summarize", _summarize)
    graph.add_node("router", _router)
    graph.add_node("executor", _executor)
    graph.add_node("responder", _responder)
    graph.set_entry_point("summarize")
    graph.add_edge("summarize", "router")
    graph.add_conditional_edges(
        "router",
        route_decision,
        {"executor": "executor", "responder": "responder"},
    )
    graph.add_edge("executor", "responder")
    graph.add_edge("responder", END)

    return graph.compile(checkpointer=checkpointer or InMemorySaver())
```

- [ ] **Step 4: Run full suite**

Run: `uv run pytest tests/test_graph.py -v`
Expected: All tests pass. The existing integration tests should work because the summarize node is a no-op for short conversations.

- [ ] **Step 5: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "feat: wire summarize_node into StateGraph as entry point"
```

---

### Task 8: Update `CLAUDE.md` Mermaid diagrams

**Files:**
- Modify: `CLAUDE.md` (update the Execution Flow and Graph Detail Mermaid diagrams)

Per the project rules: "When modifying `graph.py`: verify the 'Execution Flow' Mermaid diagrams still reflect the current code."

- [ ] **Step 1: Update the End-to-End Pipeline diagram**

In `CLAUDE.md`, find the `flowchart TD` section with the `Init` subgraph. After the `GRAPH_CREATE` node, add the summarize node to the flow. Update the edges:

In the End-to-End Pipeline Mermaid diagram, update the `Exec` subgraph to show `SUMMARIZE` as the first node:

```
    subgraph Exec["Graph Execution <small>(graph.py)</small>"]
        SUMMARIZE["Summarize node<br/>Compress old messages"]
        ROUTER["Router node<br/>Classify intent"]
        EXEC["Executor node<br/>Run tools / sub-agents"]
        RESP["Responder node<br/>Format for WhatsApp"]
    end
```

And update the edge from `GRAPH_CREATE` to go through `SUMMARIZE` first:

```
    GRAPH_CREATE --> SUMMARIZE
    SUMMARIZE --> ROUTER
```

- [ ] **Step 2: Update the Graph Detail diagram**

In the Graph Detail Mermaid diagram, add the summarize node at the start:

```
    SUMMARIZE["<b>Summarize</b><br/>Token threshold check<br/><small>No-op for short conversations<br/>Compresses to ~128 token summary</small>"]

    SUMMARIZE --> ROUTER
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update Mermaid diagrams to include summarize node"
```

---

### Task 9: Final verification

- [ ] **Step 1: Run full check and test suite**

Run: `make check && make test`
Expected: Both pass with no errors.

- [ ] **Step 2: Verify test coverage for new code**

Run: `uv run pytest tests/test_graph.py -v --tb=short`
Expected: All tests pass, including all 6 `TestSummarizeNode` tests and new injection tests.

- [ ] **Step 3: Final commit if any cleanup needed**

Only if `make check` required fixes:

```bash
git add -A
git commit -m "fix: lint fixes from token-efficient memory implementation"
```
