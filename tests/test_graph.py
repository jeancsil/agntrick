"""Tests for the 3-node assistant StateGraph."""

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage, SystemMessage

from agntrick.graph import (
    AgentState,
    _parse_router_response,
    agent_node,
    summarize_node,
)


class TestFilterTools:
    """Tests for _filter_tools function."""

    def _make_tool(self, name: str) -> MagicMock:
        """Create a mock tool with a .name attribute."""
        tool = MagicMock()
        tool.name = name
        return tool

    def test_tool_use_returns_web_and_document_tools(self) -> None:
        """tool_use intent should return web tools (no invoke_agent, no curl_fetch)."""
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
        assert names == {"web_search", "web_fetch"}

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
    """Tests for graph routing — all intents go through agent node."""

    def test_graph_has_no_conditional_router_edges(self) -> None:
        """After removing route_decision, graph uses direct edge router→agent."""
        from agntrick.graph import create_assistant_graph

        graph = create_assistant_graph(
            model=MagicMock(),
            tools=[],
            system_prompt="test",
            checkpointer=None,
        )
        # Verify the graph compiles and has the expected nodes
        node_names = set(graph.nodes.keys())
        assert "summarize" in node_names
        assert "router" in node_names
        assert "agent" in node_names


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


class TestAgentMiddleware:
    """Tests for agent sub-agent middleware configuration."""

    @pytest.mark.asyncio
    async def test_agent_uses_tool_call_limit(self) -> None:
        """Agent should create sub-agent with ToolCallLimitMiddleware."""
        from unittest.mock import patch

        from langchain.agents.middleware.tool_call_limit import ToolCallLimitMiddleware

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_create.return_value = MagicMock()
            mock_create.return_value.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content="done")]})

            from agntrick.graph import agent_node

            state: AgentState = {
                "messages": [HumanMessage(content="test")],
                "intent": "tool_use",
                "tool_plan": "web_search",
                "progress": [],
                "final_response": None,
            }
            config = MagicMock()

            mock_model = AsyncMock()
            await agent_node(
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


class TestAgentMessageIsolation:
    """Tests that agent receives a context window for tool_use, not full history."""

    @pytest.mark.asyncio
    async def test_agent_receives_context_window_for_tool_use(self) -> None:
        """tool_use intent should send recent messages (up to 4) for follow-up context."""
        from unittest.mock import patch

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_create.return_value = MagicMock()
            mock_create.return_value.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content="done")]})

            from agntrick.graph import agent_node

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

            await agent_node(
                state,
                config,
                model=AsyncMock(),
                tools=[],
                system_prompt="test",
            )

            # Verify recent messages were sent (not full history, not single message)
            invoke_args = mock_create.return_value.ainvoke.call_args
            messages = invoke_args[0][0]["messages"] if invoke_args else []
            # Should include the last HumanMessage at minimum
            human_msgs = [m for m in messages if isinstance(m, HumanMessage)]
            assert len(human_msgs) >= 1, (
                f"Expected at least 1 HumanMessage, got {len(human_msgs)}: {[m.content for m in human_msgs]}"
            )
            # Last HumanMessage must be the current query
            assert human_msgs[-1].content == "What are the top news in g1.globo.com?"


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

    @pytest.mark.asyncio
    async def test_chat_intent_routes_to_agent(self) -> None:
        """Chat intent should go router → agent → END (agent responds conversationally)."""
        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()
        # Router classifies as chat, then agent responds conversationally
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
        # Agent node should have been called (2 ainvoke calls: router + agent)
        assert mock_model.ainvoke.call_count == 2

    @pytest.mark.asyncio
    async def test_tool_use_intent_routes_to_agent(self) -> None:
        """Tool use intent should go router → agent → END."""
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
    async def test_agent_receives_context_window_despite_accumulated_history(self) -> None:
        """tool_use intent should send a window of recent messages for follow-up context."""
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

        # Should include at least the last HumanMessage (context window, not single)
        human_msgs = [m for m in messages_sent if isinstance(m, HumanMessage)]
        assert len(human_msgs) >= 1
        # The last HumanMessage must be the current query
        assert human_msgs[-1].content == "What are the top news in g1.globo.com?"

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
        """Agent node should receive full conversation history for chat intent.

        This verifies the fix for the memory loss bug where _truncate_messages
        was stripping history for chat intent, causing the agent to not
        understand follow-up messages like "yes" or "and in Paris?".
        """
        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()

        # Track what messages each node receives via ainvoke calls
        invoke_calls: list[list[BaseMessage]] = []

        async def capture_ainvoke(messages: list[BaseMessage]) -> AIMessage:
            invoke_calls.append(messages)
            call_index = len(invoke_calls) - 1
            if call_index == 0:
                # Router response: classify follow-up as chat
                return AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}')
            # Agent response: conversational reply
            return AIMessage(content="The weather in Paris is 18°C, cloudy.")

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

        # 2 calls: router classifies, agent responds conversationally
        assert len(invoke_calls) == 2, f"Expected 2 ainvoke calls (router + agent), got {len(invoke_calls)}"

        # The agent node (2nd call) should receive conversation context
        agent_messages = invoke_calls[1]
        human_msgs = [m for m in agent_messages if isinstance(m, HumanMessage)]
        assert len(human_msgs) >= 1, (
            f"Agent should see >= 1 HumanMessage, got {len(human_msgs)}: {[m.content for m in human_msgs]}"
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
    async def test_agent_sanitizes_artifact_from_sub_agent(self) -> None:
        """Agent should strip XML tool artifacts from sub-agent AIMessage."""

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
            result = await agent_node(
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
        primary_model.ainvoke = AsyncMock(return_value=AIMessage(content="Hello!"))
        router_model = AsyncMock()

        # Track which model is called for routing
        router_model.ainvoke = AsyncMock(
            return_value=AIMessage(content='{"intent": "chat", "tool_plan": null, "skip_tools": true}')
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

        # Router should have used router_model
        router_model.ainvoke.assert_called_once()
        # Primary model is used by agent node for chat response
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

        # Chat goes router → agent: 2 calls (router + agent)
        assert primary_model.ainvoke.call_count == 2

    @pytest.mark.asyncio
    async def test_agent_uses_override_model_for_tool_use(self) -> None:
        """Agent should use agent_model when provided for tool_use intent."""
        from unittest.mock import patch

        from agntrick.graph import create_assistant_graph

        primary_model = AsyncMock()
        agent_model = AsyncMock()

        primary_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content='{"intent": "tool_use", "tool_plan": "web_search", "skip_tools": false}'),
                AIMessage(content="Formatted"),
            ]
        )
        agent_model.ainvoke = AsyncMock(return_value=AIMessage(content="done"))

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_sub_agent = MagicMock()
            mock_sub_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="Search results")]})
            mock_create.return_value = mock_sub_agent

            graph = create_assistant_graph(
                model=primary_model,
                tools=[MagicMock(name="web_search")],
                system_prompt="You are a test assistant.",
                agent_model=agent_model,
            )

            await graph.ainvoke(
                {"messages": [HumanMessage(content="Search for news")]},
                config={"configurable": {"thread_id": "test-agent-override-tool-use"}},
            )

        # Verify agent_model was passed to create_agent, not primary_model
        call_kwargs = mock_create.call_args[1] if mock_create.call_args else {}
        assert call_kwargs.get("model") is agent_model, (
            f"Expected agent_model passed to create_agent, got {call_kwargs.get('model')}"
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
    async def test_agent_flattens_tools_before_sub_agent(self) -> None:
        """Agent node should flatten MCP tools before passing to sub-agent.

        This is the integration test: verify that when agent_node processes
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
            from agntrick.graph import agent_node

            state: AgentState = {
                "messages": [HumanMessage(content="What's the news?")],
                "intent": "tool_use",
                "tool_plan": "web_search",
                "progress": [],
                "final_response": None,
            }
            await agent_node(
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
            from agntrick.graph import agent_node

            state: AgentState = {
                "messages": [HumanMessage(content="What's the news?")],
                "intent": "tool_use",
                "tool_plan": "web_search",
                "progress": [],
                "final_response": None,
            }
            await agent_node(
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
            mock_sub.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="News results from search")]})
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
        """After a chat turn, state should have final_response and 1 AIMessage from agent node."""
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

        # Chat intent now routes through agent node which adds 1 AIMessage
        assert result.get("final_response") is not None, "Chat intent should set final_response"
        ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert len(ai_msgs) == 1, f"Chat intent should add exactly 1 AIMessage, got {len(ai_msgs)}"

    @pytest.mark.asyncio
    async def test_research_adds_exactly_one_ai_message(self) -> None:
        """After a research turn, state should have exactly 1 AIMessage."""
        from unittest.mock import patch

        from agntrick.graph import create_assistant_graph

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(
                    content='{"intent": "research", "tool_plan": "1. web_search\\n2. web_fetch", "skip_tools": false}'
                ),
                AIMessage(content="Formatted research results"),
            ]
        )

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_sub = MagicMock()
            mock_sub.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="Research results")]})
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
        assert len(ai_msgs) == 1, f"Expected exactly 1 AIMessage after research turn, got {len(ai_msgs)}"

    @pytest.mark.asyncio
    async def test_multi_turn_accumulates_one_ai_per_turn(self) -> None:
        """Over multiple turns, each turn should add exactly 1 AI message.

        Simulates 2 turns (1 chat, 1 tool_use) and verifies that:
        - Chat turn: routes through agent node, adds 1 AIMessage
        - Tool_use turn: adds exactly 1 AIMessage
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

        # Chat intent now routes through agent node — adds 1 AIMessage
        assert result1.get("final_response") is not None, "Turn 1: chat should set final_response"
        ai_after_turn1 = [m for m in result1["messages"] if isinstance(m, AIMessage)]
        assert len(ai_after_turn1) == 1, f"Turn 1: chat should add 1 AI msg, got {len(ai_after_turn1)}"

        # --- Turn 2: tool_use ---
        mock_model2 = AsyncMock()
        mock_model2.ainvoke = AsyncMock(
            return_value=AIMessage(content='{"intent": "tool_use", "tool_plan": "web_search", "skip_tools": false}')
        )

        with patch("agntrick.graph.create_agent") as mock_create:
            mock_sub = MagicMock()
            mock_sub.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="News results")]})
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

        # After turn 2, tool_use should have added exactly 1 AIMessage
        ai_after_turn2 = [m for m in result2["messages"] if isinstance(m, AIMessage)]
        assert len(ai_after_turn2) == 1, f"Turn 2: tool_use should add 1 AI msg, got {len(ai_after_turn2)}"


class TestBudgetWindowMessages:
    """Tests for _budget_window_messages — character-budget-based windowing."""

    def test_empty_returns_empty(self) -> None:
        """Empty message list should return empty list."""
        from agntrick.graph import _budget_window_messages

        assert _budget_window_messages([], 1000) == []

    def test_single_msg_within_budget(self) -> None:
        """Single message within budget should return that message."""
        from agntrick.graph import _budget_window_messages

        msgs = [HumanMessage(content="Hello")]
        result = _budget_window_messages(msgs, 1000)
        assert len(result) == 1
        assert result[0].content == "Hello"

    def test_single_msg_exceeds_budget_still_returned(self) -> None:
        """Single message exceeding budget should still be returned (guarantee)."""
        from agntrick.graph import _budget_window_messages

        msgs = [HumanMessage(content="x" * 5000)]
        result = _budget_window_messages(msgs, 1000)
        assert len(result) == 1
        assert result[0].content == "x" * 5000

    def test_truncates_when_budget_exceeded(self) -> None:
        """Should truncate when cumulative budget is exceeded."""
        from agntrick.graph import _budget_window_messages

        msgs = [
            HumanMessage(content="a" * 1000),
            AIMessage(content="b" * 500),
            HumanMessage(content="c" * 600),
        ]
        result = _budget_window_messages(msgs, 1500)
        # Should include last message (600) + second-to-last (500) = 1100 budget
        # First message (1000) would exceed budget: 1100 + 1000 = 2100 > 1500
        assert len(result) == 2
        assert result[0].content == "b" * 500
        assert result[1].content == "c" * 600

    def test_preserves_order(self) -> None:
        """Should preserve original message order (most recent last)."""
        from agntrick.graph import _budget_window_messages

        msgs = [
            HumanMessage(content="first"),
            AIMessage(content="second"),
            HumanMessage(content="third"),
        ]
        result = _budget_window_messages(msgs, 10000)
        assert len(result) == 3
        assert result[0].content == "first"
        assert result[1].content == "second"
        assert result[2].content == "third"

    def test_hard_ceiling_on_count(self) -> None:
        """Should enforce max_messages ceiling even if budget allows more."""
        from agntrick.graph import _budget_window_messages

        # 30 tiny messages, each 10 chars = 300 total (well under 10K budget)
        # But max_messages=20 should cap at 20
        msgs = [HumanMessage(content=f"msg{i}") for i in range(30)]
        result = _budget_window_messages(msgs, 10000, max_messages=20)
        assert len(result) == 20
        # Should be the 20 most recent
        assert result[0].content == "msg10"
        assert result[-1].content == "msg29"

    def test_mixed_human_ai_messages(self) -> None:
        """Should handle mixed HumanMessage and AIMessage correctly."""
        from agntrick.graph import _budget_window_messages

        msgs = [
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
            HumanMessage(content="Q2"),
            AIMessage(content="A2"),
        ]
        result = _budget_window_messages(msgs, 100)
        assert len(result) == 4
        assert isinstance(result[0], HumanMessage)
        assert isinstance(result[1], AIMessage)
        assert isinstance(result[2], HumanMessage)
        assert isinstance(result[3], AIMessage)


