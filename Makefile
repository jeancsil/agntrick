.PHONY: help install run test clean lint check format
.DEFAULT_GOAL := help

# Use `uv` for python environment management
UV ?= uv
PYTHON ?= $(UV) --directory $(PROJECT_DIR) run python
PYTEST ?= $(UV) --directory $(PROJECT_DIR) run pytest
RUFF ?= $(UV) --directory $(PROJECT_DIR) run ruff

# Project directory
PROJECT_DIR = agentic-framework

## -- Help System --

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

## -- Commands --

install: ## Install all dependencies using uv
	@$(UV) --directory $(PROJECT_DIR) sync

run: ## Run the agentic-run simple command
	@$(UV) --project $(PROJECT_DIR) run agentic-run simple -i "Tell me a joke"

test: ## Run pytest in the project directory
	@$(UV) --project $(PROJECT_DIR) run pytest $(PROJECT_DIR)/tests/

lint: ## Run ruff linting with auto-fix
	@$(UV) --project $(PROJECT_DIR) run ruff check --fix .

format: ## Run ruff code formatting
	@$(UV) --project $(PROJECT_DIR) run ruff format .

check: lint ## Run lint, format check, and mypy type checking
	@$(UV) --project $(PROJECT_DIR) run ruff format --check .

clean: ## Deep clean temporary files and virtual environment
	rm -rf $(PROJECT_DIR)/.venv
	rm -rf $(PROJECT_DIR)/.pytest_cache
	rm -rf $(PROJECT_DIR)/.ruff_cache
	find $(PROJECT_DIR) -type d -name "__pycache__" -exec rm -rf {} +
	find $(PROJECT_DIR) -type f -name "*.pyc" -delete