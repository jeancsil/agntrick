"""3-node StateGraph for intelligent assistant routing.

Router → Executor → Responder with conditional skip for simple chat.
"""

import json
import logging
import re
from typing import Any, Callable, Coroutine, Sequence

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict

logger = logging.getLogger(__name__)

# Type for progress callback
ProgressCallback = Callable[[str], Coroutine[Any, Any, None]] | None

# Maximum chars of message content to send to the LLM to avoid 400 errors
_MAX_MESSAGE_CHARS = 15_000


def _truncate_messages(
    messages: list[BaseMessage],
    max_chars: int = _MAX_MESSAGE_CHARS,
) -> list[BaseMessage]:
    """Truncate long messages to keep total content within limits.

    TEMPORARILY DISABLED — pass through all messages unchanged while
    diagnosing truncation issues that cause the LLM to misinterpret
    tool responses as failures.
    """
    return messages


def _safe_invoke_messages(
    system_prompt: str,
    messages: list[BaseMessage],
) -> list[BaseMessage]:
    """Build a safe message list for the LLM API.

    The GLM/z.ai API (error 1214) rejects messages arrays that:
    - Contain only SystemMessage (no user message)
    - Contain consecutive SystemMessage objects

    This function ensures the output always has exactly one SystemMessage
    followed by at least one non-SystemMessage (HumanMessage or AIMessage).
    """
    if not messages:
        # No messages — add a minimal human prompt
        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content="Please respond."),
        ]

    # Keep only HumanMessage/AIMessage — GLM API rejects ToolMessage,
    # SystemMessage, and other types in chat completions.
    safe = [m for m in messages if isinstance(m, (HumanMessage, AIMessage))]

    if not safe:
        # No valid user/assistant messages — add a minimal human prompt
        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content="Please respond."),
        ]

    return [SystemMessage(content=system_prompt), *safe]


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

Tool selection rules (CRITICAL — follow these strictly):
- News, current events, headlines → ALWAYS use web_search FIRST. Do NOT use web_fetch for news/RSS URLs.
- Specific URL content the user wants to read → use web_fetch
- RSS/feed URLs → use web_search to find the same content (direct fetch often fails)
- API calls with custom headers → use curl_fetch
- YouTube links → "youtube" agent
- General web queries → web_search

Delegation rules:
- Code analysis, debugging, file operations → "developer"
- YouTube links or video questions → "youtube"
- PR review requests → "github-pr-reviewer"
- News queries → handle directly with web_search (do NOT delegate)
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


class AgentState(TypedDict, total=False):
    """State flowing through the 3-node graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    intent: str
    tool_plan: str | None
    progress: list[str]
    final_response: str | None


def _parse_router_response(content: str) -> dict[str, Any]:
    """Parse JSON from router LLM response, with fallback."""
    try:
        result: dict[str, Any] = json.loads(content)
        return result
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                parsed: dict[str, Any] = json.loads(match.group())
                return parsed
            except json.JSONDecodeError:
                pass
        return {"intent": "chat", "tool_plan": None, "skip_tools": True}


async def router_node(state: AgentState, config: RunnableConfig, *, model: Any) -> dict:
    """Classify intent and decide strategy. Single fast LLM call."""
    last_message = state["messages"][-1]
    # Only send the last message to the router — it just needs the query
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
    config: RunnableConfig,
    *,
    model: Any,
    tools: Sequence[Any],
    system_prompt: str,
    progress_callback: ProgressCallback = None,
) -> dict:
    """Execute tool calls guided by the router's plan."""
    if progress_callback:
        await progress_callback("Analyzing your request...")

    tool_plan = state.get("tool_plan")

    guided_prompt = system_prompt
    if tool_plan:
        guided_prompt += f"\n\n## CURRENT TASK PLAN\n{tool_plan}"

    sub_agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=guided_prompt,
        checkpointer=InMemorySaver(),
    )

    if progress_callback:
        await progress_callback("Searching for information...")

    try:
        result = await sub_agent.ainvoke(
            {"messages": _truncate_messages(state["messages"])},  # type: ignore[arg-type]
            config={"configurable": {"thread_id": "executor"}},
        )
    except Exception as e:
        logger.warning("Executor sub-agent failed: %s", e)
        return {
            "messages": [
                AIMessage(content="I encountered an error while processing your request. Please try again in a moment.")
            ]
        }

    if progress_callback:
        await progress_callback("Formatting response...")

    # Only return the final assistant message from the sub-agent.
    # Tool call/response messages are sub-agent internals that should
    # not leak into the main graph's state (they lack matching tool_call_ids
    # in the main graph, causing KeyError in add_messages).
    final_msg = result["messages"][-1]
    return {"messages": [final_msg]}


async def responder_node(state: AgentState, config: RunnableConfig, *, model: Any) -> dict:
    """Format the final response for WhatsApp.

    Uses _safe_invoke_messages to ensure the GLM API always receives
    a valid message sequence (SystemMessage + at least one HumanMessage).
    """
    if state.get("intent") == "chat":
        msgs = _truncate_messages(state["messages"])
        safe_msgs = _safe_invoke_messages(RESPONDER_PROMPT, msgs)
        try:
            response = await model.ainvoke(safe_msgs)
        except Exception as e:
            logger.warning("Responder LLM call failed for chat: %s", e)
            # Fallback: return the last message content directly
            last = state["messages"][-1] if state["messages"] else None
            return {
                "final_response": str(last.content) if last else "Sorry, please try again.",
                "messages": [],
            }
        return {"final_response": str(response.content), "messages": [response]}

    # tool_use / research / delegate intent — format executor output
    last_msg = state["messages"][-1]
    content = str(last_msg.content)
    if len(content) > _MAX_MESSAGE_CHARS:
        content = content[:_MAX_MESSAGE_CHARS] + "\n...[truncated]"

    safe_msgs = _safe_invoke_messages(
        RESPONDER_PROMPT,
        [HumanMessage(content=f"Format this response for WhatsApp:\n\n{content}")],
    )
    try:
        response = await model.ainvoke(safe_msgs)
    except Exception as e:
        logger.warning("Responder LLM call failed for tool_use: %s", e)
        # Fallback: return raw content, truncated for WhatsApp
        return {
            "final_response": content[:4096],
            "messages": [],
        }

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
    progress_callback: ProgressCallback = None,
) -> Any:
    """Create the 3-node assistant StateGraph.

    Args:
        model: LLM model instance.
        tools: Sequence of tools available to the executor.
        system_prompt: Base system prompt for the agent.
        checkpointer: Optional checkpointer for persistent memory.
        progress_callback: Optional async callback for progress updates.

    Returns:
        Compiled StateGraph ready for ainvoke().
    """

    async def _router(state: AgentState, config: RunnableConfig) -> dict:
        return await router_node(state, config, model=model)

    async def _executor(state: AgentState, config: RunnableConfig) -> dict:
        return await executor_node(
            state,
            config,
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            progress_callback=progress_callback,
        )

    async def _responder(state: AgentState, config: RunnableConfig) -> dict:
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
