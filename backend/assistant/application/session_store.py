"""Chat session store with TTL, turn-based windowing, and cost tracking.

When Redis is available, sessions are stored as Redis hashes with automatic
TTL expiry.  Without Redis, falls back to an in-process dict (single-worker
dev/test).

All public functions are async to support both paths transparently.
"""
from __future__ import annotations

import json
import logging
import time

logger = logging.getLogger(__name__)

_SESSIONS: dict = {}
_SESSION_TTL = 1800  # 30 min
_MAX_TURNS = 20      # keep last N user+assistant pairs (= 2N messages)

_KEY_PREFIX = "sku_ops:session:"


def _redis():
    from shared.infrastructure.redis import get_redis
    return get_redis()


def _use_redis() -> bool:
    from shared.infrastructure.redis import is_redis_available
    return is_redis_available()


# --------------------------------------------------------------------------
# Public API — async
# --------------------------------------------------------------------------

async def get_or_create(session_id: str) -> list[dict]:
    """Return existing message history or initialise a new empty session."""
    if _use_redis():
        return await _redis_get_or_create(session_id)
    _lazy_cleanup()
    entry = _SESSIONS.setdefault(
        session_id,
        {"history": [], "cost_usd": 0.0, "ts": time.monotonic()},
    )
    entry["ts"] = time.monotonic()
    return list(entry["history"])


async def get_cost(session_id: str) -> float:
    """Return cumulative spend for this session (0.0 if missing)."""
    if _use_redis():
        return await _redis_get_cost(session_id)
    entry = _SESSIONS.get(session_id)
    return entry["cost_usd"] if entry else 0.0


async def update(session_id: str, history: list[dict], cost_usd: float = 0.0) -> None:
    """Replace session history (windowed) and accumulate cost."""
    trimmed = history[-(_MAX_TURNS * 2):]
    if _use_redis():
        await _redis_update(session_id, trimmed, cost_usd)
        return
    existing = _SESSIONS.get(session_id, {})
    _SESSIONS[session_id] = {
        "history": trimmed,
        "cost_usd": existing.get("cost_usd", 0.0) + cost_usd,
        "ts": time.monotonic(),
    }


async def clear(session_id: str) -> None:
    if _use_redis():
        await _redis().delete(f"{_KEY_PREFIX}{session_id}")
        return
    _SESSIONS.pop(session_id, None)


# --------------------------------------------------------------------------
# Redis implementation
# --------------------------------------------------------------------------

async def _redis_get_or_create(session_id: str) -> list[dict]:
    r = _redis()
    key = f"{_KEY_PREFIX}{session_id}"
    raw = await r.hget(key, "history")
    if raw is not None:
        await r.expire(key, _SESSION_TTL)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    await r.hset(key, mapping={"history": "[]", "cost_usd": "0.0"})
    await r.expire(key, _SESSION_TTL)
    return []


async def _redis_get_cost(session_id: str) -> float:
    raw = await _redis().hget(f"{_KEY_PREFIX}{session_id}", "cost_usd")
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0


async def _redis_update(session_id: str, trimmed: list[dict], cost_usd: float) -> None:
    r = _redis()
    key = f"{_KEY_PREFIX}{session_id}"
    prev_cost = await _redis_get_cost(session_id)
    await r.hset(key, mapping={
        "history": json.dumps(trimmed),
        "cost_usd": str(prev_cost + cost_usd),
    })
    await r.expire(key, _SESSION_TTL)


# --------------------------------------------------------------------------
# Fallback helpers
# --------------------------------------------------------------------------

def _lazy_cleanup() -> None:
    now = time.monotonic()
    expired = [sid for sid, e in list(_SESSIONS.items()) if now - e["ts"] > _SESSION_TTL]
    for sid in expired:
        del _SESSIONS[sid]
