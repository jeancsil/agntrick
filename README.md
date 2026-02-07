# Agentic Framework

An agentic framework built with LangChain and Python 3.12+.

## Prerequisites

- Python >= 3.12, < 3.14
- Uv (recommended): `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Getting Started

### Installation

Install dependencies using `uv`:

```bash
make install
```

### Development

The following Makefile targets are available:

- `make install`: Install dependencies and set up the virtual environment.
- `make run`: Run the default agent example.
- `make test`: Run tests using pytest.
- `make clean`: Clean up temporary files and caches.
- `make lint`: Run linting and formatting checks.


### Usage with UV
The pattern is:  
`uv run agentic-run **agent_name** --input "your prompt"`

E.g:  
```bash
uv run agentic-run simple --input "Tell me a joke"
uv run agentic-run chef -i "I have bread, tuna, lettuce and mayo."
```

### Project Structure

```
agentic-framework/
├── Makefile              # Commands for install, test, lint, run
├── README.md             # Documentation and setup instructions
├── pyproject.toml        # Dependencies and tool config (pytest, ruff, mypy)
├── .gitignore            # Standard Python gitignore
├── src/
│   └── agentic_framework/
│       ├── __init__.py
│       ├── core/         # Core logic (e.g., your Agent implementation)
│       ├── interfaces/   # Abstract base classes
│       └── tools/        # Sample tools
└── tests/
```

## Creating Your First Agent

See `src/agentic_framework/core/agent.py` for a basic agent implementation.
