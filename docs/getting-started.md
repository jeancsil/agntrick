# Getting started

There are two supported paths. Pick the one that matches what you want to do.

## I want to use agntrick (pip)

Requirements: Python 3.12+.

```bash
pip install agntrick
agntrick init       # wizard writes ~/.agntrick.yaml + .env
agntrick serve      # API on :8000
```

uv users can substitute `uv tool install agntrick` for the install step.

For WhatsApp, download the Go gateway binary from the [latest release](https://github.com/jeancsil/agntrick/releases/latest) and run it in a second terminal. See [`docs/deployment.md`](deployment.md) for production setup.

## I want to develop on agntrick (clone)

Requirements: Python 3.12+, Go 1.21+, [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/jeancsil/agntrick.git
cd agntrick
uv sync
cp .env.example .env
# edit .env — set OPENAI_API_KEY or ANTHROPIC_API_KEY
uv run agntrick serve
```

For WhatsApp:

```bash
cd gateway && go run .
```

Then open `http://localhost:8000/api/v1/whatsapp/qr/<tenant>/page` and scan with WhatsApp.

## Smoke test (no WhatsApp)

```bash
agntrick chat "hello"          # users path
uv run agntrick chat "hello"   # contributors path
```

## Where to next

- [`docs/configuration.md`](configuration.md) — `.env` and `.agntrick.yaml` reference
- [`docs/agents.md`](agents.md) — what ships, how to write your own
- [`docs/architecture.md`](architecture.md) — how the platform fits together
- [`docs/api.md`](api.md) — HTTP endpoints
- [`docs/toolbox.md`](toolbox.md) — optional MCP tool server
- [`docs/deployment.md`](deployment.md) — production deploy on a VPS
- [`docs/claude-code.md`](claude-code.md) — automations for Claude Code users
