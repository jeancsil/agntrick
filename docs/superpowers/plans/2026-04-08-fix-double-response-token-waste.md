# Fix Double Response & Token Waste in Graph Execution

Read AGENTS.md to follow development rules and pass it across the subagents too so they also know and follow the rules.
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. You don't need to execute tests you know are going to fail from TDD perspective.

**Goal:** Fix the bug where every tool_use/research/delegate turn adds TWO AI messages to the conversation state (one from executor, one from responder), causing token waste, context bloat, and escalating costs.

**Architecture:** The responder node currently returns `{"messages": [AIMessage]}` for ALL intents. For tool_use intents, this creates a duplicate because the executor already added its AIMessage to state. The fix: responder returns `"messages": []` for non-chat intents (it only needs to set `final_response`). For chat intent, responder returns `"messages": [response]` because it's the ONLY node producing a response. A new `_trim_state_messages` helper caps conversation history at a configurable window to prevent unbounded growth. Unit tests cover responder_node directly and an integration test verifies exactly 1 AIMessage per turn for all intent types.

**Tech Stack:** Python 3.12+, pytest, pytest-asyncio, langgraph

---

### Task 1: Write failing tests for responder_node message output

**Files:**
- Modify: `tests/test_graph.py` (add new test class)

- [ ] **Step 1: Write failing tests for responder message deduplication**

Add to `tests/test_graph.py` after the existing `TestMakeFlatTool` class:

```python
class TestResponderMessageOutput:
    """Tests for responder_node message output — verifies no duplicate AI messages."""

    @pytest.mark.asyncio
    async def test_responder_tool_use_returns_no_messages(self) -> None:
        """For tool_use intent, responder should NOT add messages to state.

        The executor already added its AIMessage. The responder should only
        set final_response, not append another AIMessage.
        """
        from agntrick.graph import responder_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="Formatted response"))

        state: AgentState = {
            "messages": [
                HumanMessage(content="What's the news?"),
                AIMessage(content="Here are the news results from executor."),
            ],
            "intent": "tool_use",
            "tool_plan": "web_search",
            "progress": [],
            "final_response": None,
        }

        result = await responder_node(state, {}, model=mock_model)

        assert result["final_response"] is not None
        assert result["messages"] == [], (
            f"Responder should return empty messages for tool_use intent, "
            f"got {len(result['messages'])} messages"
        )

    @pytest.mark.asyncio
    async def test_responder_research_returns_no_messages(self) -> None:
        """For research intent, responder should NOT add messages to state."""
        from agntrick.graph import responder_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="Formatted research"))

        state: AgentState = {
            "messages": [
                HumanMessage(content="Compare React vs Vue"),
                AIMessage(content="Research results..."),
            ],
            "intent": "research",
            "tool_plan": "1. web_search\n2. web_fetch",
            "progress": [],
            "final_response": None,
        }

        result = await responder_node(state, {}, model=mock_model)
        assert result["messages"] == []
        assert result["final_response"] is not None

    @pytest.mark.asyncio
    async def test_responder_delegate_returns_no_messages(self) -> None:
        """For delegate intent, responder should NOT add messages to state."""
        from agntrick.graph import responder_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="Formatted delegation"))

        state: AgentState = {
            "messages": [
                HumanMessage(content="Summarize this video"),
                AIMessage(content="Video summary from youtube agent..."),
            ],
            "intent": "delegate",
            "tool_plan": "youtube agent",
            "progress": [],
            "final_response": None,
        }

        result = await responder_node(state, {}, model=mock_model)
        assert result["messages"] == []
        assert result["final_response"] is not None

    @pytest.mark.asyncio
    async def test_responder_chat_returns_message(self) -> None:
        """For chat intent, responder IS the response node — it should add its message."""
        from agntrick.graph import responder_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="Hello! How can I help?"))

        state: AgentState = {
            "messages": [HumanMessage(content="Hello")],
            "intent": "chat",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        result = await responder_node(state, {}, model=mock_model)
        assert len(result["messages"]) == 1, (
            f"Chat intent should add exactly 1 AIMessage, got {len(result['messages'])}"
        )
        assert isinstance(result["messages"][0], AIMessage)
        assert result["final_response"] is not None

    @pytest.mark.asyncio
    async def test_responder_tool_use_fallback_returns_no_messages(self) -> None:
        """Responder fallback for tool_use should also not add messages."""
        from agntrick.graph import responder_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(side_effect=RuntimeError("API error"))

        state: AgentState = {
            "messages": [
                HumanMessage(content="Search news"),
                AIMessage(content="Results here that are very long" * 100),
            ],
            "intent": "tool_use",
            "tool_plan": "web_search",
            "progress": [],
            "final_response": None,
        }

        result = await responder_node(state, {}, model=mock_model)
        assert result["messages"] == []
        assert result["final_response"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_graph.py::TestResponderMessageOutput -v`
