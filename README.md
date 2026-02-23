# Agentic Framework

A LangChain + MCP framework for building agentic systems in Python 3.12+.

![Build Status](https://github.com/jeancsil/agentic-framework/actions/workflows/ci.yml/badge.svg)
![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)
![GitHub License](https://img.shields.io/github/license/jeancsil/agentic-framework)

## What is this?

This framework helps you build AI agents that can:
- Use **local tools** (file operations, code search, etc.)
- Connect to **MCP servers** (web search, flight booking, etc.)
- Combine both in a single runtime

**Key features:**
- Decorator-based agent registration with automatic CLI generation
- Reusable LangGraph agent pattern with checkpointing
- Per-agent MCP server permissions
- Multi-language code navigation tools
- Safe file editing with automatic syntax validation

---

## Quick Start (Docker - Recommended)

**Docker is the recommended way to run this framework.** It comes pre-configured with all required tools and dependencies.

```bash
# Build the Docker image
make docker-build

# Run agents (no rebuild needed for code changes)
bin/agent.sh developer -i "Explain project structure"
bin/agent.sh chef -i "I have eggs and cheese"
bin/agent.sh list

# View logs (same location as local)
tail -f agentic-framework/logs/agent.log
```

**Why Docker?**
- All dependencies pre-installed: `ripgrep`, `fd`, `fzf`, `tree-sitter`
- No environment setup needed - just build and run
- Code changes reflected immediately (mounted volumes)
- Consistent environment across all machines

---

## Local Installation

If you need to run locally, you must install these dependencies:

**System packages:**
- `ripgrep` - Ultra-fast text searching
- `fd` - User-friendly alternative to `find`
- `fzf` - General-purpose command-line fuzzy finder

**Python packages (managed by `uv`):**
- `tree-sitter` - Parser generator
- `tree-sitter-languages` - Grammar packages

```bash
# Install Python dependencies
make install

# Run tests
make test

# Run agents
uv --directory agentic-framework run agentic-run developer -i "Explain project structure"
```

---

## Available Tools

| Tool | Purpose | Input Format |
|-------|---------|--------------|
| `find_files` | Fast file search via `fd` | `pattern` |
| `discover_structure` | Directory tree exploration | `[max_depth]` (default: 3) |
| `get_file_outline` | Extract class/function signatures | `file_path` |
| `read_file_fragment` | Read specific line ranges | `path:start:end` (1-indexed) |
| `code_search` | Pattern search via `ripgrep` | `regex_pattern` |
| `edit_file` | Safe file editing with syntax validation | See below |
| `web_search` | Web search via Tavily | `query` |

### File Editing

**RECOMMENDED: search_replace (no line numbers needed)**
```json
{"op": "search_replace", "path": "file.py", "old": "exact text", "new": "replacement text"}
```

**Line-based operations:**
```
replace:path:start:end:content
insert:path:after_line:content
delete:path:start:end
```

---

## Available MCP Servers

| Server | Purpose | API Key Required |
|--------|---------|------------------|
| `kiwi-com-flight-search` | Flight search | No |
| `webfetch` | Web content fetching | No |
| `tavily` | Web search | Yes (`TAVILY_API_KEY`) |
| `tinyfish` | AI assistant | Yes (`TINYFISH_API_KEY`) |

---

## Available Agents

| Agent | Purpose | MCP Access | Tools |
|-------|---------|------------|-------|
| `developer` | Codebase exploration & editing | webfetch | find_files, discover_structure, get_file_outline, read_file_fragment, code_search, edit_file |
| `travel-coordinator` | Multi-agent trip planning | kiwi-com-flight-search, web-fetch | Orchestrates 3 specialist agents |
| `chef` | Recipe suggestions | tavily | web_search |
| `news` | AI news aggregation | web-fetch | - |
| `travel` | Flight search | kiwi-com-flight-search | - |
| `simple` | Basic conversation | none | - |

---

## CLI Reference

```bash
# List all agents
uv --directory agentic-framework run agentic-run list

# Get agent info
uv --directory agentic-framework run agentic-run info <agent>

# Run an agent
uv --directory agentic-framework run agentic-run <agent> -i "your input"

# With timeout (seconds)
uv --directory agentic-framework run agentic-run <agent> -i "input" -t 120

# Verbose logging
uv --directory agentic-framework run agentic-run <agent> -i "input" -v
```

**In Docker:**
```bash
bin/agent.sh <agent> -i "input"
bin/agent.sh list
```

---

## Developer Agent

The `developer` agent is a Principal Software Engineer assistant for codebase work.

**Supported languages for `get_file_outline`:** Python, JavaScript, TypeScript, Rust, Go, Java, C/C++, PHP

---

## Multi-Agent Systems

The `travel-coordinator` demonstrates multi-agent orchestration:

```bash
bin/agent.sh travel-coordinator -i "Plan a 5-day trip from Lisbon to Berlin in May"
```

**Workflow:**
1. `FlightSpecialistAgent` → gathers flight options
2. `CityIntelAgent` → adds destination intelligence
3. `TravelReviewerAgent` → final itinerary

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_MODEL_NAME` | No | LLM model (default: gpt-4) |
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `TAVILY_API_KEY` | For chef agent | Tavily search API |
| `TINYFISH_API_KEY` | Optional | TinyFish MCP access |

---

## Building New Agents

### Minimal Agent

```python
from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry

@AgentRegistry.register("my-agent", mcp_servers=["tavily"])
class MyAgent(LangGraphMCPAgent):
    @property
    def system_prompt(self) -> str:
        return "You are my custom agent."
```

### Agent with Local Tools

```python
from langchain_core.tools import StructuredTool
from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry

@AgentRegistry.register("my-agent", mcp_servers=None)
class MyAgent(LangGraphMCPAgent):
    @property
    def system_prompt(self) -> str:
        return "You are a helpful assistant."

    def local_tools(self) -> list:
        return [
            StructuredTool.from_function(
                func=my_function,
                name="my_tool",
                description="What this tool does",
            )
        ]
```

### Multi-Agent Coordinator

```python
from agentic_framework.interfaces.base import Agent
from agentic_framework.registry import AgentRegistry

@AgentRegistry.register("coordinator", mcp_servers=["server1", "server2"])
class CoordinatorAgent(Agent):
    async def run(self, input_data, config=None):
        # Stage 1: First specialist
        specialist1 = Specialist1Agent()
        result1 = await specialist1.run(input_data)

        # Stage 2: Second specialist
        specialist2 = Specialist2Agent()
        result2 = await specialist2.run(result1)

        return result2

    def get_tools(self):
        return []
```

After creating your agent in `src/agentic_framework/core/`, it automatically becomes available:

```bash
uv --directory agentic-framework run agentic-run my-agent -i "hello"
```

---

## Architecture

```
User Input
    │
    ▼
┌─────────────────┐
│   CLI (Typer)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ AgentRegistry   │────▶│ Agent Discovery │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  MCPProvider    │────▶│  MCP Servers    │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│ LangGraph Agent │
│  (base class)   │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────┐
│ Local │ │  MCP  │
│ Tools │ │ Tools │
└───────┘ └───────┘
```

**Key files:**
- `src/agentic_framework/core/langgraph_agent.py` - Reusable agent base
- `src/agentic_framework/registry.py` - Agent registration
- `src/agentic_framework/mcp/provider.py` - MCP connection management
- `src/agentic_framework/tools/` - Tool implementations

---

## Development

For contributing to the framework itself, see [AGENTS.md](AGENTS.md).

```bash
make install    # Install dependencies
make test       # Run tests (coverage threshold: 60%)
make format     # Auto-format code
make check      # Run all checks (lint + format check)
```

**Before committing:** Run `make check && make test`

---

## License

MIT License - see [LICENSE](LICENSE) for details.
