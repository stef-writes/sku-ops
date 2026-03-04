"""In-memory chat session store with TTL, turn-based windowing, and cost tracking.

Sessions expire after 30 min of inactivity. History is trimmed to the last
_MAX_TURNS user+assistant pairs to keep model context bounded.
"""
import time

_SESSIONS: dict = {}
_SESSION_TTL = 1800  # 30 min inactivity → expire
_MAX_TURNS = 20      # keep last N user+assistant pairs (= 2N messages)


def get_or_create(session_id: str) -> list[dict]:
    """Return existing message history or initialise a new empty session."""
    _lazy_cleanup()
    entry = _SESSIONS.setdefault(session_id, {"history": [], "cost_usd": 0.0, "ts": time.monotonic()})
    entry["ts"] = time.monotonic()
    return list(entry["history"])


def get_cost(session_id: str) -> float:
    """Return cumulative spend for this session (0.0 if session doesn't exist)."""
    entry = _SESSIONS.get(session_id)
    return entry["cost_usd"] if entry else 0.0


def update(session_id: str, history: list[dict], cost_usd: float = 0.0) -> None:
    """Replace session history (windowed) and accumulate cost."""
    trimmed = history[-(_MAX_TURNS * 2):]
    existing = _SESSIONS.get(session_id, {})
    _SESSIONS[session_id] = {
        "history": trimmed,
        "cost_usd": existing.get("cost_usd", 0.0) + cost_usd,
        "ts": time.monotonic(),
    }


def clear(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


def _lazy_cleanup() -> None:
    now = time.monotonic()
    expired = [sid for sid, e in list(_SESSIONS.items()) if now - e["ts"] > _SESSION_TTL]
    for sid in expired:
        del _SESSIONS[sid]
