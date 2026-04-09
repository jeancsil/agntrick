# Paywall Remover Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a `paywall-remover` specialist agent that owns the `DeepScrapeTool` (renamed from `WebExtractorTool`) and is reachable via the delegation pipeline, replacing the broken tool-based routing approach.

**Architecture:** A dedicated agent (mirroring the `youtube` agent pattern) with `DeepScrapeTool` as its local tool. The assistant delegates to it via `invoke_agent`. This sidesteps the graph routing complexity that prevented `web_extract` from surfacing as a local tool in the executor.

**Tech Stack:** Python, LangChain tools, crawl4ai v0.8.x (headless browser), httpx (Firecrawl v2/Archive.ph), agntrick agent framework

**Documentation sources verified via Context7:**
- Crawl4AI: `/unclecode/crawl4ai` (Benchmark: 89.12)
- Firecrawl: `/websites/firecrawl_dev` (Benchmark: 85.76)

---

## API Reference (from Context7 docs)

### Crawl4AI v0.8.x (verified 2026-04-08)

**Key changes from old code:**
- `result.markdown` is now a `MarkdownGenerationResult` object with `.raw_markdown` and `.fit_markdown` — NOT a plain string
- `PruningContentFilter` must be passed to `DefaultMarkdownGenerator`, NOT directly to `CrawlerRunConfig`
- `CrawlerRunConfig` takes `markdown_generator=`, not `content_filter=`
- `result.metadata` is a dict with `.get("title", "")` — this part is unchanged

**Correct imports:**
```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
```

**Correct usage:**
```python
md_generator = DefaultMarkdownGenerator(
    content_filter=PruningContentFilter(threshold=0.45, threshold_type="dynamic", min_word_threshold=5)
)
config = CrawlerRunConfig(markdown_generator=md_generator)

async with AsyncWebCrawler() as crawler:
    result = await crawler.arun(url=url, config=config)
    if result.success:
        raw = result.markdown.raw_markdown      # full markdown
        fit = result.markdown.fit_markdown       # pruned/filtered markdown
        title = result.metadata.get("title", "")
    else:
        error = result.error_message
```

### Firecrawl v2 (verified 2026-04-08)

**Key change:** endpoint is now `/v2/scrape` (was `/v1/scrape`). Response format unchanged.

**Correct request:**
```python
response = httpx.post(
    f"{firecrawl_url}/v2/scrape",  # v2, not v1
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    json={"url": url, "formats": ["markdown"]},
    timeout=45.0,
)
data = response.json()
content = data.get("data", {}).get("markdown", "")
title = data.get("data", {}).get("metadata", {}).get("title", "")
```

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/agntrick/tools/web_extractor.py` | **Rename** to `deep_scrape.py` | Rename tool: `WebExtractorTool` → `DeepScrapeTool`, tool name: `web_extract` → `deep_scrape` |
| `src/agntrick/tools/__init__.py` | Modify | Update exports to new names |
| `src/agntrick/config.py` | Modify | Rename `WebExtractorConfig` → `DeepScrapeConfig` |
| `src/agntrick/agents/paywall_remover.py` | Create | Agent class — mirrors youtube.py pattern |
| `src/agntrick/prompts/paywall_remover.md` | Create | System prompt with extraction strategy |
| `src/agntrick/tools/agent_invocation.py` | Modify | Add `"paywall-remover"` to `DELEGATABLE_AGENTS` + description |
| `src/agntrick/graph.py` | Modify | Update ROUTER_PROMPT (delegation examples), remove `web_extract` from `_INTENT_TOOLS` |
| `src/agntrick/prompts/assistant.md` | Modify | Add paywall-remover to agent table, delegation rules, remove `web_extract` |
| `src/agntrick/agents/assistant.py` | Modify | Remove `WebExtractorTool` from `local_tools()` |
| `tests/test_web_extractor.py` | **Rename** to `test_deep_scrape.py` | Update all class/import references |
| `tests/test_paywall_remover_agent.py` | Create | Registration + delegation + wiring tests |

---

### Task 1: Rename tool — `WebExtractorTool` → `DeepScrapeTool` + fix APIs

**Files:**
- Rename: `src/agntrick/tools/web_extractor.py` → `src/agntrick/tools/deep_scrape.py`
- Rename: `tests/test_web_extractor.py` → `tests/test_deep_scrape.py`
- Modify: `src/agntrick/tools/__init__.py`
- Modify: `src/agntrick/config.py`

- [ ] **Step 1: Rename the tool file**

```bash
git mv src/agntrick/tools/web_extractor.py src/agntrick/tools/deep_scrape.py
git mv tests/test_web_extractor.py tests/test_deep_scrape.py
```

- [ ] **Step 2: Update the tool module — rename class + fix Crawl4AI v0.8.x API**

In `src/agntrick/tools/deep_scrape.py`, apply these changes:

**Rename classes:**
- `WebExtractorTool` → `DeepScrapeTool`
- `WebContentResult` → `DeepScrapeResult`
- Keep `ExtractionStage` and `ExtractionStatus` (they're fine as-is)

**Rename tool property:**
- `name` property returns `"deep_scrape"` (was `"web_extract"`)

**Fix Crawl4AI v0.8.x API in `_crawl4ai_async()` method:**

Replace:
```python
async def _crawl4ai_async(self, url: str) -> WebContentResult:
    """Async Crawl4AI extraction."""
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    from crawl4ai.content_filter_strategy import PruningContentFilter

    run_config = CrawlerRunConfig(
        content_filter=PruningContentFilter(),
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=run_config)
        content = result.markdown or ""
        if not content or len(content.strip()) < 100:
            return WebContentResult(...)
        title = result.metadata.get("title", "") if result.metadata else ""
        return WebContentResult(...)
