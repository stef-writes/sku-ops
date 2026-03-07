"""Dialect-aware SQL fragments.

Only needed for the handful of queries that use SQLite-specific functions.
Import ``dialect`` from the db package, then call these helpers to get the
correct SQL string for the active backend.
"""
from __future__ import annotations


def _get_dialect() -> str:
    from shared.infrastructure.db import _state
    backend = _state["backend"]
    return backend.dialect if backend else "sqlite"


# ── Time window filters ──────────────────────────────────────────────────────

def time_ago_expr(column: str, *, minutes: int = 0, hours: int = 0, days: int = 0) -> tuple[str, list]:
    """Return (sql_fragment, params) for a ``column >= NOW() - interval`` filter.

    SQLite:     ``created_at >= datetime('now', '-60 minutes')``
    PostgreSQL: ``created_at >= NOW() - INTERVAL '60 minutes'``

    The caller should splice the sql_fragment into a WHERE clause and extend
    their params list with the returned params.
    """
    d = _get_dialect()
    if minutes:
        interval_str = f"-{minutes} minutes"
        label = f"{minutes} minutes"
    elif hours:
        interval_str = f"-{hours} hours"
        label = f"{hours} hours"
    elif days:
        interval_str = f"-{days} days"
        label = f"{days} days"
    else:
        raise ValueError("Specify minutes, hours, or days")

    if d == "sqlite":
        return f"{column} >= datetime('now', ?)", [interval_str]
    return f"{column} >= NOW() - INTERVAL '{label}'", []


# ── Date formatting / grouping ────────────────────────────────────────────────

def date_group_expr(column: str, grain: str) -> str:
    """Return a SQL expression that groups a timestamp column by grain.

    grain: 'day' | 'week' | 'month'
    """
    d = _get_dialect()
    if d == "sqlite":
        return {
            "week": f"strftime('%Y-W%W', {column})",
            "month": f"strftime('%Y-%m', {column})",
        }.get(grain, f"strftime('%Y-%m-%d', {column})")
    if grain == "week":
        return f"to_char({column}::date, 'IYYY-\"W\"IW')"
    if grain == "month":
        return f"to_char({column}::date, 'YYYY-MM')"
    return f"to_char({column}::date, 'YYYY-MM-DD')"


def date_extract(column: str) -> str:
    """Return DATE(column) equivalent for grouping by calendar date."""
    d = _get_dialect()
    if d == "sqlite":
        return f"DATE({column})"
    return f"({column})::date"
