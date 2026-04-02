#!/usr/bin/env bash
# Deploy Agntrick on Digital Ocean droplet
#
# Usage:
#   git push  (from local)
#   ssh droplet "cd ~/projects/test-agntrick && git pull && ./scripts/deploy-do.sh"
#
# Or after pulling manually:
#   ./scripts/deploy-do.sh          # restart everything
#   ./scripts/deploy-do.sh build    # build only (no restart)
#   ./scripts/deploy-do.sh stop     # stop all services
#   ./scripts/deploy-do.sh logs     # tail logs

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────
PROJECT_DIR="${PROJECT_DIR:-$HOME/projects/test-agntrick}"
TOOLBOX_DIR="${TOOLBOX_DIR:-$HOME/code/agntrick-toolkit}"
LOG_DIR="${LOG_DIR:-$HOME/.local/share/agntrick/logs}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

GATEWAY_DIR="${PROJECT_DIR}/gateway"
GATEWAY_BIN="${GATEWAY_DIR}/agntrick-gateway"
GATEWAY_LOG="${LOG_DIR}/gateway.log"
API_LOG="${LOG_DIR}/api.log"
PID_FILE="${PROJECT_DIR}/.agntrick-pids"

# ── Helpers ────────────────────────────────────────────────────────

log_info()  { echo -e "\033[0;32m[INFO]\033[0m $1"; }
log_warn()  { echo -e "\033[1;33m[WARN]\033[0m $1"; }
log_error() { echo -e "\033[0;31m[ERROR]\033[0m $1"; }

mkdir -p "$LOG_DIR"

is_running() {
    local pid="$1"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

read_pids() {
    if [ -f "$PID_FILE" ]; then
        GATEWAY_PID=$(sed -n '1p' "$PID_FILE")
        API_PID=$(sed -n '2p' "$PID_FILE")
    fi
}

save_pids() {
    echo "$GATEWAY_PID" > "$PID_FILE"
    echo "$API_PID" >> "$PID_FILE"
}

# ── Stop ───────────────────────────────────────────────────────────

do_stop() {
    read_pids
    log_info "Stopping Agntrick services..."

    if is_running "${GATEWAY_PID:-}"; then
        kill "$GATEWAY_PID" 2>/dev/null && log_info "Gateway stopped (PID: $GATEWAY_PID)" || true
    fi
    if is_running "${API_PID:-}"; then
        kill "$API_PID" 2>/dev/null && log_info "API stopped (PID: $API_PID)" || true
    fi
    rm -f "$PID_FILE"
    log_info "All services stopped"
}

# ── Build ──────────────────────────────────────────────────────────

do_build() {
    log_info "Installing Python dependencies..."
    (cd "$PROJECT_DIR" && uv sync --frozen --no-dev)

    log_info "Building Go gateway..."
    (cd "$GATEWAY_DIR" && go build -o agntrick-gateway .)
    log_info "Build complete"
}

# ── Start ──────────────────────────────────────────────────────────

do_start() {
    read_pids

    if is_running "${GATEWAY_PID:-}" && is_running "${API_PID:-}"; then
        log_warn "Already running (gateway=$GATEWAY_PID, api=$API_PID)"
        return 0
    fi

    # Start Python API first (gateway needs it for QR codes)
    if ! is_running "${API_PID:-}"; then
        log_info "Starting Python API on ${HOST}:${PORT}..."
        nohup "${PROJECT_DIR}/.venv/bin/agntrick" serve --host "$HOST" --port "$PORT" > "$API_LOG" 2>&1 &
        API_PID=$!
        log_info "API started (PID: $API_PID)"

        log_info "Waiting for API to be ready..."
        for i in $(seq 1 30); do
            if curl -sf "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1; then
                log_info "API is ready"
                break
            fi
            if [ "$i" -eq 30 ]; then
                log_error "API failed to start within 30 seconds"
                tail -20 "$API_LOG"
                return 1
            fi
            sleep 1
        done
    fi

    # Start Go gateway
    if ! is_running "${GATEWAY_PID:-}"; then
        log_info "Starting Go gateway..."
        nohup "$GATEWAY_BIN" > "$GATEWAY_LOG" 2>&1 &
        GATEWAY_PID=$!
        log_info "Gateway started (PID: $GATEWAY_PID)"
    fi

    save_pids

    echo ""
    log_info "Services running:"
    echo "  Gateway:  PID $GATEWAY_PID"
    echo "  API:      PID $API_PID"
    echo "  Health:   http://localhost:${PORT}/health"
    echo "  QR:       http://$(hostname -I | awk '{print $1}'):${PORT}/api/v1/whatsapp/qr/primary/page"
}

# ── Toolbox ────────────────────────────────────────────────────────

do_toolbox() {
    if [ -d "$TOOLBOX_DIR" ]; then
        log_info "Starting toolbox MCP server..."
        (cd "$TOOLBOX_DIR" && docker-compose up -d)
        log_info "Toolbox running at http://localhost:8080/sse"
    else
        log_warn "Toolbox not found at $TOOLBOX_DIR (skipping)"
    fi
}

# ── Status ─────────────────────────────────────────────────────────

do_status() {
    read_pids
    local all_ok=true

    if is_running "${GATEWAY_PID:-}"; then
        log_info "Gateway: RUNNING (PID: $GATEWAY_PID)"
    else
        log_error "Gateway: STOPPED"
        all_ok=false
    fi

    if is_running "${API_PID:-}"; then
        log_info "API:     RUNNING (PID: $API_PID)"
    else
        log_error "API:     STOPPED"
        all_ok=false
    fi

    if [ "$all_ok" = true ]; then
        echo ""
        echo "  Health: curl http://localhost:${PORT}/health"
    fi
}

# ── Logs ───────────────────────────────────────────────────────────

do_logs() {
    local target="${1:-all}"
    case "$target" in
        gateway) tail -f "$GATEWAY_LOG" ;;
        api)     tail -f "$API_LOG" ;;
        all|*)   tail -f "$GATEWAY_LOG" "$API_LOG" ;;
    esac
}

# ── Main ───────────────────────────────────────────────────────────

case "${1:-start}" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_stop; sleep 1; do_start ;;
    build)   do_build ;;
    deploy)  do_build; do_stop; sleep 1; do_start; do_toolbox ;;
    toolbox) do_toolbox ;;
    status)  do_status ;;
    logs)    do_logs "${2:-all}" ;;
    *)
        echo "Usage: $0 {start|stop|restart|build|deploy|toolbox|status|logs [gateway|api]}"
        echo ""
        echo "Commands:"
        echo "  deploy   Build + restart + toolbox (full deploy)"
        echo "  build    Install deps and build gateway"
        echo "  start    Start both services"
        echo "  stop     Stop both services"
        echo "  restart  Stop and start"
        echo "  toolbox  Start MCP toolbox (Docker)"
        echo "  status   Check if services are running"
        echo "  logs     Tail logs (optional: gateway, api)"
        exit 1
        ;;
esac
