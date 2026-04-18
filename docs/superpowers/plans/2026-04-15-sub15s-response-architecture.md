# Sub-15s WhatsApp Response Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce WhatsApp assistant response time to under 15s by removing the responder LLM call, pooling agent instances, and reusing MCP connections.

**Architecture:** 3-node graph (Summarize → Router → Agent) replaces the current 4-node graph (Summarize → Router → Executor → Responder). The responder's WhatsApp formatting is replaced with a template function. Agent instances are pooled per tenant and reused across requests with persistent MCP connections.

**Tech Stack:** Python 3.12, LangGraph, LangChain, FastAPI, AsyncSqliteSaver, MCP (SSE)

**Spec:** `docs/superpowers/specs/2026-04-15-sub15s-response-architecture-design.md`

---

## Subagent Model Tier Guidance

When executing this plan's tasks via subagents (e.g., using `superpowers:subagent-driven-development`), use the following Claude Code model tiers to balance cost and capability:

| Model Tier | Use For | Examples |
|------------|---------|----------|
| **haiku** (glm-4.7) | Simple, repetitive tasks | Writing tests, simple file edits, formatting, commits |
| **sonnet** (glm-5.1) | Moderate complexity | Graph refactors, adding new functions, class changes |
| **opus** (claude-opus-4-6) | Complex, multi-file tasks | Architecture design, cross-file refactors, tricky debugging |

**Rationale:** Haiku is fastest/cheapest for straightforward work like test generation. Sonnet balances quality and cost for most implementation tasks. Reserve opus for tasks requiring deep reasoning or complex coordination.

Each task below includes a `[Model: ...]` tag indicating the recommended tier.

---

## File Map

| File | Responsibility | Status |
|------|---------------|--------|
| `src/agntrick/graph.py` | 3-node graph, `_format_for_whatsapp()`, agent_node | Modify |
| `src/agntrick/api/routes/whatsapp.py` | Webhook handler using agent pool | Modify |
| `src/agntrick/api/server.py` | Agent discovery at startup, pool init | Modify |
| `src/agntrick/api/pool.py` | TenantAgentPool class | Create |
| `src/agntrick/agents/assistant.py` | Updated graph creation, model routing | Modify |
| `tests/test_graph.py` | Graph routing, agent node, formatting tests | Modify |
| `tests/test_pool.py` | Agent pool tests | Create |

---

## Phase 1: Template WhatsApp Formatting

Removes the responder LLM call. Independent of all other changes.

### Task 1: Implement `_format_for_whatsapp()` function `[Model: haiku]`

**Files:**
- Modify: `src/agntrick/graph.py` (add after `_sanitize_ai_content`, around line 87)
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing tests**

Add a new test class `TestFormatForWhatsApp` to `tests/test_graph.py`:

```python
class TestFormatForWhatsApp:
    """Tests for template-based WhatsApp formatting (replaces responder LLM)."""

    def test_truncates_to_4096_chars(self) -> None:
        from agntrick.graph import _format_for_whatsapp

        long_text = "A" * 10_000
        result = _format_for_whatsapp(long_text)
        assert len(result) <= 4096
        assert result.endswith("...")

    def test_strips_xml_tool_artifacts(self) -> None:
        from agntrick.graph import _format_for_whatsapp

        text = 'Here is the result.\n<web_search query="barcelona"/>'
        result = _format_for_whatsapp(text)
        assert "<web_search" not in result
        assert "Here is the result." in result

    def test_strips_raw_json_blocks(self) -> None:
        from agntrick.graph import _format_for_whatsapp

        text = 'The score is 2-1.\n{"type": "text", "text": "extra data"}'
        result = _format_for_whatsapp(text)
        assert '{"type":' not in result
        assert "The score is 2-1." in result

    def test_passes_short_text_unchanged(self) -> None:
        from agntrick.graph import _format_for_whatsapp

        text = "Hello! The weather is nice today."
        result = _format_for_whatsapp(text)
        assert result == text

    def test_handles_empty_string(self) -> None:
        from agntrick.graph import _format_for_whatsapp

        assert _format_for_whatsapp("") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_graph.py::TestFormatForWhatsApp -v`
