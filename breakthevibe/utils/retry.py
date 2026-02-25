"""Retry decorator with exponential backoff."""

import asyncio
import functools
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def retry(
    max_attempts: int = 3, delay_ms: int = 1000, backoff_factor: float = 2.0
) -> Callable[..., Any]:
    """Decorator for async functions with retry logic."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts:
                        wait = (delay_ms * (backoff_factor ** (attempt - 1))) / 1000
                        logger.debug(
                            "retry_attempt",
                            func=func.__name__,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            wait_seconds=wait,
                        )
                        await asyncio.sleep(wait)
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator
