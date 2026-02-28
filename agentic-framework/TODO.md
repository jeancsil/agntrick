# TODO

This file tracks bugs, missing features, gaps, and improvement suggestions.

## Bugs

### None currently identified

## Missing Features

### Testing

- [x] Add test file for `developer_agent.py` (`tests/test_developer_agent.py`)
- [ ] Add integration tests for CLI commands
- [ ] Add end-to-end tests for MCP server connections
- [ ] Add tests for concurrent agent execution (multiple thread IDs)

### Documentation

- [ ] Add inline documentation (docstrings) for all public APIs
- [ ] Add examples for each agent in AGENTS.md
- [ ] Add contribution guidelines
- [ ] Add troubleshooting section for common MCP connection issues

### CLI

- [x] Add command to view agent details (system prompt, tools, MCP servers)
- [ ] Add command to list available MCP servers and their status
- [ ] Add interactive mode for multi-turn conversations
- [ ] Add streaming output support for long-running responses

### Tools

- [ ] Add file editing tool to `CodebaseExplorer` tools
- [ ] Add git integration tools (status, diff, log)
- [ ] Add shell execution tool with safety guards
- [ ] Add test runner tool (pytest wrapper)

## Gaps

### Registry

- [x] Registry doesn't validate duplicate registrations (silent overwrite)
- [ ] No way to unregister an agent
- [ ] No agent metadata (version, author, description)

### MCP Provider

- [ ] No connection health check/status API
- [ ] No way to list available MCP servers without initializing provider
- [ ] Fallback behavior on server failure could be improved
- [ ] No caching of MCP tool schemas

### Agent Base Classes

- [ ] `LangGraphMCPAgent` doesn't expose model configuration for customization
- [ ] No shared state management between coordinated agents
- [ ] No built-in rate limiting for tool usage

## Improvement Suggestions

### Code Quality

- [x] The `CalculatorTool` uses `eval()` which is dangerous - should use `ast.literal_eval` or a proper parser
- [ ] Type hints could be more complete throughout
- [ ] Some imports are scattered and could be organized better

### Performance

- [ ] Consider adding LRU cache for tool results
- [ ] MCP tool loading could be parallelized (with anyio task identity fixes)
- [ ] File search results could be paginated for large codebases

### Usability

- [ ] Add environment variable validation at startup
- [ ] Add configuration file support (e.g., `.agentic-framework.toml`)
- [ ] Add agent aliases/shortcuts
- [ ] Better error messages for missing external tools (fd, rg, fzf)

### Architecture

- [ ] Consider splitting `CodebaseExplorer` tools into separate files
- [ ] Could add a plugin system for third-party agents/tools
- [ ] Consider separating agent definitions from the registry decorator
- [ ] Add support for LangChain's tool call retry middleware

## Potential Future Enhancements

### Agent Capabilities

- [ ] Add memory management agents (conversation history)
- [ ] Add planning agents (task decomposition)
- [ ] Add reflection agents (self-critique and improvement)
- [ ] Add multi-modal support (image, audio, document parsing)

### Integration

- [ ] Add LangSmith tracing integration
- [ ] Add support for custom LLM providers
- [ ] Add support for vector stores (RAG capabilities)
- [ ] Add support for databases (SQL tools)

### Observability

- [ ] Add metrics collection (tool usage, response times)
- [ ] Add structured logging format
- [ ] Add agent execution visualization
- [ ] Add cost tracking for LLM API calls

## Environment Setup Notes

### External Tool Dependencies

The developer agent requires these external tools:
- `fd` - Fast file search
- `rg` (ripgrep) - Fast content search
- `fzf` - Fuzzy finder (optional, with fallback)

Installation:
```bash
# macOS
brew install fd ripgrep fzf

# Ubuntu/Debian
apt install fd-find ripgrep fzf
```

## Deprecated / Legacy

None currently.