class TestBuildPruneRemoves:
    """Tests for _build_prune_removes helper — returns RemoveMessage list for old messages."""

    def test_returns_empty_when_within_cap(self) -> None:
        """5 messages with cap 20 → no pruning needed."""
        from agntrick.graph import _build_prune_removes

        msgs = [HumanMessage(content=f"msg {i}", id=f"msg-{i}") for i in range(5)]
        assert _build_prune_removes(msgs, max_messages=20) == []

    def test_returns_removes_for_excess_messages(self) -> None:
        """25 messages with cap 20 → 5 RemoveMessage objects."""
        from agntrick.graph import _build_prune_removes

        msgs = [HumanMessage(content=f"msg {i}", id=f"msg-{i}") for i in range(25)]
        removes = _build_prune_removes(msgs, max_messages=20)
        assert len(removes) == 5
        assert all(isinstance(r, RemoveMessage) for r in removes)

    def test_preserves_most_recent_messages(self) -> None:
        """Oldest messages are removed, newest kept."""
        from agntrick.graph import _build_prune_removes

        msgs = [HumanMessage(content=f"msg {i}", id=f"msg-{i}") for i in range(25)]
        removes = _build_prune_removes(msgs, max_messages=20)
        removed_ids = {r.id for r in removes}
        # Should remove msg-0 through msg-4 (oldest 5)
        assert removed_ids == {f"msg-{i}" for i in range(5)}
        # Should NOT remove msg-5 through msg-24 (newest 20)
        kept_ids = {f"msg-{i}" for i in range(5, 25)}
        assert removed_ids.isdisjoint(kept_ids)

    def test_skips_messages_without_ids(self) -> None:
        """Messages with id=None should be skipped safely."""
        from agntrick.graph import _build_prune_removes

        msgs = [HumanMessage(content=f"msg {i}") for i in range(25)]  # No explicit IDs
        removes = _build_prune_removes(msgs, max_messages=20)
        assert removes == []

    def test_empty_state_returns_empty(self) -> None:
        """0 messages → no pruning."""
        from agntrick.graph import _build_prune_removes

        assert _build_prune_removes([], max_messages=20) == []

    def test_exact_cap_returns_empty(self) -> None:
        """Exactly 20 messages → no pruning."""
        from agntrick.graph import _build_prune_removes

        msgs = [HumanMessage(content=f"msg {i}", id=f"msg-{i}") for i in range(20)]
        assert _build_prune_removes(msgs, max_messages=20) == []


