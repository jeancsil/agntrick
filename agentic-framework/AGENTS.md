# Agents Guide

This guide is for both external LLMs working within this codebase and developers building new agents and tools.

## Project Overview

This is an educational **LangChain + MCP framework** for building agentic systems in Python 3.12+.

### Key Technologies

- **LangChain**: LLM orchestration framework
- **LangGraph**: Stateful agent workflows with checkpoints
- **MCP (Model Context Protocol)**: External tool integration
- **Typer**: CLI interface
- **Rich**: Terminal formatting

## Architecture

### Directory Structure

```
src/agentic_framework/
├── core/               # Agent implementations
│   ├── __init__.py     # Exports only base classes (no concrete agents)
│   ├── langgraph_agent.py    # Reusable LangGraphMCPAgent base
│   ├── simple_agent.py       # Basic LLM agent (no tools)
│   ├── chef_agent.py         # Recipe finder with web search
│   ├── travel_agent.py       # Flight search via Kiwi MCP
│   ├── news_agent.py         # AI news via web-fetch MCP
│   ├── travel_coordinator_agent.py  # Multi-agent orchestration
│   └── developer_agent.py    # Codebase exploration agent
├── interfaces/          # Abstract base classes
│   └── base.py          # Agent and Tool ABCs
├── mcp/                 # Model Context Protocol
│   ├── config.py        # MCP server configurations
│   └── provider.py      # MCP client and session management
├── tools/               # Tool implementations
│   ├── codebase_explorer.py  # Code navigation tools
│   ├── code_searcher.py      # ripgrep wrapper
│   ├── web_search.py         # Tavily search
│   └── example.py            # Demo tools
├── constants.py         # Project-wide constants
├── registry.py          # Agent discovery and registration
└── cli.py               # CLI interface
```

## Core Concepts

### Agent

Base class defined in `interfaces/base.py`:

```python
class Agent(ABC):
    @abstractmethod
    async def run(
        self,
        input_data: Union[str, List[BaseMessage]],
        config: Optional[Dict[str, Any]] = None,
    ) -> Union[str, BaseMessage]:
        """Run the agent with the given input."""

    @abstractmethod
    def get_tools(self) -> List[Any]:
        """Return available tools for this agent."""
```

### Tool

Base class defined in `interfaces/base.py`:

```python
class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the tool."""

    @property
    @abstractmethod
    def description(self) -> str:
        """A description of what the tool does."""

    @abstractmethod
    def invoke(self, input_str: str) -> Any:
        """Execute the tool logic."""
```

### Agent Registry

Central registration system in `registry.py`:

```python
@AgentRegistry.register("agent-name", mcp_servers=["server1", "server2"])
class MyAgent(Agent):
    # Implementation
```

**Registry Methods:**
- `AgentRegistry.list_agents()` - List all registered agents
- `AgentRegistry.get(name)` - Get agent class by name
- `AgentRegistry.get_mcp_servers(name)` - Get allowed MCP servers for an agent
- `AgentRegistry.discover_agents()` - Auto-discover agents in `core/` package
- `AgentRegistry.set_strict_registration(strict=True)` - Enable strict mode (raises error on duplicate registrations)
- `AgentRegistry.register(name, mcp_servers, override=False)` - Register an agent with optional override flag

### MCP (Model Context Protocol)

External tool integration managed by `MCPProvider`.

**Available MCP Servers** (see `mcp/config.py`):
- `kiwi-com-flight-search` - Flight search
- `tinyfish` - AI assistant
- `web-fetch` - Web content fetching
- `tavily` - Web search

## Available Agents

### simple
Basic LLM assistant with no tools. Minimal example.

### chef
Recipe finder using local web search tool + Tavily MCP.

### travel
Flight search assistant using Kiwi MCP.

### news
AI news aggregator using web-fetch MCP.

### travel-coordinator
Orchestrates 3 specialist agents (flight, city intel, reviewer) with MCP tools.

### developer
Codebase exploration agent with specialized local tools and webfetch MCP:
- `find_files` - Fast file search via fd
- `discover_structure` - Directory tree exploration
- `get_file_outline` - Extract class/function signatures
- `read_file_fragment` - Read specific line ranges
- `code_search` - Fast pattern search via ripgrep
- `webfetch` (MCP) - Web content fetching

## Using Existing Agents

### CLI Usage

```bash
# List all available agents
agentic-run list

# View detailed information about an agent
agentic-run info developer

# Run an agent
agentic-run developer --input "Find all files with 'agent' in the name"

# With timeout override
agentic-run travel --input "BCN to LIS next week" --timeout 120
```

### Programmatic Usage

```python
from agentic_framework.registry import AgentRegistry
from agentic_framework.mcp import MCPProvider

# Get agent class
agent_cls = AgentRegistry.get("developer")

# Without MCP
agent = agent_cls()
result = await agent.run("Explain the project structure")

# With MCP (if agent supports it)
provider = MCPProvider(server_names=["webfetch"])
async with provider.tool_session() as mcp_tools:
    agent = agent_cls(initial_mcp_tools=mcp_tools)
    result = await agent.run("Search for...")
```