Expected: 5 failures — `test_responder_tool_use_returns_no_messages`, `test_responder_research_returns_no_messages`, `test_responder_delegate_returns_no_messages`, and `test_responder_tool_use_fallback_returns_no_messages` fail because responder currently returns `"messages": [response]` for all intents. `test_responder_chat_returns_message` should PASS (chat already adds messages correctly).

---

### Task 2: Fix responder_node to return empty messages for non-chat intents

**Files:**
- Modify: `src/agntrick/graph.py:498-547` (responder_node function)

- [ ] **Step 1: Update responder_node to conditionally return messages**

In `src/agntrick/graph.py`, replace the `responder_node` function (lines 498-547) with:

```python
async def responder_node(state: AgentState, config: RunnableConfig, *, model: Any) -> dict:
    """Format the final response for WhatsApp.

    For chat intent: the responder IS the response node (router classified
    no tools needed), so it returns its AIMessage in ``messages`` to persist
    in the conversation state.

    For tool_use/research/delegate intents: the executor already added its
    AIMessage to state. The responder only formats it for WhatsApp output
    via ``final_response`` — it must NOT append another AIMessage to state,
    as that would create a duplicate and bloat the conversation history.

    Uses _safe_invoke_messages to ensure the GLM API always receives
    a valid message sequence (SystemMessage + at least one HumanMessage).
    """
    if state.get("intent") == "chat":
        msgs = state["messages"]  # Chat needs full conversation history for follow-ups
        logger.debug(
            "[responder] chat intent: %d messages, types=%s",
            len(msgs),
            [type(m).__name__ for m in msgs],
        )
        safe_msgs = _safe_invoke_messages(RESPONDER_PROMPT, msgs)
        try:
            response = await _log_llm_call(model, safe_msgs, node="responder-chat")
        except Exception as e:
            logger.warning(f"Responder LLM call failed for chat: {e}")
            # Fallback: return the last message content directly
            last = state["messages"][-1] if state["messages"] else None
            return {
                "final_response": str(last.content) if last else "Sorry, please try again.",
                "messages": [],
            }
        return {"final_response": str(response.content), "messages": [response]}

    # tool_use / research / delegate intent — format executor output
    last_msg = state["messages"][-1]
    content = str(last_msg.content)
    logger.info(f"[responder] intent={state.get('intent')}, executor output len={len(content)} preview={content[:200]}")
    if len(content) > _MAX_MESSAGE_CHARS:
        content = content[:_MAX_MESSAGE_CHARS] + "\n...[truncated]"

    safe_msgs = _safe_invoke_messages(
        RESPONDER_PROMPT,
        [HumanMessage(content=f"Format this response for WhatsApp:\n\n{content}")],
    )
    try:
        response = await _log_llm_call(model, safe_msgs, node="responder-tool")
    except Exception as e:
        logger.warning(f"Responder LLM call failed for tool_use: {e}")
        # Fallback: return raw content, truncated for WhatsApp
        return {
            "final_response": content[:4096],
            "messages": [],
        }

    final = str(response.content)
    logger.info(f"[responder] final_response len={len(final)} preview={final[:300]}")
    return {"final_response": final, "messages": []}
```

The key changes:
1. Chat intent path: unchanged — returns `"messages": [response]` (responder is the only response node)
2. Tool_use/research/delegate path: returns `"messages": []` instead of `"messages": [response]` (executor already added its message)
3. Both fallback paths: return `"messages": []`

- [ ] **Step 2: Run the new tests to verify they pass**

Run: `uv run pytest tests/test_graph.py::TestResponderMessageOutput -v`
Expected: All 5 tests PASS.

- [ ] **Step 3: Run full test suite to check no regressions**

Run: `make check && make test`
Expected: All tests pass. Existing integration tests in `TestGraphIntegration` and `test_e2e_whatsapp.py` should still pass because they assert on `final_response` (which is still set correctly).

