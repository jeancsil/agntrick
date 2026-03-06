# Coding Standards

## Mypy Is Mandatory

The repo enforces mypy in `make check`. Treat type errors as blocking.

Current enforced settings (from `agentic-framework/pyproject.toml`):

- `disallow_untyped_defs = true`
- `check_untyped_defs = true`
- `warn_return_any = true`

Implications:

- Every function and method needs explicit parameter and return types.
- Internal logic inside typed and untyped bodies is still type-checked.
- Avoid returning `Any` from public or shared utility boundaries.

## Type Hints

```python
async def run(self, input_data: str, config: dict[str, object] | None = None) -> str:
    ...
```

## Docstrings

Update docstrings when behavior changes. Use Google-style structure for public functions and include `Args`/`Returns` where relevant.

## Async Patterns

- Keep `run()` methods async where expected.
- Avoid blocking operations inside async paths.
- Use `await` for async dependencies.

## Tool Error Handling

Tool implementations should return error strings rather than raising operational exceptions.

## Agent Registration

Register new agents with the decorator pattern:

```python
@AgentRegistry.register("agent-name", mcp_servers=["server-name"])
class MyAgent(LangGraphMCPAgent):
    ...
```