```

With:
```python
async def _crawl4ai_async(self, url: str) -> DeepScrapeResult:
    """Async Crawl4AI extraction using v0.8.x API."""
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    from crawl4ai.content_filter_strategy import PruningContentFilter
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(
            threshold=0.45,
            threshold_type="dynamic",
            min_word_threshold=5,
        )
    )
    run_config = CrawlerRunConfig(markdown_generator=md_generator)
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=run_config)
        if not result.success:
            return DeepScrapeResult(
                url=url,
                status=ExtractionStatus.ERROR,
                stage=ExtractionStage.CRAWL4AI,
                error=result.error_message or "Crawl4AI failed.",
            )
        fit = result.markdown.fit_markdown or ""
        raw = result.markdown.raw_markdown or ""
        # fit_markdown can be too aggressive on non-standard layouts — fall back
        # to raw if it pruned more than 80% of the content
        if fit and raw and len(fit) < len(raw) * 0.2:
            content = raw
        else:
            content = fit or raw
        if not content or len(content.strip()) < 100:
            return DeepScrapeResult(
                url=url,
                status=ExtractionStatus.BLOCKED,
                stage=ExtractionStage.CRAWL4AI,
                error="Crawl4AI returned insufficient content (possibly blocked).",
            )
        title = result.metadata.get("title", "") if result.metadata else ""
        return DeepScrapeResult(
            url=url,
            status=ExtractionStatus.SUCCESS,
            stage=ExtractionStage.CRAWL4AI,
            content=content,
            title=title,
            final_url=result.url,
        )