Expected: FAIL with `ImportError: cannot import name '_format_for_whatsapp'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/agntrick/graph.py` after `_sanitize_ai_content` (around line 87):

```python
_WHATSAPP_CHAR_LIMIT = 4096

# Regex to strip raw JSON content blocks from tool output
_JSON_BLOCK_RE = re.compile(r"\n?\{[^{}]*\}(?=\n|$)", re.MULTILINE)


def _format_for_whatsapp(content: str) -> str:
    """Format agent output for WhatsApp without an LLM call.

    Strips tool artifacts, raw JSON, and truncates to WhatsApp char limit.

    Args:
        content: Raw agent response text.

    Returns:
        WhatsApp-friendly formatted string (max 4096 chars).
    """
    if not content:
        return content

    # Strip XML tool artifacts
    cleaned = _sanitize_ai_content(content)

    # Strip raw JSON content blocks (e.g., {"type": "text", "text": "..."})
    cleaned = _JSON_BLOCK_RE.sub("", cleaned).strip()

    # Truncate to WhatsApp limit
    if len(cleaned) > _WHATSAPP_CHAR_LIMIT:
        cleaned = cleaned[: _WHATSAPP_CHAR_LIMIT - 3] + "..."

    return cleaned
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_graph.py::TestFormatForWhatsApp -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Run full check**

Run: `make check && make test`
Expected: All 643+ tests pass, no lint errors

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "feat: add _format_for_whatsapp template function (replaces responder LLM)"
```

---

## Phase 2: 3-Node Graph Refactor

Replaces the 4-node graph (Summarize → Router → Executor → Responder) with a 3-node graph (Summarize → Router → Agent). The router gets a chat fast-path.

### Task 2: Rename executor_node → agent_node and add WhatsApp formatting `[Model: sonnet]`

**Files:**
- Modify: `src/agntrick/graph.py` — rename `executor_node` to `agent_node`, apply `_format_for_whatsapp()` at the end, remove `responder_node`
- Modify: `tests/test_graph.py`

- [ ] **Step 1: Write failing test for agent_node producing final_response**

Add to `tests/test_graph.py` in the executor/agent test section:

```python
class TestAgentNodeOutput:
    """Tests for the unified agent_node (executor + formatting)."""

    @pytest.mark.asyncio
    async def test_tool_use_produces_final_response(self) -> None:
        """Agent node for tool_use should set final_response via template."""
        from agntrick.graph import agent_node

        state: AgentState = {
            "messages": [HumanMessage(content="test")],
            "intent": "tool_use",
            "tool_plan": "web_search",
            "progress": [],
            "final_response": None,
        }
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="Result here"))

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_sub = MagicMock()
            mock_sub.ainvoke = AsyncMock(return_value={
                "messages": [AIMessage(content="The score is 2-1.")]
            })
            mock_create.return_value = mock_sub

            result = await agent_node(
                state, MagicMock(),
                model=mock_model,
                tools=[MagicMock(name="web_search")],
                system_prompt="test",
            )

        assert result.get("final_response") is not None
        assert "2-1" in result["final_response"]
```

- [ ] **Step 2: Rename executor_node to agent_node in graph.py**

In `src/agntrick/graph.py`:
- Rename `async def executor_node(` to `async def agent_node(`
- At the end of `agent_node`, before the return, apply `_format_for_whatsapp()` and set `final_response`:

Replace the final return in `agent_node` (the line `return {"messages": [final_msg]}`):

```python
    # Format for WhatsApp via template (no LLM call)
    formatted = _format_for_whatsapp(final_msg.content if isinstance(final_msg, AIMessage) else str(final_msg.content))
    logger.info(f"[agent] final_response len={len(formatted)} preview={formatted[:300]}")

    # Prune old messages
    removes = _build_prune_removes(state["messages"], _MAX_STATE_MESSAGES)
    return {"final_response": formatted, "messages": [final_msg] + removes}
```

- [ ] **Step 3: Remove responder_node function**

Delete the entire `async def responder_node(...)` function from `graph.py`.

- [ ] **Step 4: Update create_assistant_graph to 3-node**

Replace `create_assistant_graph` in `graph.py`:

