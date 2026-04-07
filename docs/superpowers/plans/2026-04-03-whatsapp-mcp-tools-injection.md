# WhatsApp MCP Tools Injection Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WhatsApp webhook agents connect to MCP toolbox server so they have access to agntrick tools.

**Architecture:** The WhatsApp webhook handler (`whatsapp.py:362-391`) currently creates agents without MCP tools. The fix mirrors the CLI pattern (`cli.py:75-88`): look up the agent's registered MCP servers and tool categories from `AgentRegistry`, create an `MCPProvider`, open a `tool_session()`, and pass the tools + categories to the agent constructor.

**Tech Stack:** Python, FastAPI, LangChain MCP adapters, asyncio

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/agntrick/api/routes/whatsapp.py:362-391` | Modify | Inject MCP provider + tool categories when creating agent |
| `tests/test_api/test_whatsapp_route.py` | Modify | Add tests verifying MCP tools are passed to agents |

---

### Task 1: Write failing test — agent gets MCP tools in WhatsApp webhook

**Files:**
- Modify: `tests/test_api/test_whatsapp_route.py`

- [ ] **Step 1: Write the failing test**

Add a new test class `TestWhatsAppMCPInjection` to `tests/test_api/test_whatsapp_route.py`. The test patches `AgentRegistry.get_mcp_servers` to return `["toolbox"]`, patches `MCPProvider.tool_session` to yield fake tools, and verifies the agent constructor receives them.

```python
from unittest.mock import AsyncMock, MagicMock, patch


