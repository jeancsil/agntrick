# Project Map

```
agentic-framework/
├── src/agentic_framework/
│   ├── core/           # Agent implementations
│   ├── interfaces/     # Agent and tool interfaces
│   ├── mcp/            # MCP configuration and provider
│   ├── tools/          # Local tool implementations
│   ├── registry.py     # Agent registration and discovery
│   └── cli.py          # Typer CLI entrypoint
├── tests/              # Test suite
├── pyproject.toml      # Project configuration
└── uv.lock             # Generated lockfile
```

## Key Files

- `agentic-framework/src/agentic_framework/core/langgraph_agent.py`: base runtime for MCP-enabled agents.
- `agentic-framework/src/agentic_framework/registry.py`: agent registration and lookup.
- `agentic-framework/src/agentic_framework/mcp/config.py`: canonical MCP server definitions.
- `agentic-framework/src/agentic_framework/cli.py`: CLI commands and runtime orchestration.
- `agentic-framework/pyproject.toml`: lint/test/type-check configuration (including mypy rules).
