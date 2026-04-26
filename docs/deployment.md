# Deployment

Production deployment target: bare-metal Linux (Ubuntu 22.04+) on a small VPS. Reference target = a $6/month Digital Ocean droplet (1 vCPU, 1 GB RAM). Docker is intentionally not used in production — overhead is meaningful at this footprint.

## Architecture on a single host

Three long-running processes:

1. **Toolbox MCP server** — `agntrick-toolkit`, runs on port 8080. Provides curated CLI tools (pdf, ffmpeg, ripgrep, etc.) over MCP.
2. **Python API** — `agntrick serve`, runs on port 8000.
3. **Go gateway** — `agntrick-gateway` binary, connects to WhatsApp and forwards messages to the API.

All three are managed by `scripts/deploy-do.sh`.

## First-time setup on the droplet

```bash
# As the deploy user
git clone https://github.com/jeancsil/agntrick.git ~/projects/agntrick
git clone https://github.com/jeancsil/agntrick-toolkit.git ~/agntrick-toolkit

cd ~/projects/agntrick
cp .env.example .env
# edit .env — set API keys

cp .agntrick.yaml.example .agntrick.yaml   # if a template exists; otherwise hand-craft
# edit .agntrick.yaml — set tenants

./scripts/deploy-do.sh
```

The `deploy-do.sh` driver runs from the droplet and orchestrates:

- `pull` — `git pull` in both `~/projects/agntrick` and `~/agntrick-toolkit`
- `build` — `uv sync` in both, install Playwright Chromium if missing, `go build` the gateway
- `start` — start toolbox, wait for `:8080`, start API, wait for `:8000/health`, start gateway

## Operating commands

| Goal | Command |
|---|---|
| Full deploy (pull + build + restart) | `./scripts/deploy-do.sh` or `make deploy-do` |
| Status of all three services | `./scripts/deploy-do.sh status` |
| Stop everything | `./scripts/deploy-do.sh stop` or `make deploy-do-stop` |
| Restart without re-pulling | `./scripts/deploy-do.sh restart` |
| Tail all logs | `./scripts/deploy-do.sh logs` or `make deploy-do-logs` |

PIDs are tracked in `~/projects/agntrick/.agntrick-pids` and `~/agntrick-toolkit/.toolbox.pid`. Logs go to `~/.local/share/agntrick/logs/`.

## Updating

```bash
ssh deploy@droplet
cd ~/projects/agntrick
./scripts/deploy-do.sh   # pulls, rebuilds, restarts
```

`scripts/deploy-do.sh logs` to confirm services came back healthy.

## Why no Docker

- Memory budget is tight on a 1 GB droplet; Docker overhead matters.
- All three services are simple processes — `nohup` + PID files + a deploy script is enough.
- `Dockerfile` and `docker-compose.yml` exist in the repo for development convenience but are not part of the production deploy. They are unmaintained relative to `scripts/deploy-do.sh`.

## Roadmap

A future change (Spec 2) will switch the API from `git clone + uv sync` to `pip install agntrick`, mirroring the end-user install path. Until then, the droplet runs from source.
