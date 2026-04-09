# Paywall Remover Agent — Design Spec

**Date:** 2026-04-08
**Status:** Approved

## Problem

The `WebExtractorTool` was registered as a local tool on the `AssistantAgent`, but the graph's routing pipeline doesn't surface local tools to the router/executor properly. The assistant needs a way to extract content from paywalled and bot-protected sites (globo.com, wsj.com, nyt.com, etc.) that `web_fetch` can't handle.

## Solution

Create a dedicated `paywall-remover` agent that owns the `WebExtractorTool` and is reachable via the existing delegation pipeline (like `youtube`, `br-news`). This sidesteps the graph routing complexity entirely.

## Architecture

### Agent: `paywall-remover`

Mirrors the `youtube` agent pattern — a specialist agent with `WebExtractorTool` as its local tool.

```
User → Assistant → (delegates) → paywall-remover → WebExtractorTool (3-stage pipeline)
```

### 3-Stage Extraction Pipeline

The `WebExtractorTool` (already built) cascades through:

1. **Crawl4AI** — Playwright-based headless browser (local, free, fast). Handles JS rendering, basic anti-bot. Covers ~80% of cases.
2. **Firecrawl API** — Credit-based REST API. Handles Cloudflare/turnstile/hard anti-bot. High success on tough sites.
3. **Archive.ph** — Free archived snapshots. Last resort for cached content.

Each stage returns a `WebContentResult` with status, content, and metadata. The pipeline stops at first success.

### Delegation Triggers

The assistant delegates to `paywall-remover` when:

1. **User explicitly asks** — "remove paywall https://...", "extract from https://..."
2. **Known paywalled site** — globo.com, wsj.com, nyt.com, ft.com, etc.
3. **Fallback** — `web_fetch` failed or returned insufficient content

## Files

| File | Action | Purpose |
|------|--------|---------|
| `src/agntrick/agents/paywall_remover.py` | Create | Agent class with `WebExtractorTool` as local tool |
| `src/agntrick/prompts/paywall_remover.md` | Create | System prompt with extraction strategy |
| `src/agntrick/graph.py` | Modify | Add routing rules + examples for delegation |
| `src/agntrick/prompts/assistant.md` | Modify | Add to agent table, delegation rules |
| `src/agntrick/tools/agent_invocation.py` | Modify | Add to `DELEGATABLE_AGENTS` |
| `src/agntrick/agents/assistant.py` | Modify | Remove `WebExtractorTool` from `local_tools()` |
| `src/agntrick/graph.py` | Modify | Remove `web_extract` from `_INTENT_TOOLS` sets |
| `tests/test_paywall_remover_agent.py` | Create | Agent registration + delegation tests |

## Wiring Details

### `agent_invocation.py`

Add `"paywall-remover"` to `DELEGATABLE_AGENTS` and description list.

### `graph.py` ROUTER_PROMPT

Add to Tool selection rules:
```
- Paywalled or blocked URL → delegate to "paywall-remover"
```

Add to Examples:
```
"remove paywall https://globo.com/..." → {"intent": "delegate", "tool_plan": "paywall-remover"}
"extract from https://wsj.com/..." → {"intent": "delegate", "tool_plan": "paywall-remover"}
```

Remove `web_extract` from `_INTENT_TOOLS` for `tool_use` and `research` intents.

### `assistant.md`

Add to agent table:
```
| paywall-remover | Extract content from paywalled/blocked sites | web_fetch fails on a URL, user asks to remove paywall, or known paywalled site |
```

Add to delegation rules:
```
- Paywalled/blocked URLs (globo.com, wsj.com, nyt.com, etc.) → delegate to "paywall-remover"
- web_fetch returns insufficient content → delegate to "paywall-remover"
```

Add to tool-selection-rules:
```
- User says "remove paywall" or "extract from" a URL → delegate to "paywall-remover"
```

### `assistant.py`

Remove `WebExtractorTool` from `local_tools()` — it now belongs to the agent.

## What Doesn't Change

- `WebExtractorTool` code (`tools/web_extractor.py`) — unchanged
- `WebExtractorConfig` in `config.py` — unchanged
- Existing `test_web_extractor.py` tests — unchanged
- `.env.example` — unchanged

## Dependencies

- `crawl4ai` (already added) — headless browser
- `httpx` (already in deps) — HTTP client for Firecrawl and Archive.ph
- `FIRECRAWL_API_KEY` env var (optional — Stage 2 is skipped without it)
