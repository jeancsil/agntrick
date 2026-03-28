"""WhatsApp QR code and status endpoints with SSE support."""

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from agntrick.config import get_config
from agntrick.logging_config import TenantLogAdapter
from agntrick.registry import AgentRegistry
from agntrick.whatsapp import WhatsAppRegistry

router = APIRouter()

# Global WhatsApp registry instance
_whatsapp_registry: WhatsAppRegistry | None = None


def get_whatsapp_registry() -> WhatsAppRegistry:
    """Get or initialize the WhatsApp registry from config."""
    global _whatsapp_registry
    if _whatsapp_registry is None:
        config = get_config()
        _whatsapp_registry = WhatsAppRegistry(config.whatsapp.tenants)
    return _whatsapp_registry


# In-memory storage for QR codes and connection status
# In production, this should be replaced with Redis or similar
qr_codes: dict[str, dict[str, str]] = defaultdict(dict)
connection_status: dict[str, dict[str, str]] = defaultdict(dict)
# Event queues for SSE clients
sse_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)
# Timestamps for cleanup
_last_activity: dict[str, float] = {}
_MAX_INACTIVE_TENANTS = 100  # Maximum number of inactive tenant entries to keep


def _cleanup_stale_entries() -> None:
    """Remove entries for inactive tenants to prevent unbounded memory growth."""
    now = time.time()
    if len(_last_activity) <= _MAX_INACTIVE_TENANTS:
        return

    # Remove entries older than 1 hour
    cutoff = now - 3600
    stale = [tid for tid, ts in _last_activity.items() if ts < cutoff]
    for tid in stale:
        qr_codes.pop(tid, None)
        connection_status.pop(tid, None)
        sse_queues.pop(tid, None)
        del _last_activity[tid]


class QRCodeRequest(BaseModel):
    """Request model for QR code submission."""

    image: str


class StatusRequest(BaseModel):
    """Request model for connection status updates."""

    status: str
    phone: str | None = None


@router.get("/qr/{tenant_id}/page", response_class=HTMLResponse)
async def qr_page(tenant_id: str) -> str:
    """Return a simple HTML page for displaying QR codes.

    Args:
        tenant_id: The tenant ID.

    Returns:
        HTML page with QR code display.
    """
    # Use a multiline string with line breaks to avoid E501
    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        f"    <title>WhatsApp QR Code - {tenant_id}</title>",
        "    <style>",
        "        body {",
        "            font-family: Arial, sans-serif;",
        "            display: flex;",
        "            flex-direction: column;",
        "            align-items: center;",
        "            justify-content: center;",
        "            min-height: 100vh;",
        "            margin: 0;",
        "            background-color: #f5f5f5;",
        "        }",
        "        .container {",
        "            background: white;",
        "            padding: 2rem;",
        "            border-radius: 8px;",
        "            box-shadow: 0 2px 10px rgba(0,0,0,0.1);",
        "            text-align: center;",
        "        }",
        "        h1 {",
        "            color: #333;",
        "        }",
        "        #qr-code {",
        "            margin: 2rem 0;",
        "        }",
        "        #qr-code img {",
        "            max-width: 300px;",
        "            border: 2px solid #ddd;",
        "            border-radius: 4px;",
        "        }",
        "        #status {",
        "            margin-top: 1rem;",
        "            padding: 1rem;",
        "            border-radius: 4px;",
        "            font-weight: bold;",
        "        }",
        "        .connected {",
        "            background-color: #d4edda;",
        "            color: #155724;",
        "        }",
        "        .disconnected {",
        "            background-color: #f8d7da;",
        "            color: #721c24;",
        "        }",
        "        .loading {",
        "            background-color: #fff3cd;",
        "            color: #856404;",
        "        }",
        "    </style>",
        "</head>",
        "<body>",
        '    <div class="container">',
        f"        <h1>WhatsApp QR Code - {tenant_id}</h1>",
        '        <div id="status" class="loading">Waiting for QR code...</div>',
        '        <div id="qr-code"></div>',
        "        <p>Scan this QR code with WhatsApp to connect</p>",
        "    </div>",
        "    <script>",
        f"        const eventSource = new EventSource('/api/v1/whatsapp/qr/{tenant_id}');",
        "        eventSource.addEventListener('qr_code', function(e) {",
        "            const data = JSON.parse(e.data);",
        "            const img = document.createElement('img');",
        "            img.src = 'data:image/png;base64,' + data.image;",
        "            img.alt = 'QR Code';",
        "            document.getElementById('qr-code').innerHTML = '';",
        "            document.getElementById('qr-code').appendChild(img);",
        "            document.getElementById('status').className = 'loading';",
        "            document.getElementById('status').textContent = 'QR Code received - scan now!';",
        "        });",
        "        eventSource.addEventListener('connected', function(e) {",
        "            const data = JSON.parse(e.data);",
        "            document.getElementById('qr-code').innerHTML = '';",
        "            document.getElementById('status').className = 'connected';",
        "            document.getElementById('status').textContent = 'Connected as ' + data.phone;",
        "            eventSource.close();",
        "        });",
        "        eventSource.addEventListener('disconnected', function(e) {",
        "            document.getElementById('status').className = 'disconnected';",
        "            document.getElementById('status').textContent = 'Disconnected from WhatsApp';",
        "        });",
        "        eventSource.onerror = function(e) {",
        "            console.error('EventSource error:', e);",
        "            document.getElementById('status').className = 'disconnected';",
        "            document.getElementById('status').textContent = 'Connection error - please refresh';",
        "        };",
        "    </script>",
        "</body>",
        "</html>",
    ]
    return "\n".join(html_parts)


