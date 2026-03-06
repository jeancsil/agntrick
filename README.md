# Agentic Framework

Build AI agents that combine local tools and MCP servers in a single runtime.

## What You Get

- Registry-based agent architecture with auto-discovery.
- MCP integration for external capabilities.
- Local code tools for search, structure discovery, and safe edits.
- CLI-first workflows for running and inspecting agents.
- Docker-first development setup.

## Available Agents

| Agent | How to run | Primary use |
| --- | --- | --- |
| `developer` | `bin/agent.sh developer -i "..."` | Code exploration and editing workflows |
| `travel-coordinator` | `bin/agent.sh travel-coordinator -i "..."` | Multi-agent travel planning |
| `chef` | `bin/agent.sh chef -i "..."` | Ingredient-based recipe help |
| `news` | `bin/agent.sh news -i "..."` | AI-news aggregation |
| `travel` | `bin/agent.sh travel -i "..."` | Flight-focused planning |
| `simple` | `bin/agent.sh simple -i "..."` | Minimal conversational agent |
| `github-pr-reviewer` | `bin/agent.sh github-pr-reviewer -i "..."` | Automated pull request review |
| `whatsapp` (CLI command) | `bin/agent.sh whatsapp --config config/whatsapp.yaml` | WhatsApp channel agent |

Detailed agent behavior and configuration: [docs/agents.md](docs/agents.md)

## Local Tools (Built In)

| Tool | Purpose |
| --- | --- |
| `find_files` | Fast file discovery via `fd` |
| `discover_structure` | Directory structure mapping |
| `get_file_outline` | Signature extraction via AST parsing |
| `read_file_fragment` | Targeted file reads by line range |
| `code_search` | Fast code search via `ripgrep` |
| `edit_file` | Controlled file editing operations |

Tool details: [docs/tools.md](docs/tools.md)

## MCP Servers (Built In)

| Server | Purpose |
| --- | --- |
| `kiwi-com-flight-search` | Flight data and search |
| `web-fetch` | Web page retrieval and clean extraction |
| `duckduckgo-search` | Web search |

Server details: [docs/mcp-servers.md](docs/mcp-servers.md)

## LLM Providers

The framework supports multiple providers via LangChain integrations including Anthropic, OpenAI, Azure OpenAI, Google GenAI, Google Vertex AI, Groq, Mistral, Cohere, AWS Bedrock, Ollama, and Hugging Face.

Provider setup and environment variables: [docs/llm-providers.md](docs/llm-providers.md)

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
```

Set one provider credential in `.env` (for example `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`).

### 2. Build and Run (Docker Recommended)

```bash
make docker-build
bin/agent.sh list
bin/agent.sh developer -i "Explain the project structure"
```

### 3. Run a Different Built-in Agent

```bash
bin/agent.sh chef -i "I have chicken, rice, and soy sauce. What can I make?"
```

## CLI Reference

```bash
# list available agents
bin/agent.sh list

# show details for one agent
bin/agent.sh info developer

# run an agent with input
bin/agent.sh developer -i "Analyze this module"

# run with timeout (seconds)
bin/agent.sh developer -i "Refactor suggestions" -t 120

# run with verbose logging
bin/agent.sh developer -i "Hello" -v

# run WhatsApp command
bin/agent.sh whatsapp --config config/whatsapp.yaml
```

## Create Your Own Agent

```python
from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry


@AgentRegistry.register("my-agent", mcp_servers=["web-fetch"])
class MyAgent(LangGraphMCPAgent):
    @property
    def system_prompt(self) -> str:
        return "You are a custom MCP-enabled agent."
```

Then run:

```bash
bin/agent.sh my-agent -i "Summarize https://example.com"
```

## Documentation Index

- User guide: [README.md](README.md)
- Agent catalog: [docs/agents.md](docs/agents.md)
- Tool docs: [docs/tools.md](docs/tools.md)
- MCP docs: [docs/mcp-servers.md](docs/mcp-servers.md)
- Provider docs: [docs/llm-providers.md](docs/llm-providers.md)
- Maintainer/LLM-agent rules: [AGENTS.md](AGENTS.md)
- Detailed maintainer topics: [docs/agents/README.md](docs/agents/README.md)

## Local Development (Without Docker)

```bash
make install
make format
make check
make test
```

Run CLI directly with `uv`:

```bash
uv --project agentic-framework run agentic-run developer -i "Hello"
```

## Development Quality Gates

From repository root:

```bash
make format   # apply ruff auto-fixes + formatting
make check    # mypy + ruff lint + format check
make test     # pytest + coverage
```

Mypy is an enforced gate in `make check`, not an optional step.

## Contributing

Before opening a pull request:

1. Run `make format`.
2. Run `make check`.
3. Run `make test`.
4. Update docs for any user-facing behavior changes.

Contributor and coding-agent workflow details: [AGENTS.md](AGENTS.md)

## License

MIT. See [LICENSE](LICENSE).