## Building New Agents

### Simple Agent (No Tools)

```python
from agentic_framework.interfaces.base import Agent
from agentic_framework.registry import AgentRegistry

@AgentRegistry.register("my-simple-agent", mcp_servers=None)
class MySimpleAgent(Agent):
    async def run(self, input_data, config=None):
        return f"Response to: {input_data}"

    def get_tools(self):
        return []
```

### LangGraph Agent with Local Tools

```python
from langchain_core.tools import StructuredTool
from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry

@AgentRegistry.register("my-agent", mcp_servers=None)
class MyAgent(LangGraphMCPAgent):
    @property
    def system_prompt(self) -> str:
        return "You are a helpful assistant specialized in X."

    def local_tools(self) -> Sequence[Any]:
        # Add your tools here
        return [
            StructuredTool.from_function(
                func=my_function,
                name="my_tool",
                description="Description of what the tool does",
            )
        ]
```

### LangGraph Agent with MCP Tools

```python
@AgentRegistry.register("my-agent", mcp_servers=["web-fetch", "tavily"])
class MyAgent(LangGraphMCPAgent):
    @property
    def system_prompt(self) -> str:
        return "You have access to web tools."

    def local_tools(self) -> Sequence[Any]:
        return []  # No local tools, just MCP
```

## Building New Tools

### Simple Tool

```python
from agentic_framework.interfaces.base import Tool

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Description of what the tool does."

    def invoke(self, input_str: str) -> Any:
        # Tool logic here
        return f"Result: {input_str}"
```

### Codebase Explorer Tool

```python
from agentic_framework.tools.codebase_explorer import CodebaseExplorer, Tool

class MyExplorerTool(CodebaseExplorer, Tool):
    @property
    def name(self) -> str:
        return "my_explorer"

    @property
    def description(self) -> str:
        return "Description of the explorer tool."

    def invoke(self, input_str: str) -> Any:
        # Use self.root_dir for project root
        # Tool logic here
        return result
```

### Export from tools/__init__.py

Add your tool to `tools/__init__.py`:

```python
from .my_tool import MyTool

__all__ = [
    # existing...
    "MyTool",
]
```

## Patterns and Conventions

### Agent Registration

- Always use `@AgentRegistry.register(name, mcp_servers)` decorator
- `mcp_servers=None` means no MCP access
- `mcp_servers=[]` or `mcp_servers=["server1"]` for MCP access

### System Prompts

- Define as a property named `system_prompt`
- Keep prompts concise and focused
- Include instructions on when/how to use tools

### Tool Initialization

- Tools in `local_tools()` should be initialized once (not per-call)
- Use `StructuredTool.from_function()` to wrap functions for LangChain
- Tool names should be snake_case

### Codebase Tools Usage

- Use `find_files` when you need to locate files by name/pattern
- Use `discover_structure` for project layout overview
- Use `get_file_outline` to skim file contents before reading
- Use `read_file_fragment` to read specific lines (format: `path:start:end`)
- Use `code_search` for fast global pattern matching

### Async/Await

- All agent `run()` methods are async
- Use `await` when calling agent methods
- MCP operations use async context managers

### Thread IDs

- LangGraph uses thread IDs for checkpointing
- Provide unique thread_ids for concurrent agent runs
- Format: `"1"`, `"agent:1"`, etc.

### Error Handling

- Tools should return error messages as strings, not raise exceptions
- CLI provides error reporting with `--verbose` flag
- MCP connection errors are handled via `MCPConnectionError`

## Testing

```python
# Test agent discovery
def test_my_agent_registered():
    AgentRegistry.discover_agents()
    assert "my-agent" in AgentRegistry.list_agents()

# Test agent behavior (use monkeypatch for external dependencies)
def test_my_agent_run(monkeypatch):
    # Mock external dependencies
    monkeypatch.setattr("module.Class", mock_class)
    agent = MyAgent()
    result = await agent.run("test")
    assert "expected" in result
```

## Constants

- `BASE_DIR` - Project root directory
- `LOGS_DIR` - Logs directory (logs/)
- Default timeout: 600 seconds
- Connection timeout: 15 seconds

## Notes for External LLMs

When working with this codebase:

1. **Agent Discovery**: All agents are auto-registered in `AgentRegistry`
2. **MCP Access**: Check `AgentRegistry.get_mcp_servers(name)` before using MCP
3. **Tool Conventions**: Tools return strings for errors, not exceptions
4. **Codebase Navigation**: The developer agent has specialized tools for code exploration
5. **Model Selection**: The default model name may be a placeholder - check environment variables
6. **File Patterns**: Ignore patterns include `.git`, `__pycache__`, `node_modules`, `.venv`, etc.
