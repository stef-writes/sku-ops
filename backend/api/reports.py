"""Sales and inventory report routes."""
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends

from auth import require_role
from db import get_connection
from repositories import product_repo, withdrawal_repo

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/sales")
async def get_sales_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.get("organization_id") or "default"
    withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=start_date, end_date=end_date, limit=10000, organization_id=org_id
    )

    total_revenue = sum(w.get("total", 0) for w in withdrawals)
    total_tax = sum(w.get("tax", 0) for w in withdrawals)
    total_transactions = len(withdrawals)

    by_status = {}
    for w in withdrawals:
        status = w.get("payment_status", "unknown")
        by_status[status] = by_status.get(status, 0) + w.get("total", 0)

    product_sales = {}
    total_cogs = 0.0
    for w in withdrawals:
        for item in w.get("items", []):
            pid = item.get("product_id")
            qty = item.get("quantity", 0)
            total_cogs += item.get("cost", 0) * qty
            if pid:
                if pid not in product_sales:
                    product_sales[pid] = {"name": item.get("name"), "quantity": 0, "revenue": 0}
                product_sales[pid]["quantity"] += qty
                product_sales[pid]["revenue"] += item.get("subtotal", 0)

    top_products = sorted(product_sales.values(), key=lambda x: x["revenue"], reverse=True)[:10]
    gross_profit = total_revenue - total_cogs

    return {
        "total_revenue": round(total_revenue, 2),
        "total_cogs": round(total_cogs, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_margin_pct": round(gross_profit / total_revenue * 100, 1) if total_revenue > 0 else 0,
        "total_tax": round(total_tax, 2),
        "total_transactions": total_transactions,
        "average_transaction": round(total_revenue / total_transactions, 2) if total_transactions > 0 else 0,
        "by_payment_status": by_status,
        "top_products": top_products,
    }


@router.get("/inventory")
async def get_inventory_report(current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.get("organization_id") or "default"
    products = await product_repo.list_products(organization_id=org_id)

    total_products = len(products)
    total_value = sum(p.get("price", 0) * p.get("quantity", 0) for p in products)
    total_cost = sum(p.get("cost", 0) * p.get("quantity", 0) for p in products)
    low_stock = [p for p in products if p.get("quantity", 0) <= p.get("min_stock", 5)]
    out_of_stock = [p for p in products if p.get("quantity", 0) == 0]

    by_department = {}
    for p in products:
        dept = p.get("department_name", "Unknown")
        if dept not in by_department:
            by_department[dept] = {"count": 0, "value": 0, "cost": 0}
        by_department[dept]["count"] += 1
        by_department[dept]["value"] += p.get("price", 0) * p.get("quantity", 0)
        by_department[dept]["cost"] += p.get("cost", 0) * p.get("quantity", 0)

    return {
        "total_products": total_products,
        "total_retail_value": round(total_value, 2),
        "total_cost_value": round(total_cost, 2),
        "potential_profit": round(total_value - total_cost, 2),
        "low_stock_count": len(low_stock),
        "out_of_stock_count": len(out_of_stock),
        "low_stock_items": low_stock[:20],
        "by_department": by_department,
    }


@router.get("/trends")
async def get_trends_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = "day",
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.get("organization_id") or "default"

    period_expr = {
        "week": "strftime('%Y-W%W', created_at)",
        "month": "strftime('%Y-%m', created_at)",
    }.get(group_by, "strftime('%Y-%m-%d', created_at)")

    query = f"""
        SELECT {period_expr} AS period,
               SUM(total) AS revenue,
               COALESCE(SUM(cost_total), 0) AS cost
        FROM withdrawals
        WHERE (organization_id = ? OR organization_id IS NULL)
          AND created_at IS NOT NULL
    """
    params = [org_id]
    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND created_at <= ?"
        params.append(end_date)
    query += " GROUP BY period ORDER BY period ASC"

    conn = get_connection()
    cursor = await conn.execute(query, params)
    rows = await cursor.fetchall()

    series = [
        {
            "date": row["period"],
            "revenue": round(row["revenue"] or 0, 2),
            "cost": round(row["cost"] or 0, 2),
            "profit": round((row["revenue"] or 0) - (row["cost"] or 0), 2),
        }
        for row in rows
    ]
    totals = {
        "revenue": round(sum(r["revenue"] for r in series), 2),
        "cost": round(sum(r["cost"] for r in series), 2),
        "profit": round(sum(r["profit"] for r in series), 2),
    }
    return {"series": series, "totals": totals}


@router.get("/product-margins")
async def get_product_margins(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.get("organization_id") or "default"
    withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=start_date, end_date=end_date, limit=10000, organization_id=org_id
    )

    product_stats: dict = {}
    for w in withdrawals:
        for item in w.get("items", []):
            pid = item.get("product_id")
            if not pid:
                continue
            if pid not in product_stats:
                product_stats[pid] = {
                    "name": item.get("name", "Unknown"),
                    "revenue": 0.0,
                    "cost": 0.0,
                    "quantity": 0,
                }
            qty = item.get("quantity", 0)
            product_stats[pid]["revenue"] += item.get("subtotal", 0)
            # Use historical cost stored at time of sale, not current catalog cost
            product_stats[pid]["cost"] += item.get("cost", 0) * qty
            product_stats[pid]["quantity"] += qty

    result = []
    for p in product_stats.values():
        profit = p["revenue"] - p["cost"]
        margin_pct = (profit / p["revenue"] * 100) if p["revenue"] > 0 else 0
        result.append({
            "name": p["name"],
            "revenue": round(p["revenue"], 2),
            "cost": round(p["cost"], 2),
            "profit": round(profit, 2),
            "margin_pct": round(margin_pct, 1),
            "quantity": p["quantity"],
        })

    result.sort(key=lambda x: x["revenue"], reverse=True)
    return {"products": result[:limit]}


@router.get("/job-pl")
async def get_job_pl(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """P&L grouped by job_id. sku-ops is the SSOT; this is the primary per-job P&L view."""
    org_id = current_user.get("organization_id") or "default"
    withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=start_date, end_date=end_date, limit=10000, organization_id=org_id
    )

    stats: dict = {}
    for w in withdrawals:
        job = w.get("job_id") or "—"
        if job not in stats:
            stats[job] = {
                "job_id": job,
                "billing_entity": w.get("billing_entity") or "",
                "revenue": 0.0,
                "cost": 0.0,
                "withdrawal_count": 0,
            }
        stats[job]["revenue"] += w.get("subtotal", 0)
        stats[job]["cost"] += w.get("cost_total", 0)
        stats[job]["withdrawal_count"] += 1
        if not stats[job]["billing_entity"]:
            stats[job]["billing_entity"] = w.get("billing_entity") or ""

    jobs = []
    for s in stats.values():
        profit = s["revenue"] - s["cost"]
        margin_pct = (profit / s["revenue"] * 100) if s["revenue"] > 0 else 0
        jobs.append({
            "job_id": s["job_id"],
            "billing_entity": s["billing_entity"],
            "withdrawal_count": s["withdrawal_count"],
            "revenue": round(s["revenue"], 2),
            "cost": round(s["cost"], 2),
            "profit": round(profit, 2),
            "margin_pct": round(margin_pct, 1),
        })

    jobs.sort(key=lambda x: x["revenue"], reverse=True)
    jobs = jobs[:limit]

    total_revenue = sum(j["revenue"] for j in jobs)
    total_cost = sum(j["cost"] for j in jobs)
    total_profit = total_revenue - total_cost

    return {
        "jobs": jobs,
        "total_revenue": round(total_revenue, 2),
        "total_cost": round(total_cost, 2),
        "total_profit": round(total_profit, 2),
        "total_margin_pct": round((total_profit / total_revenue * 100) if total_revenue > 0 else 0, 1),
    }


@router.get("/kpis")
async def get_kpis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.get("organization_id") or "default"
    products, withdrawals = await asyncio.gather(
        product_repo.list_products(organization_id=org_id),
        withdrawal_repo.list_withdrawals(
            start_date=start_date, end_date=end_date, limit=10000, organization_id=org_id
        ),
    )

    inventory_cost_value = sum(p.get("cost", 0) * p.get("quantity", 0) for p in products)
    total_units_in_catalog = sum(p.get("quantity", 0) for p in products)

    total_cogs = 0.0
    total_revenue = 0.0
    total_units_sold = 0
    for w in withdrawals:
        for item in w.get("items", []):
            qty = item.get("quantity", 0)
            total_cogs += item.get("cost", 0) * qty
            total_revenue += item.get("subtotal", 0)
            total_units_sold += qty

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
    sell_through_pct = (
        total_units_sold / (total_units_sold + total_units_in_catalog) * 100
        if (total_units_sold + total_units_in_catalog) > 0
        else 0
    )

    return {
        "period_days": period_days,
        "total_revenue": round(total_revenue, 2),
        "total_cogs": round(total_cogs, 2),
        "gross_profit": round(total_revenue - total_cogs, 2),
        "gross_margin_pct": round(gross_margin_pct, 1),
        "inventory_cost_value": round(inventory_cost_value, 2),
        "inventory_turnover": round(inventory_turnover, 2),
        "dio": round(dio, 1),
        "sell_through_pct": round(sell_through_pct, 1),
        "total_units_sold": total_units_sold,
    }


@router.get("/product-performance")
async def get_product_performance(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 200,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.get("organization_id") or "default"
    products, withdrawals = await asyncio.gather(
        product_repo.list_products(organization_id=org_id),
        withdrawal_repo.list_withdrawals(
            start_date=start_date, end_date=end_date, limit=10000, organization_id=org_id
        ),
    )

    product_map = {p["id"]: p for p in products}

    perf: dict = {}
    for w in withdrawals:
        for item in w.get("items", []):
            pid = item.get("product_id")
            if not pid:
                continue
            if pid not in perf:
                perf[pid] = {
                    "product_id": pid,
                    "name": item.get("name", "Unknown"),
                    "units_sold": 0,
                    "revenue": 0.0,
                    "cogs": 0.0,
                }
            qty = item.get("quantity", 0)
            perf[pid]["units_sold"] += qty
            perf[pid]["revenue"] += item.get("subtotal", 0)
            perf[pid]["cogs"] += item.get("cost", 0) * qty

    result = []
    for pid, stats in perf.items():
        p = product_map.get(pid, {})
        current_stock = p.get("quantity", 0)
        units_sold = stats["units_sold"]
        revenue = stats["revenue"]
        cogs = stats["cogs"]
        gross_profit = revenue - cogs
        margin_pct = (gross_profit / revenue * 100) if revenue > 0 else 0
        avg_cost_per_unit = (cogs / units_sold) if units_sold > 0 else 0
        sell_through_pct = (
            units_sold / (units_sold + current_stock) * 100
            if (units_sold + current_stock) > 0
            else 0
        )
        result.append({
            "product_id": pid,
            "name": stats["name"],
            "sku": p.get("sku", ""),
            "department": p.get("department_name", ""),
            "current_stock": current_stock,
            "catalog_unit_cost": round(p.get("cost", 0), 2),
            "units_sold": units_sold,
            "avg_cost_per_unit": round(avg_cost_per_unit, 2),
            "revenue": round(revenue, 2),
            "cogs": round(cogs, 2),
            "gross_profit": round(gross_profit, 2),
            "margin_pct": round(margin_pct, 1),
            "sell_through_pct": round(sell_through_pct, 1),
        })

    result.sort(key=lambda x: x["revenue"], reverse=True)
    return {"products": result[:limit], "total": len(result)}
