.PHONY: help install run test clean lint check format docker-build docker-run docker-chef docker-test docker-lint docker-shell docker-logs docker-start docker-stop docker-clean
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

## -- Docker Commands --

docker-build: ## Build the Docker image
	@docker compose build

docker-run: ## Run a command in Docker (usage: make docker-run CMD="chef -i 'your input'")
	@docker compose run --rm agentic-framework uv --directory agentic-framework run agentic-run $(CMD)

docker-chef: ## Run the chef agent in Docker (usage: make docker-chef INPUT="I have bread, tuna, lettuce")
	@docker compose run --rm agentic-framework uv --directory agentic-framework run agentic-run chef -i "$(INPUT)"

docker-test: ## Run tests in Docker
	@docker compose run --rm agentic-framework uv --directory agentic-framework run pytest agentic-framework/tests/ -v --cov=agentic-framework/src --cov-report=xml --cov-report=term

docker-lint: ## Run linting in Docker
	@docker compose run --rm agentic-framework uv --directory agentic-framework run mypy agentic-framework/src/
	@docker compose run --rm agentic-framework uv --directory agentic-framework run ruff check --fix agentic-framework/src/ agentic-framework/tests/
	@docker compose run --rm agentic-framework uv --directory agentic-framework run ruff format agentic-framework/src/ agentic-framework/tests/

docker-shell: ## Open a shell in the Docker container
	@docker compose run --rm -it agentic-framework /bin/bash

docker-logs: ## View logs from the container (logs are also available in agentic-framework/logs/)
	@docker compose logs -f

docker-start: ## Start the Docker container in detached mode
	@docker compose up -d

docker-stop: ## Stop the Docker container
	@docker compose down

docker-clean: ## Remove Docker containers, images, and volumes
	@docker compose down -v
	@docker rmi agents-agentic-framework 2>/dev/null || true