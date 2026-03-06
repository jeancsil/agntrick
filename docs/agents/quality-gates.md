# Quality Gates

## Required Commands

After code edits, run:

```bash
make -C .. format   # when fixes are needed
make -C .. check
make -C .. test
```

`make -C .. check` covers:
- mypy (strict typing)
- ruff lint
- ruff format check

`make -C .. test` covers:
- pytest
- coverage enforcement

## Failure Policy

- Do not ignore warnings that indicate actionable issues.
- Fix all lint and type errors.
- Fix all failing tests.
- Use `make -C .. format` for mechanical lint/format remediation.
- Re-run commands until they pass.

## Coverage

Coverage threshold is configured in `pyproject.toml`.
New functionality should include tests to maintain or improve overall coverage.
