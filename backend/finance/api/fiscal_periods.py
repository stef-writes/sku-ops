"""Fiscal period management routes."""
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request

from identity.application.auth_service import require_role
from kernel.types import CurrentUser
from shared.infrastructure.database import get_connection
from shared.infrastructure.middleware.audit import audit_log

router = APIRouter(prefix="/fiscal-periods", tags=["fiscal-periods"])


async def _get_period(period_id: str, org_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM fiscal_periods WHERE id = ? AND organization_id = ?",
        (period_id, org_id),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


@router.get("")
async def list_fiscal_periods(
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    conn = get_connection()
    org_id = current_user.organization_id
    query = "SELECT * FROM fiscal_periods WHERE organization_id = ?"
    params: list = [org_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY start_date DESC"
    cursor = await conn.execute(query, params)
    return [dict(r) for r in await cursor.fetchall()]


@router.post("")
async def create_fiscal_period(
    request: Request,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    body = await request.json()
    conn = get_connection()
    org_id = current_user.organization_id
    period_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await conn.execute(
        """INSERT INTO fiscal_periods (id, name, start_date, end_date, status, organization_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (period_id, body.get("name", ""), body["start_date"], body["end_date"], "open", org_id, now),
    )
    await conn.commit()
    return await _get_period(period_id, org_id)


@router.post("/{period_id}/close")
async def close_fiscal_period(
    period_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Close a fiscal period — prevents new ledger entries in this date range."""
    org_id = current_user.organization_id
    period = await _get_period(period_id, org_id)
    if not period:
        raise HTTPException(status_code=404, detail="Fiscal period not found")
    if period.get("status") != "open":
        raise HTTPException(status_code=400, detail="Period is already closed")

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    await conn.execute(
        "UPDATE fiscal_periods SET status = 'closed', closed_by_id = ?, closed_at = ? WHERE id = ?",
        (current_user.id, now, period_id),
    )
    await conn.commit()
    await audit_log(
        user_id=current_user.id, action="fiscal_period.close",
        resource_type="fiscal_period", resource_id=period_id,
        details={"name": period.get("name"), "start_date": period.get("start_date"), "end_date": period.get("end_date")},
        request=request, org_id=org_id,
    )
    return await _get_period(period_id, org_id)


async def check_period_open(entry_date: str, organization_id: str) -> None:
    """Raise ValueError if the entry date falls in a closed fiscal period."""
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT id, name FROM fiscal_periods
           WHERE organization_id = ? AND status = 'closed'
             AND ? >= start_date AND ? <= end_date
           LIMIT 1""",
        (organization_id, entry_date[:10], entry_date[:10]),
    )
    row = await cursor.fetchone()
    if row:
        period = dict(row)
        raise ValueError(f"Cannot create entries in closed fiscal period '{period.get('name', period['id'])}'")
