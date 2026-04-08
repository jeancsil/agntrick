"""Tests for the 3-node assistant StateGraph."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from agntrick.graph import (
    AgentState,
    _parse_router_response,
    executor_node,
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
        # For tool_use, only the router-selected tool should be available
        assert "web_search" in tool_names
        assert "web_fetch" not in tool_names, f"Only the router-selected tool should be available, got: {tool_names}"

    @pytest.mark.asyncio
    async def test_chat_intent_receives_full_conversation_history(self) -> None:
        """Responder should receive full conversation history for chat intent.

        This verifies the fix for the memory loss bug where _truncate_messages
        was stripping history for chat intent, causing the agent to not
        understand follow-up messages like "yes" or "and in Paris?".
        """
        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()

        # Track what messages the responder receives via ainvoke calls
        invoke_calls: list[list[BaseMessage]] = []

        async def capture_ainvoke(messages: list[BaseMessage]) -> AIMessage:
            invoke_calls.append(messages)
            call_index = len(invoke_calls) - 1
            if call_index == 0:
                # Router response: classify follow-up as chat
                return AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}')
            # Responder response
            return AIMessage(content="The weather in Paris is 18°C.")

        mock_model.ainvoke = capture_ainvoke

        graph = create_assistant_graph(
            model=mock_model,
            tools=[],
            system_prompt="You are a test assistant.",
        )

        # Simulate a multi-turn conversation:
        # Turn 1: user asked about Tokyo weather, agent responded
        # Turn 2: user follows up with "And in Paris?"
        await graph.ainvoke(
            {
                "messages": [
                    HumanMessage(content="What's the weather in Tokyo?"),
                    AIMessage(content="The weather in Tokyo is 22°C, sunny."),
                    HumanMessage(content="And in Paris?"),
                ]
            },
            config={"configurable": {"thread_id": "test-multi-turn-memory"}},
        )

        # First ainvoke call is the router, second is the responder
        assert len(invoke_calls) >= 2, f"Expected >= 2 ainvoke calls, got {len(invoke_calls)}"

        # The responder (second call) should receive ALL messages, not just
        # the last HumanMessage. This is the core fix being tested.
        responder_messages = invoke_calls[1]
        human_msgs = [m for m in responder_messages if isinstance(m, HumanMessage)]
        assert len(human_msgs) >= 2, (
            f"Responder should see >= 2 HumanMessages (full history), "
            f"got {len(human_msgs)}: {[m.content for m in human_msgs]}"
        )

    @pytest.mark.asyncio
    async def test_router_receives_context_window(self) -> None:
        """Router should receive a sliding window of recent messages, not just one."""
        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()

        invoke_calls: list[list[BaseMessage]] = []

        async def capture_ainvoke(messages: list[BaseMessage]) -> AIMessage:
            invoke_calls.append(messages)
            call_index = len(invoke_calls) - 1
            if call_index == 0:
                return AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}')
            return AIMessage(content="Yes, I remember.")

        mock_model.ainvoke = capture_ainvoke

        graph = create_assistant_graph(
            model=mock_model,
            tools=[],
            system_prompt="You are a test assistant.",
        )

        # Build a conversation with 3 exchange pairs (6 messages total)
        await graph.ainvoke(
            {
                "messages": [
                    HumanMessage(content="Message 1"),
                    AIMessage(content="Response 1"),
                    HumanMessage(content="Message 2"),
                    AIMessage(content="Response 2"),
                    HumanMessage(content="Message 3"),
                    AIMessage(content="Response 3"),
                ]
            },
            config={"configurable": {"thread_id": "test-router-context"}},
        )

        # First ainvoke call is the router
        router_messages = invoke_calls[0]
        # Router should see the sliding window (up to 5 messages), not just 1
        non_system_msgs = [m for m in router_messages if not isinstance(m, SystemMessage)]
        assert len(non_system_msgs) > 1, (
            f"Router should receive > 1 non-system message (context window), "
            f"got {len(non_system_msgs)}: {[type(m).__name__ for m in non_system_msgs]}"
        )


class TestSanitizeToolArtifacts:
    """Tests for _sanitize_ai_content stripping XML pseudo-tool-calls."""

    def test_strips_web_search_tag(self) -> None:
        from agntrick.graph import _sanitize_ai_content

        raw = 'I will search for that.\n\n<web_search query="site:g1.globo.com top news headlines" />'
        cleaned = _sanitize_ai_content(raw)
        assert cleaned == "I will search for that."
        assert "<web_search" not in cleaned

    def test_strips_tool_call_block(self) -> None:
        from agntrick.graph import _sanitize_ai_content

        raw = 'Let me look that up.\n<tool_call name="web_search">query: news</tool_call'
        cleaned = _sanitize_ai_content(raw)
        assert "<tool_call" not in cleaned
        assert "Let me look that up." in cleaned

    def test_no_artifact_passes_through(self) -> None:
        from agntrick.graph import _sanitize_ai_content

        raw = "Here is your answer. The weather is sunny."
        assert _sanitize_ai_content(raw) == raw

    def test_strips_execute_tag(self) -> None:
        from agntrick.graph import _sanitize_ai_content

        raw = 'Searching now...\n<execute tool="web_fetch" url="https://example.com" />'
        cleaned = _sanitize_ai_content(raw)
        assert "<execute" not in cleaned
        assert "Searching now..." in cleaned

    @pytest.mark.asyncio
    async def test_executor_sanitizes_artifact_from_sub_agent(self) -> None:
        """Executor should strip XML tool artifacts from sub-agent AIMessage."""
        from agntrick.graph import executor_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="done"))

        sub_result_msg = AIMessage(content='I will search.\n\n<web_search query="test query" />')
        mock_sub_agent = MagicMock()
        mock_sub_agent.ainvoke = AsyncMock(return_value={"messages": [sub_result_msg]})

        import agntrick.graph as graph_mod

        original_create = graph_mod.create_agent
        graph_mod.create_agent = MagicMock(return_value=mock_sub_agent)
        try:
            state: AgentState = {
                "messages": [HumanMessage(content="search for test")],
                "intent": "tool_use",
                "tool_plan": "web_search",
                "progress": [],
                "final_response": None,
            }
            result = await executor_node(
                state,
                MagicMock(),
                model=mock_model,
                tools=[],
                system_prompt="test",
            )
            returned_msg = result["messages"][0]
            assert isinstance(returned_msg, AIMessage)
            assert "<web_search" not in str(returned_msg.content)
            assert "I will search." in str(returned_msg.content)
        finally:
            graph_mod.create_agent = original_create


class TestFlattenToolContent:
    """Tests for _flatten_tool_content — the fix for MCP structured content.

    MCP tools return [{"type": "text", "text": "..."}] content blocks.
    GLM-5.1 sees these dict wrappers as opaque and responds "can't access results".
    _flatten_tool_content must extract the plain text so the LLM can use it.
    """

    def test_single_text_block(self) -> None:
        from agntrick.graph import _flatten_tool_content

        mcp_content = [{"type": "text", "text": "Globo news headline: Brazil wins Copa America"}]
        result = _flatten_tool_content(mcp_content)
        assert result == "Globo news headline: Brazil wins Copa America"
        # Must NOT contain dict wrappers
        assert '{"type"' not in result
        assert "'type'" not in result

    def test_multiple_text_blocks(self) -> None:
        from agntrick.graph import _flatten_tool_content

        mcp_content = [
            {"type": "text", "text": "Headline 1: Rain expected"},
            {"type": "text", "text": "Headline 2: Markets rally"},
        ]
        result = _flatten_tool_content(mcp_content)
        assert "Headline 1: Rain expected" in result
        assert "Headline 2: Markets rally" in result
        assert "\n" in result  # joined by newline

    def test_mixed_blocks_extracts_only_text(self) -> None:
        from agntrick.graph import _flatten_tool_content

        mcp_content = [
            {"type": "text", "text": "Search result data"},
            {"type": "image", "url": "https://example.com/img.png"},
        ]
        result = _flatten_tool_content(mcp_content)
        assert result == "Search result data"

    def test_plain_string_passes_through(self) -> None:
        from agntrick.graph import _flatten_tool_content

        assert _flatten_tool_content("simple string") == "simple string"

    def test_empty_list_returns_string_repr(self) -> None:
        from agntrick.graph import _flatten_tool_content

        result = _flatten_tool_content([])
        assert isinstance(result, str)

    def test_string_elements_in_list(self) -> None:
        from agntrick.graph import _flatten_tool_content

        result = _flatten_tool_content(["line one", "line two"])
        assert result == "line one\nline two"

    def test_real_mcp_web_search_response(self) -> None:
        """Simulate actual MCP web_search response structure."""
        from agntrick.graph import _flatten_tool_content

        mcp_content = [
            {
                "type": "text",
                "text": "## Search Results\n1. Globo - Top News\n2. BBC - World Update\n3. CNN - Breaking Story",
            }
        ]
        result = _flatten_tool_content(mcp_content)
        assert "Globo - Top News" in result
        assert "## Search Results" in result
        assert isinstance(result, str)
        # CRITICAL: no dict wrappers visible — GLM-5.1 must see plain text
        assert "type" not in result[:20]  # "type" key must not appear at start


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
        primary_model.ainvoke = AsyncMock(return_value=AIMessage(content="Hello!"))

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
        responder_model.ainvoke = AsyncMock(return_value=AIMessage(content="Formatted response"))

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


class TestMakeFlatTool:
    """Tests for _make_flat_tool — wraps MCP tools to return plain strings.

    Verifies the wrapper correctly flattens structured MCP content so that
    when the sub-agent calls a tool, it receives a plain string ToolMessage
    instead of [{"type": "text", "text": "..."}].
    """

    def _make_mcp_tool(self, name: str, return_value: Any) -> MagicMock:
        """Create a mock MCP tool that returns structured content."""
        from pydantic import BaseModel

        class FakeInput(BaseModel):
            query: str

        tool = MagicMock(spec=["name", "description", "ainvoke", "args_schema"])
        tool.name = name
        tool.description = f"Mock {name} tool"
        tool.args_schema = FakeInput
        tool.ainvoke = AsyncMock(return_value=return_value)
        return tool

    @pytest.mark.asyncio
    async def test_wraps_mcp_tool_flattens_content(self) -> None:
        """Wrapped tool should return plain string, not structured blocks."""
        from agntrick.graph import _make_flat_tool

        mcp_tool = self._make_mcp_tool(
            "web_search",
            [{"type": "text", "text": "Breaking: Earthquake hits Tokyo"}],
        )

        flat_tool = _make_flat_tool(mcp_tool)
        result = await flat_tool.ainvoke({"query": "tokyo earthquake"})

        assert isinstance(result, str)
        assert "Breaking: Earthquake hits Tokyo" in result
        assert '{"type"' not in result

    @pytest.mark.asyncio
    async def test_wrapped_tool_preserves_name_and_description(self) -> None:
        """Wrapped tool must keep same name and description."""
        from agntrick.graph import _make_flat_tool

        mcp_tool = self._make_mcp_tool("web_fetch", [{"type": "text", "text": "page content"}])
        flat_tool = _make_flat_tool(mcp_tool)

        assert flat_tool.name == "web_fetch"
        assert flat_tool.description == "Mock web_fetch tool"

    def test_skips_mock_tools_without_schema(self) -> None:
        """Tools without args_schema should pass through unchanged."""
        from agntrick.graph import _make_flat_tool

        bare_tool = MagicMock(spec=["name"])
        bare_tool.name = "fake"
        # No args_schema attribute

        result = _make_flat_tool(bare_tool)
        assert result is bare_tool

    @pytest.mark.asyncio
    async def test_executor_flattens_tools_before_sub_agent(self) -> None:
        """Executor node should flatten MCP tools before passing to sub-agent.

        This is the integration test: verify that when executor_node processes
        MCP tools with structured content, the sub-agent receives flat strings.
        """
        from pydantic import BaseModel

        import agntrick.graph as graph_mod

        class SearchInput(BaseModel):
            query: str

        # Create an MCP tool that returns structured content
        mcp_tool = MagicMock(spec=["name", "description", "ainvoke", "args_schema"])
        mcp_tool.name = "web_search"
        mcp_tool.description = "Search the web"
        mcp_tool.args_schema = SearchInput
        # This is what MCP returns — structured blocks
        mcp_tool.ainvoke = AsyncMock(return_value=[{"type": "text", "text": "## Results\n1. Globo news\n2. BBC world"}])

        # Capture what tools the sub-agent receives
        tools_received: list[Any] = []
        original_create = graph_mod.create_agent

        def capture_create(*args: Any, **kwargs: Any) -> Any:
            tools_received.extend(kwargs.get("tools", []))
            mock_sub = MagicMock()
            mock_sub.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="Here are the news results.")]})
            return mock_sub

        graph_mod.create_agent = capture_create
        try:
            state: AgentState = {
                "messages": [HumanMessage(content="What's the news?")],
                "intent": "tool_use",
                "tool_plan": "web_search",
                "progress": [],
                "final_response": None,
            }
            await executor_node(
                state,
                MagicMock(),
                model=AsyncMock(),
                tools=[mcp_tool],
                system_prompt="test",
            )

            # The sub-agent should have received exactly one tool
            assert len(tools_received) == 1, f"Expected 1 tool, got {len(tools_received)}"

            # Verify the wrapped tool returns flat string, not structured blocks
            wrapped_tool = tools_received[0]
            result = await wrapped_tool.ainvoke({"query": "news"})
            assert isinstance(result, str), f"Expected str, got {type(result)}: {result}"
            assert "Globo news" in result
            assert '{"type"' not in result
        finally:
            graph_mod.create_agent = original_create

    @pytest.mark.asyncio
    async def test_tool_use_intent_gets_single_tool(self) -> None:
        """For tool_use intent, only the router-selected tool should be available.

        This prevents the secondary issue: LLM calling web_search twice then
        trying web_fetch. With only one tool available, it must call once and respond.
        """
        from pydantic import BaseModel

        import agntrick.graph as graph_mod

        class FakeInput(BaseModel):
            query: str

        def make_tool(name: str) -> MagicMock:
            t = MagicMock(spec=["name", "description", "ainvoke", "args_schema"])
            t.name = name
            t.description = f"Mock {name}"
            t.args_schema = FakeInput
            t.ainvoke = AsyncMock(return_value=[{"type": "text", "text": f"{name} result"}])
            return t

        all_tools = [make_tool("web_search"), make_tool("web_fetch"), make_tool("curl_fetch")]

        tools_received: list[Any] = []
        original_create = graph_mod.create_agent

        def capture_create(*args: Any, **kwargs: Any) -> Any:
            tools_received.extend(kwargs.get("tools", []))
            mock_sub = MagicMock()
            mock_sub.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="Results")]})
            return mock_sub

        graph_mod.create_agent = capture_create
        try:
            state: AgentState = {
                "messages": [HumanMessage(content="What's the news?")],
                "intent": "tool_use",
                "tool_plan": "web_search",
                "progress": [],
                "final_response": None,
            }
            await executor_node(
                state,
                MagicMock(),
                model=AsyncMock(),
                tools=all_tools,
                system_prompt="test",
            )

            tool_names = [getattr(t, "name", "?") for t in tools_received]
            assert tool_names == ["web_search"], (
                f"Expected only ['web_search'], got {tool_names} — tool_use should narrow to router-selected tool"
            )
        finally:
            graph_mod.create_agent = original_create
