# OllamaAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform OllamaAgent into a powerful local AI orchestrator with agent-to-agent delegation, full web capabilities, and robust error recovery.

**Architecture:** Tool-based orchestration pattern where OllamaAgent has an AgentInvocationTool to delegate to specialized agents. Each delegation is a fresh session with context-rich prompts crafted by OllamaAgent.

**Tech Stack:** Python 3.12, LangChain/LangGraph, asyncio, Pydantic, pytest

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `src/agntrick/prompts/ollama.md` | Create | Orchestrator system prompt |
| `src/agntrick/tools/agent_invocation.py` | Create | AgentInvocationTool implementation |
| `src/agntrick/tools/__init__.py` | Modify | Export AgentInvocationTool |
| `src/agntrick/agents/ollama.py` | Modify | Use ollama prompt, add tool, expand MCPs |
| `tests/test_agent_invocation.py` | Create | Tool tests |
| `tests/test_ollama_agent.py` | Create | Agent tests |

---

## Task 1: Create Ollama System Prompt

**Files:**
- Create: `src/agntrick/prompts/ollama.md`

- [ ] **Step 1: Create the ollama.md prompt file**

```markdown
# OllamaAgent - Local AI Orchestrator

You are a powerful local AI assistant running on GLM-4.7-Flash via Ollama.
You are the central orchestrator capable of handling diverse tasks and delegating to specialized agents when appropriate.

## Core Capabilities

- **Research & Synthesis**: Search the web, fetch content, analyze multiple sources, verify facts
- **Knowledge Management**: Document analysis, summarization, information extraction, organization
- **Creative & Content**: Writing, brainstorming, outlining, editing, translation
- **Data & Analysis**: Working with structured data, analysis, reasoning
- **Agent Orchestration**: Delegate to specialized agents for domain-specific tasks

## Available MCP Tools

| Tool | Purpose |
|------|---------|
| `web-forager` | Search the web for current information |
| `fetch` | Extract clean, readable content from URLs |
| `hacker-news` | Access Hacker News stories and discussions |

## Agent Delegation

You have the `invoke_agent` tool to delegate to specialized agents:

| Agent | Best For |
|-------|----------|
| `developer` | Code exploration, file operations, technical analysis, debugging |
| `learning` | Educational tutorials, step-by-step guides, explanations |
| `news` | Current news, events, breaking stories |
| `youtube` | Video transcript extraction and analysis |

### Delegation Protocol

When using `invoke_agent`, the delegated agent starts with **no prior context**.
You MUST include all necessary context in your delegation prompt:

1. **User's goal**: What they're trying to accomplish
2. **Relevant background**: Key information from the conversation
3. **Specific focus**: What exactly you need from the delegated agent
4. **Constraints**: Any requirements or preferences mentioned

**Example good delegation:**
```
Agent: developer
Prompt: "Analyze the authentication module structure in src/auth/. The user is building a Flask OAuth2 application and wants to understand the token handling flow before adding 2FA support. Focus on: current token validation logic, session management, and extension points for 2FA."
```

### Decision Framework

| Task Type | Action |
|-----------|--------|
| Code/file operations | Delegate to `developer` |
| Teaching/explaining concepts | Delegate to `learning` |
| Current news/events | Delegate to `news` |
| YouTube video analysis | Delegate to `youtube` |
| General questions, writing, analysis | Handle yourself |
| Web research, fact-checking | Handle yourself (use MCP tools) |

## Error Recovery Protocol

When tools or delegation fail:

1. **Try alternatives first**: Different agent, different MCP tool, different approach
2. **Attempt yourself**: If within your capabilities, handle the task directly
3. **Only report failure after exhausting options**
4. **Explain what you tried**: Help the user understand the attempted solutions

**Recovery Examples:**
- `web-forager` unavailable → Use `fetch` on known URLs, or `hacker-news` for tech topics
- `developer` agent times out → Simplify the request, retry, or provide guidance yourself
- Agent not found → Suggest the closest matching available agent

## Communication Style

- Be direct and helpful
- When delegating, briefly explain why you're choosing that agent
- Synthesize results from delegated tasks into coherent responses
- Admit limitations honestly
- Provide clear, actionable information

## Guardrails

- **Privacy**: You cannot access files outside the project context
- **Delegation limits**: Do not delegate to yourself (ollama agent)
- **Timeout awareness**: Long-running delegations may timeout; keep prompts focused
```

