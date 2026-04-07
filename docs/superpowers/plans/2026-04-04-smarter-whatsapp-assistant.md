# Smarter WhatsApp Assistant — Implementation Plan

> **Spec:** `docs/superpowers/specs/2026-04-04-smarter-whatsapp-assistant-design.md`
> **Branch:** `fix/typing-indicator-audio-transcription` → new branch `feat/smarter-whatsapp-assistant`
> **Execution:** Use `superpowers:executing-plans` or `superpowers:subagent-driven-development`

---

## Summary

Transform the WhatsApp assistant from a stateless single-shot ReAct agent into a stateful, routing-aware conversational agent with memory, smart tool usage, and multi-turn interaction. Three layers applied in order:

1. **Layer 1 (Memory):** Wire existing SQLite checkpointer into WhatsApp webhook — smallest change, highest impact.
2. **Layer 3 (Prompts):** Rewrite assistant.md with ACI tool-selection rules — independent of graph work.
3. **Layer 2 (Graph):** Build a 3-node StateGraph (Router → Executor → Responder) replacing the single ReAct node — depends on Layer 1.

---

## File Manifest

| Action | File | Purpose |
|--------|------|---------|
| CREATE | `src/agntrick/graph.py` | AgentState, Router/Executor/Responder nodes, StateGraph factory |
| MODIFY | `src/agntrick/agent.py` | Extract `_create_graph()` method from `_ensure_initialized()` |
| MODIFY | `src/agntrick/agents/assistant.py` | Override `_create_graph()` to use custom StateGraph |
| MODIFY | `src/agntrick/api/routes/whatsapp.py` | Wire TenantManager + checkpointer + thread_id; add progress callback |
| MODIFY | `src/agntrick/prompts/assistant.md` | Rewrite with tool selection rules, error recovery, multi-step guidance |
| CREATE | `tests/test_graph.py` | Unit tests for AgentState, Router, Executor, Responder, full graph |
| MODIFY | `tests/test_api/test_whatsapp_route.py` | Add memory persistence test for webhook |

---

## Task 1: Wire persistent memory into WhatsApp webhook

**Layer 1 — Memory. Smallest change, highest immediate impact.**

The infrastructure already exists: `TenantManager` creates per-tenant SQLite databases, `Database.get_checkpointer()` returns `AsyncSqliteSaver`, and `AgentBase` accepts `checkpointer` + `thread_id`. The webhook just doesn't use them.

### Step 1: Write failing test

**File:** `tests/test_api/test_whatsapp_route.py`

Add a new test class `TestWhatsAppMemoryPersistence` that verifies the webhook passes `checkpointer` and a properly scoped `thread_id` to the agent constructor.