- [ ] **Step 4: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "fix: stop responder from duplicating AI messages for tool_use intent"
```

---

### Task 3: Write integration test verifying single AI message per turn

**Files:**
- Modify: `tests/test_graph.py` (add test class)

- [ ] **Step 1: Write integration test that counts AI messages per turn**

Add to `tests/test_graph.py` after `TestResponderMessageOutput`:

```python
class TestSingleAIMessagePerTurn:
    """Integration tests verifying exactly 1 AI message is added per turn."""

    @pytest.mark.asyncio
    async def test_tool_use_adds_exactly_one_ai_message(self) -> None:
        """After a tool_use turn, state should have exactly 1 HumanMessage + 1 AIMessage."""
        from unittest.mock import patch

        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "tool_use", "tool_plan": "web_search", "skip_tools": false}'),
                AIMessage(content="WhatsApp formatted news"),
            ]
        )

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_sub = MagicMock()
            mock_sub.ainvoke = AsyncMock(
                return_value={"messages": [AIMessage(content="News results from search")]}
            )
            mock_create.return_value = mock_sub

            graph = create_assistant_graph(
                model=mock_model,
                tools=[MagicMock(name="web_search")],
                system_prompt="You are a test assistant.",
            )

            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="What's the news?")]},
                config={"configurable": {"thread_id": "test-single-msg-tool-use"}},
            )

        ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert len(ai_msgs) == 1, (
            f"Expected exactly 1 AIMessage after tool_use turn, got {len(ai_msgs)}. "
            f"Contents: {[m.content[:50] for m in ai_msgs]}"
        )

    @pytest.mark.asyncio
    async def test_chat_adds_exactly_one_ai_message(self) -> None:
        """After a chat turn, state should have exactly 1 HumanMessage + 1 AIMessage."""
        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}'),
                AIMessage(content="Hello! How can I help?"),
            ]
        )

        graph = create_assistant_graph(
            model=mock_model,
            tools=[],
            system_prompt="You are a test assistant.",
        )

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="Hello")]},
            config={"configurable": {"thread_id": "test-single-msg-chat"}},
        )

        ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert len(ai_msgs) == 1, (
            f"Expected exactly 1 AIMessage after chat turn, got {len(ai_msgs)}"
        )

    @pytest.mark.asyncio
    async def test_research_adds_exactly_one_ai_message(self) -> None:
        """After a research turn, state should have exactly 1 AIMessage."""
        from unittest.mock import patch

        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "research", "tool_plan": "1. web_search\\n2. web_fetch", "skip_tools": false}'),
                AIMessage(content="Formatted research results"),
            ]
        )

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_sub = MagicMock()
            mock_sub.ainvoke = AsyncMock(
                return_value={"messages": [AIMessage(content="Research results")]}
            )
            mock_create.return_value = mock_sub

            graph = create_assistant_graph(
                model=mock_model,
                tools=[MagicMock(name="web_search"), MagicMock(name="web_fetch")],
                system_prompt="You are a test assistant.",
            )

            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="Compare React vs Vue")]},
                config={"configurable": {"thread_id": "test-single-msg-research"}},
            )

        ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert len(ai_msgs) == 1, (
            f"Expected exactly 1 AIMessage after research turn, got {len(ai_msgs)}"
        )

    @pytest.mark.asyncio
    async def test_multi_turn_accumulates_one_ai_per_turn(self) -> None:
        """Over multiple turns, each turn should add exactly 1 AI message.

        Simulates 3 turns (2 chat, 1 tool_use) and verifies the final
        state has exactly 3 HumanMessages and 3 AIMessages.
        """
        from unittest.mock import patch

        from agntrick.graph import create_assistant_graph

        thread_id = "test-multi-turn-single-ai"

        # --- Turn 1: chat ---
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}'),
                AIMessage(content="Hello!"),
            ]
        )

        graph = create_assistant_graph(
            model=mock_model,
            tools=[MagicMock(name="web_search")],
            system_prompt="You are a test assistant.",
        )

        result1 = await graph.ainvoke(
            {"messages": [HumanMessage(content="Hi")]},
            config={"configurable": {"thread_id": thread_id}},
        )

        ai_after_turn1 = [m for m in result1["messages"] if isinstance(m, AIMessage)]
        assert len(ai_after_turn1) == 1, f"Turn 1: expected 1 AI msg, got {len(ai_after_turn1)}"

        # --- Turn 2: tool_use ---
        mock_model2 = AsyncMock()
        mock_model2.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "tool_use", "tool_plan": "web_search", "skip_tools": false}'),
                AIMessage(content="Formatted news"),
            ]
        )

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_sub = MagicMock()
            mock_sub.ainvoke = AsyncMock(
                return_value={"messages": [AIMessage(content="News results")]}
            )
            mock_create.return_value = mock_sub

            graph2 = create_assistant_graph(
                model=mock_model2,
                tools=[MagicMock(name="web_search")],
                system_prompt="You are a test assistant.",
            )

            result2 = await graph2.ainvoke(
                {"messages": [HumanMessage(content="What's the news?")]},
                config={"configurable": {"thread_id": thread_id}},
            )

        # After turn 2, we should have exactly 2 AI messages total
        # (1 from turn 1 + 1 from turn 2)
        ai_after_turn2 = [m for m in result2["messages"] if isinstance(m, AIMessage)]
        assert len(ai_after_turn2) == 1, (
            f"Turn 2: expected 1 NEW AI msg (total should be 1 since state is per-invoke), "
            f"got {len(ai_after_turn2)}"
        )