- [ ] **Step 2: Verify prompt file exists**

Run: `ls -la src/agntrick/prompts/ollama.md`
Expected: File exists with content

- [ ] **Step 3: Commit**

```bash
git add src/agntrick/prompts/ollama.md
git commit -m "feat(prompts): add ollama orchestrator prompt"
```

---

## Task 2: Create AgentInvocationTool

**Files:**
- Create: `src/agntrick/tools/agent_invocation.py`
- Test: `tests/test_agent_invocation.py`

### Task 2.1: Write Tool Tests

- [ ] **Step 1: Create test file with initial tests**

```python
# tests/test_agent_invocation.py
"""Tests for AgentInvocationTool."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agntrick.tools.agent_invocation import AgentInvocationTool


class TestAgentInvocationTool:
    """Tests for AgentInvocationTool."""

    def test_tool_name(self):
        """Tool should have correct name."""
        tool = AgentInvocationTool()
        assert tool.name == "invoke_agent"

    def test_tool_description_not_empty(self):
        """Tool should have a description."""
        tool = AgentInvocationTool()
        assert len(tool.description) > 50
        assert "agent" in tool.description.lower()

    def test_invoke_valid_agent_returns_response(self):
        """Valid agent invocation should return response."""
        tool = AgentInvocationTool()

        input_json = json.dumps({
            "agent_name": "developer",
            "prompt": "Test prompt"
        })

        with patch("agntrick.tools.agent_invocation.AgentRegistry") as mock_registry:
            mock_agent_cls = MagicMock()
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value="Agent response")
            mock_agent_cls.return_value = mock_agent
            mock_registry.get.return_value = mock_agent_cls
            mock_registry.list_agents.return_value = ["developer", "learning", "news", "youtube"]

            result = tool.invoke(input_json)
            assert result == "Agent response"

    def test_invoke_agent_not_found_returns_error(self):
        """Non-existent agent should return error message."""
        tool = AgentInvocationTool()

        input_json = json.dumps({
            "agent_name": "nonexistent",
            "prompt": "Test prompt"
        })

        with patch("agntrick.tools.agent_invocation.AgentRegistry") as mock_registry:
            mock_registry.get.return_value = None
            mock_registry.list_agents.return_value = ["developer", "learning", "news", "youtube"]

            result = tool.invoke(input_json)
            assert "not found" in result.lower()
            assert "developer" in result  # Lists available agents

    def test_invoke_invalid_json_returns_error(self):
        """Invalid JSON input should return clear error."""
        tool = AgentInvocationTool()
        result = tool.invoke("not valid json")
        assert "error" in result.lower()
        assert "json" in result.lower()

    def test_invoke_missing_agent_name_returns_error(self):
        """Missing agent_name field should return error."""
        tool = AgentInvocationTool()
        result = tool.invoke(json.dumps({"prompt": "test"}))
        assert "error" in result.lower()
        assert "agent_name" in result.lower()

    def test_invoke_missing_prompt_returns_error(self):
        """Missing prompt field should return error."""
        tool = AgentInvocationTool()
        result = tool.invoke(json.dumps({"agent_name": "developer"}))
        assert "error" in result.lower()
        assert "prompt" in result.lower()

    def test_invoke_agent_crash_returns_error_not_exception(self):
        """Agent crash should return error string, not raise."""
        tool = AgentInvocationTool()

        input_json = json.dumps({
            "agent_name": "developer",
            "prompt": "Test prompt"
        })

        with patch("agntrick.tools.agent_invocation.AgentRegistry") as mock_registry:
            mock_agent_cls = MagicMock()
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(side_effect=RuntimeError("Agent crashed"))
            mock_agent_cls.return_value = mock_agent
            mock_registry.get.return_value = mock_agent_cls
            mock_registry.list_agents.return_value = ["developer"]

            # Should NOT raise, should return error string
            result = tool.invoke(input_json)
            assert "error" in result.lower()

    def test_invoke_blocks_self_delegation(self):
        """Tool should block ollama from delegating to itself."""
        tool = AgentInvocationTool()

        input_json = json.dumps({
            "agent_name": "ollama",
            "prompt": "Test prompt"
        })

        result = tool.invoke(input_json)
        assert "cannot delegate to itself" in result.lower()

    def test_to_langchain_tool(self):
        """Tool should convert to LangChain StructuredTool."""
        from langchain_core.tools import StructuredTool

        tool = AgentInvocationTool()
        lc_tool = tool.to_langchain_tool()

        assert isinstance(lc_tool, StructuredTool)
        assert lc_tool.name == "invoke_agent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_invocation.py -v`
