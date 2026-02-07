# Agentic Framework

An agentic framework built with LangChain and Python 3.12+.

![Build Status](https://github.com/jeancsil/agentic-framework/actions/workflows/ci.yml/badge.svg)
![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)
![GitHub License](https://img.shields.io/github/license/jeancsil/agentic-framework)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-checked-blue)](https://mypy-lang.org/)

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

### Available Agents

| Agent | Description | Tools / Integration |
|-------|-------------|---------------------|
| `simple` | A basic conversational agent. | - |
| `chef` | Personal chef that suggests recipes based on ingredients. | Web Search |
| `travel` | Travel assistant for flight search and planning. | **Kiwi MCP** (Flight Search) |

#### Examples:  
```bash
# Chef Agent
uv run agentic-run chef -i "I have bread, tuna, lettuce and mayo."

# Travel Agent (using Kiwi MCP)
uv run agentic-run travel --input "From BCN to Lisbon any date in June or July during 5 days."
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