```python
def create_assistant_graph(
    model: Any,
    tools: Sequence[Any],
    system_prompt: str,
    checkpointer: Any | None = None,
    progress_callback: ProgressCallback = None,
    router_model: Any | None = None,
    agent_model: Any | None = None,
) -> Any:
    """Create the 3-node assistant StateGraph.

    Summarize → Router → Agent (with template WhatsApp formatting)
    Chat intent: Router responds directly (1 LLM call).

    Args:
        model: Primary LLM model instance.
        tools: Sequence of tools available to the agent.
        system_prompt: Base system prompt for the agent.
        checkpointer: Optional checkpointer for persistent memory.
        progress_callback: Optional async callback for progress updates.
        router_model: Optional model override for the router node.
        agent_model: Optional model override for the agent node.

    Returns:
        Compiled StateGraph ready for ainvoke().
    """
    _router_model = router_model or model
    _agent_model = agent_model or model

    async def _summarize(state: AgentState, config: RunnableConfig) -> dict:
        return await summarize_node(state, config, model=model)

    async def _router(state: AgentState, config: RunnableConfig) -> dict:
        return await router_node(state, config, model=_router_model)

    async def _agent(state: AgentState, config: RunnableConfig) -> dict:
        return await agent_node(
            state,
            config,
            model=_agent_model,
            tools=tools,
            system_prompt=system_prompt,
            progress_callback=progress_callback,
        )

    graph = StateGraph(AgentState)
    graph.add_node("summarize", _summarize)
    graph.add_node("router", _router)
    graph.add_node("agent", _agent)
    graph.set_entry_point("summarize")
    graph.add_edge("summarize", "router")
    graph.add_conditional_edges(
        "router",
        route_decision,
        {"agent": "agent", "responder": END},
    )
    graph.add_edge("agent", END)
    return graph.compile(checkpointer=checkpointer or InMemorySaver())
```

- [ ] **Step 5: Update route_decision for chat fast-path**

Replace `route_decision` in `graph.py`:

```python
def route_decision(state: AgentState) -> str:
    """Decide next node after Router.

    For chat intent: respond directly (router sets final_response).
    For other intents: route to agent node.
    """
    if state.get("intent") == "chat":
        return "responder"  # END — router already set final_response
    return "agent"
```

Update `router_node` to set `final_response` for chat intent. In the `router_node` function, after the existing return, modify the chat path:

```python
async def router_node(state: AgentState, config: RunnableConfig, *, model: Any) -> dict:
    """Classify intent and decide strategy. For chat, respond directly."""
    # ... existing context window and LLM call code stays the same ...

    parsed = _parse_router_response(response.content)
    intent = parsed.get("intent", "chat")
    tool_plan = parsed.get("tool_plan")
    logger.info(f"[router] output: intent={intent}, plan={str(tool_plan)[:200] if tool_plan else 'None'}")

    # Chat fast-path: respond directly with formatted output
    if intent == "chat":
        formatted = _format_for_whatsapp(str(response.content))
        return {
            "intent": intent,
            "tool_plan": tool_plan,
            "final_response": formatted,
        }

    return {
        "intent": intent,
        "tool_plan": tool_plan,
    }
```

- [ ] **Step 6: Run tests and fix failures**

Run: `make check && make test`

Expected: Some test failures due to renamed function and removed responder. Fix by:
- Updating all references to `executor_node` → `agent_node`
- Updating all references to `responder_model` → `agent_model`
- Removing/updating responder-specific tests

- [ ] **Step 7: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "refactor: 3-node graph (summarize → router → agent) with template formatting"
```

### Task 3: Update assistant.py for model routing `[Model: sonnet]`

**Files:**
- Modify: `src/agntrick/agents/assistant.py`
- Modify: `src/agntrick/agent.py` (update `_get_node_models`)

- [ ] **Step 1: Update _get_node_models in agent.py**

Change the node names in `_get_node_models` from `("router", "executor", "responder")` to `("router", "agent")`:

```python
def _get_node_models(self) -> dict[str, Any]:
    """Resolve per-node model instances for graph nodes.

    Returns:
        Dict mapping node names ("router", "agent") to model instances.
        Only includes nodes that have explicit overrides configured.
    """
    config = get_config()
    node_map = config.agent_models.node_overrides.get(self._agent_name, {})
    overrides: dict[str, Any] = {}
    for node in ("router", "agent"):
        node_model_name = node_map.get(node)
        if node_model_name:
            overrides[node] = _create_model(node_model_name, config.llm.temperature)
    return overrides
