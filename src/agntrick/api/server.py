"""FastAPI application factory and server."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agntrick.api.middleware import catch_exceptions_middleware, request_logging_middleware
from agntrick.api.routes import agents, health, whatsapp
from agntrick.config import get_config

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    from agntrick.logging_config import setup_logging

    config = get_config()
    setup_logging(config)
    logger.info("Starting agntrick API server on %s:%s", config.api.host, config.api.port)

    from agntrick.storage.tenant_manager import TenantManager

    app.state.tenant_manager = TenantManager(base_path=config.storage.base_path)

    yield

    app.state.tenant_manager.close_all()
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
    # Note: FastAPI middleware is executed in reverse order of registration
    # Exception handler should be outermost (registered first)
    app.middleware("http")(catch_exceptions_middleware)
    app.middleware("http")(request_logging_middleware)

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
    )