Expected: FAIL - module not found

### Task 2.2: Implement AgentInvocationTool

- [ ] **Step 3: Create the tool implementation**

```python
# src/agntrick/tools/agent_invocation.py
"""Agent Invocation Tool for delegating tasks to other agents."""

import asyncio
import json
import logging
from typing import Any

from agntrick.interfaces.base import Tool
from agntrick.registry import AgentRegistry

logger = logging.getLogger(__name__)

# Agents that can be delegated to (excludes ollama to prevent recursion)
DELEGATABLE_AGENTS = ["developer", "learning", "news", "youtube"]


class AgentInvocationTool(Tool):
    """Tool to invoke other registered agents.

    This tool allows an orchestrator agent to delegate tasks to specialized
    agents. Each invocation creates a fresh agent instance with no prior
    conversation context.

    Input format (JSON string):
        {
            "agent_name": "developer",
            "prompt": "Analyze the auth module...",
            "timeout": 60  // optional, defaults to 60
        }

    Returns:
        The delegated agent's response as a string, or an error message.
    """

    @property
    def name(self) -> str:
        return "invoke_agent"

    @property
    def description(self) -> str:
        return """Invoke a specialized agent to handle a task.

The delegated agent starts with no conversation context - include all necessary
context in your prompt.

Available agents:
- developer: Code exploration, file operations, technical analysis
- learning: Educational tutorials, step-by-step guides, explanations
- news: Current news, events, breaking stories
- youtube: Video transcript extraction and analysis

Input (JSON):
{
    "agent_name": "developer",
    "prompt": "Your task with full context...",
    "timeout": 60
}

Returns the agent's response or an error message."""

    def invoke(self, input_str: str) -> str:
        """Execute agent invocation.

        Args:
            input_str: JSON string with agent_name, prompt, and optional timeout.

        Returns:
            Agent response or error message (never raises exceptions).
        """
        # Parse input
        try:
            data = json.loads(input_str)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON input. Expected format: {{'agent_name': '...', 'prompt': '...'}}. Details: {e}"

        # Validate required fields
        if "agent_name" not in data:
            return "Error: Missing required field 'agent_name'. Available agents: " + ", ".join(DELEGATABLE_AGENTS)
        if "prompt" not in data:
            return "Error: Missing required field 'prompt'."

        agent_name = data["agent_name"]
        prompt = data["prompt"]
        timeout = data.get("timeout", 60)

        # Block self-delegation
        if agent_name == "ollama":
            return "Error: Ollama agent cannot delegate to itself. Choose a different agent: " + ", ".join(DELEGATABLE_AGENTS)

        # Validate agent exists
        agent_cls = AgentRegistry.get(agent_name)
        if agent_cls is None:
            available = AgentRegistry.list_agents()
            delegatable = [a for a in available if a in DELEGATABLE_AGENTS]
            return f"Error: Agent '{agent_name}' not found. Available agents: {', '.join(delegatable)}"

        # Check agent is delegatable
        if agent_name not in DELEGATABLE_AGENTS:
            return f"Error: Agent '{agent_name}' cannot be delegated to. Available: {', '.join(DELEGATABLE_AGENTS)}"

        # Invoke agent in async context
        try:
            return asyncio.run(self._invoke_agent_async(agent_cls, prompt, timeout))
        except Exception as e:
            logger.error(f"Agent invocation failed: {e}")
            return f"Error: Agent '{agent_name}' encountered an error: {e}"

    async def _invoke_agent_async(
        self,
        agent_cls: Any,
        prompt: str,
        timeout: float,
    ) -> str:
        """Invoke agent asynchronously with timeout.

        Args:
            agent_cls: The agent class to instantiate.
            prompt: The prompt to send to the agent.
            timeout: Timeout in seconds.

        Returns:
            Agent response or error message.
        """
        try:
            agent = agent_cls()
            result = await asyncio.wait_for(
                agent.run(prompt),
                timeout=timeout,
            )
            return str(result)
        except asyncio.TimeoutError:
            return f"Error: Agent timed out after {timeout} seconds. Try simplifying your request."
        except Exception as e:
            logger.error(f"Async agent invocation failed: {e}")
            raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_invocation.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/agntrick/tools/agent_invocation.py tests/test_agent_invocation.py
git commit -m "feat(tools): add AgentInvocationTool for agent delegation"
```