```

- [ ] **Step 2: Update assistant.py _create_graph**

Change parameter names from `executor_model`/`responder_model` to `agent_model`:

```python
def _create_graph(self, model, tools, system_prompt, checkpointer):
    """Use the 3-node StateGraph with per-node model overrides."""
    node_models = self._get_node_models()
    return create_assistant_graph(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        progress_callback=self._progress_callback,
        router_model=node_models.get("router"),
        agent_model=node_models.get("agent"),
    )
```

- [ ] **Step 3: Run tests**

Run: `make check && make test`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/agntrick/agents/assistant.py src/agntrick/agent.py
git commit -m "refactor: update model routing for 3-node graph (router=glm-4.7, agent=glm-5.1)"
```

### Task 4: Update DO config for model routing `[Model: haiku]`

**Files:** No code change — config update on droplet

- [ ] **Update `.agntrick.yaml` on DO droplet with:**

```yaml
agent_models:
  assistant: glm-5.1
  assistant_nodes:
    router: glm-4.7    # classification only — cheap and fast
    agent: glm-5.1     # execution — needs quality
```

This ensures glm-4.7 handles the cheap router work (~2s) while glm-5.1 handles the complex agent execution.

---

## Phase 3: Agent Pool

Creates `TenantAgentPool` to reuse agent instances across requests.

### Task 5: Implement TenantAgentPool `[Model: sonnet]`

**Files:**
- Create: `src/agntrick/api/pool.py`
- Create: `tests/test_pool.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pool.py`:

```python
"""Tests for TenantAgentPool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTenantAgentPool:
    """Tests for agent pooling per tenant."""

    def test_pool_starts_empty(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool()
        assert len(pool) == 0

    @pytest.mark.asyncio
    async def test_creates_agent_on_first_request(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool(max_size=5)
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value="Hello")

        with patch.object(pool, "_create", return_value=mock_agent) as mock_create:
            agent = await pool.get_or_create(
                tenant_id="primary",
                agent_name="assistant",
                agent_cls=MagicMock(),
                agent_kwargs={},
            )
            assert agent is mock_agent
            assert mock_create.call_count == 1
            assert len(pool) == 1

    @pytest.mark.asyncio
    async def test_reuses_agent_on_second_request(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool(max_size=5)
        mock_agent = MagicMock()

        with patch.object(pool, "_create", return_value=mock_agent):
            agent1 = await pool.get_or_create(
                tenant_id="primary", agent_name="assistant",
                agent_cls=MagicMock(), agent_kwargs={},
            )
            agent2 = await pool.get_or_create(
                tenant_id="primary", agent_name="assistant",
                agent_cls=MagicMock(), agent_kwargs={},
            )
            assert agent1 is agent2
            assert len(pool) == 1

    @pytest.mark.asyncio
    async def test_separate_tenants_get_separate_agents(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool(max_size=5)

        with patch.object(pool, "_create", side_effect=[MagicMock(), MagicMock()]):
            agent1 = await pool.get_or_create(
                tenant_id="tenant-a", agent_name="assistant",
                agent_cls=MagicMock(), agent_kwargs={},
            )
            agent2 = await pool.get_or_create(
                tenant_id="tenant-b", agent_name="assistant",
                agent_cls=MagicMock(), agent_kwargs={},
            )
            assert agent1 is not agent2
            assert len(pool) == 2

    def test_evict_removes_oldest_entry(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool(max_size=2)
        pool._agents = {
            "tenant-a:assistant": MagicMock(),
            "tenant-b:assistant": MagicMock(),
        }
        pool._access_order = ["tenant-a:assistant", "tenant-b:assistant"]

        pool._evict_if_needed()

        assert "tenant-a:assistant" not in pool._agents
        assert "tenant-b:assistant" in pool._agents
        assert len(pool) == 1

    @pytest.mark.asyncio
    async def test_evict_calls_cleanup(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool(max_size=1)
        mock_old = MagicMock()
        mock_old.cleanup = AsyncMock()
        pool._agents = {"old:assistant": mock_old}
        pool._access_order = ["old:assistant"]

        pool._evict_if_needed()

        mock_old.cleanup.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agntrick.api.pool'`

