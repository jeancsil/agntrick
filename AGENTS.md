# AGENTS.md

Guidance for LLM agents that modify this repository.

## Purpose

Use this file as a quick operating index. Detailed instructions are split by topic under `docs/agents/`.

## Non-Negotiables

1. Always run `make -C .. check` after code changes.
2. Always run `make -C .. test` after code changes.
3. Fix all lint and test failures before claiming completion.
4. Use `uv` exclusively for dependency and Python command execution.
5. Prefer Docker workflows when possible.
6. Do not commit or push unless explicitly requested.
7. Do not add dependencies without discussion.
8. Do not edit generated files such as `uv.lock` directly.
9. Keep README and docs aligned with behavior changes.
10. Follow existing patterns before introducing new ones.
11. Treat mypy as a hard gate (`disallow_untyped_defs=true`, `check_untyped_defs=true`, `warn_return_any=true`).

## Working Directory

Framework code lives in `agentic-framework/` and the `Makefile` is one level up.

```bash
# From agentic-framework/
make -C .. check
make -C .. test
make -C .. format
```

## Topic Index

| Topic | Detailed doc |
| --- | --- |
| Workflow (understand -> implement -> verify -> repair) | [docs/agents/workflow.md](docs/agents/workflow.md) |
| Runtime, Docker, and `uv` policy | [docs/agents/runtime-and-dependencies.md](docs/agents/runtime-and-dependencies.md) |
| Quality gates and CI expectations | [docs/agents/quality-gates.md](docs/agents/quality-gates.md) |
| Coding standards (typing, async, tool errors) | [docs/agents/coding-standards.md](docs/agents/coding-standards.md) |
| Testing standards and coverage | [docs/agents/testing.md](docs/agents/testing.md) |
| Project map and key files | [docs/agents/project-map.md](docs/agents/project-map.md) |
| Keeping user docs in sync | [docs/agents/documentation.md](docs/agents/documentation.md) |
| Agent docs index | [docs/agents/README.md](docs/agents/README.md) |

## Task Checklist

Before edits:
- Read relevant source and tests.
- Confirm there is no existing equivalent implementation.

During edits:
- Keep types and docstrings consistent with strict mypy standards.
- Follow existing patterns and keep changes focused.

Before completion:
- Run `make -C .. format` when lint/format corrections are required.
- Run `make -C .. check`.
- Run `make -C .. test`.
- Update docs if behavior, APIs, agents, tools, or MCP mappings changed.
