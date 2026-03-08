# Agent with MCP Example

Use MCP servers for external tool capabilities.

## Basic MCP Agent

```python
from agntrick import AgentBase, AgentRegistry

@AgentRegistry.register("web-fetcher", mcp_servers=["fetch"])
class WebFetcherAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return "You can fetch content from URLs."
```

## Running with MCP

```python
import asyncio
from agntrick import AgentRegistry
from agntrick.mcp import MCPProvider

async def main():
    agent_cls = AgentRegistry.get("web-fetcher")
    mcp_servers = AgentRegistry.get_mcp_servers("web-fetcher")

    provider = MCPProvider(server_names=mcp_servers)

    async with provider.tool_session() as mcp_tools:
        agent = agent_cls(initial_mcp_tools=mcp_tools)
        result = await agent.run("Fetch https://example.com and summarize it")
        print(result)

asyncio.run(main())
```

## Multiple MCP Servers

```python
@AgentRegistry.register(
    "web-researcher",
    mcp_servers=["fetch", "web-forager"]
)
class WebResearcherAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return """You are a research assistant.
        Use web-forager to search for information.
        Use fetch to get detailed content from URLs."""
```

## MCP + Local Tools

Combine MCP with local Python tools:

```python
from typing import Sequence, Any
from langchain_core.tools import StructuredTool
from agntrick import AgentBase, AgentRegistry
from agntrick.tools import CodeSearcher

def analyze_code(code: str) -> str:
    """Analyze code for patterns."""
    return f"Code analysis: {len(code)} characters"

@AgentRegistry.register(
    "code-researcher",
    mcp_servers=["fetch"]
)
class CodeResearcherAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return "You analyze code and fetch documentation."

    def local_tools(self) -> Sequence[Any]:
        return [
            CodeSearcher("."),
            StructuredTool.from_function(
                func=analyze_code,
                name="analyze_code",
                description="Analyze code for patterns",
            ),
        ]
```

## CLI Usage

```bash
# MCP servers are connected automatically
agntrick web-fetcher -i "Fetch https://docs.python.org/3/library/asyncio.html"
agntrick web-researcher -i "Research Python asyncio best practices"
```

## Error Handling

```python
from agntrick.mcp import MCPConnectionError

async def run_with_error_handling():
    provider = MCPProvider(server_names=["fetch"])

    try:
        async with provider.tool_session() as tools:
            agent = agent_cls(initial_mcp_tools=tools)
            return await agent.run("Fetch something")
    except MCPConnectionError as e:
        print(f"MCP connection failed: {e}")
        # Fall back to local-only operation
        agent = agent_cls()
        return await agent.run("Try to help without web access")
```

## Custom MCP Server

Add your own MCP server:

```yaml
# .agntrick.yaml
mcp:
  custom:
    my-server:
      url: https://my-server.com/mcp
      transport: sse
```

```python
@AgentRegistry.register("custom-mcp", mcp_servers=["my-server"])
class CustomMCPAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return "You use custom MCP tools."
```

## See Also

- [MCP Overview](../mcp/index.md) - MCP integration guide
- [MCP Servers](../mcp/servers.md) - Bundled servers
- [Tools Overview](../tools/index.md) - Local tools
