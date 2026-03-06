# Testing

## Location and Naming

- Tests live in `agentic-framework/tests/`.
- File name format: `test_<module>.py`.
- Test function format: `test_<behavior>_<scenario>()`.

## Expectations

- Add tests for new functionality.
- Update tests for behavior changes.
- Do not delete tests without replacement coverage.

## Patterns

Use `monkeypatch` for external dependency seams.
Prefer deterministic tests with explicit assertions.

## Validation Commands

```bash
make -C .. format
make -C .. check
make -C .. test
```