- [ ] **Step 3: Implement TenantAgentPool**

Create `src/agntrick/api/pool.py`:

```python
"""Tenant-scoped agent pool for reusing agent instances across requests."""

import asyncio
import logging
import time
from typing import Any

from agntrick.agent import AgentBase

logger = logging.getLogger(__name__)


class TenantAgentPool:
    """Pool of agent instances keyed by tenant_id:agent_name.

    Agents are created on first access and reused across requests.
    LRU eviction when pool exceeds max_size.
    """

    def __init__(self, max_size: int = 10) -> None:
        self._agents: dict[str, AgentBase] = {}
        self._access_order: list[str] = []
        self._lock = asyncio.Lock()
        self.max_size = max_size

    def __len__(self) -> int:
        return len(self._agents)

    async def get_or_create(
        self,
        tenant_id: str,
        agent_name: str,
        agent_cls: type,
        agent_kwargs: dict[str, Any],
    ) -> AgentBase:
        """Get a pooled agent or create one if not cached.

        Args:
            tenant_id: Tenant identifier.
            agent_name: Agent name (e.g., "assistant").
            agent_cls: Agent class to instantiate.
            agent_kwargs: Keyword arguments for agent constructor.

        Returns:
            Agent instance (pooled or freshly created).
        """
        key = f"{tenant_id}:{agent_name}"

        if key in self._agents:
            self._touch(key)
            logger.debug(f"[pool] reuse agent: {key}")
            return self._agents[key]

        async with self._lock:
            # Double-checked locking
            if key in self._agents:
                self._touch(key)
                return self._agents[key]

            self._evict_if_needed()
            agent = await self._create(agent_cls, agent_kwargs)
            self._agents[key] = agent
            self._access_order.append(key)
            logger.info(f"[pool] created agent: {key} (pool_size={len(self._agents)})")
            return agent

    async def _create(
        self,
        agent_cls: type,
        agent_kwargs: dict[str, Any],
    ) -> AgentBase:
        """Create and initialize a new agent instance.

        Args:
            agent_cls: Agent class to instantiate.
            agent_kwargs: Constructor arguments.

        Returns:
            Initialized agent with MCP tools loaded.
        """
        agent = agent_cls(**agent_kwargs)
        # Trigger lazy initialization (MCP connection, graph compilation)
        await agent._ensure_initialized()
        return agent

    def _touch(self, key: str) -> None:
        """Move key to end of access order (most recently used)."""
        if key in self._access_order:
            self._access_order.remove(key)
            self._access_order.append(key)

    def _evict_if_needed(self) -> None:
        """Evict oldest entry if pool is at capacity."""
        while len(self._agents) >= self.max_size and self._access_order:
            oldest_key = self._access_order.pop(0)
            agent = self._agents.pop(oldest_key, None)
            if agent and hasattr(agent, "cleanup"):
                # Fire-and-forget cleanup
                asyncio.create_task(self._safe_cleanup(agent, oldest_key))
            logger.info(f"[pool] evicted agent: {oldest_key}")

    @staticmethod
    async def _safe_cleanup(agent: AgentBase, key: str) -> None:
        """Safely clean up an evicted agent."""
        try:
            await agent.cleanup()
        except Exception as e:
            logger.warning(f"[pool] cleanup failed for {key}: {e}")

    async def evict(self, tenant_id: str, agent_name: str) -> None:
        """Manually evict an agent (e.g., after MCP connection failure).

        Args:
            tenant_id: Tenant identifier.
            agent_name: Agent name.
        """
        key = f"{tenant_id}:{agent_name}"
        agent = self._agents.pop(key, None)
        if key in self._access_order:
            self._access_order.remove(key)
        if agent and hasattr(agent, "cleanup"):
            await self._safe_cleanup(agent, key)
        logger.info(f"[pool] manually evicted: {key}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pool.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run full suite**

Run: `make check && make test`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/api/pool.py tests/test_pool.py
git commit -m "feat: add TenantAgentPool for reusing agent instances across requests"
```

