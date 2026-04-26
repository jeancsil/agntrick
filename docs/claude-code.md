# Claude Code automations

This repository ships project-specific automations for [Claude Code](https://docs.claude.com/en/docs/claude-code). They live under `.claude/` and become available automatically when working on this checkout.

This page is a read-only inventory. The active contributor reference (with rationale, conventions, and code-quality rules) is [`CLAUDE.md`](../CLAUDE.md).

## Skills (`.claude/skills/`)

Slash commands you can invoke from a Claude Code session.

| Skill | Purpose |
|---|---|
| `agntrick-add-agent` | Scaffold a new agent — creates `agents/<name>.py`, prompt `.md`, and a unit test, wired to the registry. |
| `agntrick-add-tool` | Scaffold a new tool — creates `tools/<name>.py`, exports it from `tools/__init__.py`, adds a unit test. |
| `agntrick-list-agents` | List all registered agents with their MCP servers, tool categories, prompt status, and local tools. |
| `integration-test` | Run end-to-end integration verification: real prompt loading, real tool registration, real agent instantiation. Catches gaps unit tests miss. |
| `release` | End-to-end release flow — version bump, changelog, tag, build, publish to PyPI. |

Source files: `.claude/skills/<name>/SKILL.md`.

## Subagents (`.claude/agents/`)

Specialized agents Claude Code can dispatch for focused review tasks.

| Agent | When to use |
|---|---|
| `diagram-sync-checker` | After modifying `agent.py`, `graph.py`, `mcp/provider.py`, `tools/manifest.py`, `api/routes/`, or `whatsapp/`. Verifies Mermaid diagrams in `CLAUDE.md` still match the code. |
| `go-test-runner` | After modifying `gateway/`. Runs `go vet`, `go fmt`, `go test`. |
| `prompt-consistency-checker` | After adding/removing agents. Cross-references registrations against prompt `.md` files in `prompts/`. |
| `python-dep-auditor` | After adding/removing packages. Audits `pyproject.toml` against actual imports. |

Source files: `.claude/agents/<name>.md`.

## Hooks (`.claude/settings.json` and `settings.local.json`)

| Hook | Effect |
|---|---|
| `PreToolUse` on `Write\|Edit` | Blocks edits to `.bak` files and to anything inside `.claude/worktrees/`. |
| `PostToolUse` on `Write\|Edit` for `.py` | Auto-formats with `ruff format` and `ruff check --fix`. |
| `PostToolUse` on `Write\|Edit` for `.go` | Auto-formats with `gofmt -w` (lives in `settings.local.json`). |

Source: `.claude/settings.json`, `.claude/settings.local.json`.

## Updating this page

When you add, remove, or rename anything under `.claude/`, update this page in the same commit. Source-of-truth files are referenced inline above so a curious reader can always read the actual implementation.