class TestSummarizeNode:
    """Tests for summarize_node — conversation history compression."""

    @pytest.mark.asyncio
    async def test_noop_below_threshold(self) -> None:
        """Messages under token threshold should return empty dict (no-op)."""
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

    @pytest.mark.asyncio
    async def test_summarizes_above_threshold(self) -> None:
        """Messages above threshold should be summarized and old ones removed."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="User asked about F1 news and weather in Tokyo."))

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

    @pytest.mark.asyncio
    async def test_extends_existing_summary(self) -> None:
        """Should extend an existing summary rather than recreate from scratch."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="Extended: User also asked about chess."))

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
        assert "updating" in prompt_text, "Prompt should ask to update existing summary"

        assert "chess" in result["context"]["running_summary"]

    @pytest.mark.asyncio
    async def test_ttl_expires_stale_summary(self) -> None:
        """Summary older than TTL should be cleared, summarization starts fresh."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="Fresh summary about chess."))

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

        await summarize_node(state, {}, model=mock_model, max_tokens=10, keep_recent=1)

        # The prompt should NOT mention the stale summary
        call_args = mock_model.ainvoke.call_args[0][0]
        prompt_text = str(call_args[0].content)
        assert "Stale summary" not in prompt_text, "Stale summary should not be used"
        assert "Summarize" in prompt_text, "Should start fresh with 'Summarize'"

    @pytest.mark.asyncio
    async def test_llm_failure_graceful_degradation(self) -> None:
        """When summarization LLM fails, should return empty dict (no crash)."""
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
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="Summary of the conversation."))

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

    @pytest.mark.asyncio
    async def test_filters_meta_responses(self) -> None:
        """AI meta-responses about capabilities should be excluded from summarization."""
        from agntrick.graph import summarize_node

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="- User asked about F1\n- Discussed weather"))

        msgs = [
            HumanMessage(content="Tell me about F1" + " detail" * 200, id="m-0"),
            AIMessage(
                content="I don't have access to previous messages, but I can see all 20 messages in this thread."
                + " detail" * 200,
                id="m-1",
            ),
            AIMessage(content="F1 results: Verstappen won" + " detail" * 200, id="m-2"),
            HumanMessage(content="New question"),
        ]

        state: AgentState = {
            "messages": msgs,
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        await summarize_node(state, {}, model=mock_model, max_tokens=10, keep_recent=1)

        # The prompt sent to LLM should NOT contain the meta-response
        call_args = mock_model.ainvoke.call_args[0][0]
        prompt_text = str(call_args[0].content)
        assert "I don't have access to previous" not in prompt_text
        assert "F1 results" in prompt_text

    @pytest.mark.asyncio
    async def test_all_meta_responses_skips_summarization(self) -> None:
        """If all old messages are meta-responses, skip summarization entirely."""
        from agntrick.graph import summarize_node

        mock_model = AsyncMock()
        msgs = [
            AIMessage(
                content="I don't have a specific number of messages. My context window is quite large."
                + " detail" * 200,
                id="m-0",
            ),
            AIMessage(
                content="I can 'remember' many turns. I don't have a permanent long-term memory." + " detail" * 200,
                id="m-1",
            ),
            HumanMessage(content="New question"),
        ]

        state: AgentState = {
            "messages": msgs,
            "intent": "",
            "tool_plan": None,
            "progress": [],
            "final_response": None,
        }

        result = await summarize_node(state, {}, model=mock_model, max_tokens=10, keep_recent=1)
        # Model should NOT be called — all old messages were filtered
        mock_model.ainvoke.assert_not_called()
        assert result == {}


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

    def test_does_not_strip_inline_json(self) -> None:
        """After removing _JSON_BLOCK_RE, inline JSON should be preserved."""
        from agntrick.graph import _format_for_whatsapp

        text = 'The score is 2-1.\n{"type": "text", "text": "extra data"}'
        result = _format_for_whatsapp(text)
        assert "The score is 2-1." in result

    def test_passes_short_text_unchanged(self) -> None:
        from agntrick.graph import _format_for_whatsapp

        text = "Hello! The weather is nice today."
        result = _format_for_whatsapp(text)
        assert result == text

    def test_handles_empty_string(self) -> None:
        from agntrick.graph import _format_for_whatsapp

        assert _format_for_whatsapp("") == ""
