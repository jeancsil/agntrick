# Agntrick

Multi-tenant WhatsApp AI platform. LangGraph-based Python agents and a Go WhatsApp gateway.

[![License](https://img.shields.io/github/license/jeancsil/agntrick?style=plastic)](LICENSE)

---

## Requirements

**Users:** Python 3.12+

**Contributors:** Python 3.12+, Go 1.21+, [uv](https://docs.astral.sh/uv/)

> uv can install Python for you: `uv python install 3.12`.

---

## Install

### Users (pip)

```bash
pip install agntrick
agntrick init       # wizard writes ~/.agntrick.yaml + .env
agntrick serve      # API on :8000
```

uv users can substitute `uv tool install agntrick`.

For WhatsApp, download the gateway binary from the [latest release](https://github.com/jeancsil/agntrick/releases/latest) and run it in a second terminal.

### Contributors (clone)

```bash
git clone https://github.com/jeancsil/agntrick.git
cd agntrick
uv sync
cp .env.example .env   # set OPENAI_API_KEY or ANTHROPIC_API_KEY
uv run agntrick serve
```

For WhatsApp: `cd gateway && go run .` in a second terminal.

---

## Quick test (no WhatsApp)

```bash
agntrick chat "hello"          # users
uv run agntrick chat "hello"   # contributors
```

---

## Toolbox (optional, recommended)

`agntrick-toolkit` adds curated CLI tools (pdf, pandoc, jq, ffmpeg, ripgrep, git, and more) over MCP. Without it, agntrick runs fine — agents just have fewer tools.

Setup: see [`docs/toolbox.md`](docs/toolbox.md). Source: <https://github.com/jeancsil/agntrick-toolkit>.

---

## Configuration

- `.env` — API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, optional `GROQ_AUDIO_API_KEY`, `GITHUB_TOKEN`, etc.)
- `.agntrick.yaml` — tenants, default agents, logging, auth

Full reference: [`docs/configuration.md`](docs/configuration.md).

---

## Writing an agent

```python
from agntrick import AgentBase, AgentRegistry

@AgentRegistry.register("my-assistant", mcp_servers=["fetch"])
class MyAssistant(AgentBase):
    @property
    def system_prompt(self) -> str:
        return "You are a helpful assistant with web access."
```

More: [`docs/agents.md`](docs/agents.md).

---

## Development

```bash
make check && make test
```

Working with [Claude Code](https://docs.claude.com/en/docs/claude-code)? This repo ships project-specific skills, subagents, and hooks — see [`docs/claude-code.md`](docs/claude-code.md).

Architecture and execution flow: [`CLAUDE.md`](CLAUDE.md).

---

## Deployment

See [`docs/deployment.md`](docs/deployment.md) for the bare-metal VPS deploy flow.

---

## License

MIT. See [`LICENSE`](LICENSE).
