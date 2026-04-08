# Agent Model Routing Implementation Plan
Read AGENTS.md to follow development rules and pass it accross the subagents too so they also know and follwo the rules.
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. You don't need to execute tests you know are going to fail from TDD perspective.

**Goal:** Allow each agent to use a different LLM model via YAML config, with per-node overrides for the 3-node graph.

**Architecture:** Add `AgentModelConfig` dataclass to `config.py` that maps agent names to model names and supports `<agent>_nodes` entries for per-graph-node overrides. `AgentBase.__init__` resolves the model via config lookup before falling back to global/provider defaults. `create_assistant_graph` accepts optional per-node model instances.

**Tech Stack:** Python 3.12+, dataclasses, PyYAML, pytest, pytest-asyncio

---

### Task 1: Add `AgentModelConfig` dataclass and config parsing

**Files:**
- Modify: `src/agntrick/config.py:18-26` (add new dataclass after `LLMConfig`)
- Modify: `src/agntrick/config.py:109-126` (add field to `AgntrickConfig`)
- Modify: `src/agntrick/config.py:129-163` (update `from_dict`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for `AgentModelConfig`**

Add to `tests/test_config.py`:

```python
class TestAgentModelConfig:
    """Tests for per-agent model configuration."""

    def test_get_model_for_agent_default(self) -> None:
        """Should return model name when agent is configured."""
        from agntrick.config import AgentModelConfig

        config = AgentModelConfig(models={"assistant": "glm-5.1", "committer": "glm-4.7"})
        assert config.get_model_for("assistant") == "glm-5.1"
        assert config.get_model_for("committer") == "glm-4.7"

    def test_get_model_for_unknown_agent_returns_none(self) -> None:
        """Should return None when agent is not configured."""
        from agntrick.config import AgentModelConfig

        config = AgentModelConfig(models={"assistant": "glm-5.1"})
        assert config.get_model_for("developer") is None

    def test_get_model_for_node_override(self) -> None:
        """Should return node-specific model when configured."""
        from agntrick.config import AgentModelConfig

        config = AgentModelConfig(
            models={"assistant": "glm-5.1"},
            node_overrides={"assistant": {"router": "glm-4.7", "responder": "glm-4.7"}},
        )
        assert config.get_model_for("assistant", node="router") == "glm-4.7"
        assert config.get_model_for("assistant", node="responder") == "glm-4.7"

    def test_get_model_for_node_falls_back_to_agent_default(self) -> None:
        """Should fall back to agent default when node is not overridden."""
        from agntrick.config import AgentModelConfig

        config = AgentModelConfig(
            models={"assistant": "glm-5.1"},
            node_overrides={"assistant": {"router": "glm-4.7"}},
        )
        # executor is not in node_overrides, should fall back to agent default
        assert config.get_model_for("assistant", node="executor") == "glm-5.1"

    def test_get_model_for_node_none_returns_agent_default(self) -> None:
        """Should return agent default when node is None."""
        from agntrick.config import AgentModelConfig

        config = AgentModelConfig(
            models={"assistant": "glm-5.1"},
            node_overrides={"assistant": {"router": "glm-4.7"}},
        )
        assert config.get_model_for("assistant", node=None) == "glm-5.1"

    def test_empty_config_returns_none(self) -> None:
        """Empty config should return None for all lookups."""
        from agntrick.config import AgentModelConfig

        config = AgentModelConfig()
        assert config.get_model_for("assistant") is None
        assert config.get_model_for("assistant", node="router") is None

    def test_config_from_dict_parses_agent_models(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config should parse agent_models section from YAML."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "llm": {"model": "glm-4.7"},
                    "agent_models": {
                        "assistant": "glm-5.1",
                        "developer": "glm-5",
                        "committer": "glm-4.7",
                        "assistant_nodes": {
                            "router": "glm-4.7",
                            "executor": "glm-5.1",
                            "responder": "glm-4.7",
                        },
                    },
                }
            )
        )

        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))
        from agntrick.config import get_config

        config = get_config(force_reload=True)

        assert config.agent_models.get_model_for("assistant") == "glm-5.1"
        assert config.agent_models.get_model_for("developer") == "glm-5"
        assert config.agent_models.get_model_for("committer") == "glm-4.7"
        assert config.agent_models.get_model_for("assistant", node="router") == "glm-4.7"
        assert config.agent_models.get_model_for("assistant", node="executor") == "glm-5.1"
        assert config.agent_models.get_model_for("assistant", node="responder") == "glm-4.7"

    def test_config_from_dict_without_agent_models(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config without agent_models should have empty AgentModelConfig."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(yaml.dump({"llm": {"model": "gpt-4"}}))

        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))
        from agntrick.config import get_config

        config = get_config(force_reload=True)

        assert config.agent_models.get_model_for("assistant") is None
        assert config.agent_models.models == {}
        assert config.agent_models.node_overrides == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py::TestAgentModelConfig -v`
Expected: FAIL — `ImportError` or `AttributeError` because `AgentModelConfig` doesn't exist yet.

- [ ] **Step 3: Add `AgentModelConfig` dataclass to `config.py`**

After the `LLMConfig` dataclass (line 26), add:

```python
@dataclass
class AgentModelConfig:
    """Per-agent model configuration with optional per-graph-node overrides.

    Allows mapping each agent to a specific LLM model name, and optionally
    overriding the model for individual graph nodes (router, executor, responder).

    Configured in YAML under ``agent_models``:

    .. code-block:: yaml

        agent_models:
          assistant: glm-5.1
          developer: glm-5
          assistant_nodes:
            router: glm-4.7
            responder: glm-4.7
    """

    models: dict[str, str] = field(default_factory=dict)
    node_overrides: dict[str, dict[str, str]] = field(default_factory=dict)

    def get_model_for(self, agent_name: str, node: str | None = None) -> str | None:
        """Resolve model name for a given agent and optional graph node.

        Lookup order:
            1. ``node_overrides[agent_name][node]``
            2. ``models[agent_name]``

        Args:
            agent_name: Registered agent name (e.g. "assistant").
            node: Optional graph node name (e.g. "router", "executor", "responder").

        Returns:
            Model name string, or None if no override is configured.
        """
        if node:
            node_map = self.node_overrides.get(agent_name)
            if node_map and node in node_map:
                return node_map[node]
        return self.models.get(agent_name)
```

Add the field to `AgntrickConfig` (after `storage` field, around line 124):

```python
    agent_models: AgentModelConfig = field(default_factory=AgentModelConfig)
```

Update `AgntrickConfig.from_dict` to parse the new section. Add before the `return cls(` call (around line 139):

```python
    # Parse agent_models section
    am_dict = config_dict.get("agent_models", {})
    am_models: dict[str, str] = {}
    am_node_overrides: dict[str, dict[str, str]] = {}
    for key, value in am_dict.items():
        if key.endswith("_nodes") and isinstance(value, dict):
            agent_name = key.removesuffix("_nodes")
            am_node_overrides[agent_name] = value
        elif isinstance(value, str):
            am_models[key] = value
    agent_models_config = AgentModelConfig(models=am_models, node_overrides=am_node_overrides)
```

Add `agent_models=agent_models_config,` to the `return cls(...)` call:

```python
        return cls(
            llm=LLMConfig(**config_dict.get("llm", {})),
            logging=LoggingConfig(**config_dict.get("logging", {})),
            mcp=MCPConfig(**config_dict.get("mcp", {})),
            agents=AgentsConfig(**config_dict.get("agents", {})),
            api=APIConfig(**config_dict.get("api", {})),
            auth=AuthConfig(
                api_keys=config_dict.get("auth", {}).get("api_keys", {}),
            ),
            storage=StorageConfig(**config_dict.get("storage", {})),
            whatsapp=WhatsAppConfig(tenants=tenants),
            agent_models=agent_models_config,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py::TestAgentModelConfig -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `make check && make test`
Expected: All tests pass, no new lint errors.

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/config.py tests/test_config.py
git commit -m "feat: add AgentModelConfig for per-agent model routing"
```

---

### Task 2: Update `AgentBase.__init__` to use config-based model resolution

**Files:**
- Modify: `src/agntrick/agent.py:57-110` (reorder init, add model lookup, add `_get_node_models`)
- Test: `tests/test_agent.py` (create new file)

- [ ] **Step 1: Write failing tests for model resolution**

Create `tests/test_agent.py`:

```python
"""Tests for AgentBase model resolution from config."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


class TestAgentModelResolution:
    """Tests for per-agent model resolution in AgentBase.__init__."""

    def test_uses_agent_model_from_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Agent should use model from agent_models config when set."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "llm": {"model": "global-default-model"},
                    "agent_models": {"developer": "glm-5"},
                }
            )
        )
        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))

        with patch("agntrick.agent._create_model") as mock_create:
            mock_create.return_value = MagicMock()
            from agntrick.agent import AgentBase
            from agntrick.config import get_config

            get_config(force_reload=True)

            class TestAgent(AgentBase):
                @property
                def system_prompt(self) -> str:
                    return "test"

            agent = TestAgent(_agent_name="developer")
            mock_create.assert_called_once_with("glm-5", 0.1)

    def test_falls_back_to_global_model(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Agent should fall back to llm.model when not in agent_models."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "llm": {"model": "global-default-model"},
                    "agent_models": {"assistant": "glm-5.1"},
                }
            )
        )
        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))

        with patch("agntrick.agent._create_model") as mock_create:
            mock_create.return_value = MagicMock()
            from agntrick.agent import AgentBase
            from agntrick.config import get_config

            get_config(force_reload=True)

            class TestAgent(AgentBase):
                @property
                def system_prompt(self) -> str:
                    return "test"

            # "developer" is not in agent_models, should use global default
            agent = TestAgent(_agent_name="developer")
            mock_create.assert_called_once_with("global-default-model", 0.1)

    def test_explicit_model_name_overrides_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit model_name parameter should override config."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(
            yaml.dump({"llm": {"model": "global-default"}, "agent_models": {"assistant": "glm-5.1"}})
        )
        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))

        with patch("agntrick.agent._create_model") as mock_create:
            mock_create.return_value = MagicMock()
            from agntrick.agent import AgentBase
            from agntrick.config import get_config

            get_config(force_reload=True)

            class TestAgent(AgentBase):
                @property
                def system_prompt(self) -> str:
                    return "test"

            agent = TestAgent(model_name="explicit-model", _agent_name="assistant")
            mock_create.assert_called_once_with("explicit-model", 0.1)

    def test_no_config_falls_back_to_provider_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without config, should fall back to provider default."""
        monkeypatch.setenv("AGNTRICK_CONFIG", "__nonexistent__")

        with patch("agntrick.agent._create_model") as mock_create:
            mock_create.return_value = MagicMock()
            with patch("agntrick.agent.get_default_model", return_value="provider-default"):
                from agntrick.agent import AgentBase
                from agntrick.config import get_config

                get_config(force_reload=True)

                class TestAgent(AgentBase):
                    @property
                    def system_prompt(self) -> str:
                        return "test"

                agent = TestAgent(_agent_name="unknown-agent")
                mock_create.assert_called_once_with("provider-default", 0.1)


class TestGetNodeModels:
    """Tests for _get_node_models helper on AgentBase."""

    def test_returns_configured_node_models(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return model instances for nodes with overrides."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "llm": {"model": "glm-4.7", "temperature": 0.1},
                    "agent_models": {
                        "assistant": "glm-5.1",
                        "assistant_nodes": {
                            "router": "glm-4.7",
                            "responder": "glm-4.7",
                        },
                    },
                }
            )
        )
        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))

        with patch("agntrick.agent._create_model") as mock_create:
            mock_create.return_value = MagicMock()
            from agntrick.agent import AgentBase
            from agntrick.config import get_config

            get_config(force_reload=True)

            class TestAgent(AgentBase):
                @property
                def system_prompt(self) -> str:
                    return "test"

            agent = TestAgent(_agent_name="assistant")
            node_models = agent._get_node_models()

            # Should have router and responder, but not executor (not in overrides)
            assert "router" in node_models
            assert "responder" in node_models
            assert "executor" not in node_models

    def test_returns_empty_when_no_overrides(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty dict when no node overrides configured."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(
            yaml.dump({"llm": {"model": "glm-4.7"}, "agent_models": {"developer": "glm-5"}})
        )
        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))

        with patch("agntrick.agent._create_model") as mock_create:
            mock_create.return_value = MagicMock()
            from agntrick.agent import AgentBase
            from agntrick.config import get_config

            get_config(force_reload=True)

            class TestAgent(AgentBase):
                @property
                def system_prompt(self) -> str:
                    return "test"

            agent = TestAgent(_agent_name="developer")
            node_models = agent._get_node_models()
            assert node_models == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent.py -v`
Expected: FAIL — tests expect config-based model resolution that doesn't exist yet.

- [ ] **Step 3: Reorder `AgentBase.__init__` and add model lookup**

In `src/agntrick/agent.py`, replace lines 86-110 (`__init__` body) with:

```python
        config = get_config()

        # Resolve agent name early (needed for model lookup)
        self._agent_name = _agent_name or config.agents.default_agent_name

        # Resolve model: agent config > global config > provider default
        if model_name is None:
            model_name = (
                config.agent_models.get_model_for(self._agent_name)
                or config.llm.model
                or get_default_model()
            )

        if temperature is None:
            temperature = config.llm.temperature

        self.model = _create_model(model_name, temperature)
        self._mcp_provider = mcp_provider
        self._initial_mcp_tools = initial_mcp_tools
        self._thread_id = thread_id
        self._checkpointer = checkpointer
        self._tools: List[Any] = list(self.local_tools())
        self._graph: Any | None = None
        self._init_lock = asyncio.Lock()
        self._tool_categories = tool_categories
        # Get toolbox_url from: parameter > config > default
        if toolbox_url is None:
            toolbox_url = config.mcp.toolbox_url or "http://localhost:8080"
        self._toolbox_url = toolbox_url
        self._tool_manifest: ToolManifest | None = None
        self._progress_callback = progress_callback
```

Note: `self._agent_name` is moved BEFORE model creation. The duplicate line `self._agent_name = _agent_name or config.agents.default_agent_name` that was at line 109 is removed.

Add `_get_node_models` method after `_get_system_prompt` (around line 172):

```python
    def _get_node_models(self) -> dict[str, Any]:
        """Resolve per-node model instances for graph nodes.

        Returns:
            Dict mapping node names ("router", "executor", "responder") to
            model instances. Only includes nodes that have overrides configured.
        """
        config = get_config()
        overrides: dict[str, Any] = {}
        for node in ("router", "executor", "responder"):
            node_model_name = config.agent_models.get_model_for(self._agent_name, node=node)
            if node_model_name:
                overrides[node] = _create_model(node_model_name, config.llm.temperature)
        return overrides
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `make check && make test`
Expected: All tests pass, no new lint errors.

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/agent.py tests/test_agent.py
git commit -m "feat: resolve model per-agent from config in AgentBase.__init__"
```

---

### Task 3: Add per-node model parameters to `create_assistant_graph`

**Files:**
- Modify: `src/agntrick/graph.py:557-606` (update `create_assistant_graph`)
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write failing test for per-node model usage**

Add to `tests/test_graph.py`:

```python
class TestPerNodeModels:
    """Tests for per-node model overrides in create_assistant_graph."""

    @pytest.mark.asyncio
    async def test_router_uses_override_model(self) -> None:
        """Router should use router_model when provided."""
        from agntrick.graph import create_assistant_graph

        primary_model = AsyncMock()
        router_model = AsyncMock()

        # Track which model is called for routing
        router_model.ainvoke = AsyncMock(
            return_value=AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}')
        )
        primary_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="Hello!")
        )

        graph = create_assistant_graph(
            model=primary_model,
            tools=[],
            system_prompt="You are a test assistant.",
            router_model=router_model,
        )

        await graph.ainvoke(
            {"messages": [HumanMessage(content="Hi")]},
            config={"configurable": {"thread_id": "test-router-override"}},
        )

        # Router should have used router_model, not primary
        router_model.ainvoke.assert_called_once()
        # Primary should NOT have been called for routing
        primary_model.ainvoke.assert_called_once()  # only for responder

    @pytest.mark.asyncio
    async def test_responder_uses_override_model(self) -> None:
        """Responder should use responder_model when provided."""
        from agntrick.graph import create_assistant_graph

        primary_model = AsyncMock()
        responder_model = AsyncMock()

        primary_model.ainvoke = AsyncMock(
            return_value=AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}')
        )
        responder_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="Formatted response")
        )

        graph = create_assistant_graph(
            model=primary_model,
            tools=[],
            system_prompt="You are a test assistant.",
            responder_model=responder_model,
        )

        await graph.ainvoke(
            {"messages": [HumanMessage(content="Hi")]},
            config={"configurable": {"thread_id": "test-responder-override"}},
        )

        responder_model.ainvoke.assert_called_once()
        # Primary should only have been called for routing
        primary_model.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_overrides_uses_primary_for_all(self) -> None:
        """Without overrides, all nodes should use the primary model."""
        from agntrick.graph import create_assistant_graph

        primary_model = AsyncMock()
        primary_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}'),
                AIMessage(content="Hello!"),
            ]
        )

        graph = create_assistant_graph(
            model=primary_model,
            tools=[],
            system_prompt="You are a test assistant.",
        )

        await graph.ainvoke(
            {"messages": [HumanMessage(content="Hi")]},
            config={"configurable": {"thread_id": "test-no-overrides"}},
        )

        # Primary should have been called twice (router + responder)
        assert primary_model.ainvoke.call_count == 2

    @pytest.mark.asyncio
    async def test_executor_uses_override_model(self) -> None:
        """Executor should use executor_model when provided."""
        from unittest.mock import patch

        from agntrick.graph import create_assistant_graph

        primary_model = AsyncMock()
        executor_model = AsyncMock()

        primary_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "tool_use", "tool_plan": "web_search", "skip_tools": false}'),
                AIMessage(content="Formatted"),
            ]
        )
        executor_model.ainvoke = AsyncMock(return_value=AIMessage(content="done"))

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_sub_agent = MagicMock()
            mock_sub_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="Search results")]})
            mock_create.return_value = mock_sub_agent

            graph = create_assistant_graph(
                model=primary_model,
                tools=[MagicMock(name="web_search")],
                system_prompt="You are a test assistant.",
                executor_model=executor_model,
            )

            await graph.ainvoke(
                {"messages": [HumanMessage(content="Search for news")]},
                config={"configurable": {"thread_id": "test-executor-override"}},
            )

        # Verify executor_model was passed to create_agent, not primary_model
        call_kwargs = mock_create.call_args[1] if mock_create.call_args else {}
        assert call_kwargs.get("model") is executor_model, (
            f"Expected executor_model passed to create_agent, got {call_kwargs.get('model')}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_graph.py::TestPerNodeModels -v`
Expected: FAIL — `create_assistant_graph` doesn't accept `router_model`/`executor_model`/`responder_model` params yet.

- [ ] **Step 3: Update `create_assistant_graph` signature and closures**

In `src/agntrick/graph.py`, replace the `create_assistant_graph` function (lines 557-606) with:

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_graph.py::TestPerNodeModels -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `make check && make test`
Expected: All tests pass. Existing graph tests should work since new params default to `None`.

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/graph.py tests/test_graph.py
git commit -m "feat: add per-node model overrides to create_assistant_graph"
```

---

### Task 4: Wire up `AssistantAgent` to pass node models

**Files:**
- Modify: `src/agntrick/agents/assistant.py:45-59` (update `_create_graph`)

- [ ] **Step 1: Update `_create_graph` in `AssistantAgent`**

Replace the `_create_graph` method in `src/agntrick/agents/assistant.py`:

```python
    def _create_graph(
        self,
        model: Any,
        tools: list[Any],
        system_prompt: str,
        checkpointer: Any,
    ) -> Any:
        """Use the 3-node StateGraph with per-node model overrides."""
        node_models = self._get_node_models()
        return create_assistant_graph(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            checkpointer=checkpointer,
            progress_callback=self._progress_callback,
            router_model=node_models.get("router"),
            executor_model=node_models.get("executor"),
            responder_model=node_models.get("responder"),
        )
```

- [ ] **Step 2: Run full test suite to check no regressions**

Run: `make check && make test`
Expected: All tests pass. The assistant agent now passes node model overrides, but without config they default to `None` (same behavior as before).

- [ ] **Step 3: Commit**

```bash
git add src/agntrick/agents/assistant.py
git commit -m "feat: wire up per-node model overrides in AssistantAgent"
```

---

### Task 5: Final validation

**Files:** None (validation only)

- [ ] **Step 1: Run full check and test suite**

Run: `make check && make test`
Expected: All pass.

- [ ] **Step 2: Verify existing agent tests still pass**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests pass with no regressions.

- [ ] **Step 3: Manual smoke test with config**

Create a test config and verify the model resolution works end-to-end:

```bash
cat > /tmp/test-agent-models.yaml << 'EOF'
llm:
  model: glm-4.7
agent_models:
  assistant: glm-5.1
  assistant_nodes:
    router: glm-4.7
    executor: glm-5.1
    responder: glm-4.7
  developer: glm-5
  committer: glm-4.7
EOF

AGNTRICK_CONFIG=/tmp/test-agent-models.yaml uv run python -c "
from agntrick.config import get_config
config = get_config(force_reload=True)
print('assistant:', config.agent_models.get_model_for('assistant'))
print('assistant/router:', config.agent_models.get_model_for('assistant', node='router'))
print('developer:', config.agent_models.get_model_for('developer'))
print('unknown:', config.agent_models.get_model_for('unknown'))
print('global:', config.llm.model)
"
```

Expected output:
```
assistant: glm-5.1
assistant/router: glm-4.7
developer: glm-5
unknown: None
global: glm-4.7
```

- [ ] **Step 4: Clean up temp config**

Run: `rm /tmp/test-agent-models.yaml`

- [ ] **Step 5: Final commit (if any cleanup needed)**

```bash
git add {specific added/updated/removed files}
git commit -m "chore: final cleanup for agent model routing"
```