@router.get("/qr/{tenant_id}")
async def qr_stream(tenant_id: str, request: Request) -> StreamingResponse:
    """SSE endpoint for streaming QR codes and connection status.

    Args:
        tenant_id: The tenant ID.
        request: The FastAPI request.

    Returns:
        StreamingResponse with SSE events.
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events."""
        # Create a queue for this client
        queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        sse_queues[tenant_id].append(queue)

        try:
            # Send current QR code if available
            if tenant_id in qr_codes and "image" in qr_codes[tenant_id]:
                data = json.dumps({"image": qr_codes[tenant_id]["image"]})
                yield f"event: qr_code\ndata: {data}\n\n"

            # Send current status if available
            if tenant_id in connection_status and connection_status[tenant_id].get("status") == "connected":
                phone = connection_status[tenant_id].get("phone", "")
                data = json.dumps({"phone": phone})
                yield f"event: connected\ndata: {data}\n\n"

            # Keep connection alive and send new events
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    # Wait for new events (with heartbeat every 15 seconds)
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    event_type: str = event.get("type", "message")
                    event_data: str | dict[str, str] = event.get("data", {})
                    yield f"event: {event_type}\ndata: {event_data}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            # Remove queue on disconnect
            if queue in sse_queues[tenant_id]:
                sse_queues[tenant_id].remove(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/qr/{tenant_id}")
async def receive_qr_code(tenant_id: str, request: QRCodeRequest) -> dict[str, str]:
    """Receive QR code from Go gateway and cache it.

    Args:
        tenant_id: The tenant ID.
        request: The QR code request.

    Returns:
        Success message.
    """
    qr_codes[tenant_id]["image"] = request.image

    # Notify all SSE clients
    event_data = json.dumps({"image": request.image})
    for queue in sse_queues[tenant_id]:
        await queue.put({"type": "qr_code", "data": event_data})

    return {"status": "ok", "message": "QR code received"}


@router.post("/status/{tenant_id}")
async def receive_status(tenant_id: str, request: StatusRequest) -> dict[str, str]:
    """Receive connection status from Go gateway.

    Args:
        tenant_id: The tenant ID.
        request: The status request.

    Returns:
        Success message.
    """
    connection_status[tenant_id]["status"] = request.status
    if request.phone:
        connection_status[tenant_id]["phone"] = request.phone

    # Notify all SSE clients
    if request.status == "connected" and request.phone:
        event_data = json.dumps({"phone": request.phone})
        for queue in sse_queues[tenant_id]:
            await queue.put({"type": "connected", "data": event_data})
    elif request.status == "disconnected":
        for queue in sse_queues[tenant_id]:
            await queue.put({"type": "disconnected", "data": json.dumps({})})

    # Track activity and cleanup
    _last_activity[tenant_id] = time.time()
    _cleanup_stale_entries()

    return {"status": "ok", "message": "Status updated"}


# Webhook router for channels endpoints (different prefix from whatsapp router)
channels_router = APIRouter()


@channels_router.post("/whatsapp/message")
async def whatsapp_webhook(
    request: Request, registry: WhatsAppRegistry = Depends(get_whatsapp_registry)
) -> dict[str, str]:
    """Receive WhatsApp message from Go gateway and route to tenant's agent.

    Args:
        request: The FastAPI request containing message data.
        registry: WhatsApp registry instance.

    Returns:
        Agent response with tenant_id.

    Raises:
        HTTPException: If authentication fails or tenant not found.
    """
    logger = logging.getLogger(__name__)

    # Check API key against keys (not values) of api_keys dict
    api_key = request.headers.get("X-API-Key")
    config = get_config()

    if not api_key or api_key not in config.auth.api_keys:
        logger.warning("Invalid API key attempted for WhatsApp webhook")
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Parse request body
    try:
        body = await request.json()
        phone = body.get("from")
        message = body.get("message")
        tenant_id = body.get("tenant_id")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    if not phone or not message:
        raise HTTPException(status_code=400, detail="Missing 'from' or 'message' in request body")

    # Look up tenant by phone number
    resolved_tenant_id = registry.lookup_by_phone(phone)

    # If tenant_id provided in body, use it for validation
    if tenant_id:
        if resolved_tenant_id != tenant_id:
            logger.error("Phone number maps to different tenant")
            raise HTTPException(
                status_code=400,
                detail="Phone number does not match provided tenant_id",
            )
    else:
        tenant_id = resolved_tenant_id

    if not tenant_id:
        logger.error("No tenant found for phone number")
        raise HTTPException(status_code=404, detail="No tenant found for phone number")

    # Get logger with tenant context
    tenant_logger = TenantLogAdapter(logger, tenant_id)
    tenant_logger.info("Received WhatsApp message")

    # Get tenant configuration
    tenant_config = None
    for tenant in get_config().whatsapp.tenants:
        if tenant.id == tenant_id:
            tenant_config = tenant
            break

    if not tenant_config:
        tenant_logger.error("Tenant configuration not found: %s", tenant_id)
        raise HTTPException(status_code=404, detail="Tenant configuration not found")

    # Check if contact is allowed
    if tenant_config.allowed_contacts and phone not in tenant_config.allowed_contacts:
        tenant_logger.warning("Phone number not in allowed contacts for tenant %s", tenant_id)
        raise HTTPException(status_code=403, detail="Phone number not in allowed contacts")

    # Run the tenant's configured agent
    try:
        AgentRegistry.discover_agents()
        agent_cls = AgentRegistry.get(tenant_config.default_agent)

        if not agent_cls:
            tenant_logger.error("Agent '%s' not found for tenant %s", tenant_config.default_agent, tenant_id)
            raise HTTPException(status_code=500, detail="Agent not found")

        # Create and run agent
        config = get_config()

        # Prepare agent constructor arguments
        constructor_args = {
            "model_name": config.llm.model,
            "temperature": config.llm.temperature,
            "thread_id": "whatsapp_webhook",
        }

        # Add checkpointer if available (but not for WhatsApp messages)
        if hasattr(agent_cls, "__init__"):
            import inspect

            signature = inspect.signature(agent_cls.__init__)
            if "checkpointer" in signature.parameters:
                constructor_args["checkpointer"] = None  # No checkpointing for WhatsApp messages

        # Create and run agent
        agent = agent_cls(**constructor_args)
        result = await agent.run(message)

        tenant_logger.info("Successfully processed WhatsApp message for tenant %s", tenant_id)
        return {"response": str(result) if result is not None else "", "tenant_id": tenant_id}

    except Exception as e:
        tenant_logger.error("Failed to process WhatsApp message for tenant %s: %s", tenant_id, str(e))
        raise HTTPException(status_code=500, detail="Internal error processing message")
