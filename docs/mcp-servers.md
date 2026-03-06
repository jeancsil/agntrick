# MCP Servers

Built-in Model Context Protocol (MCP) servers available in this framework.

## Server Overview

| Server | Purpose | API Key Required |
| --- | --- | --- |
| `kiwi-com-flight-search` | Search real-time flights | No |
| `web-fetch` | Fetch and clean web content | No |
| `duckduckgo-search` | Web search | No |

## kiwi-com-flight-search

Provides flight lookup data used by travel-focused agents.

## web-fetch

Fetches and extracts readable content from web pages.

## duckduckgo-search

Provides search results used by agents that need current web discovery.

## Add a Custom MCP Server

1. Update `agentic-framework/src/agentic_framework/mcp/config.py` with a new server entry.
2. Register the server key in the target agent decorator via `mcp_servers=[...]`.
3. Validate by running the agent from CLI.

Example:

```python
@AgentRegistry.register("my-agent", mcp_servers=["web-fetch", "duckduckgo-search"])
class MyAgent(LangGraphMCPAgent):
    ...
```
