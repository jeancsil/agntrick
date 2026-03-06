# Runtime and Dependencies

## Working Directory

Code is in `agentic-framework/`. The root `Makefile` is one level above.

```bash
make -C .. format
make -C .. check
make -C .. test
```

## `uv` Is Mandatory

Use `uv` for dependency and Python command execution.

Allowed examples:

```bash
uv sync
uv add package-name
uv add --dev package-name
uv run <command>
uv lock --upgrade-package package-name
```

Forbidden examples:

```bash
pip install <package>
pipenv install <package>
poetry add <package>
```

## Docker Is Preferred

Prefer Docker for local runs and tests where practical.

```bash
make docker-build
bin/agent.sh developer -i "Explain this project"
docker compose run --rm app make test
```
