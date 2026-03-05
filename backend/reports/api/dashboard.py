"""Dashboard stats routes."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from identity.application.auth_service import get_current_user, require_role
from kernel.types import CurrentUser
from catalog.application.queries import count_all_products, count_low_stock, list_low_stock, count_vendors
from identity.application.user_service import count_contractors
from operations.application.queries import list_withdrawals

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _parse_date_range(start_date: Optional[str], end_date: Optional[str]):
    """Return (start_iso, end_iso) falling back to sensible defaults when absent."""
    return start_date or None, end_date or None


def _build_revenue_by_day(withdrawals: list, start: datetime, end: datetime) -> list:
    """Bucket withdrawal totals by calendar day between start and end."""
    days = (end - start).days + 1
    buckets: dict[str, float] = {}
    for i in range(days):
        key = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        buckets[key] = 0
    for w in withdrawals:
        created = w.get("created_at", "")[:10]
        if created in buckets:
            buckets[created] += w.get("total", 0)
    return [{"date": k, "revenue": round(v, 2)} for k, v in sorted(buckets.items())]


@router.get("/stats")
async def get_dashboard_stats(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    org_id = current_user.organization_id
    sd, ed = _parse_date_range(start_date, end_date)

    if current_user.role == "contractor":
        my_withdrawals = await list_withdrawals(
            contractor_id=current_user.id, start_date=sd, end_date=ed,
            limit=1000, organization_id=org_id,
        )
        total_spent = sum(w.get("total", 0) for w in my_withdrawals)
        unpaid = sum(w.get("total", 0) for w in my_withdrawals if w.get("payment_status") == "unpaid")
        return {
            "total_withdrawals": len(my_withdrawals),
            "total_spent": round(total_spent, 2),
            "unpaid_balance": round(unpaid, 2),
            "recent_withdrawals": my_withdrawals[:5],
        }

    range_withdrawals = await list_withdrawals(
        start_date=sd, end_date=ed, limit=10000, organization_id=org_id,
    )
    range_revenue = sum(w.get("total", 0) for w in range_withdrawals)
    range_transactions = len(range_withdrawals)

    total_products = await count_all_products(org_id)
    low_stock_products = await count_low_stock(org_id)
    total_vendors = await count_vendors(org_id)
    total_contractors = await count_contractors(org_id)

    unpaid_withdrawals = await list_withdrawals(
        payment_status="unpaid", start_date=sd, end_date=ed,
        limit=10000, organization_id=org_id,
    )
    unpaid_total = sum(w.get("total", 0) for w in unpaid_withdrawals)

    low_stock_items = await list_low_stock(10, org_id)

    chart_start = (
        datetime.fromisoformat(sd) if sd
        else (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    )
    chart_end = datetime.fromisoformat(ed) if ed else now
    revenue_by_day_list = _build_revenue_by_day(range_withdrawals, chart_start, chart_end)

    return {
        "range_revenue": round(range_revenue, 2),
        "range_transactions": range_transactions,
        "revenue_by_day": revenue_by_day_list,
        "total_products": total_products,
        "low_stock_count": low_stock_products,
        "total_vendors": total_vendors,
        "total_contractors": total_contractors,
        "unpaid_total": round(unpaid_total, 2),
        "low_stock_alerts": low_stock_items,
    }


@router.get("/transactions")
async def get_dashboard_transactions(
    limit: int = 20,
    offset: int = 0,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    contractor_id: Optional[str] = Query(None),
    payment_status: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    """Paginated transactions for the dashboard. Supports date range + filters."""
    org_id = current_user.organization_id
    sd, ed = _parse_date_range(start_date, end_date)

    fetch_limit = limit + 1
    rows = await list_withdrawals(
        start_date=sd,
        end_date=ed,
        contractor_id=contractor_id or None,
        payment_status=payment_status or None,
        limit=fetch_limit,
        offset=offset,
        organization_id=org_id,
    )
    has_more = len(rows) > limit
    withdrawals = rows[:limit]
    return {"withdrawals": withdrawals, "has_more": has_more}