### Task 6: Wire agent pool into webhook handler `[Model: sonnet]`

**Files:**
- Modify: `src/agntrick/api/routes/whatsapp.py`
- Modify: `src/agntrick/api/server.py`

- [ ] **Step 1: Add pool initialization to server lifespan**

In `src/agntrick/api/server.py`, inside the `lifespan` function, after `app.state.tenant_manager = ...`:

```python
    from agntrick.api.pool import TenantAgentPool
    from agntrick.registry import AgentRegistry

    AgentRegistry.discover_agents()
    app.state.agent_pool = TenantAgentPool(max_size=10)
    logger.info("Agent pool initialized (max_size=10)")
```

Also in the shutdown section (before `app.state.tenant_manager.close_all()`):

```python
    # Evict all pooled agents
    pool = getattr(app.state, "agent_pool", None)
    if pool:
        for key in list(pool._agents.keys()):
            tenant_id, agent_name = key.split(":", 1)
            await pool.evict(tenant_id, agent_name)
```

- [ ] **Step 2: Modify webhook to use pool instead of per-request creation**

In `src/agntrick/api/routes/whatsapp.py`, replace the agent creation block (lines ~378-432). The new approach:

```python
    # Run the tenant's configured agent
    agent_name = tenant_config.default_agent
    try:
        config = get_config()

        # Look up MCP servers and tool categories registered for this agent
        allowed_mcp = AgentRegistry.get_mcp_servers(agent_name)
        tool_categories = AgentRegistry.get_tool_categories(agent_name)

        # Build thread_id for persistent memory
        thread_id = f"whatsapp:{tenant_id}:{phone}"
        tenant_logger.info("Using persistent memory for thread: %s", thread_id)

        # Get the agent pool from app state
        pool = request.app.state.agent_pool
        agent_cls = AgentRegistry.get(agent_name)

        if not agent_cls:
            tenant_logger.error("Agent '%s' not found for tenant %s", agent_name, tenant_id)
            raise HTTPException(status_code=500, detail="Agent not found")

        # Build agent kwargs (model, MCP, etc.)
        agent_kwargs: dict[str, Any] = dict(
            _agent_name=agent_name,
            tool_categories=tool_categories,
            model_name=config.llm.model,
            temperature=config.llm.temperature,
            thread_id=thread_id,
            progress_callback=lambda msg: tenant_logger.debug("Progress: %s", msg),
        )

        if allowed_mcp:
            agent_kwargs["mcp_server_names"] = allowed_mcp

        # Get or create pooled agent
        agent = await pool.get_or_create(
            tenant_id=tenant_id,
            agent_name=agent_name,
            agent_cls=agent_cls,
            agent_kwargs=agent_kwargs,
        )

        result = await asyncio.wait_for(
            agent.run(message, config={"configurable": {"thread_id": thread_id}}),
            timeout=300,
        )

        tenant_logger.info("Successfully processed WhatsApp message for tenant %s", tenant_id)
        return {"response": str(result) if result is not None else "", "tenant_id": tenant_id}
```

Note: The agent's `__init__` needs to accept `mcp_server_names` for the pool to pass MCP config at creation time. This means adding a small change to `AgentBase.__init__` to store `mcp_server_names` and use them in `_ensure_initialized`.

- [ ] **Step 3: Add mcp_server_names support to AgentBase**

In `src/agntrick/agent.py`, add `mcp_server_names` parameter to `__init__`:

```python
def __init__(
    self,
    ...
    mcp_server_names: list[str] | None = None,
    ...
):
    ...
    self._mcp_server_names = mcp_server_names
```

And update `_ensure_initialized` to use it:

