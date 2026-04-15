"""3-node StateGraph for intelligent assistant routing.

Router → Executor → Responder with conditional skip for simple chat.
"""

import json
import logging
import re
import time
import uuid
from typing import Any, Callable, Coroutine, Sequence

from langchain.agents import create_agent
from langchain.agents.middleware.tool_call_limit import ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately
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

# Character budget for router context (~1K tokens — router only classifies intent)
_ROUTER_CONTEXT_BUDGET = 4_000

# Character budget for responder chat context (~2K tokens — responder needs richer context)
_RESPONDER_CHAT_BUDGET = 8_000

# Hard ceiling on number of messages in window (prevents 100+ tiny messages)
_MAX_WINDOW_MESSAGES = 20

# Maximum messages retained in checkpointer state.
# Prunes the oldest messages when exceeded — prevents unbounded token waste.
# Lowered to 10 (from 20) to keep context tight for WhatsApp where
# RemoveMessage doesn't persist in AsyncSqliteSaver.
_MAX_STATE_MESSAGES = 10

# Intent-specific tool call limits to prevent tool usage spirals.
_INTENT_TOOL_LIMITS: dict[str, int] = {
    "tool_use": 1,  # single call — speed > perfection for WhatsApp
    "research": 5,  # multi-step research
    "delegate": 1,  # single agent invocation
}
_DEFAULT_TOOL_LIMIT = 3

# Regex to strip XML-style pseudo-tool-call artifacts that some models (e.g.
# glm-4.7) emit as plain text instead of proper structured tool_calls.
# Matches tags like <web_search query="..."/>, <tool_call name="foo">...</tool_call, etc.
_TOOL_ARTIFACT_RE = re.compile(
    r"\n*"
    r"<(?:web_search|tool_call|invoke|execute|function_call)\b[^>]*"
    r"(?:"
    r"/>?"  # self-closing or bare open tag (no body)
    r"|"
    r">.*?"  # opening tag with body...
    r"</(?:web_search|tool_call|invoke|execute|function_call)\b[^>]*>?"  # ...closing tag
    r")",
    re.DOTALL,
)


def _sanitize_ai_content(content: str) -> str:
    """Strip XML-style tool call artifacts from AIMessage content.

    Some LLMs (notably glm-4.7) emit pseudo-tool-calls as raw text like
    ``<web_search query="..."/>`` instead of using the structured tool_call
    API.  Left unchecked, these tags pollute the conversation history and get
    fed back to the model on every turn, confusing it further.

    Args:
        content: Raw AIMessage content string.

    Returns:
        Cleaned content with tool artifacts removed.
    """
    cleaned = _TOOL_ARTIFACT_RE.sub("", content).strip()
    if cleaned != content:
        logger.info("[sanitize] stripped tool artifact from AIMessage (%d → %d chars)", len(content), len(cleaned))
    return cleaned


_WHATSAPP_CHAR_LIMIT = 4096

# Regex to strip raw JSON content blocks from tool output
_JSON_BLOCK_RE = re.compile(r"\n?\{[^{}]*\}(?=\n|$)", re.MULTILINE)


def _format_for_whatsapp(content: str) -> str:
    """Format agent output for WhatsApp without an LLM call.

    Strips tool artifacts, raw JSON, and truncates to WhatsApp char limit.

    Args:
        content: Raw agent response text.

    Returns:
        WhatsApp-friendly formatted string (max 4096 chars).
    """
    if not content:
        return content

    # Strip XML tool artifacts
    cleaned = _sanitize_ai_content(content)

    # Strip raw JSON content blocks (e.g., {"type": "text", "text": "..."})
    cleaned = _JSON_BLOCK_RE.sub("", cleaned).strip()

    # Truncate to WhatsApp limit
    if len(cleaned) > _WHATSAPP_CHAR_LIMIT:
        cleaned = cleaned[: _WHATSAPP_CHAR_LIMIT - 3] + "..."

    return cleaned


