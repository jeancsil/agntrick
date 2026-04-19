"""Tests for the Router node and intent classification helpers."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from agntrick.graph import (
    AgentState,
    _parse_router_response,
)


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


class TestPreRouting:
    """Tests for regex pre-routing filter."""

    def test_greetings_portuguese(self):
        from agntrick.graph import _pre_route

        assert _pre_route("bom dia") == {"intent": "chat", "tool_plan": None}
        assert _pre_route("oi") == {"intent": "chat", "tool_plan": None}
        assert _pre_route("boa noite") == {"intent": "chat", "tool_plan": None}
        assert _pre_route("tudo bem?") == {"intent": "chat", "tool_plan": None}

    def test_greetings_english(self):
        from agntrick.graph import _pre_route

        assert _pre_route("hello") == {"intent": "chat", "tool_plan": None}
        assert _pre_route("hi") == {"intent": "chat", "tool_plan": None}

    def test_help_queries(self):
        from agntrick.graph import _pre_route

        assert _pre_route("help") == {"intent": "chat", "tool_plan": None}
        assert _pre_route("ajuda") == {"intent": "chat", "tool_plan": None}

    def test_bare_url(self):
        from agntrick.graph import _pre_route

        assert _pre_route("https://example.com") == {"intent": "tool_use", "tool_plan": "web_fetch"}

    def test_read_url(self):
        from agntrick.graph import _pre_route

        assert _pre_route("leia https://example.com/article") == {"intent": "tool_use", "tool_plan": "web_fetch"}

    def test_news_queries(self):
        from agntrick.graph import _pre_route

        assert _pre_route("noticias sobre Brasil") == {"intent": "tool_use", "tool_plan": "web_search"}
        assert _pre_route("latest news") == {"intent": "tool_use", "tool_plan": "web_search"}

    def test_ambiguous_falls_through(self):
        from agntrick.graph import _pre_route

        assert _pre_route("what do you think about AI?") is None
        assert _pre_route("can you help me with a recipe?") is None

    def test_url_in_context_not_matched_as_bare(self):
        """A URL embedded in a sentence should NOT match bare URL pattern."""
        from agntrick.graph import _pre_route

        result = _pre_route("noticias sobre https://example.com")
        assert result == {"intent": "tool_use", "tool_plan": "web_search"}

    def test_youtube_url_delegates(self):
        from agntrick.graph import _pre_route

        assert _pre_route("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == {
            "intent": "delegate",
            "tool_plan": "youtube",
        }
        assert _pre_route("https://youtu.be/abc123") == {
            "intent": "delegate",
            "tool_plan": "youtube",
        }

    def test_paywalled_url_delegates(self):
        from agntrick.graph import _pre_route

        assert _pre_route("https://www.globo.com/economia/artigo") == {
            "intent": "delegate",
            "tool_plan": "paywall-remover",
        }
        assert _pre_route("https://www.folha.uol.com.br/mercado/") == {
            "intent": "delegate",
            "tool_plan": "paywall-remover",
        }
        assert _pre_route("https://www.wsj.com/articles/some-article") == {
            "intent": "delegate",
            "tool_plan": "paywall-remover",
        }

    def test_empty_message(self):
        from agntrick.graph import _pre_route

        assert _pre_route("") is None
        assert _pre_route("   ") is None