```python
class TestWhatsAppMemoryPersistence:
    """Tests that the WhatsApp webhook uses persistent memory."""

    @patch("agntrick.api.routes.whatsapp.MCPProvider")
    @patch("agntrick.api.routes.whatsapp.AgentRegistry")
    @patch("agntrick.api.routes.whatsapp.get_config")
    def test_webhook_passes_checkpointer_and_thread_id(
        self,
        mock_config: MagicMock,
        mock_registry_cls: MagicMock,
        mock_mcp_cls: MagicMock,
    ) -> None:
        """Webhook should pass a checkpointer and scoped thread_id to the agent."""
        from agntrick.api.routes.whatsapp import get_whatsapp_registry
        from agntrick.api.server import create_app

        mock_tenant = MagicMock()
        mock_tenant.id = "tenant-1"
        mock_tenant.default_agent = "assistant"
        mock_tenant.allowed_contacts = None

        mock_config.return_value = MagicMock(
            auth=MagicMock(api_keys={"key": "val"}),
            llm=MagicMock(model="gpt-4", temperature=0.7),
            whatsapp=MagicMock(tenants=[mock_tenant]),
            storage=MagicMock(base_path=None),
        )

        mock_registry_instance = MagicMock()
        mock_registry_instance.lookup_by_phone.return_value = "tenant-1"

        mock_registry_cls.discover_agents = MagicMock()

        mock_agent_instance = AsyncMock()
        mock_agent_instance.run = AsyncMock(return_value="Got it")

        mock_agent_cls = MagicMock()
        constructor_calls: list[dict[str, object]] = []

        def capture_constructor(**kwargs: object) -> MagicMock:
            constructor_calls.append(kwargs)
            return mock_agent_instance

        mock_agent_cls.side_effect = capture_constructor
        mock_registry_cls.get.return_value = mock_agent_cls
        mock_registry_cls.get_mcp_servers.return_value = []
        mock_registry_cls.get_tool_categories.return_value = ["web"]

        mock_mcp_cls.return_value = MagicMock()

        app = create_app()
        app.dependency_overrides[get_whatsapp_registry] = lambda: mock_registry_instance
        client = TestClient(app)

        response = client.post(
            "/api/v1/channels/whatsapp/message",
            json={"from": "+5511999999999", "message": "hello", "tenant_id": "tenant-1"},
            headers={"X-API-Key": "key"},
        )

        assert response.status_code == 200
        assert len(constructor_calls) == 1
        args = constructor_calls[0]

        # Verify thread_id is scoped per tenant + phone
        assert args["thread_id"] == "whatsapp:tenant-1:+5511999999999"

        # Verify checkpointer is not None (it's an AsyncSqliteSaver)
        assert args["checkpointer"] is not None
```

### Step 2: Implement in webhook

**File:** `src/agntrick/api/routes/whatsapp.py`

Changes at lines 363-401 (the agent instantiation section):

1. Add import at top of file:
```python
from agntrick.storage.tenant_manager import TenantManager
```

2. Add module-level TenantManager (lazy singleton):
```python
_tenant_manager: TenantManager | None = None

def _get_tenant_manager() -> TenantManager:
    global _tenant_manager
    if _tenant_manager is None:
        config = get_config()
        base = config.storage.base_path
        _tenant_manager = TenantManager(base_path=base)
    return _tenant_manager
```

3. Replace both agent instantiation blocks (lines 378-401) with a single block:

```python
        # Build thread_id and checkpointer for persistent memory
        thread_id = f"whatsapp:{tenant_id}:{phone}"
        tenant_manager = _get_tenant_manager()
        tenant_db = tenant_manager.get_database(tenant_id)
        checkpointer = tenant_db.get_checkpointer(is_async=True)
        tenant_logger.info("Using persistent memory for thread: %s", thread_id)

        # Agent constructor args (shared between MCP and non-MCP paths)
        agent_kwargs = dict(
            _agent_name=agent_name,
            tool_categories=tool_categories,
            model_name=config.llm.model,
            temperature=config.llm.temperature,
            thread_id=thread_id,
            checkpointer=checkpointer,
        )

        if allowed_mcp:
            provider = MCPProvider(server_names=allowed_mcp)
            async with provider.tool_session() as mcp_tools:
                agent = agent_cls(initial_mcp_tools=mcp_tools, **agent_kwargs)
                result = await agent.run(message)
        else:
            agent = agent_cls(**agent_kwargs)
            result = await agent.run(message)
```

### Step 3: Run `make check && make test`

---

## Task 2: Rewrite assistant system prompt with ACI principles

**Layer 3 — Prompts. Independent of graph work.**

### Step 1: Rewrite `src/agntrick/prompts/assistant.md`

Replace the current prompt with one that includes explicit tool selection rules, error recovery, and multi-step guidance. Key additions:

```markdown
# Assistant Agent System Prompt

You are a senior digital assistant ...

## TOOL SELECTION RULES

For current events/news: ALWAYS use web_search first. Never web_fetch a news site directly.
For specific URL content: Use web_fetch. It returns clean text via Jina Reader.
For API calls with custom headers: Use curl_fetch.
For RSS feeds: Use web_fetch (it handles RSS natively).
For file operations: Use run_shell.
For searching code: Use ripgrep_search.

## ERROR RECOVERY

If a tool returns an error:
1. Read the error message carefully
2. Try ONE alternative approach (different tool or different parameters)
3. If it still fails, inform the user what went wrong and what you tried
4. NEVER retry the exact same call that just failed

## MULTI-STEP TASKS

When a task requires multiple tool calls:
1. Briefly state your plan before starting
2. Report progress between steps
3. Synthesize results at the end

## DELEGATION RULES

- Code analysis, debugging, file operations → delegate to "developer"
- YouTube links or video questions → delegate to "youtube"
- PR review requests → delegate to "github-pr-reviewer"
- News queries → handle directly with web_search (don't delegate to news agent)
- Learning/tutorial requests → handle directly or delegate to "learning"
```

Keep the existing `<capabilities>`, `<agents>`, `<guidelines>`, and `<guardrails>` sections but integrate the new rules above.

### Step 2: Run `make check && make test`

---

## Task 3: Create graph module with AgentState and Router node

**Layer 2 — Graph foundation.**

### Step 1: Create `src/agntrick/graph.py`