---

## Task 3: Export AgentInvocationTool

**Files:**
- Modify: `src/agntrick/tools/__init__.py`

- [ ] **Step 1: Add export to tools __init__.py**

```python
# src/agntrick/tools/__init__.py
from .agent_invocation import AgentInvocationTool
from .code_searcher import CodeSearcher
from .codebase_explorer import (
    FileEditorTool,
    FileFinderTool,
    FileFragmentReaderTool,
    FileOutlinerTool,
    StructureExplorerTool,
)
from .example import CalculatorTool, WeatherTool
from .syntax_validator import SyntaxValidator, ValidationResult, get_validator
from .youtube_cache import YouTubeTranscriptCache
from .youtube_transcript import YouTubeTranscriptTool

__all__ = [
    "AgentInvocationTool",
    "CalculatorTool",
    "WeatherTool",
    "CodeSearcher",
    "StructureExplorerTool",
    "FileOutlinerTool",
    "FileFragmentReaderTool",
    "FileFinderTool",
    "FileEditorTool",
    "SyntaxValidator",
    "ValidationResult",
    "get_validator",
    "YouTubeTranscriptCache",
    "YouTubeTranscriptTool",
]
```

- [ ] **Step 2: Verify import works**

Run: `uv run python -c "from agntrick.tools import AgentInvocationTool; print(AgentInvocationTool().name)"`
Expected: `invoke_agent`

- [ ] **Step 3: Commit**

```bash
git add src/agntrick/tools/__init__.py
git commit -m "feat(tools): export AgentInvocationTool"
```

---

## Task 4: Update OllamaAgent

**Files:**
- Modify: `src/agntrick/agents/ollama.py`

- [ ] **Step 1: Update OllamaAgent with new prompt, tools, and MCPs**

```python
# src/agntrick/agents/ollama.py
"""Ollama Agent using local GLM-4.7-Flash model.

This agent uses LocalReasoningLLM to connect to a local Ollama server
running GLM-4.7-Flash with thinking tags automatically stripped from responses.
It serves as a versatile orchestrator capable of delegating to other agents.
"""

from typing import Any, Sequence

from agntrick.agent import AgentBase
from agntrick.llm.local_reasoning import get_local_developer_model
from agntrick.prompts import load_prompt
from agntrick.registry import AgentRegistry
from agntrick.tools import AgentInvocationTool


@AgentRegistry.register("ollama", mcp_servers=["web-forager", "fetch", "hacker-news"])
class OllamaAgent(AgentBase):
    """Agent using local GLM-4.7-Flash model via Ollama.

    A versatile local AI orchestrator that can:
    - Search the web and fetch content via MCP tools
    - Delegate to specialized agents (developer, learning, news, youtube)
    - Handle research, writing, and analysis tasks directly

    MCP Servers:
        web-forager: Web search for current information
        fetch: Extract clean content from URLs
        hacker-news: Access Hacker News stories and discussions

    Server Configuration:
        Make sure your Ollama server is running with:
        ollama serve --port 8080

    Usage:
        agntrick ollama -i "Your question here"
    """

    def __init__(self) -> None:
        """Initialize OllamaAgent with local GLM-4.7-Flash model."""
        # Store custom model before calling parent init
        self._custom_model = get_local_developer_model()
        # Parent sets self.model, so we provide a property to return our custom one
        super().__init__()

    @property
    def system_prompt(self) -> str:
        """Return the orchestrator system prompt."""
        return load_prompt("ollama")

    def local_tools(self) -> Sequence[Any]:
        """Return local tools including agent invocation."""
        return [AgentInvocationTool().to_langchain_tool()]

    @property
    def model(self) -> Any:
        """Return the custom LocalReasoningLLM model.

        Overrides parent's model to use LocalReasoningLLM that strips
        <reasoning>...</reasoning> tags from responses.
        """
        return self._custom_model

    @model.setter
    def model(self, value: Any) -> None:
        """No-op setter to allow parent's __init__ to set self.model."""
        pass
```

