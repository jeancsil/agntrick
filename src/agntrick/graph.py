"""3-node StateGraph for intelligent assistant routing.

Router → Executor → Responder with conditional skip for simple chat.
"""

import json
import logging
import re
import uuid
from typing import Any, Callable, Coroutine, Sequence

from langchain.agents import create_agent
from langchain.agents.middleware.tool_call_limit import ToolCallLimitMiddleware
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
    """Isolate the last user message for the executor sub-agent.

    Sending accumulated history (previous failed attempts) causes the
    sub-agent to repeat failures.  Instead, only send the last HumanMessage
    so the sub-agent starts fresh.

    For the responder node (chat intent), pass through all messages since
    it needs conversation context.
    """
    if not messages:
        return messages

    # Find the last HumanMessage — this is the current query
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return [msg]

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
- "tool_use": Simple factual query that needs one tool call
- "research": Complex multi-step query that needs 2-5 tool calls
- "delegate": Task clearly matches a specialist agent's domain

Respond with JSON only: {"intent": "...", "tool_plan": "...", "delegate_to": null, "skip_tools": false}

Tool selection rules (CRITICAL):
- News, current events, headlines → web_search
- Specific URL to read → web_fetch
- API calls → curl_fetch
- YouTube links → delegate to "youtube"
- Code questions → delegate to "developer"