class TestWhatsAppMCPInjection:
    """Tests that the WhatsApp webhook injects MCP tools into agents."""

    @patch("agntrick.api.routes.whatsapp.MCPProvider")
    @patch("agntrick.api.routes.whatsapp.AgentRegistry")
    def test_webhook_injects_mcp_tools_into_agent(self, mock_registry_cls, mock_mcp_cls):
        """WhatsApp webhook should pass MCP tools and tool_categories to agent."""
        from agntrick.api.server import create_app

        # Set up registry
        mock_registry_cls.discover_agents = MagicMock()
        mock_agent_cls = MagicMock()
        mock_agent_instance = AsyncMock()
        mock_agent_instance.run = AsyncMock(return_value="Hello from agent")
        mock_agent_cls.return_value = mock_agent_cls
        # Track constructor call
        constructor_calls = []
        def capture_constructor(**kwargs):
            constructor_calls.append(kwargs)
            return mock_agent_instance
        mock_agent_cls.side_effect = capture_constructor
        mock_registry_cls.get.return_value = mock_agent_cls
        mock_registry_cls.get_mcp_servers.return_value = ["toolbox"]
        mock_registry_cls.get_tool_categories.return_value = ["web", "hackernews"]

        # Set up MCP provider
        fake_tool = MagicMock(name="web_search")
        mock_provider_instance = MagicMock()
        mock_provider_instance.tool_session.return_value.__aenter__ = AsyncMock(return_value=[fake_tool])
        mock_provider_instance.tool_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_mcp_cls.return_value = mock_provider_instance

        app = create_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/channels/whatsapp/message",
            json={"from": "+1234567890", "message": "hello", "tenant_id": "test-tenant"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        # Verify MCPProvider was created with the agent's registered servers
        mock_mcp_cls.assert_called_once_with(server_names=["toolbox"])
        # Verify agent constructor received MCP tools and tool_categories
        assert len(constructor_calls) == 1
        args = constructor_calls[0]
        assert args.get("initial_mcp_tools") == [fake_tool]
        assert args.get("tool_categories") == ["web", "hackernews"]
        assert args.get("_agent_name") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api/test_whatsapp_route.py::TestWhatsAppMCPInjection -xvs`
Expected: FAIL — `MCPProvider` is not imported/used in `whatsapp.py` yet.

---

### Task 2: Implement MCP injection in WhatsApp webhook

**Files:**
- Modify: `src/agntrick/api/routes/whatsapp.py:362-391`

- [ ] **Step 1: Add MCPProvider import**

At the top of `src/agntrick/api/routes/whatsapp.py`, add the import alongside existing imports:

```python
from agntrick.mcp import MCPProvider
```

- [ ] **Step 2: Replace agent creation block**

Replace the block at lines 362-398 (from `# Run the tenant's configured agent` to end of except) with:

```python
    # Run the tenant's configured agent
    agent_name = tenant_config.default_agent
    try:
        AgentRegistry.discover_agents()
        agent_cls = AgentRegistry.get(agent_name)

        if not agent_cls:
            tenant_logger.error("Agent '%s' not found for tenant %s", agent_name, tenant_id)
            raise HTTPException(status_code=500, detail="Agent not found")

        # Look up MCP servers and tool categories registered for this agent
        allowed_mcp = AgentRegistry.get_mcp_servers(agent_name)
        tool_categories = AgentRegistry.get_tool_categories(agent_name)
        config = get_config()

        if allowed_mcp:
            # Connect to MCP servers and inject tools (same pattern as CLI)
            provider = MCPProvider(server_names=allowed_mcp)
            async with provider.tool_session() as mcp_tools:
                agent = agent_cls(
                    initial_mcp_tools=mcp_tools,
                    _agent_name=agent_name,
                    tool_categories=tool_categories,
                    model_name=config.llm.model,
                    temperature=config.llm.temperature,
                    thread_id="whatsapp_webhook",
                    checkpointer=None,
                )
                result = await agent.run(message)
        else:
            agent = agent_cls(
                _agent_name=agent_name,
                tool_categories=tool_categories,
                model_name=config.llm.model,
                temperature=config.llm.temperature,
                thread_id="whatsapp_webhook",
                checkpointer=None,
            )
            result = await agent.run(message)

        tenant_logger.info("Successfully processed WhatsApp message for tenant %s", tenant_id)
        return {"response": str(result) if result is not None else "", "tenant_id": tenant_id}

    except Exception as e:
        tenant_logger.error("Failed to process WhatsApp message for tenant %s: %s", tenant_id, str(e))
        raise HTTPException(status_code=500, detail="Internal error processing message")
```

Key changes:
- Looks up `allowed_mcp` and `tool_categories` from `AgentRegistry` (same as CLI)
- When MCP servers exist: creates `MCPProvider`, opens `tool_session()`, passes tools to agent
- When no MCP servers: creates agent with just tool_categories (for prompt-only agents)
- Passes `_agent_name` so manifest fetch and logging work correctly
- Removes the brittle `inspect.signature` check for checkpointer — just pass `None` directly

- [ ] **Step 3: Run the test to verify it passes**

Run: `uv run pytest tests/test_api/test_whatsapp_route.py::TestWhatsAppMCPInjection -xvs`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/test_api/test_whatsapp_route.py -xvs`
Expected: All tests PASS (existing QR/status tests unaffected)

---

### Task 3: Run lint and type checks

**Files:** None (verification only)

- [ ] **Step 1: Run make check**

Run: `make check`
Expected: PASS — no mypy or ruff errors

- [ ] **Step 2: Run make test**

Run: `make test`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/agntrick/api/routes/whatsapp.py tests/test_api/test_whatsapp_route.py
git commit -m "fix: inject MCP tools into WhatsApp webhook agents

WhatsApp agents now connect to the toolbox MCP server, matching the
CLI pattern. Previously agents were created without MCP tools or
tool_categories, so they had no access to agntrick toolkit capabilities."
```

---

## Self-Review

**Spec coverage:** The bug is that WhatsApp agents lack MCP tools. Task 2 fixes the injection. Task 1 tests it. Task 3 verifies no regressions. Complete.

**Placeholder scan:** No TBD, TODO, or "implement later" patterns. All code blocks contain full implementations.

**Type consistency:** `MCPProvider(server_names=allowed_mcp)` matches the constructor signature in `provider.py:42`. `initial_mcp_tools`, `_agent_name`, `tool_categories` match `AgentBase.__init__` parameters in `agent.py:57-68`. `AgentRegistry.get_mcp_servers` and `get_tool_categories` return `Optional[List[str]]` matching `registry.py:84-90`.