async def _log_llm_call(
    model: Any,
    messages: list,
    *,
    node: str,
) -> Any:
    """Wrap model.ainvoke() with timing and size logging."""
    input_msgs = len(messages)
    input_chars = sum(len(str(m.content)) for m in messages if hasattr(m, "content"))
    logger.debug(f"[llm] node={node} input_msgs={input_msgs} input_chars={input_chars}")
    start = time.monotonic()
    response = await model.ainvoke(messages)
    elapsed = time.monotonic() - start
    output_chars = len(str(response.content)) if hasattr(response, "content") else 0
    logger.info(f"[llm] node={node} output_chars={output_chars} elapsed={elapsed:.1f}s")
    return response


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


def _budget_window_messages(
    messages: list[BaseMessage],
    max_chars: int,
    max_messages: int = _MAX_WINDOW_MESSAGES,
) -> list[BaseMessage]:
    """Keep messages within a cumulative character budget.

    Walks backward from the most recent message, accumulating character count
    until the budget is exceeded. Always includes at least the last message.

    Args:
        messages: Full message history.
        max_chars: Maximum cumulative character budget.
        max_messages: Hard ceiling on message count (prevents many tiny messages).

    Returns:
        List of messages fitting within budget (up to max_messages).
    """
    if not messages:
        return messages
    total_chars = 0
    count = 0
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        msg_chars = len(str(msg.content))
        if count > 0 and total_chars + msg_chars > max_chars:
            break
        if count >= max_messages:
            break
        total_chars += msg_chars
        count += 1
    return messages[-count:] if count > 0 else messages[-1:]


def _build_prune_removes(
    messages: list[BaseMessage],
    max_messages: int,
) -> list[RemoveMessage]:
    """Return RemoveMessage objects for messages beyond the cap.

    Keeps the most recent ``max_messages`` and marks older ones for
    removal via the ``add_messages`` reducer.

    Args:
        messages: Current state messages (all have IDs from the reducer).
        max_messages: Maximum messages to retain in state.

    Returns:
        List of RemoveMessage for messages to prune. Empty if within cap.
    """
    if len(messages) <= max_messages:
        return []
    to_remove = messages[:-max_messages]
    return [RemoveMessage(id=m.id) for m in to_remove if m.id is not None]


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
- Paywalled or blocked URL → delegate to "paywall-remover"
- API calls → curl_fetch
- YouTube links → delegate to "youtube"
- Code questions → delegate to "developer"

