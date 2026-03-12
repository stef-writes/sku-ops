"""Fiscal period application service."""

from datetime import UTC, datetime
from uuid import uuid4

from finance.domain.fiscal_period import FiscalPeriodCreate
from finance.infrastructure.fiscal_period_repo import (
    close_period,
    find_closed_period_covering,
    get_period,
    insert_period,
    list_periods,
)
from shared.kernel.errors import ResourceNotFoundError


async def check_period_open(entry_date: str) -> None:
    """Raise ValueError if the entry date falls in a closed fiscal period."""
    period = await find_closed_period_covering(entry_date)
    if period:
        raise ValueError(
            f"Cannot create entries in closed fiscal period '{period.get('name', period['id'])}'"
        )


async def list_fiscal_periods(status: str | None = None) -> list[dict]:
    return await list_periods(status=status)


async def create_fiscal_period(body: FiscalPeriodCreate) -> dict:
    period_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    await insert_period(
        period_id=period_id,
        name=body.name,
        start_date=body.start_date,
        end_date=body.end_date,
        created_at=now,
    )
    result = await get_period(period_id)
    if not result:
        raise ResourceNotFoundError("Fiscal period not found after insert")
    return result


async def close_fiscal_period(
    period_id: str,
    closed_by_id: str,
) -> dict:
    period = await get_period(period_id)
    if not period:
        raise ResourceNotFoundError("Fiscal period not found")
    if period.get("status") != "open":
        raise ValueError("Period is already closed")

    now = datetime.now(UTC).isoformat()
    await close_period(period_id, closed_by_id=closed_by_id, closed_at=now)
    result = await get_period(period_id)
    if not result:
        raise ResourceNotFoundError("Fiscal period not found after close")
    return result