```

- [ ] **Step 2: Run the new integration tests**

Run: `uv run pytest tests/test_graph.py::TestSingleAIMessagePerTurn -v`
Expected: All 4 tests PASS (the fix from Task 2 already ensures this).

- [ ] **Step 3: Commit**

```bash
git add tests/test_graph.py
git commit -m "test: add integration tests verifying single AI message per graph turn"
```

---

### Task 4: Add conversation history window for responder chat intent

**Files:**
- Modify: `src/agntrick/graph.py` (add constant + windowing)
- Modify: `tests/test_graph.py` (add tests)

- [ ] **Step 1: Write failing tests for chat history windowing**

Add to `tests/test_graph.py` after `TestSingleAIMessagePerTurn`:

```python
class TestResponderChatWindow:
    """Tests for responder chat history windowing."""

    @pytest.mark.asyncio
    async def test_chat_intent_trims_long_history(self) -> None:
        """Responder for chat should cap messages to a sliding window."""
        from agntrick.graph import responder_node

        mock_model = AsyncMock()
        captured_messages: list[Any] = []

        async def capture_invoke(messages: list[Any]) -> AIMessage:
            captured_messages.append(messages)
            return AIMessage(content="Response")

        mock_model.ainvoke = capture_invoke

        # Build a long conversation: 20 exchange pairs = 40 messages
        long_history: list[Any] = []
        for i in range(20):
            long_history.append(HumanMessage(content=f"Question {i}"))
            long_history.append(AIMessage(content=f"Answer {i}"))

        state: AgentState = {
            "messages": long_history,
            "intent": "chat",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        await responder_node(state, {}, model=mock_model)

        # The responder should NOT send all 40 messages
        sent_messages = captured_messages[0]
        non_system = [m for m in sent_messages if not isinstance(m, SystemMessage)]
        assert len(non_system) < 40, (
            f"Responder sent all {len(non_system)} messages — should be windowed"
        )

    @pytest.mark.asyncio
    async def test_chat_intent_window_preserves_recent_messages(self) -> None:
        """Responder windowing should keep the most recent messages."""
        from agntrick.graph import responder_node

        mock_model = AsyncMock()
        captured_messages: list[Any] = []

        async def capture_invoke(messages: list[Any]) -> AIMessage:
            captured_messages.append(messages)
            return AIMessage(content="Response")

        mock_model.ainvoke = capture_invoke

        state: AgentState = {
            "messages": [
                HumanMessage(content="Old question"),
                AIMessage(content="Old answer"),
                HumanMessage(content="Recent question"),
                AIMessage(content="Recent answer"),
                HumanMessage(content="Latest question"),
            ],
            "intent": "chat",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        await responder_node(state, {}, model=mock_model)

        sent_messages = captured_messages[0]
        human_contents = [m.content for m in sent_messages if isinstance(m, HumanMessage)]
        assert "Latest question" in human_contents, (
            f"Window should include latest message, got: {human_contents}"
        )
        assert "Recent question" in human_contents, (
            f"Window should include recent messages, got: {human_contents}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_graph.py::TestResponderChatWindow -v`
Expected: `test_chat_intent_trims_long_history` FAILS (responder currently sends all messages). `test_chat_intent_window_preserves_recent_messages` may pass (short conversation fits in any window).

- [ ] **Step 3: Add windowing constant and helper to graph.py**

In `src/agntrick/graph.py`, add a new constant after `_ROUTER_CONTEXT_WINDOW` (around line 32):

```python
# Maximum number of recent messages the responder sees for chat intent.
# Matches _ROUTER_CONTEXT_WINDOW — enough for follow-up understanding
# without wasting tokens on stale context.
_RESPONDER_CHAT_WINDOW = 5
```

Add a new helper function after `_truncate_messages` (after line 116):

```python
def _window_messages(
    messages: list[BaseMessage],
    max_messages: int,
) -> list[BaseMessage]:
    """Keep only the most recent messages within a window.

    Args:
        messages: Full message history.
        max_messages: Maximum number of messages to keep.

    Returns:
        List of the most recent messages (up to max_messages).
    """
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]
```

Update the responder_node chat path to use the window (around line 505). Change:

```python
    if state.get("intent") == "chat":
        msgs = state["messages"]  # Chat needs full conversation history for follow-ups
```

To:

```python
    if state.get("intent") == "chat":
        msgs = _window_messages(state["messages"], _RESPONDER_CHAT_WINDOW)
```

- [ ] **Step 4: Run the new tests**

Run: `uv run pytest tests/test_graph.py::TestResponderChatWindow -v`
Expected: Both tests PASS.

- [ ] **Step 5: Run full suite**

Run: `make check && make test`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "fix: cap responder chat history to sliding window of 20 messages"
```

---

### Task 5: Update AGENTS.md diagram to reflect the fix

**Files:**
- Modify: `AGENTS.md` (update Graph Detail mermaid diagram)

- [ ] **Step 1: Update the graph description in AGENTS.md**

In `AGENTS.md`, find the "Graph Detail (3-Node StateGraph)" mermaid diagram section. Update the RESP node description to clarify it does NOT add duplicate messages:

Change the RESP node label from:
```
RESP["<b>Responder</b><br/>Format for WhatsApp<br/><small>max 15K chars</small>"]
```

To:
```
RESP["<b>Responder</b><br/>Format for WhatsApp<br/><small>chat: adds msg to state<br/>tool_use: sets final_response only<br/>max 15K chars</small>"]
```

- [ ] **Step 2: Verify diagram renders correctly**

Run: `grep -A 20 "Graph Detail" AGENTS.md`
Expected: The mermaid diagram is syntactically valid with the updated RESP label.

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: update graph diagram to reflect responder message dedup fix"
```

---

### Task 6: Final validation

**Files:** None (validation only)

- [ ] **Step 1: Run full check and test suite**

Run: `make check && make test`
Expected: All pass.

- [ ] **Step 2: Verify no duplicate messages in existing integration tests**

Run: `uv run pytest tests/test_graph.py tests/test_integration/test_e2e_whatsapp.py -v --tb=short`
Expected: All tests pass. No test relied on duplicate messages.

- [ ] **Step 3: Smoke test — verify graph produces correct output structure**

Run: `uv run python -c "
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage
import asyncio

async def test():
    from agntrick.graph import create_assistant_graph

    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(content='{\"intent\": \"tool_use\", \"tool_plan\": \"web_search\", \"skip_tools\": false}'),
            AIMessage(content='Formatted: News here'),
        ]
    )

    with patch('agntrick.graph.create_agent') as mock_create:
        mock_sub = MagicMock()
        mock_sub.ainvoke = AsyncMock(return_value={'messages': [AIMessage(content='News results')]})
        mock_create.return_value = mock_sub

        graph = create_assistant_graph(
            model=mock_model,
            tools=[MagicMock(name='web_search')],
            system_prompt='You are a test.',
        )

        result = await graph.ainvoke(
            {'messages': [HumanMessage(content='news?')]},
            config={'configurable': {'thread_id': 'smoke-test'}},
        )

    ai_msgs = [m for m in result['messages'] if isinstance(m, AIMessage)]
    print(f'AI messages in output: {len(ai_msgs)}')
    print(f'final_response: {result[\"final_response\"][:80]}')
    assert len(ai_msgs) == 1, f'Expected 1 AI msg, got {len(ai_msgs)}'
    assert result['final_response'] is not None
    print('PASS: exactly 1 AI message, final_response set correctly')

asyncio.run(test())
"`
Expected output:
```
AI messages in output: 1
final_response: Formatted: News here
PASS: exactly 1 AI message, final_response set correctly
```