```python
"""3-node StateGraph for intelligent assistant routing.

Router → Executor → Responder with conditional skip for simple chat.
"""

import json
import logging
from typing import Any, Sequence

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """You are a query router for a WhatsApp assistant. Classify the user's message:

- "chat": General conversation, greetings, opinions, jokes — no tools needed
- "tool_use": Simple factual query that needs one or two tool calls
- "research": Complex multi-step query that needs multiple tool calls
- "delegate": Task clearly matches a specialist agent's domain

Respond with JSON only: {"intent": "...", "tool_plan": "...", "delegate_to": null, "skip_tools": false}

For "chat": tool_plan=null, skip_tools=true
For "tool_use": tool_plan should specify which single tool to use
For "research": tool_plan should outline the sequence of tool calls
For "delegate": set delegate_to to the agent name, tool_plan to the delegation prompt

Delegation rules:
- Code analysis, debugging, file operations → "developer"
- YouTube links or video questions → "youtube"
- PR review requests → "github-pr-reviewer"
- News queries → handle directly with web_search
- Learning/tutorial requests → handle directly or delegate to "learning"
"""

RESPONDER_PROMPT = """You are formatting a response for WhatsApp. Take the assistant's response and:

1. Make it concise and mobile-friendly (under 4096 characters)
2. Use simple markdown: **bold**, bullet points, numbered lists
3. Strip internal tool artifacts, raw JSON, or verbose technical output
4. Keep structure (headers, bullet points) for complex answers
5. If content is very long, truncate with a "message continued" hint
6. Always respond in the same language as the user

Output only the formatted response, nothing else."""


class AgentState(TypedDict):
    """State flowing through the 3-node graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    intent: str  # "chat" | "tool_use" | "research" | "delegate"
    tool_plan: str | None  # Router's guidance for tool selection
    progress: list[str]  # Progress messages sent to user
    final_response: str | None


def _parse_router_response(content: str) -> dict[str, Any]:
    """Parse JSON from router LLM response, with fallback."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try extracting JSON from markdown code blocks
        import re
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # Fallback: treat as chat
        return {"intent": "chat", "tool_plan": None, "skip_tools": True}


async def router_node(state: AgentState, config: dict, *, model: Any) -> dict:
    """Classify intent and decide strategy. Single fast LLM call."""
    last_message = state["messages"][-1]
    response = await model.ainvoke(
        [
            SystemMessage(content=ROUTER_PROMPT),
            last_message,
        ],
    )
    parsed = _parse_router_response(response.content)
    logger.info("Router classified intent=%s", parsed.get("intent"))
    return {
        "intent": parsed.get("intent", "chat"),
        "tool_plan": parsed.get("tool_plan"),
    }


async def executor_node(
    state: AgentState,
    config: dict,
    *,
    model: Any,
    tools: Sequence[Any],
    system_prompt: str,
) -> dict:
    """Execute tool calls guided by the router's plan."""
    tool_plan = state.get("tool_plan")
    intent = state.get("intent", "tool_use")

    # Build guided system prompt
    guided_prompt = system_prompt
    if tool_plan:
        guided_prompt += f"\n\n## CURRENT TASK PLAN\n{tool_plan}"

    # For delegation, the tool_plan IS the delegation prompt
    # invoke_agent tool will handle it

    # Create a sub-agent for tool execution
    sub_agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=guided_prompt,
        checkpointer=InMemorySaver(),  # Sub-agent doesn't need persistence
    )

    result = await sub_agent.ainvoke(
        {"messages": state["messages"]},
        config={"configurable": {"thread_id": "executor"}},
    )

    return {"messages": result["messages"]}


async def responder_node(state: AgentState, config: dict, *, model: Any) -> dict:
    """Format the final response for WhatsApp."""
    # Get the last assistant message (from executor or direct)
    last_msg = state["messages"][-1]

    # For "chat" intent with no executor, generate a direct response
    if state.get("intent") == "chat":
        response = await model.ainvoke(
            [
                SystemMessage(content=RESPONDER_PROMPT),
                *state["messages"],
            ],
        )
        return {"final_response": str(response.content), "messages": [response]}

    # For tool intents, reformat the executor's output
    response = await model.ainvoke(
        [
            SystemMessage(content=RESPONDER_PROMPT),
            SystemMessage(content=f"Format this response for WhatsApp:\n\n{last_msg.content}"),
        ],
    )
    return {"final_response": str(response.content), "messages": [response]}


def route_decision(state: AgentState) -> str:
    """Decide next node after Router."""
    if state.get("intent") == "chat":
        return "responder"
    return "executor"


def create_assistant_graph(
    model: Any,
    tools: Sequence[Any],
    system_prompt: str,
    checkpointer: Any | None = None,
) -> Any:
    """Create the 3-node assistant StateGraph.

    Args:
        model: LLM model instance.
        tools: Sequence of tools available to the executor.
        system_prompt: Base system prompt for the agent.
        checkpointer: Optional checkpointer for persistent memory.

    Returns:
        Compiled StateGraph ready for ainvoke().
    """
    async def _router(state: AgentState, config: dict) -> dict:
        return await router_node(state, config, model=model)

    async def _executor(state: AgentState, config: dict) -> dict:
        return await executor_node(
            state, config, model=model, tools=tools, system_prompt=system_prompt,
        )

    async def _responder(state: AgentState, config: dict) -> dict:
        return await responder_node(state, config, model=model)

    graph = StateGraph(AgentState)
    graph.add_node("router", _router)
    graph.add_node("executor", _executor)
    graph.add_node("responder", _responder)
    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        route_decision,
        {"executor": "executor", "responder": "responder"},
    )
    graph.add_edge("executor", "responder")
    graph.add_edge("responder", END)

    return graph.compile(checkpointer=checkpointer or InMemorySaver())
```

### Step 2: Write tests for graph module

**File:** `tests/test_graph.py`