```python
async def _ensure_initialized(self) -> None:
    if self._graph is not None:
        return
    async with self._init_lock:
        if self._graph is not None:
            return

        if self._tool_manifest is None and self._tool_categories:
            self._tool_manifest = await self._fetch_tool_manifest()

        system_prompt = self._get_system_prompt()

        # Load MCP tools — use persistent provider if mcp_server_names given
        if self._mcp_server_names and self._mcp_provider is None:
            self._mcp_provider = MCPProvider(server_names=self._mcp_server_names)
            mcp_tools = await self._mcp_provider.get_tools()
            self._tools.extend(mcp_tools)
        else:
            self._tools.extend(await self._load_mcp_tools())

        self._graph = self._create_graph(...)
```

- [ ] **Step 4: Run tests**

Run: `make check && make test`
Expected: All tests pass. Some whatsapp webhook tests may need updates for the pool pattern.

- [ ] **Step 5: Commit**

```bash
git add src/agntrick/api/routes/whatsapp.py src/agntrick/api/server.py src/agntrick/agent.py
git commit -m "feat: wire TenantAgentPool into webhook handler, discover agents at startup"
```

---

## Phase 4: MCP + DB Connection Reuse

Makes the pool use persistent MCP connections instead of per-request reconnection.

### Task 7: Persistent MCP connections in pool `[Model: haiku]`

**Files:**
- Modify: `src/agntrick/api/pool.py`
- Modify: `src/agntrick/api/server.py`

- [ ] **Step 1: The agent pool already uses persistent MCP via `get_tools()`**

The `_create` method in `TenantAgentPool` calls `agent._ensure_initialized()` which calls `MCPProvider.get_tools()` — this keeps connections open. No code change needed for this step.

- [ ] **Step 2: Add MCP health check to server lifespan**

In `src/agntrick/api/server.py`, add a periodic health check task:

```python
async def _check_mcp_health(app: FastAPI) -> None:
    """Periodically check MCP health and evict unhealthy agents."""
    import httpx

    config = get_config()
    toolbox_url = config.mcp.toolbox_url or "http://localhost:8080"
    pool = app.state.agent_pool

    while True:
        await asyncio.sleep(60)  # Check every 60s
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{toolbox_url}/health", timeout=5)
                if resp.status_code != 200:
                    logger.warning("Toolbox health check failed, evicting all agents")
                    for key in list(pool._agents.keys()):
                        tenant_id, agent_name = key.split(":", 1)
                        await pool.evict(tenant_id, agent_name)
        except Exception as e:
            logger.warning(f"MCP health check failed: {e}, evicting all agents")
            for key in list(pool._agents.keys()):
                tenant_id, agent_name = key.split(":", 1)
                await pool.evict(tenant_id, agent_name)
```

Start in lifespan after pool init:

```python
    import asyncio
    app.state._health_task = asyncio.create_task(_check_mcp_health(app))
```

Cancel on shutdown:

```python
    if hasattr(app.state, "_health_task"):
        app.state._health_task.cancel()
```

- [ ] **Step 3: Run tests**

Run: `make check && make test`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/agntrick/api/pool.py src/agntrick/api/server.py
git commit -m "feat: add MCP health check for agent pool connection reuse"
```

---

## Spec Coverage Check

| Spec requirement | Task |
|-----------------|------|
| Remove responder LLM | Task 1 (_format_for_whatsapp), Task 2 (graph refactor) |
| Merge executor + formatting | Task 2 (agent_node) |
| Agent pool per tenant | Task 5 (TenantAgentPool), Task 6 (webhook wiring) |
| MCP connection reuse | Task 6 (persistent provider), Task 7 (health check) |
| AsyncSqliteSaver pool | Handled via checkpointer passed to graph.ainvoke config — no separate pool needed |
| Agent discovery at startup | Task 6 (server.py lifespan) |
| Chat fast path | Task 2 (router responds directly for chat) |
| Model routing (glm-4.7/glm-5.1) | Task 3 (_get_node_models, config) |

---

## DO Config After Deployment

```yaml
agent_models:
  assistant: glm-5.1
  developer: glm-5.1
  news: glm-5.1
  learning: glm-5.1
  youtube: glm-5.1
  committer: glm-4.7
  github-pr-reviewer: glm-5.1

  assistant_nodes:
    router: glm-4.7    # ~2s classification — cheap and fast
    agent: glm-5.1      # execution + response — needs quality
```
