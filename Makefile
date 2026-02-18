.PHONY: help install run test clean fix check docker-build docker-clean
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

check: ## Run all checks (mypy, ruff lint, ruff format) - no modifications
	@$(UV) --project $(PROJECT_DIR) run mypy $(PROJECT_DIR)/src/
	@$(UV) --project $(PROJECT_DIR) run ruff check $(PROJECT_DIR)/src/ $(PROJECT_DIR)/tests/
	@$(UV) --project $(PROJECT_DIR) run ruff format --check $(PROJECT_DIR)/src/ $(PROJECT_DIR)/tests/

fix: ## Auto-fix lint and format issues (runs ruff check --fix and ruff format)
	@$(UV) --project $(PROJECT_DIR) run ruff check --fix $(PROJECT_DIR)/src/ $(PROJECT_DIR)/tests/
	@$(UV) --project $(PROJECT_DIR) run ruff format $(PROJECT_DIR)/src/ $(PROJECT_DIR)/tests/

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

## -- Docker Commands --

docker-build: ## Build the Docker image
	@echo "Building Docker image..."
	@docker compose build
	@echo ""
	@echo "✓ Build complete!"
	@echo ""
	@echo "Run agents using: bin/agent.sh <agent-name> [args]"
	@echo "Example: bin/agent.sh chef -i 'I have eggs and cheese'"
	@echo "Example: bin/agent.sh -v travel-coordinator -i 'Plan a trip'"
	@echo ""
	@echo "See bin/agent.sh --help for more information"

docker-clean: ## Remove Docker containers, images, and volumes
	@echo "Cleaning up Docker resources..."
	@docker compose down -v 2>/dev/null || true
	@docker rmi agents-agentic-framework 2>/dev/null || true
	@echo "✓ Cleanup complete!"