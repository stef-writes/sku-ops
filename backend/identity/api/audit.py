"""Audit log read API — exposes the audit trail for admin review and export."""
import csv
import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from identity.application.auth_service import require_role
from kernel.types import CurrentUser
from shared.infrastructure.database import get_connection

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


async def _query_audit_log(
    org_id: str,
    *,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[dict], int]:
    conn = get_connection()
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

    count_cursor = await conn.execute(
        f"SELECT COUNT(*) FROM audit_log {where}", params
    )
    count_row = await count_cursor.fetchone()
    total = count_row[0] if count_row else 0

    cursor = await conn.execute(
        f"SELECT * FROM audit_log {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    rows = await cursor.fetchall()

    entries = []
    for row in rows:
        d = dict(row)
        if d.get("details"):
            try:
                d["details"] = json.loads(d["details"])
            except (json.JSONDecodeError, TypeError):
                pass
        entries.append(d)

    return entries, total


@router.get("")
async def list_audit_log(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """List audit log entries with optional filters. Admin only."""
    org_id = current_user.organization_id
    entries, total = await _query_audit_log(
        org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return {"entries": entries, "total": total, "limit": limit, "offset": offset}


@router.get("/actions")
async def list_audit_actions(
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Return distinct action names for filter dropdowns."""
    conn = get_connection()
    org_id = current_user.organization_id
    cursor = await conn.execute(
        "SELECT DISTINCT action FROM audit_log WHERE organization_id = ? ORDER BY action",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [row[0] for row in rows]


@router.get("/export")
async def export_audit_log(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Export audit log as CSV. Admin only."""
    org_id = current_user.organization_id
    entries, _ = await _query_audit_log(
        org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        start_date=start_date,
        end_date=end_date,
        limit=10000,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Timestamp", "User ID", "Action",
        "Resource Type", "Resource ID", "Details", "IP Address",
    ])
    for e in entries:
        details = e.get("details", "")
        if isinstance(details, dict):
            details = json.dumps(details)
        writer.writerow([
            e.get("id", ""),
            e.get("created_at", ""),
            e.get("user_id", ""),
            e.get("action", ""),
            e.get("resource_type", ""),
            e.get("resource_id", ""),
            details,
            e.get("ip_address", ""),
        ])

    output.seek(0)
    filename = f"audit_log_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
