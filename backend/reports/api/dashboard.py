"""Dashboard stats routes."""
import asyncio
from datetime import UTC, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from catalog.application.queries import (
    count_all_products,
    count_low_stock,
    count_vendors,
    list_low_stock,
    list_products,
)
from finance.application import ledger_queries as ledger_repo
from identity.application.auth_service import get_current_user, require_role
from identity.application.user_service import count_contractors
from kernel.types import CurrentUser, round_money
from operations.application.queries import list_withdrawals
from shared.infrastructure.database import get_connection

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _parse_date_range(start_date: str | None, end_date: str | None):
    """Return (start_iso, end_iso) falling back to sensible defaults when absent."""
    return start_date or None, end_date or None


def _parse_iso(s: str) -> datetime:
    """Parse an ISO date string, handling the trailing 'Z' that JS produces."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _build_daily_chart(withdrawals: list, start: datetime, end: datetime) -> list:
    """Bucket withdrawal totals and costs by calendar day between start and end."""
    days = (end - start).days + 1
    rev_buckets: dict[str, float] = {}
    cost_buckets: dict[str, float] = {}
    for i in range(days):
        key = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        rev_buckets[key] = 0
        cost_buckets[key] = 0
    for w in withdrawals:
        created = w.get("created_at", "")[:10]
        if created in rev_buckets:
            rev_buckets[created] += w.get("total", 0)
            cost_buckets[created] += w.get("cost_total", 0)
    return [
        {"date": k, "revenue": round(rev_buckets[k], 2), "cost": round(cost_buckets[k], 2),
         "profit": round(rev_buckets[k] - cost_buckets[k], 2)}
        for k in sorted(rev_buckets)
    ]


@router.get("/stats")
async def get_dashboard_stats(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
):
    now = datetime.now(UTC)
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

    (
        range_withdrawals,
        unpaid_withdrawals,
        products,
        total_products,
        low_stock_products,
        total_vendors,
        total_contractors,
        low_stock_items,
        by_department,
    ) = await asyncio.gather(
        list_withdrawals(start_date=sd, end_date=ed, limit=10000, organization_id=org_id),
        list_withdrawals(payment_status="unpaid", start_date=sd, end_date=ed, limit=10000, organization_id=org_id),
        list_products(organization_id=org_id),
        count_all_products(org_id),
        count_low_stock(org_id),
        count_vendors(org_id),
        count_contractors(org_id),
        list_low_stock(10, org_id),
        ledger_repo.summary_by_department(org_id, start_date=sd, end_date=ed),
    )

    range_revenue = sum(w.get("total", 0) for w in range_withdrawals)
    range_cogs = sum(w.get("cost_total", 0) for w in range_withdrawals)
    range_transactions = len(range_withdrawals)
    unpaid_total = sum(w.get("total", 0) for w in unpaid_withdrawals)

    # Inventory investment: what's the cost basis of stock on hand
    inventory_cost = round_money(sum(p.get("cost", 0) * p.get("quantity", 0) for p in products))
    inventory_retail = round_money(sum(p.get("price", 0) * p.get("quantity", 0) for p in products))
    inventory_units = sum(p.get("quantity", 0) for p in products)

    # Department margins from the ledger (for the selected period)
    dept_margins = []
    for d in by_department:
        dept_margins.append({
            "department": d["department"],
            "revenue": round_money(d["revenue"]),
            "cost": round_money(d["cost"]),
            "profit": round_money(d["profit"]),
            "margin_pct": d["margin_pct"],
        })
    dept_margins.sort(key=lambda x: x["revenue"], reverse=True)

    # PO summary
    conn = get_connection()
    po_cursor = await conn.execute(
        """SELECT status, COUNT(*) as cnt, COALESCE(SUM(total), 0) as total
           FROM purchase_orders WHERE organization_id = ?
           GROUP BY status""",
        (org_id,),
    )
    po_rows = await po_cursor.fetchall()
    po_summary = {r["status"]: {"count": r["cnt"], "total": round_money(r["total"])} for r in po_rows}

    chart_start = (
        _parse_iso(sd) if sd
        else (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    )
    chart_end = _parse_iso(ed) if ed else now
    daily_chart = _build_daily_chart(range_withdrawals, chart_start, chart_end)

    gross_profit = round_money(range_revenue - range_cogs)
    margin_pct = round(gross_profit / range_revenue * 100, 1) if range_revenue > 0 else 0

    return {
        "range_revenue": round_money(range_revenue),
        "range_cogs": round_money(range_cogs),
        "range_gross_profit": gross_profit,
        "range_margin_pct": margin_pct,
        "range_transactions": range_transactions,
        "revenue_by_day": daily_chart,
        "total_products": total_products,
        "low_stock_count": low_stock_products,
        "total_vendors": total_vendors,
        "total_contractors": total_contractors,
        "unpaid_total": round_money(unpaid_total),
        "low_stock_alerts": low_stock_items,
        "inventory_cost": inventory_cost,
        "inventory_retail": inventory_retail,
        "inventory_units": inventory_units,
        "dept_margins": dept_margins,
        "po_summary": po_summary,
    }


@router.get("/transactions")
async def get_dashboard_transactions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    contractor_id: str | None = Query(None),
    payment_status: str | None = Query(None),
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
