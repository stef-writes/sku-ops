"""Fiscal period repository — persistence for fiscal periods."""

from finance.domain.fiscal_period import FiscalPeriod
from shared.infrastructure.database import get_connection, get_org_id


async def get_period(period_id: str) -> FiscalPeriod | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM fiscal_periods WHERE id = ? AND organization_id = ?",
        (period_id, org_id),
    )
    row = await cursor.fetchone()
    return FiscalPeriod.model_validate(dict(row)) if row else None


async def list_periods(status: str | None = None) -> list[FiscalPeriod]:
    conn = get_connection()
    org_id = get_org_id()
    query = "SELECT * FROM fiscal_periods WHERE organization_id = ?"
    params: list = [org_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY start_date DESC"
    cursor = await conn.execute(query, params)
    return [FiscalPeriod.model_validate(dict(r)) for r in await cursor.fetchall()]


async def insert_period(
    period_id: str,
    name: str,
    start_date: str,
    end_date: str,
    created_at: str,
) -> None:
    conn = get_connection()
    org_id = get_org_id()
    await conn.execute(
        """INSERT INTO fiscal_periods (id, name, start_date, end_date, status, organization_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (period_id, name, start_date, end_date, "open", org_id, created_at),
    )
    await conn.commit()


async def close_period(period_id: str, closed_by_id: str, closed_at: str) -> None:
    conn = get_connection()
    await conn.execute(
        "UPDATE fiscal_periods SET status = 'closed', closed_by_id = ?, closed_at = ? WHERE id = ?",
        (closed_by_id, closed_at, period_id),
    )
    await conn.commit()


async def find_closed_period_covering(entry_date: str) -> tuple[str, str] | None:
    """Return (id, name) of a closed fiscal period covering entry_date, or None."""
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, name FROM fiscal_periods
           WHERE organization_id = ? AND status = 'closed'
             AND ? >= start_date AND ? <= end_date
           LIMIT 1""",
        (org_id, entry_date[:10], entry_date[:10]),
    )
    row = await cursor.fetchone()
    return (row["id"], row["name"]) if row else None
