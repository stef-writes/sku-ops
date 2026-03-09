"""Redis client lifecycle — mirrors shared/infrastructure/db/__init__.py.

Provides a single shared ``redis.asyncio.Redis`` connection for pub/sub,
session storage, and distributed locks.  If ``REDIS_URL`` is empty (local dev
or test), ``init_redis()`` is a no-op and ``is_redis_available()`` returns False.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_state: dict[str, object] = {"client": None}


async def init_redis() -> None:
    """Open a Redis connection.  No-op when ``REDIS_URL`` is not set."""
    from shared.infrastructure.config import REDIS_URL

    if not REDIS_URL:
        logger.info("REDIS_URL not set — running in local-only mode (no Redis)")
        return

    import redis.asyncio as aioredis

    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    await client.ping()
    _state["client"] = client
    logger.info("Redis connected (%s)", REDIS_URL.split("@")[-1])


def get_redis():
    """Return the active ``redis.asyncio.Redis`` client.

    Raises ``RuntimeError`` if Redis was not initialised (or REDIS_URL was empty).
    """
    client = _state["client"]
    if client is None:
        raise RuntimeError("Redis not initialised. Call init_redis() at startup.")
    return client


def is_redis_available() -> bool:
    """True when a Redis connection is active."""
    return _state["client"] is not None


async def close_redis() -> None:
    """Close the Redis connection pool."""
    client = _state["client"]
    if client is not None:
        await client.aclose()
        _state["client"] = None
        logger.info("Redis connection closed")
