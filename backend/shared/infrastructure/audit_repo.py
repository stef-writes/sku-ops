"""Audit log repository — persistence for audit trail queries.

Cross-cutting concern: every context writes audit entries,
and admins query them from a single API.
"""

from __future__ import annotations

import contextlib
import json

from shared.infrastructure.database import get_connection, get_org_id


async def query_audit_log(
    *,
    user_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Query audit log entries with optional filters. Returns (entries, total_count)."""
    org_id = get_org_id()
    conn = get_connection()
    where = "WHERE organization_id = $1"
    params: list = [org_id]
    n = 2

    if user_id:
        where += f" AND user_id = ${n}"
        params.append(user_id)
        n += 1
    if action:
        where += f" AND action LIKE ${n}"
        params.append(f"%{action}%")
        n += 1
    if resource_type:
        where += f" AND resource_type = ${n}"
        params.append(resource_type)
        n += 1
    if resource_id:
        where += f" AND resource_id = ${n}"
        params.append(resource_id)
        n += 1
    if start_date:
        where += f" AND created_at >= ${n}"
        params.append(start_date)
        n += 1
    if end_date:
        where += f" AND created_at <= ${n}"
        params.append(end_date)
        n += 1

    count_cursor = await conn.execute("SELECT COUNT(*) FROM audit_log " + where, params)
    count_row = await count_cursor.fetchone()
    total = count_row[0] if count_row else 0

    cursor = await conn.execute(
        "SELECT * FROM audit_log "
        + where
        + f" ORDER BY created_at DESC LIMIT ${n} OFFSET ${n + 1}",
        [*params, limit, offset],
    )
    rows = await cursor.fetchall()

    entries = []
    for row in rows:
        d = dict(row)
        if d.get("details"):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                d["details"] = json.loads(d["details"])
        entries.append(d)

    return entries, total


async def distinct_actions() -> list[str]:
    """Return distinct action names for filter dropdowns."""
    org_id = get_org_id()
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT DISTINCT action FROM audit_log WHERE organization_id = $1 ORDER BY action",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [row[0] for row in rows]