```python
"""Tests for the 3-node assistant StateGraph."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agntrick.graph import (
    AgentState,
    _parse_router_response,
    route_decision,
    ROUTER_PROMPT,
    RESPONDER_PROMPT,
)


class TestAgentState:
    """Tests for AgentState TypedDict."""

    def test_state_has_required_fields(self) -> None:
        state: AgentState = {
            "messages": [],
            "intent": "chat",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }
        assert state["intent"] == "chat"
        assert state["tool_plan"] is None


class TestParseRouterResponse:
    """Tests for _parse_router_response."""

    def test_valid_json(self) -> None:
        raw = '{"intent": "chat", "tool_plan": null, "skip_tools": true}'
        result = _parse_router_response(raw)
        assert result["intent"] == "chat"
        assert result["skip_tools"] is True

    def test_json_in_markdown_code_block(self) -> None:
        raw = '```json\n{"intent": "tool_use", "tool_plan": "use web_search"}\n```'
        result = _parse_router_response(raw)
        assert result["intent"] == "tool_use"

    def test_invalid_json_falls_back_to_chat(self) -> None:
        raw = "I don't know what this is"
        result = _parse_router_response(raw)
        assert result["intent"] == "chat"
        assert result["skip_tools"] is True


class TestRouteDecision:
    """Tests for route_decision."""

    def test_chat_goes_to_responder(self) -> None:
        state: AgentState = {
            "messages": [],
            "intent": "chat",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }
        assert route_decision(state) == "responder"

    def test_tool_use_goes_to_executor(self) -> None:
        state: AgentState = {
            "messages": [],
            "intent": "tool_use",
            "tool_plan": "use web_search",
            "progress": [],
            "final_response": None,
        }
        assert route_decision(state) == "executor"

    def test_research_goes_to_executor(self) -> None:
        state: AgentState = {
            "messages": [],
            "intent": "research",
            "tool_plan": "multi-step plan",
            "progress": [],
            "final_response": None,
        }
        assert route_decision(state) == "executor"

    def test_delegate_goes_to_executor(self) -> None:
        state: AgentState = {
            "messages": [],
            "intent": "delegate",
            "tool_plan": "delegate to developer",
            "progress": [],
            "final_response": None,
        }
        assert route_decision(state) == "executor"


class TestRouterNode:
    """Tests for router_node with mocked LLM."""

    @pytest.mark.asyncio
    async def test_router_classifies_chat(self) -> None:
        from langchain_core.messages import HumanMessage

        from agntrick.graph import router_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"intent": "chat", "tool_plan": null, "skip_tools": true}'
            )
        )

        state: AgentState = {
            "messages": [HumanMessage(content="good morning")],
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        result = await router_node(state, {}, model=mock_model)
        assert result["intent"] == "chat"
        assert result["tool_plan"] is None

    @pytest.mark.asyncio
    async def test_router_classifies_tool_use(self) -> None:
        from langchain_core.messages import HumanMessage

        from agntrick.graph import router_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"intent": "tool_use", "tool_plan": "use web_search for weather", "skip_tools": false}'
            )
        )

        state: AgentState = {
            "messages": [HumanMessage(content="What's the weather in São Paulo?")],
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        result = await router_node(state, {}, model=mock_model)
        assert result["intent"] == "tool_use"
        assert "web_search" in result["tool_plan"]


class TestCreateAssistantGraph:
    """Tests for the full graph compilation."""

    def test_graph_compiles(self) -> None:
        from agntrick.graph import create_assistant_graph

        mock_model = MagicMock()
        graph = create_assistant_graph(
            model=mock_model,
            tools=[],
            system_prompt="You are a test assistant.",
        )
        assert graph is not None
        assert hasattr(graph, "ainvoke")
```

### Step 3: Run `make check && make test`

---

## Task 4: Override AssistantAgent to use custom graph

### Step 1: Extract `_create_graph()` from `AgentBase._ensure_initialized()`

**File:** `src/agntrick/agent.py`

Add a new method to `AgentBase` (after `_ensure_initialized`):

```python
def _create_graph(
    self,
    model: Any,
    tools: list[Any],
    system_prompt: str,
    checkpointer: Any,
) -> Any:
    """Create the agent graph. Override in subclasses for custom graphs.

    Args:
        model: LLM model instance.
        tools: List of available tools.
        system_prompt: System prompt string.
        checkpointer: Checkpointer for persistent memory.

    Returns:
        A compiled graph with ainvoke().
    """
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
    )
```

Then modify `_ensure_initialized()` line 276 to use it:

```python
# Before:
self._graph = create_agent(...)

# After:
self._graph = self._create_graph(
    model=self.model,
    tools=self._tools,
    system_prompt=system_prompt,
    checkpointer=self._checkpointer or InMemorySaver(),
)
```

### Step 2: Override in `AssistantAgent`

**File:** `src/agntrick/agents/assistant.py`

```python
from typing import Any

from agntrick.agent import AgentBase
from agntrick.graph import create_assistant_graph
from agntrick.prompts import load_prompt
from agntrick.registry import AgentRegistry
from agntrick.tools import AgentInvocationTool


@AgentRegistry.register(
    "assistant",
    mcp_servers=["toolbox"],
    tool_categories=["web", "hackernews", "document", "search", "media"],
)
class AssistantAgent(AgentBase):
    """Default generalist agent that orchestrates specialized agents and tools."""

    @property
    def system_prompt(self) -> str:
        """Return the assistant system prompt."""
        return load_prompt("assistant")

    def local_tools(self) -> list[Any]:
        """Return local tools including agent invocation."""
        return [AgentInvocationTool().to_langchain_tool()]

    def _create_graph(
        self,
        model: Any,
        tools: list[Any],
        system_prompt: str,
        checkpointer: Any,
    ) -> Any:
        """Use the 3-node StateGraph instead of the default ReAct agent."""
        return create_assistant_graph(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            checkpointer=checkpointer,
        )
```

### Step 3: Update the `run()` method to handle `final_response`

**File:** `src/agntrick/agent.py`

The graph now returns a `final_response` field in state. Modify `run()` to prefer it:

```python
# In run() method, line ~327-331:
result = await self._graph.ainvoke(
    {"messages": self._normalize_messages(input_data)},
    config=config or self._default_config(),
)
# Prefer final_response from the graph (set by Responder node)
if result.get("final_response"):
    return str(result["final_response"])
return str(result["messages"][-1].content)
```

### Step 4: Run `make check && make test`

---

## Task 5: Add progress message support

### Step 1: Add progress callback to graph

**File:** `src/agntrick/graph.py`

Add a `progress_callback` parameter to `create_assistant_graph` and use it in the executor:

```python
from typing import Any, Callable, Coroutine, Sequence

# Type for progress callback
ProgressCallback = Callable[[str], Coroutine[Any, Any, None]] | None

async def executor_node(
    state: AgentState,
    config: dict,
    *,
    model: Any,
    tools: Sequence[Any],
    system_prompt: str,
    progress_callback: ProgressCallback = None,
) -> dict:
    """Execute tool calls with progress reporting."""
    if progress_callback:
        await progress_callback("🔍 Analyzing your request...")

    tool_plan = state.get("tool_plan")
    # ... (rest of executor logic)

    if progress_callback:
        await progress_callback("🔧 Searching for information...")

    # ... execute tools ...

    if progress_callback and len(state.get("progress", [])) > 0:
        await progress_callback("📝 Formatting response...")

    return {...}
```

Wire through in `create_assistant_graph`:

```python
def create_assistant_graph(
    model: Any,
    tools: Sequence[Any],
    system_prompt: str,
    checkpointer: Any | None = None,
    progress_callback: ProgressCallback = None,
) -> Any:
    async def _executor(state: AgentState, config: dict) -> dict:
        return await executor_node(
            state, config,
            model=model, tools=tools, system_prompt=system_prompt,
            progress_callback=progress_callback,
        )
    # ... rest unchanged
```

### Step 2: Wire progress into AgentBase

**File:** `src/agntrick/agent.py`

Add `progress_callback` parameter to `AgentBase.__init__`:

```python
def __init__(
    self,
    ...,
    progress_callback: ProgressCallback = None,
):
    self._progress_callback = progress_callback
```

Pass it through in `_create_graph()` default implementation (as None — subclasses handle it).

Override `_ensure_initialized()` or `_create_graph()` in `AssistantAgent` to pass the callback:

