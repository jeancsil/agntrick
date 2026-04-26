# Toolbox (`agntrick-toolkit`)

Optional but recommended. Provides curated CLI tools (pdf, pandoc, jq, ffmpeg, ripgrep, git, and more) over MCP, exposing them to your agents.

Without the toolbox, agntrick still runs — agents simply lack those tools.

## Source

- Repository: <https://github.com/jeancsil/agntrick-toolkit>
- Python package name (unpublished on PyPI): `agntrick-toolbox`

The toolbox is not currently available on PyPI. Install from source.

## Setup

```bash
# Clone next to the agntrick checkout (any path is fine)
git clone https://github.com/jeancsil/agntrick-toolkit.git ~/agntrick-toolkit
cd ~/agntrick-toolkit
uv sync
```

Tell agntrick where to find it via the environment variable:

```bash
# In agntrick's .env
AGNTRICK_TOOLKIT_PATH=/home/you/agntrick-toolkit
```

When `AGNTRICK_TOOLKIT_PATH` is set and points to a valid checkout, `agntrick chat` and `agntrick serve` start the toolbox subprocess automatically.

## Verifying

```bash
# After agntrick serve starts the toolbox
curl -s http://localhost:8080/health
# Expected: 200 OK
```

In a chat session:

```bash
agntrick chat "Summarize the PDF at ./report.pdf"
```

If the agent reports it cannot find a `pdf` tool, the toolbox is not running — check `agntrick serve` logs for `MCP` errors.

## Running standalone

If you prefer to manage the toolbox yourself (e.g. systemd unit), start it manually:

```bash
cd ~/agntrick-toolkit
uv run toolbox-server
```

It listens on port 8080.
