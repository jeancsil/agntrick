# Docker Setup for Agentic Framework

This document explains how to run the Agentic Framework using Docker with mounted volumes for live code updates.

## Features

- ✅ **Live Code Updates**: Source code is mounted as a volume - no rebuild needed when you change Python files
- ✅ **Environment Variables**: Safely passed from `.env` file
- ✅ **Persistent Logs**: Logs are written to `agentic-framework/logs/` and accessible from both host and container
- ✅ **UV Package Manager**: Uses `uv` for fast dependency management, same as local development

## Prerequisites

- Docker and Docker Compose installed
- `.env` file with your API keys (see `.env.example`)

## Quick Start

### 1. Build the Docker Image

```bash
make docker-build
```

This builds the image and installs all dependencies using `uv`.

### 2. Run an Agent

Run the chef agent:

```bash
make docker-chef INPUT="I have bread, tuna, lettuce and mayo"
```

Or run any agent using the generic command:

```bash
make docker-run CMD="chef -i 'your input here'"
make docker-run CMD="list"
```

### 3. View Logs

Logs are automatically written to `agentic-framework/logs/agent.log` and are accessible from your host machine:

```bash
# View logs from host
tail -f agentic-framework/logs/agent.log

# Or view Docker container logs
make docker-logs
```

## Available Make Targets

| Target | Description |
|--------|-------------|
| `make docker-build` | Build the Docker image |
| `make docker-run CMD="..."` | Run any agentic-run command |
| `make docker-chef INPUT="..."` | Run the chef agent |
| `make docker-test` | Run tests in Docker |
| `make docker-lint` | Run linting in Docker |
| `make docker-shell` | Open an interactive shell in the container |
| `make docker-logs` | View container logs |
| `make docker-start` | Start container in detached mode |
| `make docker-stop` | Stop the container |
| `make docker-clean` | Remove containers, images, and volumes |

## How It Works

### Volume Mounts

The `docker-compose.yml` configures the following mounts:

```yaml
volumes:
  # Source code (read-only) - changes reflected immediately
  - ./agentic-framework/src:/app/agentic-framework/src:ro
  - ./agentic-framework/tests:/app/agentic-framework/tests:ro
  
  # Logs (read-write) - accessible from host
  - ./agentic-framework/logs:/app/agentic-framework/logs
  
  # Project files (read-only)
  - ./agentic-framework/pyproject.toml:/app/agentic-framework/pyproject.toml:ro
  - ./agentic-framework/uv.lock:/app/agentic-framework/uv.lock:ro
```

### Environment Variables

Environment variables are loaded from `.env`:

```yaml
env_file:
  - .env
```

This safely passes your API keys to the container without embedding them in the image.

### When to Rebuild

You **DO NOT** need to rebuild when:
- ✅ Changing Python source code in `src/` or `tests/`
- ✅ Modifying `.env` variables

You **DO** need to rebuild when:
- ⚠️ Adding/removing dependencies in `pyproject.toml`
- ⚠️ Updating `uv.lock`
- ⚠️ Changing the Dockerfile

To rebuild:
```bash
make docker-build
```

## Advanced Usage

### Running Tests with Coverage

```bash
make docker-test
```

### Interactive Shell

Access the container shell for debugging:

```bash
make docker-shell
```

Then inside the container:
```bash
uv --directory agentic-framework run agentic-run --help
uv --directory agentic-framework run agentic-run list
```

### Custom Commands

Run any `agentic-run` command:

```bash
# List available agents
make docker-run CMD="list"

# Run with verbose logging
make docker-run CMD="chef -i 'your input' --verbose"

# Run with custom timeout
make docker-run CMD="chef -i 'your input' --timeout 120"
```

### Direct Docker Compose Usage

You can also use `docker compose` directly:

```bash
# Run a command
docker compose run --rm agentic-framework uv --directory agentic-framework run agentic-run chef -i "your input"

# Start in detached mode
docker compose up -d

# Stop
docker compose down

# View logs
docker compose logs -f
```

## Troubleshooting

### Logs Not Appearing

Logs are written to `agentic-framework/logs/agent.log`. Make sure:
1. The directory exists: `mkdir -p agentic-framework/logs`
2. You have write permissions
3. Check the log file: `cat agentic-framework/logs/agent.log`

### Environment Variables Not Working

1. Ensure `.env` file exists in the project root
2. Check the file is not empty: `cat .env`
3. Rebuild the container: `make docker-build`

### Code Changes Not Reflected

If you're changing code but not seeing updates:
1. Verify volumes are mounted correctly: `docker compose config`
2. Ensure you're editing files in the mounted directories (`src/`, `tests/`)
3. The container runs each command fresh, so changes should be immediate

### Permission Issues

If you encounter permission issues with logs:
```bash
# Fix permissions on the logs directory
chmod -R 755 agentic-framework/logs
```

## Comparison: Local vs Docker

| Aspect | Local | Docker |
|--------|-------|--------|
| Setup | `make install` | `make docker-build` |
| Run Agent | `make run` | `make docker-chef INPUT="..."` |
| Tests | `make test` | `make docker-test` |
| Lint | `make lint` | `make docker-lint` |
| Logs | `agentic-framework/logs/agent.log` | Same location |
| Code Changes | Immediate | Immediate (via volumes) |
| Dependencies | Local `.venv` | Container image |

## Best Practices

1. **Use `.env` for secrets**: Never commit API keys to version control
2. **Check logs regularly**: Monitor `agentic-framework/logs/agent.log`
3. **Rebuild after dependency changes**: Run `make docker-build` when updating `pyproject.toml`
4. **Use `--rm` flag**: Automatically remove containers after use (already in Makefile targets)
5. **Clean up periodically**: Run `make docker-clean` to remove old images and volumes
