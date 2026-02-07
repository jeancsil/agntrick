
.PHONY: install run test clean lint check format

# Use `uv` for python environment management
UV ?= uv
PYTHON ?= $(UV) run python
PYTEST ?= $(UV) run pytest
RUFF ?= $(UV) run ruff

# Default target
all: install test

# Install all dependencies (production + development)
install:
	$(UV) sync

# Run the project
run:
	$(UV) run agentic-run simple -i "Tell me a joke"

# Run tests
test:
	$(PYTEST) tests/

# Clean temporary files
clean:
	rm -rf .venv
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Lint code using ruff
lint:
	$(RUFF) check --fix .

# Format code using ruff
format:
	$(RUFF) format .

# Check code (lint + format check + type check)
check: lint
	$(RUFF) format --check .
	$(UV) run mypy src/