URL handling rules (CRITICAL):
- "news from a site" or "top news in X" → web_search (search for that site's news)
- "read this URL" or "open this link" → web_fetch (fetch the specific URL)
- Paywalled/blocked site (globo.com, wsj.com, nyt.com, etc.) or user says
  "extract" or "remove paywall" → delegate to "paywall-remover"
- If user mentions a site name/URL but asks for NEWS → web_search, NOT web_fetch

For "tool_use": tool_plan = exact tool name, e.g. "web_search"
For "research": tool_plan = numbered steps, e.g. "1. web_search for topic\\n2. web_fetch top result"
For "delegate": tool_plan = agent name + prompt
For "chat": tool_plan = null, skip_tools = true

Examples:
"What's happening in Brazil?" → {"intent": "tool_use", "tool_plan": "web_search", "skip_tools": false}
"What are the top news in g1.globo.com?" → {"intent": "tool_use", \
"tool_plan": "web_search", "skip_tools": false}
"Read this article: https://..." → {"intent": "tool_use", "tool_plan": "web_fetch", "skip_tools": false}
"Extract content from https://globo.com/..." → {"intent": "delegate", \
"tool_plan": "paywall-remover", "skip_tools": false}
"Remove paywall from https://wsj.com/..." → {"intent": "delegate", \
"tool_plan": "paywall-remover", "skip_tools": false}
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
    context: dict[str, Any]


# Token threshold above which summarization is triggered.
# 500 tokens ≈ 10-12 short WhatsApp messages — triggers early compression
# before context bloats and slows every LLM call.
_SUMMARIZE_TOKEN_THRESHOLD = 500

# Number of most-recent messages to keep unsummarized.
_SUMMARIZE_KEEP_RECENT = 2

# Maximum tokens for the summary output.
_SUMMARY_MAX_TOKENS = 128

# Hours after which a running summary is considered stale and cleared.
_SUMMARY_TTL_HOURS = 24


async def summarize_node(
    state: AgentState,
    config: RunnableConfig,
    *,
    model: Any,
    max_tokens: int = _SUMMARIZE_TOKEN_THRESHOLD,
    keep_recent: int = _SUMMARIZE_KEEP_RECENT,
    summary_max_tokens: int = _SUMMARY_MAX_TOKENS,
    ttl_hours: int = _SUMMARY_TTL_HOURS,
) -> dict:
    """Compress old conversation messages into a running summary.

    Checks token count of messages in state. If below threshold, returns
    empty dict (no-op). If above, uses the LLM to summarize older messages
    into a compact running summary stored in ``state["context"]``.

    Args:
        state: Current graph state with messages and optional context.
        config: LangGraph runnable config.
        model: LLM model for summarization.
        max_tokens: Token threshold to trigger summarization.
        keep_recent: Number of recent messages to keep unsummarized.
        summary_max_tokens: Max tokens for the summary LLM output.
        ttl_hours: Hours before a summary is considered stale.

    Returns:
        Dict with updated context and optional RemoveMessage directives.
        Empty dict if no summarization needed (no-op).
    """
    messages = state.get("messages", [])
    if not messages:
        logger.debug("[summarize] no messages, skipping")
        return {}

    token_count = count_tokens_approximately(messages)
    if token_count < max_tokens:
        logger.debug(
            "[summarize] below threshold (%d < %d tokens), skipping",
            token_count,
            max_tokens,
        )
        return {}

    # Split messages: old ones to summarize vs recent to keep
    split_index = max(0, len(messages) - keep_recent)
    old_messages = messages[:split_index]

    if not old_messages:
        logger.debug("[summarize] no old messages to compress, skipping")
        return {}

    # Filter out AI meta-responses (self-referential messages about capabilities)
    _META_PATTERNS = (
        "i don't have access to previous",
        "i can see all",
        "my context window",
        "i don't have a permanent",
        "i don't have a specific number",
        'i can "remember"',
        "tokens i can process",
    )

    def _is_meta_response(msg: BaseMessage) -> bool:
        if not isinstance(msg, AIMessage):
            return False
        content_lower = str(msg.content).lower()
        return any(p in content_lower for p in _META_PATTERNS)

    filtered_messages = [m for m in old_messages if not _is_meta_response(m)]
    if len(filtered_messages) < len(old_messages):
        logger.info(
            "[summarize] filtered %d meta-responses from %d old messages",
            len(old_messages) - len(filtered_messages),
            len(old_messages),
        )
    if not filtered_messages:
        logger.info("[summarize] all old messages were meta-responses, skipping")
        return {}

    # Build summarization prompt
    existing_summary = state.get("context", {}).get("running_summary")
    summary_age = state.get("context", {}).get("summary_updated_at", 0.0)

    # TTL check: clear stale summary
    if existing_summary and (time.time() - summary_age) > ttl_hours * 3600:
        logger.info("[summarize] TTL expired, clearing stale summary")
        existing_summary = None

    # Build the content to summarize (using filtered messages)
    old_content = "\n".join(f"{type(m).__name__}: {str(m.content)[:500]}" for m in filtered_messages)

    if existing_summary:
        prompt = (
            f"You are updating a conversation summary. Add the key information "
            f"from the new messages below to the existing summary.\n\n"
            f"Rules:\n"
            f"- Output ONLY the updated summary, nothing else\n"
            f"- Keep it under {summary_max_tokens} tokens\n"
            f"- Focus on: topics discussed, facts learned, user preferences, "
            f"decisions made, actions taken\n"
            f"- Do NOT include meta-commentary about your capabilities\n\n"
            f"Existing summary:\n{existing_summary}\n\n"
            f"New messages:\n{old_content}"
        )
    else:
        prompt = (
            f"Summarize this conversation in bullet points.\n\n"
            f"Rules:\n"
            f"- Output ONLY the summary, nothing else\n"
            f"- Keep it under {summary_max_tokens} tokens\n"
            f"- Include: topics discussed, facts learned, user preferences, "
            f"decisions made, actions taken\n"
            f"- Do NOT include meta-commentary about AI capabilities\n\n"
            f"Messages:\n{old_content}"
        )

    # Call LLM for summarization
    try:
        response = await model.ainvoke([HumanMessage(content=prompt)])
        new_summary = str(response.content).strip()
    except Exception as e:
        logger.warning("[summarize] LLM summarization failed: %s", e)
        return {}

    # Build RemoveMessage directives for ALL old messages (including filtered ones)
    removes = [RemoveMessage(id=m.id) for m in old_messages if m.id is not None]

    logger.info(
        "[summarize] compressed %d messages (%d tokens) into %d-char summary",
        len(old_messages),
        token_count,
        len(new_summary),
    )

    return {
        "messages": removes,
        "context": {
            "running_summary": new_summary,
            "summary_updated_at": time.time(),
        },
    }


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
    },
    "research": {
        "web_search",
        "web_fetch",
        "curl_fetch",
        "pdf_extract_text",
        "pandoc_convert",
        "hacker_news_top",
        "hacker_news_item",
    },
    "delegate": {"invoke_agent"},
}


