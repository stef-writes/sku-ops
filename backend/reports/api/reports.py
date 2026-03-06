"""Sales, inventory, and financial report routes.

All monetary reports read from the financial_ledger table via ledger_repo.
Inventory report remains current-state (product quantities).
"""
import asyncio
from datetime import UTC, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from catalog.application.queries import list_low_stock, list_products
from finance.application import ledger_queries as ledger_repo
from identity.application.auth_service import require_role
from kernel.types import CurrentUser, round_money
from shared.infrastructure.database import get_connection

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/sales")
async def get_sales_report(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id

    accounts, top_products, counts, catalog, payment_status = await asyncio.gather(
        ledger_repo.summary_by_account(org_id, start_date=start_date, end_date=end_date),
        ledger_repo.product_margins(org_id, start_date=start_date, end_date=end_date, limit=10),
        ledger_repo.reference_counts(org_id, start_date=start_date, end_date=end_date),
        list_products(organization_id=org_id),
        ledger_repo.payment_status_breakdown(org_id, start_date=start_date, end_date=end_date),
    )
    product_map = {p["id"]: p for p in catalog}
    for m in top_products:
        p = product_map.get(m["product_id"], {})
        m["name"] = p.get("name", "Unknown")
        m["sku"] = p.get("sku", "")

    revenue = accounts.get("revenue", 0)
    cogs = accounts.get("cogs", 0)
    tax = accounts.get("tax_collected", 0)
    gross_profit = round_money(revenue - cogs)
    tx_count = counts.get("withdrawal", 0)
    return_count = counts.get("return", 0)

    return {
        "gross_revenue": round_money(revenue),
        "returns_total": 0,
        "net_revenue": round_money(revenue),
        "total_cogs": round_money(cogs),
        "gross_profit": gross_profit,
        "gross_margin_pct": round(gross_profit / revenue * 100, 1) if revenue > 0 else 0,
        "total_tax": round_money(tax),
        "total_transactions": tx_count,
        "return_count": return_count,
        "average_transaction": round_money(revenue / tx_count) if tx_count > 0 else 0,
        "by_payment_status": payment_status,
        "top_products": top_products,
        "total_revenue": round_money(revenue),
    }


@router.get("/inventory")
async def get_inventory_report(current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.organization_id
    products = await list_products(organization_id=org_id)

    total_products = len(products)
    total_retail = round_money(sum(p.get("price", 0) * p.get("quantity", 0) for p in products))
    total_cost = round_money(sum(p.get("cost", 0) * p.get("quantity", 0) for p in products))
    unrealized_margin = round_money(total_retail - total_cost)
    margin_pct = round(unrealized_margin / total_retail * 100, 1) if total_retail > 0 else 0
    low_stock = [p for p in products if p.get("quantity", 0) <= p.get("min_stock", 5)]
    out_of_stock = [p for p in products if p.get("quantity", 0) == 0]

    by_department: dict = {}
    for p in products:
        dept = p.get("department_name", "Unknown")
        if dept not in by_department:
            by_department[dept] = {"count": 0, "retail_value": 0, "cost_value": 0}
        by_department[dept]["count"] += 1
        by_department[dept]["retail_value"] += p.get("price", 0) * p.get("quantity", 0)
        by_department[dept]["cost_value"] += p.get("cost", 0) * p.get("quantity", 0)

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
        # Keep old key for backwards compat
        "potential_profit": unrealized_margin,
        "low_stock_count": len(low_stock),
        "out_of_stock_count": len(out_of_stock),
        "low_stock_items": low_stock[:20],
        "by_department": by_department,
    }


@router.get("/trends")
async def get_trends_report(
    start_date: str | None = None,
    end_date: str | None = None,
    group_by: str = "day",
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    """Revenue/cost/profit trends from the ledger."""
    org_id = current_user.organization_id
    series = await ledger_repo.trend_series(
        org_id=org_id, start_date=start_date, end_date=end_date, group_by=group_by,
    )

    totals = {
        "revenue": round_money(sum(r["revenue"] for r in series)),
        "cost": round_money(sum(r["cost"] for r in series)),
        "profit": round_money(sum(r["profit"] for r in series)),
    }
    return {"series": series, "totals": totals}


@router.get("/product-margins")
async def get_product_margins(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id
    margin_data, catalog = await asyncio.gather(
        ledger_repo.product_margins(
            org_id=org_id, start_date=start_date, end_date=end_date, limit=limit,
        ),
        list_products(organization_id=org_id),
    )
    product_map = {p["id"]: p for p in catalog}
    for m in margin_data:
        p = product_map.get(m["product_id"], {})
        m["name"] = p.get("name", "Unknown")
        m["sku"] = p.get("sku", "")
    return {"products": margin_data}


@router.get("/job-pl")
async def get_job_pl(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    """Per-job P&L from the ledger."""
    org_id = current_user.organization_id
    jobs = await ledger_repo.summary_by_job(
        org_id=org_id, start_date=start_date, end_date=end_date, limit=limit,
    )

    total_revenue = sum(j["revenue"] for j in jobs)
    total_cost = sum(j["cost"] for j in jobs)
    total_profit = total_revenue - total_cost

    return {
        "jobs": jobs,
        "total_revenue": round_money(total_revenue),
        "total_cost": round_money(total_cost),
        "total_profit": round_money(total_profit),
        "total_margin_pct": round((total_profit / total_revenue * 100) if total_revenue > 0 else 0, 1),
    }


@router.get("/pl")
async def get_pl(
    group_by: str = "overall",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    """Unified P&L endpoint. group_by: overall | job | contractor | department | entity | product."""
    org_id = current_user.organization_id
    date_kw = dict(start_date=start_date, end_date=end_date)

    if group_by == "overall":
        accounts = await ledger_repo.summary_by_account(org_id, **date_kw)
        revenue = accounts.get("revenue", 0)
        cogs = accounts.get("cogs", 0)
        tax = accounts.get("tax_collected", 0)
        shrinkage = accounts.get("shrinkage", 0)
        profit = round_money(revenue - cogs - shrinkage)
        return {
            "group_by": "overall",
            "summary": {
                "revenue": round_money(revenue),
                "cogs": round_money(cogs),
                "tax_collected": round_money(tax),
                "shrinkage": round_money(shrinkage),
                "gross_profit": profit,
                "margin_pct": round(profit / revenue * 100, 1) if revenue > 0 else 0,
            },
            "rows": [],
        }

    if group_by == "job":
        rows = await ledger_repo.summary_by_job(org_id, **date_kw, limit=limit)
        label_key = "job_id"
    elif group_by == "contractor":
        rows = await ledger_repo.summary_by_contractor(org_id, **date_kw)
        label_key = "contractor_id"
    elif group_by == "department":
        rows = await ledger_repo.summary_by_department(org_id, **date_kw)
        label_key = "department"
    elif group_by == "entity":
        rows = await ledger_repo.summary_by_billing_entity(org_id, **date_kw)
        label_key = "billing_entity"
    elif group_by == "product":
        rows, catalog = await asyncio.gather(
            ledger_repo.product_margins(org_id, **date_kw, limit=limit),
            list_products(organization_id=org_id),
        )
        pmap = {p["id"]: p for p in catalog}
        for m in rows:
            p = pmap.get(m["product_id"], {})
            m["name"] = p.get("name", "Unknown")
        label_key = "name"
    else:
        rows = []
        label_key = "name"

    total_revenue = sum(r.get("revenue", 0) for r in rows)
    total_cost = sum(r.get("cost", 0) for r in rows)
    total_profit = round_money(total_revenue - total_cost)

    return {
        "group_by": group_by,
        "summary": {
            "revenue": round_money(total_revenue),
            "cogs": round_money(total_cost),
            "gross_profit": total_profit,
            "margin_pct": round(total_profit / total_revenue * 100, 1) if total_revenue > 0 else 0,
        },
        "rows": rows,
        "label_key": label_key,
    }


@router.get("/ar-aging")
async def get_ar_aging(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    """Accounts receivable aging buckets by billing entity."""
    return await ledger_repo.ar_aging(
        current_user.organization_id, start_date=start_date, end_date=end_date,
    )


@router.get("/kpis")
async def get_kpis(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id

    accounts, products_data, units_sold_map = await asyncio.gather(
        ledger_repo.summary_by_account(org_id=org_id, start_date=start_date, end_date=end_date),
        list_products(organization_id=org_id),
        ledger_repo.units_sold_by_product(org_id=org_id, start_date=start_date, end_date=end_date),
    )

    total_revenue = accounts.get("revenue", 0)
    total_cogs = accounts.get("cogs", 0)
    inventory_cost_value = sum(p.get("cost", 0) * p.get("quantity", 0) for p in products_data)

    if start_date and end_date:
        try:
            d_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            d_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            period_days = max((d_end - d_start).days, 1)
        except ValueError:
            period_days = 365
    else:
        period_days = 365

    inventory_turnover = total_cogs / inventory_cost_value if inventory_cost_value > 0 else 0
    dio = (inventory_cost_value / total_cogs * period_days) if total_cogs > 0 else 0
    gross_margin_pct = ((total_revenue - total_cogs) / total_revenue * 100) if total_revenue > 0 else 0

    total_units_sold = sum(units_sold_map.values())
    total_stock = sum(p.get("quantity", 0) for p in products_data)
    sell_through_pct = (total_units_sold / (total_units_sold + total_stock) * 100) if (total_units_sold + total_stock) > 0 else 0

    return {
        "period_days": period_days,
        "total_revenue": round_money(total_revenue),
        "total_cogs": round_money(total_cogs),
        "gross_profit": round_money(total_revenue - total_cogs),
        "gross_margin_pct": round(gross_margin_pct, 1),
        "inventory_cost_value": round_money(inventory_cost_value),
        "inventory_turnover": round(inventory_turnover, 2),
        "dio": round(dio, 1),
        "sell_through_pct": round(sell_through_pct, 1),
        "total_units_sold": total_units_sold,
    }


@router.get("/product-performance")
async def get_product_performance(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 200,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id

    margin_data, products_data, units_sold_map = await asyncio.gather(
        ledger_repo.product_margins(
            org_id=org_id, start_date=start_date, end_date=end_date, limit=limit,
        ),
        list_products(organization_id=org_id),
        ledger_repo.units_sold_by_product(org_id=org_id, start_date=start_date, end_date=end_date),
    )

    product_map = {p["id"]: p for p in products_data}

    result = []
    for m in margin_data:
        pid = m["product_id"]
        p = product_map.get(pid, {})
        current_stock = p.get("quantity", 0)
        units_sold = units_sold_map.get(pid, 0)
        avg_cost = m["cost"] / units_sold if units_sold > 0 else 0
        sell_through = (units_sold / (units_sold + current_stock) * 100) if (units_sold + current_stock) > 0 else 0
        result.append({
            "product_id": pid,
            "name": p.get("name", "Unknown"),
            "sku": p.get("sku", ""),
            "department": p.get("department_name", ""),
            "current_stock": current_stock,
            "catalog_unit_cost": round(p.get("cost", 0), 2),
            "units_sold": units_sold,
            "avg_cost_per_unit": round(avg_cost, 2),
            "revenue": m["revenue"],
            "cogs": m["cost"],
            "gross_profit": m["profit"],
            "margin_pct": m["margin_pct"],
            "sell_through_pct": round(sell_through, 1),
        })

    return {"products": result, "total": len(result)}


@router.get("/reorder-urgency")
async def get_reorder_urgency(
    days: int = 30,
    limit: int = 50,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    """Products ranked by days-until-stockout using withdrawal velocity."""
    org_id = current_user.organization_id
    since = (datetime.now(UTC) - timedelta(days=min(days, 365))).isoformat()

    low_stock, all_products = await asyncio.gather(
        list_low_stock(limit=200, organization_id=org_id),
        list_products(organization_id=org_id),
    )

    product_ids = [p["id"] for p in low_stock]
    if not product_ids:
        return {"products": [], "total": 0}

    conn = get_connection()
    placeholders = ",".join("?" * len(product_ids))
    cur = await conn.execute(
        f"""SELECT product_id, COALESCE(SUM(ABS(quantity_delta)), 0) as total_used
            FROM stock_transactions
            WHERE product_id IN ({placeholders}) AND transaction_type = 'WITHDRAWAL' AND created_at >= ?
            GROUP BY product_id""",
        (*product_ids, since),
    )
    velocity_map = {row["product_id"]: row["total_used"] for row in await cur.fetchall()}

    result = []
    for p in low_stock:
        total_used = velocity_map.get(p["id"], 0)
        avg_daily = total_used / days
        qty = p.get("quantity", 0)
        days_until_zero = round(qty / avg_daily, 1) if avg_daily > 0 else None
        urgency = (
            "critical" if days_until_zero is not None and days_until_zero <= 3
            else "high" if days_until_zero is not None and days_until_zero <= 7
            else "medium" if days_until_zero is not None and days_until_zero <= 30
            else "low" if days_until_zero is not None
            else "no_data"
        )
        result.append({
            "product_id": p["id"],
            "name": p.get("name", "Unknown"),
            "sku": p.get("sku", ""),
            "department": p.get("department_name", ""),
            "current_stock": qty,
            "min_stock": p.get("min_stock", 0),
            "avg_daily_use": round(avg_daily, 2),
            "days_until_stockout": days_until_zero,
            "urgency": urgency,
        })

    result.sort(key=lambda x: (
        x["days_until_stockout"] is None,
        x["days_until_stockout"] if x["days_until_stockout"] is not None else 9999,
    ))

    return {"products": result[:limit], "total": len(result)}


@router.get("/product-activity")
async def get_product_activity(
    product_id: str | None = None,
    days: int = 365,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    """Daily withdrawal activity heatmap data. Optional product_id filter."""
    org_id = current_user.organization_id
    since = (datetime.now(UTC) - timedelta(days=min(days, 730))).isoformat()
    conn = get_connection()

    params: list = [org_id, since]
    product_filter = ""
    if product_id:
        product_filter = " AND product_id = ?"
        params.append(product_id)

    cur = await conn.execute(
        f"""SELECT DATE(created_at) AS day,
                   COUNT(*) AS transaction_count,
                   COALESCE(SUM(ABS(quantity_delta)), 0) AS units_moved
            FROM stock_transactions
            WHERE (organization_id = ? OR organization_id IS NULL)
              AND transaction_type = 'WITHDRAWAL'
              AND created_at >= ?
              {product_filter}
            GROUP BY day
            ORDER BY day""",
        params,
    )
    rows = [dict(r) for r in await cur.fetchall()]

    return {"series": rows, "product_id": product_id, "days": days}
