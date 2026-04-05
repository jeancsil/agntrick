"""Tests for the 3-node assistant StateGraph."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agntrick.graph import (
    AgentState,
    _parse_router_response,
    route_decision,
)


class TestFilterTools:
    """Tests for _filter_tools function."""

    def _make_tool(self, name: str) -> MagicMock:
        """Create a mock tool with a .name attribute."""
        tool = MagicMock()
        tool.name = name
        return tool

    def test_tool_use_returns_web_and_agent_tools(self) -> None:
        """tool_use intent should return web + document + agent tools."""
        from agntrick.graph import _filter_tools

        all_tools = [
            self._make_tool("web_search"),
            self._make_tool("web_fetch"),
            self._make_tool("curl_fetch"),
            self._make_tool("run_shell"),
            self._make_tool("ffmpeg_convert"),
            self._make_tool("invoke_agent"),
        ]
        result = _filter_tools(all_tools, "tool_use")
        names = {t.name for t in result}
        assert names == {"web_search", "web_fetch", "curl_fetch", "invoke_agent"}

    def test_research_adds_hackernews_tools(self) -> None:
        """research intent should include hacker_news tools."""
        from agntrick.graph import _filter_tools

        all_tools = [
            self._make_tool("web_search"),
            self._make_tool("hacker_news_top"),
            self._make_tool("hacker_news_item"),
            self._make_tool("run_shell"),
            self._make_tool("invoke_agent"),
        ]
        result = _filter_tools(all_tools, "research")
        names = {t.name for t in result}
        assert names == {"web_search", "hacker_news_top", "hacker_news_item", "invoke_agent"}

    def test_delegate_returns_only_invoke_agent(self) -> None:
        """delegate intent should return only invoke_agent."""
        from agntrick.graph import _filter_tools

        all_tools = [
            self._make_tool("web_search"),
            self._make_tool("invoke_agent"),
            self._make_tool("run_shell"),
        ]
        result = _filter_tools(all_tools, "delegate")
        names = {t.name for t in result}
        assert names == {"invoke_agent"}

    def test_chat_returns_no_tools(self) -> None:
        """chat intent should return no tools."""
        from agntrick.graph import _filter_tools

        all_tools = [self._make_tool("web_search")]
        result = _filter_tools(all_tools, "chat")
        assert result == []

    def test_unknown_intent_returns_all_tools(self) -> None:
        """Unknown intent should fall back to returning all tools."""
        from agntrick.graph import _filter_tools

        all_tools = [self._make_tool("web_search"), self._make_tool("run_shell")]
        result = _filter_tools(all_tools, "unknown_intent")
        assert result == all_tools


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

    @pytest.mark.asyncio
    async def test_executor_uses_tool_call_limit(self) -> None:
        """Executor should create sub-agent with ToolCallLimitMiddleware."""
        from unittest.mock import patch

        from langchain.agents.middleware.tool_call_limit import ToolCallLimitMiddleware

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_create.return_value = MagicMock()
            mock_create.return_value.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content="done")]})

            from agntrick.graph import executor_node

            state: AgentState = {
                "messages": [HumanMessage(content="test")],
                "intent": "tool_use",
                "tool_plan": "web_search",
                "progress": [],
                "final_response": None,
            }
            config = MagicMock()

            mock_model = AsyncMock()
            await executor_node(
                state,
                config,
                model=mock_model,
                tools=[],
                system_prompt="test",
            )

            # Verify middleware was passed
            call_kwargs = mock_create.call_args[1] if mock_create.call_args else {}
            middleware_list = call_kwargs.get("middleware", [])
            assert any(isinstance(m, ToolCallLimitMiddleware) for m in middleware_list), (
                f"Expected ToolCallLimitMiddleware in middleware list, got: {middleware_list}"
            )


class TestExecutorMessageIsolation:
    """Tests that executor receives only the last user message, not full history."""

    @pytest.mark.asyncio
    async def test_executor_receives_only_last_message(self) -> None:
        """Executor should send only the last HumanMessage, not full history."""
        from unittest.mock import patch

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_create.return_value = MagicMock()
            mock_create.return_value.ainvoke = AsyncMock(
                return_value={"messages": [MagicMock(content="done")]}
            )

            from agntrick.graph import executor_node

            # Simulate accumulated history with previous failures
            state: AgentState = {
                "messages": [
                    HumanMessage(content="What's the weather?"),
                    AIMessage(content="All tools are down"),
                    HumanMessage(content="What are the top news in g1.globo.com?"),
                ],
                "intent": "tool_use",
                "tool_plan": "web_search",
                "progress": [],
                "final_response": None,
            }
            config = MagicMock()

            await executor_node(
                state,
                config,
                model=AsyncMock(),
                tools=[],
                system_prompt="test",
            )

            # Verify only last HumanMessage was sent to sub-agent
            invoke_args = mock_create.return_value.ainvoke.call_args
            messages = invoke_args[0][0]["messages"] if invoke_args else []
            human_msgs = [m for m in messages if isinstance(m, HumanMessage)]
            assert len(human_msgs) == 1, (
                f"Expected exactly 1 HumanMessage, got {len(human_msgs)}: {[m.content for m in human_msgs]}"
            )
            assert human_msgs[0].content == "What are the top news in g1.globo.com?"


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