def _flatten_tool_content(content: Any) -> str:
    """Flatten structured MCP content to a plain string.

    MCP tools return ``[{"type": "text", "text": "..."}]`` content blocks.
    Models like GLM-5.1 don't parse this format — they see the dict wrappers
    as opaque and respond "can't access results". This extracts the plain text.
    """
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts) if parts else str(content)
    return str(content)


def _make_flat_tool(tool: Any) -> Any:
    """Wrap an MCP tool so ``ainvoke`` returns plain strings.

    MCP tools return ``[{"type": "text", "text": "..."}]`` content blocks.
    Models like GLM-5.1 don't parse this — they see the dict wrappers as opaque.
    This creates a new StructuredTool with the same schema but plain-string output.
    """
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel

    # Skip wrapping for mock/fake tools (tests) or tools without real attributes
    if not hasattr(tool, "name") or not isinstance(tool.name, str):
        return tool
    schema = getattr(tool, "args_schema", None)
    if schema is None or not ((isinstance(schema, type) and issubclass(schema, BaseModel)) or isinstance(schema, dict)):
        return tool

    original_ainvoke = tool.ainvoke
    flatten = _flatten_tool_content

    async def _coro(**kwargs: Any) -> str:
        result = await original_ainvoke(kwargs)
        return flatten(result)

    st_kwargs: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description if isinstance(tool.description, str) else "",
        "func": lambda *a, **kw: "sync-only-stub",
        "coroutine": _coro,
    }
    schema = getattr(tool, "args_schema", None)
    if schema is not None and (
        (isinstance(schema, type) and issubclass(schema, BaseModel)) or isinstance(schema, dict)
    ):
        st_kwargs["args_schema"] = schema

    return StructuredTool(**st_kwargs)


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
    # Send a budget-based window of recent messages so the router can understand
    # follow-up questions (e.g. "yes", "and in Paris?") that need context.
    context_window = _budget_window_messages(state["messages"], _ROUTER_CONTEXT_BUDGET)
    last_message = state["messages"][-1]
    query_preview = str(last_message.content)[:200]
    logger.info(
        "[router] input: %s messages in window, last: %s",
        len(context_window),
        query_preview,
    )

    # Inject running summary as context prefix if available
    summary = state.get("context", {}).get("running_summary")
    if summary:
        context_window = [
            SystemMessage(content=f"Previous conversation summary: {summary}"),
            *context_window,
        ]

    response = await _log_llm_call(
        model,
        [SystemMessage(content=ROUTER_PROMPT), *context_window],
        node="router",
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
        # Use a focused minimal prompt for tool_use — the full assistant.md
        # system prompt contradicts "call once" with "Maximum 2-3 tool calls"
        # (assistant.md line 37), causing the model to ignore the limit.
        # A standalone prompt eliminates the contradiction entirely.
        guided_prompt = (
            "You are a helpful assistant. Answer the user's question using the tool below.\n\n"
            f"## YOUR TASK\n"
            f"Call `{tool_plan}` exactly ONCE, then respond to the user immediately.\n\n"
            f"## STRICT RULES\n"
            f"- You may call `{tool_plan}` exactly ONE time. No exceptions.\n"
            f"- After the tool returns data, respond to the user with that data. Do NOT call the tool again.\n"
            f"- After the tool returns an error, explain the issue. Do NOT call the tool again.\n"
            f"- NEVER say 'unable to retrieve' if the tool returned data.\n"
            f"- Respond in the same language as the user.\n"
        )
    elif tool_plan and intent == "research":
        guided_prompt += f"""

## RESEARCH PLAN
Follow this plan step by step:
{tool_plan}

After each tool call, evaluate:
- Can I answer the user's question with this data? If YES, stop and respond.
- Do I need more data? If YES, continue to the next step.
Maximum 5 tool calls allowed.
"""
    elif tool_plan and intent == "delegate":
        guided_prompt += f"""

## DELEGATION
Call the invoke_agent tool with input_str set to a JSON string like this:
{{"agent_name": "{tool_plan}", "prompt": "<full task description with all context>"}}

The prompt field must contain everything the agent needs — it has no memory.
Do NOT use any other tools. Just invoke the agent and return its result.
If the agent returns an error or times out, respond to the user with the error.
NEVER retry invoke_agent on failure — you only get ONE attempt.
"""
    elif tool_plan:
        guided_prompt += f"\n\n## TASK PLAN\n{tool_plan}"

    # For tool_use, narrow tools to only the one the router selected.
    # Giving the LLM 5 tools causes it to waste calls on irrelevant ones
    # (e.g. calling web_fetch after web_search instead of responding).
    if intent == "tool_use" and tool_plan and tool_plan in {getattr(t, "name", "") for t in tools}:
        filtered_tools = [t for t in tools if getattr(t, "name", "") == tool_plan]
    else:
        filtered_tools = _filter_tools(tools, intent)

    tool_limit = _INTENT_TOOL_LIMITS.get(intent, _DEFAULT_TOOL_LIMIT)
    tool_names = [getattr(t, "name", "?") for t in filtered_tools]
    logger.info(f"[executor] intent={intent} tool_limit={tool_limit} filtered_tools={tool_names}")

    # Flatten MCP tool output to plain strings. MCP tools return structured
    # content blocks ([{"type": "text", "text": "..."}]) but GLM-5.1 and
    # similar models don't parse this — they see the dict wrappers as opaque
    # and respond "can't access results" despite having good data.
    # Wrap tools to return plain strings instead of structured MCP content
    # blocks. GLM-5.1 and similar models treat [{"type":"text","text":"..."}]
    # as opaque, causing "can't access results" errors.
    filtered_tools = [_make_flat_tool(t) for t in filtered_tools]

    sub_agent = create_agent(
        model=model,
        tools=filtered_tools,
        system_prompt=guided_prompt,
        checkpointer=InMemorySaver(),
        middleware=[ToolCallLimitMiddleware(run_limit=tool_limit, exit_behavior="continue")],
    )

    if progress_callback:
        await progress_callback("Searching for information...")

    try:
        # For tool_use, include a few recent messages so follow-up queries
        # like "what about the score now?" retain context about which game.
        # For other intents, use the original single-message isolation.
        if intent == "tool_use":
            # Budget 2K chars / 4 messages — enough for the last exchange
            executor_msgs = _budget_window_messages(state["messages"], 2_000, max_messages=4)
            # Filter to types the sub-agent can handle (no ToolMessage etc.)
            executor_msgs = [m for m in executor_msgs if isinstance(m, (HumanMessage, AIMessage))]
        else:
            executor_msgs = _truncate_messages(state["messages"])

        result = await sub_agent.ainvoke(
            {"messages": executor_msgs},  # type: ignore[arg-type]
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

    # Sanitize any XML-style tool artifacts the model may have emitted
    # as text instead of structured tool_calls (e.g. <web_search query="..."/>).
    if isinstance(final_msg, AIMessage) and isinstance(final_msg.content, str):
        sanitized = _sanitize_ai_content(final_msg.content)
        if sanitized != final_msg.content:
            final_msg = AIMessage(
                content=sanitized,
                additional_kwargs=final_msg.additional_kwargs,
                response_metadata=final_msg.response_metadata,
                id=final_msg.id,
            )

    return {"messages": [final_msg]}


async def responder_node(state: AgentState, config: RunnableConfig, *, model: Any) -> dict:
    """Format the final response for WhatsApp.

    For chat intent: the responder IS the response node (router classified
    no tools needed), so it returns its AIMessage in ``messages`` to persist
    in the conversation state.

    For tool_use/research/delegate intents: the executor already added its
    AIMessage to state. The responder only formats it for WhatsApp output
    via ``final_response`` — it must NOT append another AIMessage to state,
    as that would create a duplicate and bloat the conversation history.

    Uses _safe_invoke_messages to ensure the GLM API always receives
    a valid message sequence (SystemMessage + at least one HumanMessage).
    """
    # Compute pruning once — applies to all return paths.
    removes = _build_prune_removes(state["messages"], _MAX_STATE_MESSAGES)

    if state.get("intent") == "chat":
        msgs = _budget_window_messages(state["messages"], _RESPONDER_CHAT_BUDGET)
        logger.debug(
            "[responder] chat intent: %d messages, types=%s",
            len(msgs),
            [type(m).__name__ for m in msgs],
        )

        # Inject running summary as context if available
        prompt = RESPONDER_PROMPT
        summary = state.get("context", {}).get("running_summary")
        if summary:
            prompt = f"Previous conversation summary: {summary}\n\n{RESPONDER_PROMPT}"

        safe_msgs = _safe_invoke_messages(prompt, msgs)
        try:
            response = await _log_llm_call(model, safe_msgs, node="responder-chat")
        except Exception as e:
            logger.warning(f"Responder LLM call failed for chat: {e}")
            # Fallback: return the last message content directly
            last = state["messages"][-1] if state["messages"] else None
            return {
                "final_response": str(last.content) if last else "Sorry, please try again.",
                "messages": removes,
            }
        return {"final_response": str(response.content), "messages": [response] + removes}

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
        response = await _log_llm_call(model, safe_msgs, node="responder-tool")
    except Exception as e:
        logger.warning(f"Responder LLM call failed for tool_use: {e}")
        # Fallback: return raw content, truncated for WhatsApp
        return {
            "final_response": content[:4096],
            "messages": removes,
        }

    final = str(response.content)
    logger.info(f"[responder] final_response len={len(final)} preview={final[:300]}")
    return {"final_response": final, "messages": removes}


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

    async def _summarize(state: AgentState, config: RunnableConfig) -> dict:
        return await summarize_node(state, config, model=model)

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
    graph.add_node("summarize", _summarize)
    graph.add_node("router", _router)
    graph.add_node("executor", _executor)
    graph.add_node("responder", _responder)
    graph.set_entry_point("summarize")
    graph.add_edge("summarize", "router")
    graph.add_conditional_edges(
        "router",
        route_decision,
        {"executor": "executor", "responder": "responder"},
    )
    graph.add_edge("executor", "responder")
    graph.add_edge("responder", END)

    return graph.compile(checkpointer=checkpointer or InMemorySaver())
