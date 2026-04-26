# HTTP API Reference

Agntrick exposes a FastAPI server on port 8000 by default. Start it via `agntrick serve` (users) or `uv run agntrick serve` (contributors).

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe. Returns `{"status": "ok"}`. |
| `GET` | `/ready` | Readiness probe. Returns `{"status": "ready", "checks": {...}}` or `degraded` if any dependency is down. |
| `GET` | `/api/v1/whatsapp/qr/{tenant_id}` | Server-Sent Events stream of the QR code for the named tenant. |
| `GET` | `/api/v1/whatsapp/qr/{tenant_id}/page` | HTML viewer that renders the QR via the SSE stream. |
| `POST` | `/api/v1/whatsapp/qr/{tenant_id}` | Internal — Go gateway pushes a QR payload here. |
| `POST` | `/api/v1/whatsapp/status/{tenant_id}` | Internal — Go gateway pushes connection status updates. |
| `POST` | `/api/v1/channels/whatsapp/message` | Internal — Go gateway delivers an incoming WhatsApp message. |

## Authentication

Endpoints under `/api/v1/whatsapp/*` and `/api/v1/channels/*` require an API key configured in `.agntrick.yaml` under `auth.api_keys`. The Go gateway forwards the configured key in the `X-API-Key` header.

## Health checks

- `/health` is unauthenticated and meant for upstream load balancers.
- `/ready` is unauthenticated and reports component-level health (database, MCP servers).

## Worked examples

```bash
# Liveness
curl -s http://localhost:8000/health
# {"status":"ok"}

# QR viewer (open in a browser)
open http://localhost:8000/api/v1/whatsapp/qr/personal/page
```

## Source

Routes live under `src/agntrick/api/routes/`. See `src/agntrick/api/server.py` for the app factory and middleware wiring.
