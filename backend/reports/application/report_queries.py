"""Report queries — re-export hub + KPI report.

Financial reports live in financial_reports.py.
Inventory/product reports live in inventory_reports.py.
All are re-exported here so existing imports continue to work.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from catalog.application.queries import list_products
from finance.application import ledger_queries as ledger_repo
from reports.application.financial_reports import (  # noqa: F401
    ar_aging_report,
    job_pl_report,
    pl_report,
    product_margins_report,
    sales_report,
    trends_report,
)
from reports.application.inventory_reports import (  # noqa: F401
    inventory_report,
    product_activity_report,
    product_performance_report,
    reorder_urgency_report,
)
from shared.kernel.types import round_money


async def kpi_report(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
) -> dict:
    accounts, products_data, units_sold_map = await asyncio.gather(
        ledger_repo.summary_by_account(
            start_date=start_date,
            end_date=end_date,
            job_id=job_id,
            department=department,
            billing_entity=billing_entity,
        ),
        list_products(),
        ledger_repo.units_sold_by_product(start_date=start_date, end_date=end_date),
    )

    total_revenue = accounts.get("revenue", 0)
    total_cogs = accounts.get("cogs", 0)
    inventory_cost_value = sum(p.cost * p.quantity for p in products_data)

    if start_date and end_date:
        try:
            d_start = datetime.fromisoformat(start_date)
            d_end = datetime.fromisoformat(end_date)
            period_days = max((d_end - d_start).days, 1)
        except ValueError:
            period_days = 365
    else:
        period_days = 365

    inventory_turnover = total_cogs / inventory_cost_value if inventory_cost_value > 0 else 0
    dio = (inventory_cost_value / total_cogs * period_days) if total_cogs > 0 else 0
    gross_margin_pct = (
        ((total_revenue - total_cogs) / total_revenue * 100) if total_revenue > 0 else 0
    )

    total_units_sold = sum(units_sold_map.values())
    total_stock = sum(p.quantity for p in products_data)
    sell_through_pct = (
        (total_units_sold / (total_units_sold + total_stock) * 100)
        if (total_units_sold + total_stock) > 0
        else 0
    )

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