- [ ] **Step 2: Verify agent loads correctly**

Run: `uv run python -c "from agntrick.agents.ollama import OllamaAgent; a = OllamaAgent(); print(a.system_prompt[:50])"`
Expected: First 50 chars of ollama prompt (NOT developer prompt)

- [ ] **Step 3: Commit**

```bash
git add src/agntrick/agents/ollama.py
git commit -m "feat(agents): update OllamaAgent as orchestrator with delegation"
```

---

## Task 5: Create OllamaAgent Tests

**Files:**
- Create: `tests/test_ollama_agent.py`

- [ ] **Step 1: Create OllamaAgent test file**

```python
# tests/test_ollama_agent.py
"""Tests for OllamaAgent."""
import pytest

from agntrick.agents.ollama import OllamaAgent
from agntrick.registry import AgentRegistry


class TestOllamaAgent:
    """Tests for OllamaAgent configuration and behavior."""

    def test_agent_is_registered(self):
        """OllamaAgent should be registered in AgentRegistry."""
        agent_cls = AgentRegistry.get("ollama")
        assert agent_cls is OllamaAgent

    def test_system_prompt_loads_ollama_prompt(self):
        """Agent should load ollama.md, not developer.md."""
        agent = OllamaAgent()
        prompt = agent.system_prompt

        # Should contain orchestrator identity
        assert "orchestrator" in prompt.lower()

        # Should NOT contain developer-specific content
        assert "Principal Software Engineer" not in prompt

    def test_system_prompt_not_empty(self):
        """System prompt should not be empty."""
        agent = OllamaAgent()
        assert len(agent.system_prompt) > 100

    def test_local_tools_includes_agent_invocation(self):
        """Agent should have AgentInvocationTool."""
        agent = OllamaAgent()
        tools = agent.local_tools()

        tool_names = [t.name for t in tools]
        assert "invoke_agent" in tool_names

    def test_mcp_servers_configured(self):
        """Agent should have correct MCP servers configured."""
        mcp_servers = AgentRegistry.get_mcp_servers("ollama")
        assert mcp_servers is not None
        assert "web-forager" in mcp_servers
        assert "fetch" in mcp_servers
        assert "hacker-news" in mcp_servers

    def test_mcp_servers_excludes_kiwi(self):
        """Agent should NOT have kiwi-com-flight-search (too niche)."""
        mcp_servers = AgentRegistry.get_mcp_servers("ollama")
        assert "kiwi-com-flight-search" not in mcp_servers

    def test_regression_wrong_prompt(self):
        """Regression test: ensure we never use developer prompt again."""
        agent = OllamaAgent()
        prompt = agent.system_prompt

        # These phrases should NOT appear (they're from developer prompt)
        forbidden_phrases = [
            "Principal Software Engineer",
            "MANDATORY FILE EDITING WORKFLOW",
            "edit_file",
            "read_file_fragment",
            "find_files",
        ]

        for phrase in forbidden_phrases:
            assert phrase not in prompt, f"Found forbidden phrase '{phrase}' in ollama prompt"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_ollama_agent.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_ollama_agent.py
git commit -m "test(agents): add OllamaAgent tests for prompt and tools"
```

---

## Task 6: Final Verification

- [ ] **Step 1: Run all tests**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Run linting**

Run: `uv run make check`
Expected: No errors

- [ ] **Step 3: Run full test suite with coverage**

Run: `uv run make test`
Expected: All tests pass, coverage maintained

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address final test/lint issues"
```

---

## Summary

| Task | Files | Tests |
|------|-------|-------|
| 1. Prompt | `src/agntrick/prompts/ollama.md` | - |
| 2. Tool | `src/agntrick/tools/agent_invocation.py` | `tests/test_agent_invocation.py` |
| 3. Export | `src/agntrick/tools/__init__.py` | - |
| 4. Agent | `src/agntrick/agents/ollama.py` | - |
| 5. Agent Tests | - | `tests/test_ollama_agent.py` |
| 6. Verify | - | - |