```python
def _create_graph(self, model, tools, system_prompt, checkpointer):
    return create_assistant_graph(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        progress_callback=self._progress_callback,
    )
```

### Step 3: Wire progress into WhatsApp webhook

**File:** `src/agntrick/api/routes/whatsapp.py`

Add a progress callback that sends intermediate messages via the Go gateway:

```python
async def _send_progress(phone: str, tenant_id: str, message: str) -> None:
    """Send a progress message to WhatsApp via the Go gateway."""
    try:
        config = get_config()
        gateway_url = config.mcp.gateway_url or "http://localhost:8080"
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{gateway_url}/api/send",
                json={"phone": phone, "message": message, "tenant_id": tenant_id},
                headers={"X-API-Key": config.auth.api_keys.get("gateway", "")},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning("Failed to send progress message: %s", e)
```

Then in the webhook, create the callback and pass it:

```python
progress_cb = partial(_send_progress, phone, tenant_id)
agent_kwargs["progress_callback"] = progress_cb
```

### Step 4: Run `make check && make test`

---

## Task 6: Final integration test

### Step 1: Write end-to-end integration test

**File:** `tests/test_integration/test_e2e_whatsapp.py`

Add a test that verifies the full flow with mocked LLM:

```python
class TestSmarterAssistantIntegration:
    """Integration tests for the smarter WhatsApp assistant."""

    @pytest.mark.asyncio
    async def test_full_graph_flow_with_chat_intent(self) -> None:
        """Chat messages skip executor, go directly to responder."""
        from unittest.mock import AsyncMock, MagicMock

        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()

        # Router returns chat intent
        router_response = MagicMock(
            content='{"intent": "chat", "tool_plan": null, "skip_tools": true}'
        )
        # Responder returns formatted chat
        responder_response = MagicMock(content="Good morning! How can I help?")

        mock_model.ainvoke = AsyncMock(
            side_effect=[router_response, responder_response]
        )

        graph = create_assistant_graph(
            model=mock_model,
            tools=[],
            system_prompt="You are helpful.",
        )

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="good morning")],
             "intent": "", "tool_plan": None, "progress": [], "final_response": None},
            config={"configurable": {"thread_id": "test"}},
        )

        assert result["final_response"] is not None
        assert result["intent"] == "chat"

    @pytest.mark.asyncio
    async def test_memory_persists_across_messages(self) -> None:
        """Verify conversation memory persists via checkpointer."""
        from agntrick.storage.database import Database
        import tempfile, os

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            checkpointer = db.get_checkpointer(is_async=True)

            # First message
            graph = create_assistant_graph(
                model=mock_model, tools=[], system_prompt="test",
                checkpointer=checkpointer,
            )
            await graph.ainvoke(
                {"messages": [HumanMessage(content="My name is Jean")], ...},
                config={"configurable": {"thread_id": "memory-test"}},
            )

            # Second message — should have context from first
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="What's my name?")], ...},
                config={"configurable": {"thread_id": "memory-test"}},
            )
            # The checkpointer ensures the second invocation sees the first
```

### Step 2: Run `make check && make test`

---

## Dependencies & Risks

| Risk | Mitigation |
|------|-----------|
| `create_agent` API may not match LangGraph v1.x | Verify at implementation time; fall back to `langgraph.prebuilt.create_react_agent` |
| Sub-agent in Executor creates nested checkpoints | Use `InMemorySaver` for sub-agent (no persistence needed) |
| Router misclassifies intent | Fallback to `tool_use` (safe default — just slightly slower) |
| Progress callback fails silently | Already handled — callback catches and logs exceptions |
| Large conversation history slows things down | Future: add memory compaction (not in this plan) |

## Out of Scope (Future)

- **Memory compaction** — Summarize old messages when context exceeds threshold
- **Tool description rewrites in agntrick-toolkit** — Separate repo, separate PR
- **Vector store / RAG** — Cross-conversation search
- **Template messages** — WhatsApp re-engagement templates
