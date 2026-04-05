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

    def test_tool_use_returns_web_and_document_tools(self) -> None:
        """tool_use intent should return web + document tools (no invoke_agent)."""
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
        assert names == {"web_search", "web_fetch", "curl_fetch"}

    def test_research_adds_hackernews_tools(self) -> None:
        """research intent should include hacker_news tools (no invoke_agent)."""
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
        assert names == {"web_search", "hacker_news_top", "hacker_news_item"}

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
            mock_create.return_value.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content="done")]})

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


class TestGraphIntegration:
    """Integration tests for the full 3-node graph with mock LLM.

    Verifies that message isolation, tool filtering, and middleware
    all work together through the real graph execution path.
    """

    @pytest.mark.asyncio
    async def test_chat_intent_skips_executor(self) -> None:
        """Chat intent should go router → responder (skip executor)."""
        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()
        # Router returns chat intent, responder formats response
        mock_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}'),
                AIMessage(content="Hello! How can I help you?"),
            ]
        )

        graph = create_assistant_graph(
            model=mock_model,
            tools=[],
            system_prompt="You are a test assistant.",
        )

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="Hello")]},
            config={"configurable": {"thread_id": "test-chat-integration"}},
        )

        assert result.get("final_response") is not None

    @pytest.mark.asyncio
    async def test_tool_use_intent_routes_to_executor(self) -> None:
        """Tool use intent should go router → executor → responder."""
        from unittest.mock import patch

        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "tool_use", "tool_plan": "web_search", "skip_tools": false}'),
                AIMessage(content="São Paulo: 25°C, sunny ☀️"),
            ]
        )

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_sub_agent = MagicMock()
            mock_sub_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="The weather is 25°C.")]})
            mock_create.return_value = mock_sub_agent

            graph = create_assistant_graph(
                model=mock_model,
                tools=[MagicMock(name="web_search")],
                system_prompt="You are a test assistant.",
            )

            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="What's the weather in São Paulo?")]},
                config={"configurable": {"thread_id": "test-tool-use-integration"}},
            )

        mock_create.assert_called_once()
        assert result.get("final_response") is not None

    @pytest.mark.asyncio
    async def test_executor_receives_single_message_despite_accumulated_history(self) -> None:
        """Executor should only receive the last user message even with accumulated history."""
        from unittest.mock import patch

        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "tool_use", "tool_plan": "web_search", "skip_tools": false}'),
                AIMessage(content="Formatted response"),
            ]
        )

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_sub_agent = MagicMock()
            mock_sub_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="News results here")]})
            mock_create.return_value = mock_sub_agent

            graph = create_assistant_graph(
                model=mock_model,
                tools=[MagicMock(name="web_search")],
                system_prompt="You are a test assistant.",
            )

            # Simulate accumulated history from multiple WhatsApp messages
            await graph.ainvoke(
                {
                    "messages": [
                        HumanMessage(content="What's the weather?"),
                        AIMessage(content="It's sunny."),
                        HumanMessage(content="Tell me a joke"),
                        AIMessage(content="Why did the chicken cross the road?"),
                        HumanMessage(content="What are the top news in g1.globo.com?"),
                    ]
                },
                config={"configurable": {"thread_id": "test-history-isolation"}},
            )

        # Verify sub-agent was invoked
        mock_create.assert_called_once()
        sub_invoke_args = mock_sub_agent.ainvoke.call_args
        messages_sent = sub_invoke_args[0][0]["messages"]

        # Only the last HumanMessage should have been sent
        human_msgs = [m for m in messages_sent if isinstance(m, HumanMessage)]
        assert len(human_msgs) == 1
        assert human_msgs[0].content == "What are the top news in g1.globo.com?"

    @pytest.mark.asyncio
    async def test_tool_filtering_excludes_run_shell_for_tool_use(self) -> None:
        """Tool filtering should exclude run_shell for tool_use intent."""
        from unittest.mock import patch

        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "tool_use", "tool_plan": "web_search", "skip_tools": false}'),
                AIMessage(content="Response"),
            ]
        )

        def _make_tool(name: str) -> MagicMock:
            t = MagicMock()
            t.name = name
            return t

        all_tools = [
            _make_tool("web_search"),
            _make_tool("web_fetch"),
            _make_tool("run_shell"),
            _make_tool("invoke_agent"),
        ]

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_sub_agent = MagicMock()
            mock_sub_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="Results")]})
            mock_create.return_value = mock_sub_agent

            graph = create_assistant_graph(
                model=mock_model,
                tools=all_tools,
                system_prompt="You are a test assistant.",
            )

            await graph.ainvoke(
                {"messages": [HumanMessage(content="Search for news")]},
                config={"configurable": {"thread_id": "test-tool-filter"}},
            )

        # Verify tools passed to create_agent
        call_kwargs = mock_create.call_args[1] if mock_create.call_args else {}
        tools_passed = call_kwargs.get("tools", [])
        tool_names = {getattr(t, "name", None) for t in tools_passed}

        # run_shell should NOT be in the filtered tools
        assert "run_shell" not in tool_names, f"run_shell should be filtered out, got: {tool_names}"
        assert "web_search" in tool_names
        assert "web_fetch" in tool_names
