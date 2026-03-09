# Agntrick

**Build AI agents with local tools and MCP servers.**

Agntrick is a Python framework for creating intelligent agents that combine:
- **Local Tools**: Python-based tools for codebase exploration, file operations, and more
- **MCP Servers**: Model Context Protocol integration for web fetching, search, and external services
- **Multiple LLM Providers**: Support for 10+ LLM providers (Anthropic, OpenAI, Google, etc.)
- **Flexible Configuration**: YAML-based configuration with environment variable support

## Quick Start

```bash
# Install
pip install agntrick

# Or with the WhatsApp integration
pip install agntrick[whatsapp]

# List available agents
agntrick list

# Run an agent
agntrick developer -i "Explain this codebase"
```

## Features

### Bundled Agents
- **developer**: Code exploration and editing with codebase tools
- **github-pr-reviewer**: PR review with inline comments
- **learning**: Educational tutorials with web resources
- **news**: News aggregation and summarization
- **youtube**: Video transcript analysis

### Local Tools
- Code search (ripgrep-based)
- File editing with validation
- Structure exploration
- Syntax validation (Tree-sitter)
- YouTube transcript extraction

### MCP Integration
- `fetch`: Fetch content from URLs
- `web-forager`: Web search capabilities
- Custom MCP server support

## Example

```python
from agntrick import AgentBase, AgentRegistry

@AgentRegistry.register("my-agent", mcp_servers=["fetch"])
class MyAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return "You are a helpful assistant."

# Run the agent
agent = MyAgent()
response = await agent.run("Hello!")
```

## Documentation

- [Getting Started](getting-started.md) - Installation and first steps
- [Configuration](configuration.md) - YAML config and environment variables
- [CLI Reference](cli.md) - Command-line interface
- [Agents](agents/index.md) - Built-in and custom agents
- [Tools](tools/index.md) - Local tools overview
- [MCP Servers](mcp/index.md) - MCP integration
- [LLM Providers](llm/index.md) - Provider setup

## Installation

```bash
# Core package
pip install agntrick

# With CLI tools
pip install agntrick[cli]

# With WhatsApp support
pip install agntrick[whatsapp]

# Everything
pip install agntrick[all]
```

## License

MIT License - see [LICENSE](../LICENSE) for details.
