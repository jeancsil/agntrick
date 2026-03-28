"""API middleware for error handling and request logging."""

import logging
import time

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

logger = logging.getLogger(__name__)


async def catch_exceptions_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Global exception handler that catches unhandled errors.

    Args:
        request: The incoming HTTP request.
        call_next: The next middleware/route handler.

    Returns:
        JSONResponse: Sanitized error response for production.
    """
    try:
        return await call_next(request)  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Unhandled exception: %s", type(e).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )


async def request_logging_middleware(request: Request, call_next: RequestResponseEndpoint) -> "Response":
    """Logs method, path, duration for each request.

    Args:
        request: The incoming HTTP request.
        call_next: The next middleware/route handler.

    Returns:
        Response: The response from the next handler.
    """
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    tenant_id = request.headers.get("X-API-Key", "anonymous")
    logger.info(
        "%s %s %s %d %.3fs",
        request.method,
        request.url.path,
        tenant_id,
        response.status_code,
        duration,
    )
    return response
