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

from assistant.application.session_state import SessionState

logger = logging.getLogger(__name__)

_SESSIONS: dict = {}
_SESSION_TTL = 1800  # 30 min
_MAX_TURNS = 20  # keep last N user+assistant pairs (= 2N messages)

_KEY_PREFIX = "sku_ops:session:"
_MAX_ENTITIES = 10


def _state_to_json(state: SessionState | None) -> str:
    if state is None:
        return "{}"
    entities = [{"type": e.type, "id": e.id, "label": e.label} for e in state.entities]
    return json.dumps(
        {
            "entities": entities,
            "last_topic": state.last_topic,
            "updated_at": state.updated_at.isoformat(),
        }
    )


def _state_from_json(raw: str | None) -> SessionState | None:
    if not raw or raw == "{}":
        return None
    try:
        from datetime import UTC, datetime

        data = json.loads(raw)
        from assistant.application.session_state import EntityRef

        entities = [
            EntityRef(type=e["type"], id=e["id"], label=e["label"])
            for e in data.get("entities", [])[:_MAX_ENTITIES]
        ]
        updated = data.get("updated_at")
        dt = datetime.fromisoformat(updated) if updated else datetime.now(UTC)
        return SessionState(entities=entities, last_topic=data.get("last_topic"), updated_at=dt)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


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
    trimmed = history[-(_MAX_TURNS * 2) :]
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


async def get_state(session_id: str):
    """Return session state or None. Requires session_store.state module."""
    if _use_redis():
        raw = await _redis().hget(f"{_KEY_PREFIX}{session_id}", "state")
        if raw is None:
            return None
        try:
            d = json.loads(raw)
            return _dict_to_session_state(d)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None
    entry = _SESSIONS.get(session_id, {})
    state = entry.get("state")
    return state


async def update_state(session_id: str, state: SessionState | None) -> None:
    """Update session state."""
    if _use_redis():
        r = _redis()
        key = f"{_KEY_PREFIX}{session_id}"
        raw = json.dumps(_session_state_to_dict(state)) if state else "{}"
        await r.hset(key, "state", raw)
        await r.expire(key, _SESSION_TTL)
        return
    entry = _SESSIONS.setdefault(
        session_id, {"history": [], "cost_usd": 0.0, "ts": time.monotonic()}
    )
    entry["state"] = state
    entry["ts"] = time.monotonic()


def _session_state_to_dict(state) -> dict:
    from dataclasses import asdict

    return {
        "entities": [asdict(e) for e in state.entities],
        "last_topic": state.last_topic,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _dict_to_session_state(d: dict):
    from datetime import UTC, datetime

    from assistant.application.session_state import EntityRef, SessionState

    entities = [EntityRef(**e) for e in d.get("entities", [])]
    updated = d.get("updated_at")
    if isinstance(updated, str):
        try:
            updated = datetime.fromisoformat(updated)
        except ValueError:
            updated = datetime.now(UTC)
    elif updated is None:
        updated = datetime.now(UTC)
    return SessionState(
        entities=entities[:10],
        last_topic=d.get("last_topic"),
        updated_at=updated,
    )


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
    await r.hset(
        key,
        mapping={
            "history": json.dumps(trimmed),
            "cost_usd": str(prev_cost + cost_usd),
        },
    )
    await r.expire(key, _SESSION_TTL)


# --------------------------------------------------------------------------
# Fallback helpers
# --------------------------------------------------------------------------


def _lazy_cleanup() -> None:
    now = time.monotonic()
    expired = [sid for sid, e in list(_SESSIONS.items()) if now - e["ts"] > _SESSION_TTL]
    for sid in expired:
        del _SESSIONS[sid]
