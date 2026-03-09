# Agntrick Examples

This directory contains example agents demonstrating how to use the agntrick library.

## Examples

### 1. Simple Agent (`simple_agent.py`)

A minimal agent implementation without MCP server access.

```bash
agntrick run simple -i "What is the capital of France?"
```

### 2. Chef Agent (`chef_agent.py`)

A recipe-focused agent with MCP web search capabilities.

```bash
agntrick run chef -i "I have eggs, cheese, and bread - what can I make?"
```

### 3. Travel Coordinator (`travel_coordinator.py`)

A multi-agent coordinator pattern with multiple specialist agents.

```bash
agntrick run travel-coordinator -i "Plan a 3-day trip to Paris from NYC in June"
```

## Creating Custom Agents

### Basic Pattern

```python
from agntrick import AgentBase, AgentRegistry

@AgentRegistry.register("my-agent", mcp_servers=["fetch"])
class MyAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return "You are a helpful assistant."

    # That's it! The base class handles the rest.
```

### With Local Tools

```python
from typing import Any, Sequence
from langchain_core.tools import StructuredTool
from agntrick import AgentBase, AgentRegistry
from agntrick.tools import CodeSearcher

@AgentRegistry.register("developer", mcp_servers=["fetch"])
class DeveloperAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return "You are a software engineer assistant."

    def local_tools(self) -> Sequence[Any]:
        searcher = CodeSearcher(root_dir=".")
        return [
            StructuredTool.from_function(
                func=searcher.invoke,
                name=searcher.name,
                description=searcher.description,
            )
        ]
```

### With External Prompts

```python
from agntrick import AgentBase, AgentRegistry, load_prompt

@AgentRegistry.register("my-agent", mcp_servers=["fetch"])
class MyAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        prompt = load_prompt("my-agent")  # Loads from prompts/my-agent.md
        if prompt:
            return prompt
        return "Default fallback prompt."
```

## Running Examples

### Using CLI

```bash
# List all agents
agntrick list

# Get agent info
agntrick info chef

# Run an agent
agntrick run chef -i "What's for dinner?"

# With timeout
agntrick run travel-coordinator -i "Plan my trip" --timeout 120
```

### Using Python

```python
import asyncio
from agntrick import AgentRegistry

async def main():
    # Discover agents
    AgentRegistry.discover_agents()

    # Get agent class
    AgentClass = AgentRegistry.get("chef")

    # Create instance
    agent = AgentClass()

    # Run agent
    result = await agent.run("I have eggs and cheese")
    print(result)

asyncio.run(main())
```

## MCP Servers

Agents can connect to MCP servers for extended capabilities:

| Server | Purpose | Tools |
|--------|---------|-------|
| `fetch` | Fetch content from URLs | web_fetch |
| `web-forager` | Web search | web_search |
| `kiwi-com-flight-search` | Flight search | search_flights |

## Next Steps

1. Read the [Getting Started Guide](../docs/getting-started.md)
2. Explore the [API Reference](../docs/api/)
3. Create your own agents!
