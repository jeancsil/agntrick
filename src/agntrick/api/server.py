"""FastAPI application factory and server."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agntrick.api.middleware import RequestLoggingAndErrorMiddleware
from agntrick.api.routes import agents, health, whatsapp
from agntrick.config import get_config
from agntrick.tools.deep_scrape import DeepScrapeTool

logger = logging.getLogger(__name__)


async def _check_mcp_health(app: FastAPI) -> None:
    """Periodically check MCP health and evict unhealthy agents.

    Checks toolbox /sse endpoint every 60 seconds. If unhealthy,
    evicts all agents from pool to force fresh connections on next request.
    """
    import httpx

    config = get_config()
    toolbox_url = config.mcp.toolbox_url or "http://localhost:8080"
    pool = app.state.agent_pool

    while True:
        await asyncio.sleep(60)  # Check every 60s
        try:
            async with httpx.AsyncClient() as client:
                # Toolbox uses /sse as health endpoint (returns 200 if healthy)
                resp = await client.get(f"{toolbox_url}/sse", timeout=5)
                if resp.status_code != 200:
                    logger.warning("Toolbox health check failed (status=%s), evicting all agents", resp.status_code)
                    for key in list(pool._agents.keys()):
                        tenant_id, agent_name = key.split(":", 1)
                        await pool.evict(tenant_id, agent_name)
        except Exception as e:
            logger.warning(f"MCP health check failed: {e}, evicting all agents")
            for key in list(pool._agents.keys()):
                tenant_id, agent_name = key.split(":", 1)
                await pool.evict(tenant_id, agent_name)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    from agntrick.logging_config import setup_logging

    config = get_config()
    setup_logging(config)
    logger.info("Starting agntrick API server on %s:%s", config.api.host, config.api.port)
    from agntrick.llm.providers import detect_provider, get_default_model

    provider = detect_provider()
    model = get_default_model()
    logger.info("LLM: provider=%s model=%s", provider, model)

    from agntrick.api.pool import TenantAgentPool
    from agntrick.registry import AgentRegistry
    from agntrick.storage.tenant_manager import TenantManager

    app.state.tenant_manager = TenantManager(base_path=config.storage.base_path)

    # Discover agents and initialize pool
    AgentRegistry.discover_agents()
    app.state.agent_pool = TenantAgentPool(max_size=10)
    logger.info("Agent pool initialized (max_size=10)")

    # Warm up Playwright browser for DeepScrapeTool
    try:
        await DeepScrapeTool.warmup()
        logger.info("Playwright browser warmed up successfully")
    except Exception as e:
        logger.warning("Failed to warm up Playwright browser: %s", e)

    # Start MCP health check task
    app.state._health_task = asyncio.create_task(_check_mcp_health(app))
    logger.info("MCP health check task started")

    yield

    # Cancel MCP health check task
    if hasattr(app.state, "_health_task"):
        app.state._health_task.cancel()
        logger.info("MCP health check task cancelled")

    # Clean up SSE connections
    from agntrick.api.routes.whatsapp import sse_queues

    for tenant_id, queues in sse_queues.items():
        for queue in queues:
            await queue.put({"type": "shutdown", "data": "{}"})
    sse_queues.clear()

    # Evict all pooled agents
    pool = getattr(app.state, "agent_pool", None)
    if pool:
        for key in list(pool._agents.keys()):
            tenant_id, agent_name = key.split(":", 1)
            await pool.evict(tenant_id, agent_name)

    app.state.tenant_manager.close_all()

    # Clean up Playwright browser
    await DeepScrapeTool.shutdown()
    logger.info("Playwright browser shut down")

    logger.info("Shutting down agntrick API server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Agntrick API",
        description="Production-grade API for AI agents",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register error handling and logging middleware
    app.add_middleware(RequestLoggingAndErrorMiddleware)

    app.include_router(health.router, tags=["health"])
    app.include_router(agents.router, tags=["agents"])
    app.include_router(whatsapp.router, prefix="/api/v1/whatsapp", tags=["whatsapp"])
    app.include_router(whatsapp.channels_router, prefix="/api/v1/channels", tags=["channels"])
    return app


def run_server() -> None:
    """Run the API server."""
    import uvicorn

    config = get_config()

    uvicorn.run(
        "agntrick.api.server:create_app",
        host=config.api.host,
        port=config.api.port,
        reload=config.api.debug,
        factory=True,
        timeout_graceful_shutdown=5,
    )
