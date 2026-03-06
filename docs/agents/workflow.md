# Workflow

Use this sequence for all changes.

## 1. Understand

- Read source files involved in the request.
- Read relevant tests before changing implementation.
- Confirm current patterns and architecture assumptions.
- Check whether similar functionality already exists.

## 2. Implement

- Keep changes focused and minimal.
- Follow existing style and architecture patterns.
- Add or update types and docstrings when behavior changes.
- Keep mypy requirements in mind while coding (typed defs, typed internals, no silent `Any` leakage).

## 3. Verify

From `agentic-framework/` run:

```bash
make -C .. check
make -C .. test
```

## 4. Fix

If either command fails:

1. Read the failure carefully.
2. If needed, run `make -C .. format` to apply lint/format fixes.
3. Fix root cause.
4. Re-run the failing command.
5. Repeat until both pass.

## Completion Standard

Do not report completion with unresolved lint, type, or test failures.
