"""FastAPI application factory and server."""

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

    from agntrick.storage.tenant_manager import TenantManager

    app.state.tenant_manager = TenantManager(base_path=config.storage.base_path)

    # Warm up Playwright browser for DeepScrapeTool
    try:
        await DeepScrapeTool.warmup()
        logger.info("Playwright browser warmed up successfully")
    except Exception as e:
        logger.warning("Failed to warm up Playwright browser: %s", e)

    yield

    # Clean up SSE connections
    from agntrick.api.routes.whatsapp import sse_queues

    for tenant_id, queues in sse_queues.items():
        for queue in queues:
            await queue.put({"type": "shutdown", "data": "{}"})
    sse_queues.clear()

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
