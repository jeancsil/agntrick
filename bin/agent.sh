#!/usr/bin/env bash

# agent.sh - Docker wrapper for Agntrick CLI
# Usage: bin/agent.sh [-v|--verbose] <agent-command> [args...]
# Example: bin/agent.sh developer -i "Explain this codebase"
# Example: bin/agent.sh -v news -i "What's the latest tech news?"

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the project root (parent of bin/)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    echo "Please start Docker and try again"
    exit 1
fi

# Check if docker compose is available
if ! docker compose version >/dev/null 2>&1; then
    echo -e "${RED}Error: docker compose is not available${NC}"
    echo "Please install Docker Compose and try again"
    exit 1
fi

# Parse verbose flag
VERBOSE=""
if [[ "$1" == "-v" ]] || [[ "$1" == "--verbose" ]]; then
    VERBOSE="--verbose"
    shift
fi

# Check if any arguments provided
if [[ $# -eq 0 ]]; then
    echo -e "${YELLOW}Usage: bin/agent.sh [-v|--verbose] <agent-command> [args...]${NC}"
    echo ""
    echo "Examples:"
    echo "  bin/agent.sh list"
    echo "  bin/agent.sh chef -i \"I have eggs and cheese\""
    echo "  bin/agent.sh -v travel-coordinator -i \"Plan a trip to Paris\""
    echo "  bin/agent.sh developer --input \"Explain the project\" --timeout 120"
    echo ""
    echo "Available agents:"
    docker compose -f "$PROJECT_ROOT/docker-compose.yml" run --rm agentic-framework \
        uv --directory agentic-framework run agntrick list 2>/dev/null || echo "  (run 'make docker-build' first)"
    exit 0
fi

# Build the command
CMD_ARGS=("$@")

# Add verbose flag if set
if [[ -n "$VERBOSE" ]]; then
    # Insert verbose flag after the agent name (first argument)
    AGENT_NAME="${CMD_ARGS[0]}"
    REST_ARGS=("${CMD_ARGS[@]:1}")
    CMD_ARGS=("$AGENT_NAME" "$VERBOSE" "${REST_ARGS[@]}")
fi

# Run the command in Docker
echo -e "${BLUE}Running:${NC} agntrick ${CMD_ARGS[*]}"
echo ""

cd "$PROJECT_ROOT"
docker compose run --rm agentic-framework \
    uv --directory agentic-framework run agntrick "${CMD_ARGS[@]}"

EXIT_CODE=$?

# Show log location on success
if [[ $EXIT_CODE -eq 0 ]]; then
    echo ""
    echo -e "${GREEN}✓ Command completed successfully${NC}"
    echo -e "${BLUE}Logs:${NC} $PROJECT_ROOT/agentic-framework/logs/agent.log"
else
    echo ""
    echo -e "${RED}✗ Command failed with exit code $EXIT_CODE${NC}"
    echo -e "${BLUE}Check logs:${NC} $PROJECT_ROOT/agentic-framework/logs/agent.log"
fi

exit $EXIT_CODE
