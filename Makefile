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
	@git config --local core.hooksPath .githooks

run: ## Run the agentic-run simple command to exemplify the CLI
#	@$(UV) --project $(PROJECT_DIR) run agentic-run simple --input "Tell me a joke"
	@$(UV) --project $(PROJECT_DIR) run agentic-run chef -i "I have bread, tuna, lettuce and mayo."

test: ## Run tests with coverage
	@$(UV) --project $(PROJECT_DIR) run pytest $(PROJECT_DIR)/tests/ -v --cov=$(PROJECT_DIR)/src --cov-report=xml --cov-report=term

lint: ## Run ruff linting with auto-fix
	@$(UV) --project $(PROJECT_DIR) run mypy $(PROJECT_DIR)/src/
	@$(UV) --project $(PROJECT_DIR) run ruff check --fix $(PROJECT_DIR)/src/ $(PROJECT_DIR)/tests/
	@$(UV) --project $(PROJECT_DIR) run ruff format $(PROJECT_DIR)/src/ $(PROJECT_DIR)/tests/

format: ## Run ruff code formatting
	@$(UV) --project $(PROJECT_DIR) run ruff format $(PROJECT_DIR)/src/ $(PROJECT_DIR)/tests/

check: ## Run lint, format check, and mypy type checking (no fixes)
	@$(UV) --project $(PROJECT_DIR) run mypy $(PROJECT_DIR)/src/
	@$(UV) --project $(PROJECT_DIR) run ruff check $(PROJECT_DIR)/src/ $(PROJECT_DIR)/tests/
	@$(UV) --project $(PROJECT_DIR) run ruff format --check $(PROJECT_DIR)/src/ $(PROJECT_DIR)/tests/

clean: ## Deep clean temporary files and virtual environment
	rm -rf $(PROJECT_DIR)/.venv
	rm -rf $(PROJECT_DIR)/../.pytest_cache/
	rm -rf $(PROJECT_DIR)/../.mypy_cache/
	rm -rf $(PROJECT_DIR)/.mypy_cache/
	rm -rf $(PROJECT_DIR)/.ruff_cache/
	rm -rf $(PROJECT_DIR)/.benchmarks/
	rm -rf $(PROJECT_DIR)/src/agentic_framework.egg-info/
	rm -rf $(PROJECT_DIR)/../.benchmarks/
	rm -rf $(PROJECT_DIR)/../.ruff_cache/

	find $(PROJECT_DIR) -type d -name "__pycache__" -exec rm -rf {} +
	find $(PROJECT_DIR) -type f -name "*.pyc" -delete