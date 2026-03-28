"""Resilience utilities for API operations."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Args:
        max_retries: Maximum number of retry attempts.
        backoff_factor: Factor for exponential backoff calculation.
    """

    max_retries: int = 3
    backoff_factor: float = 0.5


async def retry_async(
    func: Callable[[], Awaitable[Any]],
    config: RetryConfig | None = None,
) -> Any:
    """Retry an async function with exponential backoff.

    Args:
        func: The async function to retry.
        config: Retry configuration. Uses default if None.

    Returns:
        The result of the function call.

    Raises:
        Exception: The last exception encountered if all retries fail.
    """
    config = config or RetryConfig()
    last_error: Exception | None = None

    for attempt in range(config.max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_error = e
            if attempt < config.max_retries:
                wait = config.backoff_factor * (2**attempt)
                logger.warning(
                    "Attempt %d failed, retrying in %.1fs: %s",
                    attempt + 1,
                    wait,
                    e,
                )
                await asyncio.sleep(wait)

    if last_error is not None:
        raise last_error
    raise RuntimeError("All retries failed")
