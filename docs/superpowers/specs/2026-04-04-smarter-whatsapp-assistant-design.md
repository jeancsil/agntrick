# Smarter WhatsApp Assistant Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan.

**Goal:** Transform the WhatsApp assistant from a single-shot ReAct agent into a stateful, routing-aware conversational agent with memory, smart tool usage, and multi-turn interaction. You must know that before a big refactor of this software, I used to have memory in SQLITE, you msut find code related to that before writting from scractch. At that time, I chose to save by agent the conversation, now , you are free to design the best option, taking into consideration different type of users will use it.

**Architecture:** Three-layer enhancement over the existing AgentBase: (1) SQLite-backed conversation memory via LangGraph checkpoints, (2) a 3-node StateGraph (Router → Executor → Responder) replacing the single ReAct node, (3) rewritten system prompts and tool descriptions optimized for the agent-computer interface.

**Tech Stack:** LangGraph StateGraph, LangGraph checkpoints (SqliteSaver), MCP tools (toolbox), FastAPI, WhatsApp webhook

---

## Current State (Problems)

1. **No memory** — every WhatsApp message creates a fresh agent, runs to completion, returns a string, throws everything away. No conversation continuity.

2. **No routing** — every query hits the same ReAct loop regardless of complexity. Simple "what time is it?" queries waste tokens on full tool orchestration; complex multi-step research queries get no special handling.

3. **No multi-turn** — the agent can't ask clarifying questions or do back-and-forth. It's single-shot: message in, response out.

4. **Tool confusion** — the model has 19 tools but no guidance on which to use when. It fetches the same URL 6 times with different tools (`web_fetch` → `curl_fetch` → `run_shell`), wasting 118s on a simple RSS query.

5. **No progress reporting** — the user sees a typing indicator for 2 minutes with no feedback, then gets a response that says "I couldn't retrieve the data."

## Desired State

A WhatsApp assistant that:
- Remembers previous conversations per phone number
- Routes simple queries directly, uses tools only when needed
- Can execute multi-step research tasks with progress updates
- Uses tools intelligently (one fetch, not six)
- Sends intermediate progress messages for long-running tasks

---

## Layer 1: Conversation Memory

### Design

Use LangGraph's SQLite checkpointer per tenant, scoped by phone number thread.

**Thread ID format:** `whatsapp:{tenant_id}:{phone_number}`

**Storage path:** Reuse existing `StorageConfig.get_tenant_db_path(tenant_id)` — each tenant already has an isolated database.

**What changes:**

1. **whatsapp.py webhook** — Instead of creating a fresh agent per message, the agent maintains conversation state via the checkpointer. The `thread_id` is `{tenant_id}:{phone}`, so each user gets their own conversation thread.

2. **AgentBase** — The `run()` method already accepts `config` with `thread_id` and `checkpointer`. The webhook just needs to pass these through.

3. **Memory compaction** — When context exceeds a threshold (e.g., 80% of context window), the router node triggers compaction: summarize the conversation history, keep the summary + last N messages. This follows Claude Code's auto-compaction pattern.

**Key files:**
- Modify: `src/agntrick/api/routes/whatsapp.py` — Pass checkpointer + thread_id
- Modify: `src/agntrick/agent.py` — Add compaction logic
- No new files needed

### Conversation lifecycle

```
Message 1: "What's in the G1 RSS?"
  → Agent runs with tools, returns response
  → Checkpoint saved with full tool history

Message 2: "Summarize the Iran article"
  → Agent loads checkpoint, sees previous tool results
  → Can reference the article from message 1 without re-fetching

Message 3 (3 days later): "Any news about that?"
  → Agent loads checkpoint, sees summarized history
  → Compaction may have run, keeping key topics
  → Uses "that" context to search for related news
```

---

## Layer 2: Smart Agent Harness (3-Node Graph)

### Design

Replace the current single ReAct node (`create_agent` from LangChain) with a custom LangGraph `StateGraph` with three nodes.

**Current flow:**
```
User message → [ReAct agent with all tools] → Response string
```

**New flow:**
```
User message → [Router] → [Executor] → [Responder] → Response
                  |           |
                  |           +→ Can loop back (multi-step)
                  +→ May skip Executor (simple chat)
                  +→ May delegate to specialist agent (invoke_agent)
```

### State Schema

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str  # "chat" | "tool_use" | "research" | "code"
    tool_plan: str | None  # Router's guidance for tool selection
    progress: list[str]  # Progress messages sent to user
    final_response: str | None
```

### Node 1: Router

**Purpose:** Classify intent and decide strategy.

**Implementation:** Single LLM call with a fast model. Returns:
- `intent`: one of "chat", "tool_use", "research"
- `tool_plan`: for tool_use/research intents, which tools to use and in what order
- `skip_tools`: if true, go directly to Responder

**Router prompt:**
```
You are a query router for a WhatsApp assistant. Classify the user's message:

