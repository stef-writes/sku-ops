"""Audit log read API — exposes the audit trail for admin review and export."""

import csv
import io
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from identity.application.queries import distinct_actions, query_audit_log
from shared.api.deps import AdminDep

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


@router.get("")
async def list_audit_log(
    current_user: AdminDep,
    user_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List audit log entries with optional filters. Admin only."""
    entries, total = await query_audit_log(
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
async def list_audit_actions(current_user: AdminDep):
    """Return distinct action names for filter dropdowns."""
    return await distinct_actions()


@router.get("/export")
async def export_audit_log(
    current_user: AdminDep,
    user_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """Export audit log as CSV. Admin only."""
    entries, _ = await query_audit_log(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        start_date=start_date,
        end_date=end_date,
        limit=10000,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "Timestamp",
            "User ID",
            "Action",
            "Resource Type",
            "Resource ID",
            "Details",
            "IP Address",
        ]
    )
    for e in entries:
        details = e.get("details", "")
        if isinstance(details, dict):
            details = json.dumps(details)
        writer.writerow(
            [
                e.get("id", ""),
                e.get("created_at", ""),
                e.get("user_id", ""),
                e.get("action", ""),
                e.get("resource_type", ""),
                e.get("resource_id", ""),
                details,
                e.get("ip_address", ""),
            ]
        )

    output.seek(0)
    filename = f"audit_log_{datetime.now(UTC).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
