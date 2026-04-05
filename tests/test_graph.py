"""Tests for the 3-node assistant StateGraph."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from agntrick.graph import (
    AgentState,
    _parse_router_response,
    route_decision,
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
            return_value=MagicMock(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}')
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


class TestExecutorMiddleware:
    """Tests for executor sub-agent middleware configuration."""

    def test_executor_uses_tool_call_limit(self) -> None:
        """Executor should create sub-agent with ToolCallLimitMiddleware."""
        from unittest.mock import patch

        from langchain.agents.middleware.tool_call_limit import ToolCallLimitMiddleware

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_create.return_value = MagicMock()
            mock_create.return_value.ainvoke = AsyncMock(
                return_value={"messages": [MagicMock(content="done")]}
            )

            # Re-import to get the patched version
            from agntrick.graph import executor_node

            state: AgentState = {
                "messages": [HumanMessage(content="test")],
                "intent": "tool_use",
                "tool_plan": "web_search",
                "progress": [],
                "final_response": None,
            }
            config = MagicMock()

            import asyncio

            mock_model = AsyncMock()
            asyncio.get_event_loop().run_until_complete(
                executor_node(
                    state,
                    config,
                    model=mock_model,
                    tools=[],
                    system_prompt="test",
                )
            )

            # Verify middleware was passed
            call_kwargs = mock_create.call_args[1] if mock_create.call_args else {}
            middleware_list = call_kwargs.get("middleware", [])
            assert any(isinstance(m, ToolCallLimitMiddleware) for m in middleware_list), \
                f"Expected ToolCallLimitMiddleware in middleware list, got: {middleware_list}"


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
