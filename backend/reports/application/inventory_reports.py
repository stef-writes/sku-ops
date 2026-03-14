"""Inventory and product report queries.

Catalog/product-heavy reports that depend on product state
and withdrawal velocity rather than the financial ledger.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from catalog.application.queries import list_low_stock, list_skus
from finance.application import ledger_queries as ledger_repo
from inventory.application.queries import daily_withdrawal_activity, withdrawal_velocity
from shared.infrastructure.db import get_org_id
from shared.kernel.types import round_money


async def inventory_report() -> dict:
    products = await list_skus()

    total_products = len(products)
    total_retail = round_money(sum(p.price * p.quantity for p in products))
    total_cost = round_money(sum(p.cost * p.quantity for p in products))
    unrealized_margin = round_money(total_retail - total_cost)
    margin_pct = round(unrealized_margin / total_retail * 100, 1) if total_retail > 0 else 0
    low_stock = [p for p in products if p.quantity <= p.min_stock]
    out_of_stock = [p for p in products if p.quantity == 0]

    by_department: dict = {}
    for p in products:
        dept = p.category_name or "Unknown"
        if dept not in by_department:
            by_department[dept] = {"count": 0, "retail_value": 0, "cost_value": 0}
        by_department[dept]["count"] += 1
        by_department[dept]["retail_value"] += p.price * p.quantity
        by_department[dept]["cost_value"] += p.cost * p.quantity

    for dept_data in by_department.values():
        dept_data["retail_value"] = round_money(dept_data["retail_value"])
        dept_data["cost_value"] = round_money(dept_data["cost_value"])
        dept_data["margin"] = round_money(dept_data["retail_value"] - dept_data["cost_value"])

    return {
        "total_products": total_products,
        "total_retail_value": total_retail,
        "total_cost_value": total_cost,
        "unrealized_margin": unrealized_margin,
        "margin_pct": margin_pct,
        "potential_profit": unrealized_margin,
        "low_stock_count": len(low_stock),
        "out_of_stock_count": len(out_of_stock),
        "low_stock_items": [p.model_dump() for p in low_stock[:20]],
        "by_department": by_department,
    }


async def product_performance_report(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 200,
) -> dict:
    margin_data, products_data, units_sold_map = await asyncio.gather(
        ledger_repo.product_margins(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        ),
        list_skus(),
        ledger_repo.units_sold_by_product(start_date=start_date, end_date=end_date),
    )

    product_map = {p.id: p for p in products_data}

    result = []
    for m in margin_data:
        pid = m["product_id"]
        p = product_map.get(pid)
        current_stock = p.quantity if p else 0
        units_sold = units_sold_map.get(pid, 0)
        avg_cost = m["cost"] / units_sold if units_sold > 0 else 0
        sell_through = (
            (units_sold / (units_sold + current_stock) * 100)
            if (units_sold + current_stock) > 0
            else 0
        )
        result.append(
            {
                "product_id": pid,
                "name": p.name if p else "Unknown",
                "sku": p.sku if p else "",
                "department": p.category_name if p else "",
                "current_stock": current_stock,
                "catalog_unit_cost": round(p.cost if p else 0, 2),
                "units_sold": units_sold,
                "avg_cost_per_unit": round(avg_cost, 2),
                "revenue": m["revenue"],
                "cogs": m["cost"],
                "gross_profit": m["profit"],
                "margin_pct": m["margin_pct"],
                "sell_through_pct": round(sell_through, 1),
            }
        )

    return {"products": result, "total": len(result)}


async def reorder_urgency_report(
    *,
    days: int = 30,
    limit: int = 50,
) -> dict:
    since = (datetime.now(UTC) - timedelta(days=min(days, 365))).isoformat()

    low_stock, _all_products = await asyncio.gather(
        list_low_stock(limit=200),
        list_skus(),
    )

    product_ids = [p.id for p in low_stock]
    if not product_ids:
        return {"products": [], "total": 0}

    velocity_map = await withdrawal_velocity(product_ids, since)

    result = []
    for p in low_stock:
        total_used = velocity_map.get(p.id, 0)
        avg_daily = total_used / days
        qty = p.quantity
        days_until_zero = round(qty / avg_daily, 1) if avg_daily > 0 else None
        urgency = (
            "critical"
            if days_until_zero is not None and days_until_zero <= 3
            else "high"
            if days_until_zero is not None and days_until_zero <= 7
            else "medium"
            if days_until_zero is not None and days_until_zero <= 30
            else "low"
            if days_until_zero is not None
            else "no_data"
        )
        result.append(
            {
                "product_id": p.id,
                "name": p.name,
                "sku": p.sku,
                "department": p.category_name,
                "current_stock": qty,
                "min_stock": p.min_stock,
                "avg_daily_use": round(avg_daily, 2),
                "days_until_stockout": days_until_zero,
                "urgency": urgency,
            }
        )

    result.sort(
        key=lambda x: (
            x["days_until_stockout"] is None,
            x["days_until_stockout"] if x["days_until_stockout"] is not None else 9999,
        )
    )

    return {"products": result[:limit], "total": len(result)}


async def product_activity_report(
    *,
    product_id: str | None = None,
    days: int = 365,
) -> dict:
    since = (datetime.now(UTC) - timedelta(days=min(days, 730))).isoformat()
    rows = await daily_withdrawal_activity(get_org_id(), since, product_id=product_id)
    return {"series": rows, "product_id": product_id, "days": days}