URL handling rules (CRITICAL):
- "news from a site" or "top news in X" → web_search (search for that site's news)
- "read this URL" or "open this link" → web_fetch (fetch the specific URL)
- If user mentions a site name/URL but asks for NEWS → web_search, NOT web_fetch

For "tool_use": tool_plan = exact tool name, e.g. "web_search"
For "research": tool_plan = numbered steps, e.g. "1. web_search for topic\\n2. web_fetch top result"
For "delegate": tool_plan = agent name + prompt
For "chat": tool_plan = null, skip_tools = true

Examples:
"What's happening in Brazil?" → {"intent": "tool_use", "tool_plan": "web_search", "skip_tools": false}
"What are the top news in g1.globo.com?" → {"intent": "tool_use", "tool_plan": "web_search", "skip_tools": false}
"Read this article: https://..." → {"intent": "tool_use", "tool_plan": "web_fetch", "skip_tools": false}
"Compare React vs Vue" → {"intent": "research", \
"tool_plan": "1. web_search React vs Vue 2026\\n2. web_fetch comparison article", \
"skip_tools": false}
"Good morning" → {"intent": "chat", "tool_plan": null, "skip_tools": true}
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


# Tool names allowed per intent. Reduces the 19-tool set to prevent
# smaller models from getting confused by irrelevant tools.
_INTENT_TOOLS: dict[str, set[str]] = {
    "chat": set(),
    "tool_use": {
        "web_search",
        "web_fetch",
        "curl_fetch",
        "pdf_extract_text",
        "pandoc_convert",
        "invoke_agent",
    },
    "research": {
        "web_search",
        "web_fetch",
        "curl_fetch",
        "pdf_extract_text",
        "pandoc_convert",
        "hacker_news_top",
        "hacker_news_item",
        "invoke_agent",
    },
    "delegate": {"invoke_agent"},
}


def _filter_tools(tools: Sequence[Any], intent: str) -> list[Any]:
    """Filter tools based on intent to reduce model confusion.

    Args:
        tools: All available tools.
        intent: Router's classified intent.

    Returns:
        Filtered list of tools matching the intent, or all tools if
        the intent is unrecognized (safe default).
    """
    allowed = _INTENT_TOOLS.get(intent)
    if allowed is None:
        return list(tools)  # Unknown intent: pass all (safe default)
    if not allowed:
        return []  # chat: no tools
    return [t for t in tools if getattr(t, "name", "") in allowed]


async def router_node(state: AgentState, config: RunnableConfig, *, model: Any) -> dict:
    """Classify intent and decide strategy. Single fast LLM call."""
    last_message = state["messages"][-1]
    query_preview = str(last_message.content)[:200]
    logger.info(f"[router] input: {query_preview}")

    # Only send the last message to the router — it just needs the query
    response = await model.ainvoke(
        [
            SystemMessage(content=ROUTER_PROMPT),
            last_message,
        ],
    )
    parsed = _parse_router_response(response.content)
    intent = parsed.get("intent", "chat")
    tool_plan = parsed.get("tool_plan")
    logger.info(f"[router] output: intent={intent}, plan={str(tool_plan)[:200] if tool_plan else 'None'}")
    return {
        "intent": intent,
        "tool_plan": tool_plan,
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
    intent = state.get("intent", "tool_use")

    guided_prompt = system_prompt
    if tool_plan and intent == "tool_use":
        guided_prompt += f"""

## MANDATORY INSTRUCTION
The router determined this query needs: {tool_plan}

You MUST follow this plan:
1. Use EXACTLY the tool specified above as your FIRST tool call.
2. If the first tool returns data, USE IT to answer. Do NOT call other tools.
3. If the first tool returns an error, try ONE alternative tool.
4. Do NOT call more than 2 tools total.
"""
    elif tool_plan and intent == "research":
        guided_prompt += f"""

## RESEARCH PLAN
Follow this plan step by step:
{tool_plan}

After each tool call, evaluate the result before proceeding.
Maximum 5 tool calls allowed.
"""
    elif tool_plan and intent == "delegate":
        guided_prompt += f"""

## DELEGATION
Use the invoke_agent tool with these parameters:
{tool_plan}

Do NOT use any other tools. Just invoke the agent and return its result.
"""
    elif tool_plan:
        guided_prompt += f"\n\n## TASK PLAN\n{tool_plan}"

    filtered_tools = _filter_tools(tools, intent)

    sub_agent = create_agent(
        model=model,
        tools=filtered_tools,
        system_prompt=guided_prompt,
        checkpointer=InMemorySaver(),
        middleware=[ToolCallLimitMiddleware(run_limit=5, exit_behavior="continue")],
    )

    if progress_callback:
        await progress_callback("Searching for information...")

    try:
        result = await sub_agent.ainvoke(
            {"messages": _truncate_messages(state["messages"])},  # type: ignore[arg-type]
            config={"configurable": {"thread_id": f"executor-{uuid.uuid4().hex}"}},
        )
    except Exception as e:
        logger.warning(f"[executor] sub-agent failed: {e}")
        return {
            "messages": [
                AIMessage(content="I encountered an error while processing your request. Please try again in a moment.")
            ]
        }

    # Log the full sub-agent trace for debugging.
    sub_msgs = result.get("messages", [])
    logger.info(f"[executor] sub-agent produced {len(sub_msgs)} messages")
    for i, msg in enumerate(sub_msgs):
        msg_type = type(msg).__name__
        content = str(msg.content)
        preview = content[:150]
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tools_called = [tc.get("name", "?") for tc in msg.tool_calls]
            logger.info(f"[executor] msg[{i}] {msg_type} tool_calls={tools_called}")
        elif msg_type == "ToolMessage":
            tool_name = getattr(msg, "name", "?")
            logger.info(f"[executor] msg[{i}] {msg_type} name={tool_name} len={len(content)} preview={preview}")
        else:
            logger.info(f"[executor] msg[{i}] {msg_type} len={len(content)} preview={preview}")

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
            logger.warning(f"Responder LLM call failed for chat: {e}")
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
    logger.info(f"[responder] intent={state.get('intent')}, executor output len={len(content)} preview={content[:200]}")
    if len(content) > _MAX_MESSAGE_CHARS:
        content = content[:_MAX_MESSAGE_CHARS] + "\n...[truncated]"

    safe_msgs = _safe_invoke_messages(
        RESPONDER_PROMPT,
        [HumanMessage(content=f"Format this response for WhatsApp:\n\n{content}")],
    )
    try:
        response = await model.ainvoke(safe_msgs)
    except Exception as e:
        logger.warning(f"Responder LLM call failed for tool_use: {e}")
        # Fallback: return raw content, truncated for WhatsApp
        return {
            "final_response": content[:4096],
            "messages": [],
        }

    final = str(response.content)
    logger.info(f"[responder] final_response len={len(final)} preview={final[:300]}")
    return {"final_response": final, "messages": [response]}


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
