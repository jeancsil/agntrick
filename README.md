# Agentic Framework

An educational LangChain + MCP framework for learning and building agentic systems in Python 3.12+.

![Build Status](https://github.com/jeancsil/agentic-framework/actions/workflows/ci.yml/badge.svg)
![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)
![GitHub License](https://img.shields.io/github/license/jeancsil/agentic-framework)

## Goal of This Repository

This project is intentionally small so you can learn the core building blocks of agentic coding:

- agent registry and dynamic CLI commands
- reusable LangGraph agent pattern
- optional MCP server access with explicit per-agent permissions
- local tools + MCP tools combined in one runtime
- testable architecture (no network required in unit tests)

## Prerequisites

- Python >= 3.12, < 3.14
- [uv](https://docs.astral.sh/uv/) (recommended)

## Quickstart

```bash
make install
make test
```

Run an agent:

```bash
uv --project agentic-framework run agentic-run simple -i "Explain what an MCP server is."
```

List available agents:

```bash
uv --project agentic-framework run agentic-run list
```

## Current Agents

| Agent | What it does | MCP Access |
|---|---|---|
| `simple` | basic conversational chain | none |
| `chef` | recipe suggestions from ingredients | `tavily` |
| `travel` | flight planning assistant | `kiwi-com-flight-search` |
| `news` | AI news assistant | `web-fetch` |

## Architecture (Beginner-Friendly)

Core flow:

1. Register an agent in `src/agentic_framework/registry.py`.
2. CLI discovers registered agents and creates commands automatically.
3. If an agent has MCP permissions, CLI opens those MCP tool sessions.
4. Agent runs with local tools + MCP tools and returns final response.

Key files:

- `agentic-framework/src/agentic_framework/core/langgraph_agent.py`: reusable base class for most agents
- `agentic-framework/src/agentic_framework/mcp/config.py`: all available MCP servers
- `agentic-framework/src/agentic_framework/registry.py`: agent registration + allowed MCP servers
- `agentic-framework/src/agentic_framework/cli.py`: command runner and error handling

## Create a New Agent

Minimal pattern:

```python
from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry


@AgentRegistry.register("my-agent", mcp_servers=["tavily", "web-fetch"])
class MyAgent(LangGraphMCPAgent):
    @property
    def system_prompt(self) -> str:
        return "You are my custom agent."
```

Optional local tools:

```python
def local_tools(self):
    return [my_langchain_tool]
```

After adding the file under `src/agentic_framework/core/`, the CLI command appears automatically:

```bash
uv --project agentic-framework run agentic-run my-agent -i "hello"
```

## Scaling to Coordinators and Multi-Agent Systems

Recommended approach:

1. Build each specialist as a small `LangGraphMCPAgent` subclass.
2. Keep MCP permissions strict per specialist in the registry.
3. Add a coordinator agent that routes user intent to specialists.
4. Keep shared policies/prompts in one place; keep specialist prompts focused.
5. Add contract tests for routing and handoff behavior.

This keeps the code easy for medium-level engineers to extend while remaining production-friendly.

## Development Commands

- `make install`: install dependencies
- `make test`: run tests (coverage threshold configured to fail under 60%)
- `make lint`: run mypy + ruff
- `make run`: run a sample agent
- `make clean`: remove caches and temporary artifacts