- "chat": General conversation, greetings, opinions, jokes — no tools needed
- "tool_use": Simple factual query that needs one or two tool calls (weather, definition, single search)
- "delegate": Task clearly matches a specialist agent's domain (code analysis, video transcripts, PR review)
- "research": Complex multi-step query that needs multiple tool calls (news roundup, comparison, analysis)

Respond with JSON: {"intent": "...", "tool_plan": "...", "delegate_to": null, "skip_tools": false}

For "tool_use", tool_plan should specify which single tool to use.
For "delegate", set delegate_to to the agent name and tool_plan to the delegation prompt.
For "research", tool_plan should outline the sequence of tool calls.
For "chat", tool_plan should be null and skip_tools should be true.

Delegation rules:
- Code analysis, debugging, file operations → delegate to "developer"
- YouTube links or video questions → delegate to "youtube"
- PR review requests → delegate to "github-pr-reviewer"
- News queries → handle directly with web_search (don't delegate to news agent)
- Learning/tutorial requests → handle directly or delegate to "learning"
```

**Why this matters:** Research showed Anthropic invests more in tool selection than prompt engineering. The router ensures the model doesn't flail between 19 tools — it gets a focused plan.

### Node 2: Executor

**Purpose:** Execute the ReAct loop with tools, guided by the router's plan.

**Implementation:** This is essentially the current `create_agent` behavior, but with two key differences:
1. The system prompt includes the router's `tool_plan` as tool-selection guidance
2. A streaming callback sends progress messages back to WhatsApp

**Progress messages:** The executor uses LangGraph's `get_stream_writer()` to emit progress events. The webhook layer translates these into WhatsApp intermediate messages.

**Self-correction loop:** If a tool returns an error, the executor's prompt instructs it to try an alternative approach rather than re-fetching with the same tool. This prevents the "fetch same URL 6 times" problem.

### Node 3: Responder

**Purpose:** Format the final response for WhatsApp.

**Implementation:** Single LLM call that:
- Ensures the response is concise (WhatsApp-friendly, under 4096 chars)
- Formats markdown for readability on mobile
- Adds structure (headers, bullet points) for complex answers
- Strips internal tool output artifacts

**Why a separate node:** The raw executor output often contains tool artifacts, overly verbose explanations, or formatting that looks bad on a phone screen. The Responder cleans this up.

### Edge: Direct Chat Path

When the router classifies intent as "chat", the graph skips the Executor entirely:

```
Router → (intent=chat, skip_tools=true) → Responder
```

This saves tokens and latency for simple conversational messages like "good morning" or "thanks".

### Edge: Delegation Path

When the router classifies intent as "delegate", the Executor uses the existing `invoke_agent` tool:

```
Router → (intent=delegate, delegate_to="developer") → Executor (calls invoke_agent) → Responder
```

The Router sets `delegate_to` and `tool_plan` (the delegation prompt), so the Executor knows exactly which agent to invoke and what to ask. No trial-and-error — the Router has already classified the intent.

### Key files:
- Create: `src/agntrick/graph.py` — StateGraph definition, nodes, edges
- Modify: `src/agntrick/agent.py` — Use new graph instead of `create_agent`
- Modify: `src/agntrick/api/routes/whatsapp.py` — Progress message support

---

## Layer 3: Better Prompts & Tool Design

### Design

Rewrite the system prompt and tool descriptions following Anthropic's ACI (agent-computer interface) principles: "Think of it as writing great docstrings for a junior developer."

### System Prompt Rewrite

The current assistant prompt should be restructured to include:

1. **Tool selection guidance** — Explicit rules for when to use each tool:
   ```
   ## TOOL SELECTION RULES

   For current events/news: ALWAYS use web_search first. Never web_fetch a news site directly.
   For specific URL content: Use web_fetch. It returns clean text via Jina Reader.
   For API calls with custom headers: Use curl_fetch.
   For RSS feeds: Use web_fetch (it handles RSS natively).
   For file operations: Use run_shell.
   For searching code: Use ripgrep_search.
   ```

2. **Self-correction instructions**:
   ```
   ## ERROR RECOVERY

   If a tool returns an error:
   1. Read the error message carefully
   2. Try ONE alternative approach (different tool or different parameters)
   3. If it still fails, inform the user what went wrong and what you tried
   4. NEVER retry the exact same call that just failed
   ```

3. **Progress awareness**:
   ```
   ## MULTI-STEP TASKS

   When a task requires multiple tool calls:
   1. Briefly state your plan before starting
   2. Report progress between steps
   3. Synthesize results at the end
   ```

### Tool Description Improvements

In `agntrick-toolkit`, each tool's docstring is the LLM's primary reference. Current docstrings are minimal. They should include:

**Example — web_search:**
```python
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo.

    BEST FOR: Current events, factual questions, finding specific information.
    NOT FOR: Getting content from a specific URL (use web_fetch instead).

    Args:
        query: Search query. Be specific for better results.
            Good: "G1 Brazil news April 2026"
            Bad: "news"
        max_results: Number of results (default 5, max 10).

    Returns:
        Formatted results with titles, URLs, and content snippets.
        Each result contains enough context to answer most questions
        without needing to fetch the full page.
    """
```

**Example — web_fetch:**
```python
async def web_fetch(url: str, timeout: int = 30) -> str:
    """Fetch and extract clean text from a URL using Jina Reader.

    BEST FOR: Reading specific articles, RSS feeds, documentation pages.
    NOT FOR: General searching (use web_search instead).

    IMPORTANT: Responses are truncated at 20KB. If you need specific
    sections of a long page, try fetching section anchors or using
    web_search to find more targeted results.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        Clean text content (markdown). Truncated if > 20KB with
        original size noted.
    """
```

### Key files:
- Modify: `src/agntrick/prompts/assistant.md` — Rewrite system prompt
- Modify: `agntrick-toolkit/src/agntrick_toolbox/tools/web.py` — Improve tool docstrings
- Modify: `agntrick-toolkit/src/agntrick_toolbox/tools/utils.py` — Improve tool docstrings
- Modify: `agntrick-toolkit/src/agntrick_toolbox/tools/shell.py` — Improve tool docstrings

---

## WhatsApp Integration Changes

### Progress Messages

The Go gateway already supports sending intermediate messages (observed in the logs: `"Sent progress message"` with content like "⏳ Still thinking..."). We enhance this:

**New behavior:**
1. Router classification → send "🔍 Analyzing your request..."
2. Tool execution start → send "🔧 Searching for ..."
3. Multi-step tasks → send progress between steps
4. Final response → the actual answer

**Implementation:** The WhatsApp webhook already returns `{"response": str(result)}`. For progress, we add a callback mechanism:
- The graph's `get_stream_writer()` emits custom events
- The webhook layer listens for these and sends intermediate responses via the Go gateway's message endpoint

### Typing Indicator Coordination

The Go gateway already sends typing indicators (`<composing/>`) every 3 seconds. With the new architecture:
- Router runs fast (~1s), typing indicator sufficient
- Executor may take 10-60s, progress messages keep user engaged
- Responder runs fast (~1s), typing indicator sufficient

### Message Size

WhatsApp has a 65,536 character limit per message. The Responder node ensures responses fit within this limit, prioritizing mobile readability with:
- Concise paragraphs
- Bullet points for lists
- Truncated with "read more" hints for very long content

---

## Multi-Agent Delegation (Existing Feature)

The assistant already has multi-agent delegation via `invoke_agent` tool. The Router node enhances this:

**Current delegation flow:**
```
User: "Analyze my auth module"
  → Assistant decides to invoke developer agent
  → invoke_agent({"agent_name": "developer", "prompt": "..."})
  → Fresh developer agent runs, returns result
  → Assistant presents result to user
```

**How the Router improves delegation:**
1. The Router classifies intent → detects it's a code task
2. Instead of the LLM fumbling with `invoke_agent` JSON, the Router suggests the right agent and prompt
3. The Executor follows the plan — direct delegation, no trial-and-error

**Delegatable agents:**
| Agent | Specialty | Tools |
|-------|-----------|-------|
| developer | Code exploration, file ops, technical analysis | toolbox (search, shell) |
| learning | Educational tutorials, step-by-step guides | toolbox |
| news | Current events, breaking stories | toolbox (web, HN) |
| youtube | Video transcript extraction and analysis | toolbox |
| committer | Git commit message generation | local only |
| github-pr-reviewer | GitHub PR review with inline comments | local only |

**Key insight from research:** Anthropic's orchestrator-workers pattern — "the orchestrator dynamically determines which workers to invoke" — is exactly what the Router node does. The existing `invoke_agent` tool is the worker dispatch mechanism. The Router just makes it smarter.

---

## What We're NOT Building (YAGNI)

1. **Vector store / RAG** — Conversation memory via checkpointer is sufficient. Cross-conversation search would need embeddings, but that's a future enhancement.

2. **Safety classifier** — Anthropic uses a separate model to classify tool calls for safety. For a personal assistant, this is unnecessary overhead.

3. **Agent-to-agent protocol** — The ATA/ACP protocols are for multi-vendor agent communication. We have one orchestrator with specialist delegates via `invoke_agent`.

4. **Template messages** — WhatsApp's 24-hour window means free-form messages are fine during active conversations. Template messages for re-engagement are a separate concern.

---

## Implementation Order

1. **Layer 1 (Memory)** — Smallest change, highest immediate impact. Pass checkpointer to webhook agent.
2. **Layer 3 (Prompts)** — Rewrite prompts and tool descriptions. Can be done independently.
3. **Layer 2 (Graph)** — The biggest change. Build the 3-node graph, integrate with webhook, add progress messages.

Layers 1 and 3 can be done in parallel. Layer 2 depends on Layer 1 (memory) being in place.

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Simple query latency | 5-15s | <5s (router skips tools) |
| Complex query latency | 60-120s | <45s (guided tool plan) |
| Redundant tool calls | 6 per query | <2 per query |
| Conversation continuity | None | Multi-session memory |
| User satisfaction signal | "I can't retrieve..." | Correct answers with context |
