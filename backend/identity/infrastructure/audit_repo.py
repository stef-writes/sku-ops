"""Audit log repository — persistence for audit trail queries."""

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
    conn = get_connection()
    org_id = get_org_id()
    where = "WHERE organization_id = ?"
    params: list = [org_id]

    if user_id:
        where += " AND user_id = ?"
        params.append(user_id)
    if action:
        where += " AND action LIKE ?"
        params.append(f"%{action}%")
    if resource_type:
        where += " AND resource_type = ?"
        params.append(resource_type)
    if resource_id:
        where += " AND resource_id = ?"
        params.append(resource_id)
    if start_date:
        where += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        where += " AND created_at <= ?"
        params.append(end_date)

    count_cursor = await conn.execute("SELECT COUNT(*) FROM audit_log " + where, params)
    count_row = await count_cursor.fetchone()
    total = count_row[0] if count_row else 0

    cursor = await conn.execute(
        "SELECT * FROM audit_log " + where + " ORDER BY created_at DESC LIMIT ? OFFSET ?",
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
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT DISTINCT action FROM audit_log WHERE organization_id = ? ORDER BY action",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [row[0] for row in rows]