```

**Fix Firecrawl v2 endpoint in `_try_firecrawl()` method:**

The base URL already contains the version. Keep the endpoint path as `/scrape`:

```python
self._firecrawl_url = os.environ.get("FIRECRAWL_URL", "https://api.firecrawl.dev/v2")
```

The POST request stays as-is:
```python
response = httpx.post(
    f"{self._firecrawl_url}/scrape",   # → https://api.firecrawl.dev/v2/scrape
    ...
```

Note: keep the `json` payload as `{"url": url, "formats": ["markdown"]}` — this matches the v2 API.

**Update all `WebContentResult` references to `DeepScrapeResult` throughout the file.**

- [ ] **Step 3: Update `src/agntrick/tools/__init__.py`**

Replace:
```python
from agntrick.tools.web_extractor import (
    ExtractionStage,
    ExtractionStatus,
    WebContentResult,
    WebExtractorTool,
)
```

With:
```python
from agntrick.tools.deep_scrape import (
    DeepScrapeResult,
    DeepScrapeTool,
    ExtractionStage,
    ExtractionStatus,
)
```

- [ ] **Step 4: Update `src/agntrick/config.py`**

Rename `WebExtractorConfig` → `DeepScrapeConfig` and update the field reference inside `AgntrickConfig`. Also update the default `firecrawl_url` from `https://api.firecrawl.dev/v1` to `https://api.firecrawl.dev/v2`.

- [ ] **Step 5: Update `tests/test_deep_scrape.py`**

Rename all references:
- `WebContentResult` → `DeepScrapeResult`
- `WebExtractorTool` → `DeepScrapeTool`
- `from agntrick.tools.web_extractor` → `from agntrick.tools.deep_scrape`
- `test_web_extractor` references in test names → `test_deep_scrape`
- `tool.name == "web_extract"` → `tool.name == "deep_scrape"`

- [ ] **Step 6: Run `make check && make test`**

Fix any remaining references. Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: rename WebExtractorTool to DeepScrapeTool, fix Crawl4AI v0.8.x + Firecrawl v2 APIs"
```

---

### Task 2: Create the paywall-remover agent

**Files:**
- Create: `src/agntrick/agents/paywall_remover.py`
- Create: `src/agntrick/prompts/paywall_remover.md`

- [ ] **Step 1: Write the agent module**

Create `src/agntrick/agents/paywall_remover.py`:

```python
"""Paywall Remover Agent — specialist for extracting paywalled web content.

Uses the DeepScrapeTool's 3-stage pipeline (Crawl4AI → Firecrawl → Archive.ph)
to bypass paywalls, anti-bot protection, and JavaScript rendering barriers.
"""

from typing import Any, Sequence

from agntrick.agent import AgentBase
from agntrick.prompts import load_prompt
from agntrick.registry import AgentRegistry
from agntrick.tools import DeepScrapeTool


@AgentRegistry.register(
    "paywall-remover",
    mcp_servers=["toolbox"],
    tool_categories=["web"],
)
class PaywallRemoverAgent(AgentBase):
    """Specialist agent for extracting content from paywalled/blocked sites.

    Capabilities:
    - Extract full article text from paywalled sites (globo.com, wsj.com, nyt.com, etc.)
    - Bypass Cloudflare/turnstile anti-bot protection
    - Handle JavaScript-rendered content via headless browser (Crawl4AI)
    - Fall back through 3-stage pipeline for maximum coverage

    MCP Servers:
        toolbox: Centralized tool server for web_search as fallback
    """

    @property
    def system_prompt(self) -> str:
        """Return the paywall-remover system prompt."""
        return load_prompt("paywall_remover")

    def local_tools(self) -> Sequence[Any]:
        """Return deep scrape tool."""
        return [DeepScrapeTool().to_langchain_tool()]
```

- [ ] **Step 2: Write the system prompt**

Create `src/agntrick/prompts/paywall_remover.md`:

```markdown
You are a web content extraction specialist. Your job is to extract clean, readable markdown from web pages — especially paywalled, bot-protected, or JavaScript-heavy sites.

## Your Tool

You have the `deep_scrape` tool which uses a 3-stage deep scraping pipeline:
1. **Crawl4AI** — headless Chromium browser (handles JS rendering, basic anti-bot, outputs fit_markdown)
2. **Firecrawl** — API service (handles Cloudflare, turnstile, hard anti-bot)
3. **Archive.ph** — cached archived snapshots (last resort)

## How to Work

1. Extract the URL from the user's request
2. Call `deep_scrape` with the URL
3. If successful, present the content cleanly:
   - Include the title and source
   - Format as readable markdown
   - If the content is very long, provide a summary with key points first
4. If extraction fails, report which stages were tried and suggest alternatives

## Guidelines

- Always include the article title and source URL in your response
- Respond in the same language as the extracted content (or as the user requests)
- If content is partially extracted (truncated), note this clearly
- For very long articles, offer a concise summary followed by the full text
- Never fabricate content — only report what was actually extracted
- Language: If the extracted content is in a different language than the user's query, provide a detailed summary in the user's language, followed by the original content if requested
```

- [ ] **Step 3: Run linting to verify**

Run: `make check`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/agntrick/agents/paywall_remover.py src/agntrick/prompts/paywall_remover.md
git commit -m "feat: add paywall-remover agent with DeepScrapeTool"
```

---

### Task 3: Wire paywall-remover into the delegation pipeline

**Files:**
- Modify: `src/agntrick/tools/agent_invocation.py:15-22` (add to DELEGATABLE_AGENTS)
- Modify: `src/agntrick/tools/agent_invocation.py:49-69` (add to description list)

- [ ] **Step 1: Write the failing test**

Create `tests/test_paywall_remover_agent.py`:

```python
"""Tests for paywall-remover agent registration and delegation wiring."""

from agntrick.registry import AgentRegistry
from agntrick.tools.agent_invocation import DELEGATABLE_AGENTS


class TestPaywallRemoverRegistration:
    """Verify the agent is registered and delegatable."""

    def test_registered_in_registry(self) -> None:
        """Agent class is discoverable via AgentRegistry."""
        cls = AgentRegistry.get("paywall-remover")
        assert cls is not None

    def test_in_delegatable_agents(self) -> None:
        """Agent is in the DELEGATABLE_AGENTS list."""
        assert "paywall-remover" in DELEGATABLE_AGENTS

    def test_invoke_agent_description_includes_paywall(self) -> None:
        """invoke_agent tool description mentions paywall-remover."""
        from agntrick.tools.agent_invocation import AgentInvocationTool

        tool = AgentInvocationTool()
        assert "paywall-remover" in tool.description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paywall_remover_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Add to DELEGATABLE_AGENTS list**

In `src/agntrick/tools/agent_invocation.py`, add `"paywall-remover"` at the end of the list:

```python
DELEGATABLE_AGENTS = [
    "developer",
    "learning",
    "news",
    "youtube",
    "committer",
    "github-pr-reviewer",
    "paywall-remover",
]
```

- [ ] **Step 4: Add to invoke_agent description**

Add after the `github-pr-reviewer` line in the description string:

```
- paywall-remover: Extract content from paywalled/blocked sites
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_paywall_remover_agent.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/tools/agent_invocation.py tests/test_paywall_remover_agent.py
git commit -m "feat: wire paywall-remover into delegation pipeline"
```

---

### Task 4: Remove DeepScrapeTool from assistant and update graph routing

**Files:**
- Modify: `src/agntrick/agents/assistant.py:14,43-46` (remove import and usage)
- Modify: `src/agntrick/graph.py` (update ROUTER_PROMPT + remove `web_extract` from `_INTENT_TOOLS`)

- [ ] **Step 1: Add failing tests to `tests/test_paywall_remover_agent.py`**

```python
from agntrick.graph import _INTENT_TOOLS


class TestDeepScrapeRemovedFromGraph:
    """Verify web_extract/deep_scrape are NOT in intent tools (replaced by delegation)."""

    def test_web_extract_not_in_tool_use(self) -> None:
        assert "web_extract" not in _INTENT_TOOLS["tool_use"]

    def test_web_extract_not_in_research(self) -> None:
        assert "web_extract" not in _INTENT_TOOLS["research"]

    def test_deep_scrape_not_in_tool_use(self) -> None:
        assert "deep_scrape" not in _INTENT_TOOLS["tool_use"]

    def test_deep_scrape_not_in_research(self) -> None:
        assert "deep_scrape" not in _INTENT_TOOLS["research"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paywall_remover_agent.py::TestDeepScrapeRemovedFromGraph -v`
Expected: FAIL

- [ ] **Step 3: Remove DeepScrapeTool from assistant.py**

In `src/agntrick/agents/assistant.py`:

Change:
```python
from agntrick.tools import AgentInvocationTool, WebExtractorTool
```
To:
```python
from agntrick.tools import AgentInvocationTool
```

Change `local_tools()`:
```python
    def local_tools(self) -> Sequence[Any]:
        """Return local tools — agent invocation for delegation."""
        return [
            AgentInvocationTool().to_langchain_tool(),
        ]
```

- [ ] **Step 4: Update graph.py ROUTER_PROMPT**

In the **Tool selection rules** section, replace:
```
- Paywalled or blocked URL → web_extract (bypasses paywalls via Crawl4AI/Firecrawl/Archive.ph)
```
with:
```
- Paywalled or blocked URL → delegate to "paywall-remover"
```

In the **URL handling rules** section, replace:
```
- Paywalled/blocked site (globo.com, wsj.com, nyt.com, etc.) or user says "extract" → web_extract
```
with:
```
- Paywalled/blocked site (globo.com, wsj.com, nyt.com, etc.) or user says "extract" or "remove paywall" → delegate to "paywall-remover"
```

In the **Examples** section, replace:
```
"Extract content from https://globo.com/..." → {"intent": "tool_use", "tool_plan": "web_extract", "skip_tools": false}
"Read this paywalled article https://wsj.com/..." → {"intent": "tool_use", \
"tool_plan": "web_extract", "skip_tools": false}
```
with:
```
"Extract content from https://globo.com/..." → {"intent": "delegate", "tool_plan": "paywall-remover", "skip_tools": false}
"Remove paywall from https://wsj.com/..." → {"intent": "delegate", \
"tool_plan": "paywall-remover", "skip_tools": false}
```

- [ ] **Step 5: Remove `web_extract` from `_INTENT_TOOLS`**

In `src/agntrick/graph.py`, in `_INTENT_TOOLS`, remove `"web_extract"` from both `"tool_use"` and `"research"` sets.

- [ ] **Step 6: Run `make check && make test`**

Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/agntrick/agents/assistant.py src/agntrick/graph.py tests/test_paywall_remover_agent.py
git commit -m "feat: route paywall extraction via delegation, remove web_extract from assistant"
```

---

### Task 5: Update assistant prompt for delegation-based paywall handling

**Files:**
- Modify: `src/agntrick/prompts/assistant.md`

- [ ] **Step 1: Update tool-selection-rules**

In the `<tool-selection-rules>` block, replace:
```
- Paywalled or blocked site (globo.com, wsj.com, nyt.com, etc.): Use web_extract. It bypasses paywalls via Crawl4AI, Firecrawl, and Archive.ph.
- User says "extract" or "get content from" a URL: Use web_extract.
```
with:
```
- Paywalled or blocked site (globo.com, wsj.com, nyt.com, etc.): delegate to "paywall-remover"
- User says "extract", "remove paywall", or "get content from" a blocked URL: delegate to "paywall-remover"
- web_fetch returns insufficient content or fails on a URL: delegate to "paywall-remover"
```

- [ ] **Step 2: Add paywall-remover to agents table**

Add row:
```
| paywall-remover | Extract content from paywalled/blocked sites via deep scraping | web_fetch fails, user asks to remove paywall, or known paywalled site |
```

- [ ] **Step 3: Add delegation rules**

After existing delegation rules, add:
```
- Paywalled/blocked URLs (globo.com, wsj.com, nyt.com, ft.com, etc.) → delegate to "paywall-remover"
- web_fetch returns insufficient content → delegate to "paywall-remover"
- User says "remove paywall" or "extract from" a URL → delegate to "paywall-remover"
```

- [ ] **Step 4: Remove `web_extract` from tools section**

Delete the `web_extract` entry entirely.

- [ ] **Step 5: Run `make check`**

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/prompts/assistant.md
git commit -m "feat: update assistant prompt for paywall-remover delegation"
```

---

### Task 6: Full verification

- [ ] **Step 0: Verify dependencies**

Check `pyproject.toml` has `crawl4ai>=0.8.0`. If not, run: `uv add "crawl4ai>=0.8.0"`

- [ ] **Step 1: Run `make check && make test`**
- [ ] **Step 2: Verify import chain:** `uv run python -c "from agntrick.agents.paywall_remover import PaywallRemoverAgent; print('OK')"`
- [ ] **Step 3: Verify agent registration:** `uv run python -c "from agntrick.registry import AgentRegistry; from agntrick.agents.paywall_remover import PaywallRemoverAgent; print(AgentRegistry.get('paywall-remover'))"`
- [ ] **Step 4: Verify tool name:** `uv run python -c "from agntrick.tools.deep_scrape import DeepScrapeTool; t = DeepScrapeTool(); print(t.name)"`
  Expected: `deep_scrape`
- [ ] **Step 5: Verify delegation list:** `uv run python -c "from agntrick.tools.agent_invocation import DELEGATABLE_AGENTS; print('paywall-remover' in DELEGATABLE_AGENTS)"`
  Expected: `True`
