"""Dashboard stats computation — extracted from reports/api/dashboard.py."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from catalog.application.queries import (
    count_all_products,
    count_low_stock,
    count_vendors,
    list_low_stock,
    list_products,
)
from finance.application import ledger_queries as ledger_repo
from identity.application.user_service import count_contractors
from operations.application.queries import list_withdrawals
from purchasing.application.queries import po_summary_by_status
from shared.infrastructure.db import get_org_id
from shared.kernel.types import round_money


def _parse_date_range(start_date: str | None, end_date: str | None):
    return start_date or None, end_date or None


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


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
        created = (w.created_at or "")[:10]
        if created in rev_buckets:
            rev_buckets[created] += w.total
            cost_buckets[created] += w.cost_total
    return [
        {
            "date": k,
            "revenue": round(rev_buckets[k], 2),
            "cost": round(cost_buckets[k], 2),
            "profit": round(rev_buckets[k] - cost_buckets[k], 2),
        }
        for k in sorted(rev_buckets)
    ]


async def contractor_dashboard(
    contractor_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    sd, ed = _parse_date_range(start_date, end_date)
    my_withdrawals = await list_withdrawals(
        contractor_id=contractor_id,
        start_date=sd,
        end_date=ed,
        limit=1000,
    )
    total_spent = sum(w.total for w in my_withdrawals)
    unpaid = sum(w.total for w in my_withdrawals if w.payment_status == "unpaid")
    return {
        "total_withdrawals": len(my_withdrawals),
        "total_spent": round(total_spent, 2),
        "unpaid_balance": round(unpaid, 2),
        "recent_withdrawals": [w.model_dump() for w in my_withdrawals[:5]],
    }


async def admin_dashboard(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    now = datetime.now(UTC)
    sd, ed = _parse_date_range(start_date, end_date)

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
        list_withdrawals(start_date=sd, end_date=ed, limit=10000),
        list_withdrawals(payment_status="unpaid", start_date=sd, end_date=ed, limit=10000),
        list_products(),
        count_all_products(),
        count_low_stock(),
        count_vendors(),
        count_contractors(),
        list_low_stock(10),
        ledger_repo.summary_by_department(start_date=sd, end_date=ed),
    )

    range_revenue = sum(w.total for w in range_withdrawals)
    range_cogs = sum(w.cost_total for w in range_withdrawals)
    range_transactions = len(range_withdrawals)
    unpaid_total = sum(w.total for w in unpaid_withdrawals)

    inventory_cost = round_money(sum(p.cost * p.quantity for p in products))
    inventory_retail = round_money(sum(p.price * p.quantity for p in products))
    inventory_units = sum(p.quantity for p in products)

    dept_margins = []
    for d in by_department:
        dept_margins.append(
            {
                "department": d["department"],
                "revenue": round_money(d["revenue"]),
                "cost": round_money(d["cost"]),
                "profit": round_money(d["profit"]),
                "margin_pct": d["margin_pct"],
            }
        )
    dept_margins.sort(key=lambda x: x["revenue"], reverse=True)

    raw_po = await po_summary_by_status()
    po_summary = {
        status: {"count": v["count"], "total": round_money(v["total"])}
        for status, v in raw_po.items()
    }

    chart_start = (
        _parse_iso(sd)
        if sd
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
        "low_stock_alerts": [p.model_dump() for p in low_stock_items],
        "inventory_cost": inventory_cost,
        "inventory_retail": inventory_retail,
        "inventory_units": inventory_units,
        "dept_margins": dept_margins,
        "po_summary": po_summary,
    }


async def dashboard_transactions(
    *,
    limit: int = 20,
    offset: int = 0,
    start_date: str | None = None,
    end_date: str | None = None,
    contractor_id: str | None = None,
    payment_status: str | None = None,
) -> dict:
    sd, ed = _parse_date_range(start_date, end_date)
    fetch_limit = limit + 1
    rows = await list_withdrawals(
        start_date=sd,
        end_date=ed,
        contractor_id=contractor_id or None,
        payment_status=payment_status or None,
        limit=fetch_limit,
        offset=offset,
    )
    has_more = len(rows) > limit
    withdrawals = [w.model_dump() for w in rows[:limit]]
    return {"withdrawals": withdrawals, "has_more": has_more}
