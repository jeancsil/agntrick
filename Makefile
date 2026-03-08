.PHONY: help install run test clean format check docker-build docker-clean build build-whatsapp build-clean
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

run: ## Run the agntrick CLI to exemplify usage
	@$(UV) --directory $(PROJECT_DIR) run agntrick chef -i "I have bread, tuna, lettuce and mayo."

test: ## Run tests with coverage
	@$(UV) --directory $(PROJECT_DIR) run pytest tests/ -v --cov=src --cov-report=xml --cov-report=term

check: ## Run all checks (mypy, ruff lint, ruff format) - no modifications
	@$(UV) --directory $(PROJECT_DIR) run mypy src/
	@$(UV) --directory $(PROJECT_DIR) run ruff check src/ tests/
	@$(UV) --directory $(PROJECT_DIR) run ruff format --check src/ tests/

format: ## Auto-fix lint and format issues (runs ruff check --fix and ruff format)
	@$(UV) --directory $(PROJECT_DIR) run ruff check --fix src/ tests/
	@$(UV) --directory $(PROJECT_DIR) run ruff format src/ tests/

clean: ## Deep clean temporary files and virtual environment
	rm -rf $(PROJECT_DIR)/.venv
	rm -rf $(PROJECT_DIR)/.pytest_cache/
	rm -rf $(PROJECT_DIR)/.mypy_cache/
	rm -rf $(PROJECT_DIR)/.ruff_cache/
	rm -rf $(PROJECT_DIR)/.benchmarks/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf .benchmarks/
	rm -rf .coverage
	rm -rf coverage.xml

	find $(PROJECT_DIR) -type d -name "__pycache__" -exec rm -rf {} +
	find $(PROJECT_DIR) -type f -name "*.pyc" -delete

## -- Docker Commands --

docker-build: ## Build the Docker image
	@echo "Building Docker image..."
	@docker compose build
	@echo ""
	@echo "✓ Build complete!"
	@echo ""
	@echo "Run agents using: bin/agntrick.sh <agent-name> [args]"
	@echo "Example: bin/agntrick.sh chef -i 'I have eggs and cheese'"
	@echo "Example: bin/agntrick.sh -v travel-coordinator -i 'Plan a trip'"
	@echo ""
	@echo "See bin/agntrick.sh --help for more information"

docker-clean: ## Remove Docker containers, images, and volumes
	@echo "Cleaning up Docker resources..."
	@docker compose down -v 2>/dev/null || true
	@docker rmi agents-agntrick 2>/dev/null || true
	@echo "✓ Cleanup complete!"

## -- Build Commands --

build-whatsapp: ## Build WhatsApp package
	@cd $(PROJECT_DIR)/packages/agntrick-whatsapp && $(UV) --directory . build
	@echo ""
	@echo "✓ WhatsApp build complete!"
	@ls -la $(PROJECT_DIR)/packages/agntrick-whatsapp/dist/ 2>/dev/null || true

build: build-whatsapp ## Build wheel and sdist packages (both main and whatsapp)
	@$(UV) --directory $(PROJECT_DIR) build
	@echo ""
	@echo "✓ Build complete!"
	@echo "Main packages are in $(PROJECT_DIR)/dist/"
	@ls -la $(PROJECT_DIR)/dist/ 2>/dev/null || true
	@echo ""
	@echo "WhatsApp package is in $(PROJECT_DIR)/packages/agntrick-whatsapp/dist/"
	@ls -la $(PROJECT_DIR)/packages/agntrick-whatsapp/dist/ 2>/dev/null || true

build-clean: ## Remove build artifacts
	rm -rf $(PROJECT_DIR)/dist/
	rm -rf $(PROJECT_DIR)/build/
	rm -rf $(PROJECT_DIR)/src/*.egg-info
	rm -rf $(PROJECT_DIR)/packages/agntrick-whatsapp/dist/
	rm -rf $(PROJECT_DIR)/packages/agntrick-whatsapp/build/
	@echo "✓ Build artifacts cleaned!"