"""Sales, inventory, and financial report routes.

All monetary reports read from the financial_ledger table via ledger_repo.
Inventory report remains current-state (product quantities).
"""
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends

from identity.application.auth_service import require_role
from kernel.types import CurrentUser
from catalog.application.queries import list_products
from finance.application import ledger_queries as ledger_repo

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/sales")
async def get_sales_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id

    accounts, top_products, counts = await asyncio.gather(
        ledger_repo.summary_by_account(org_id, start_date=start_date, end_date=end_date),
        ledger_repo.product_margins(org_id, start_date=start_date, end_date=end_date, limit=10),
        ledger_repo.reference_counts(org_id, start_date=start_date, end_date=end_date),
    )

    revenue = accounts.get("revenue", 0)
    cogs = accounts.get("cogs", 0)
    tax = accounts.get("tax_collected", 0)
    gross_profit = round(revenue - cogs, 2)
    tx_count = counts.get("withdrawal", 0)
    return_count = counts.get("return", 0)

    return {
        "gross_revenue": round(revenue, 2),
        "returns_total": 0,
        "net_revenue": round(revenue, 2),
        "total_cogs": round(cogs, 2),
        "gross_profit": gross_profit,
        "gross_margin_pct": round(gross_profit / revenue * 100, 1) if revenue > 0 else 0,
        "total_tax": round(tax, 2),
        "total_transactions": tx_count,
        "return_count": return_count,
        "average_transaction": round(revenue / tx_count, 2) if tx_count > 0 else 0,
        "by_payment_status": {},
        "top_products": top_products,
        "total_revenue": round(revenue, 2),
    }


@router.get("/inventory")
async def get_inventory_report(current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.organization_id
    products = await list_products(organization_id=org_id)

    total_products = len(products)
    total_value = sum(p.get("price", 0) * p.get("quantity", 0) for p in products)
    total_cost = sum(p.get("cost", 0) * p.get("quantity", 0) for p in products)
    low_stock = [p for p in products if p.get("quantity", 0) <= p.get("min_stock", 5)]
    out_of_stock = [p for p in products if p.get("quantity", 0) == 0]

    by_department: dict = {}
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
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    """Revenue/cost/profit trends from the ledger."""
    org_id = current_user.organization_id
    series = await ledger_repo.trend_series(
        org_id=org_id, start_date=start_date, end_date=end_date, group_by=group_by,
    )

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
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id
    products = await ledger_repo.product_margins(
        org_id=org_id, start_date=start_date, end_date=end_date, limit=limit,
    )
    return {"products": products}


@router.get("/job-pl")
async def get_job_pl(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
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
        "total_revenue": round(total_revenue, 2),
        "total_cost": round(total_cost, 2),
        "total_profit": round(total_profit, 2),
        "total_margin_pct": round((total_profit / total_revenue * 100) if total_revenue > 0 else 0, 1),
    }


@router.get("/pl")
async def get_pl(
    group_by: str = "overall",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
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
        profit = round(revenue - cogs - shrinkage, 2)
        return {
            "group_by": "overall",
            "summary": {
                "revenue": round(revenue, 2),
                "cogs": round(cogs, 2),
                "tax_collected": round(tax, 2),
                "shrinkage": round(shrinkage, 2),
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
        rows = await ledger_repo.product_margins(org_id, **date_kw, limit=limit)
        label_key = "product_id"
    else:
        rows = []
        label_key = "name"

    total_revenue = sum(r.get("revenue", 0) for r in rows)
    total_cost = sum(r.get("cost", 0) for r in rows)
    total_profit = round(total_revenue - total_cost, 2)

    return {
        "group_by": group_by,
        "summary": {
            "revenue": round(total_revenue, 2),
            "cogs": round(total_cost, 2),
            "gross_profit": total_profit,
            "margin_pct": round(total_profit / total_revenue * 100, 1) if total_revenue > 0 else 0,
        },
        "rows": rows,
        "label_key": label_key,
    }


@router.get("/ar-aging")
async def get_ar_aging(
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    """Accounts receivable aging buckets by billing entity."""
    return await ledger_repo.ar_aging(current_user.organization_id)


@router.get("/kpis")
async def get_kpis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id

    accounts, products_data = await asyncio.gather(
        ledger_repo.summary_by_account(org_id=org_id, start_date=start_date, end_date=end_date),
        list_products(organization_id=org_id),
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

    # Estimate units sold from ledger: count distinct product references
    # For sell-through we need actual unit counts which the ledger doesn't store,
    # so fall back to 0 (this KPI requires operational data or a units_sold ledger column)
    total_units_sold = 0
    sell_through_pct = 0

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
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id

    margin_data, products_data = await asyncio.gather(
        ledger_repo.product_margins(
            org_id=org_id, start_date=start_date, end_date=end_date, limit=limit,
        ),
        list_products(organization_id=org_id),
    )

    product_map = {p["id"]: p for p in products_data}

    result = []
    for m in margin_data:
        pid = m["product_id"]
        p = product_map.get(pid, {})
        current_stock = p.get("quantity", 0)
        result.append({
            "product_id": pid,
            "name": p.get("name", "Unknown"),
            "sku": p.get("sku", ""),
            "department": p.get("department_name", ""),
            "current_stock": current_stock,
            "catalog_unit_cost": round(p.get("cost", 0), 2),
            "units_sold": 0,
            "avg_cost_per_unit": 0,
            "revenue": m["revenue"],
            "cogs": m["cost"],
            "gross_profit": m["profit"],
            "margin_pct": m["margin_pct"],
            "sell_through_pct": 0,
        })

    return {"products": result, "total": len(result)}
