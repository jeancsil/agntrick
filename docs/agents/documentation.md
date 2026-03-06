# Documentation Sync

Keep user docs and maintainer docs aligned with implementation.

## Update README and docs when you

- Add, remove, or rename agents.
- Add, remove, or rename tools.
- Add, remove, or rename MCP servers.
- Change CLI usage or configuration expectations.
- Change public behavior that users rely on.

## Minimum Documentation Pass

1. Update root `README.md` for user-visible changes.
2. Update `docs/agents.md` when built-in agent behavior changes.
3. Update topic docs under `docs/agents/` when maintainer workflow or standards change.
4. Ensure commands and names match actual code.
5. Ensure Makefile command names are current (`format`, `check`, `test`).
