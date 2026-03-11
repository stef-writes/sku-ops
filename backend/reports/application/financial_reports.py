"""Financial reports: sales, trends, margins, P&L, AR aging.

All read from the financial_ledger via ledger_queries.
"""

from __future__ import annotations

import asyncio

from catalog.application.queries import list_products
from finance.application import ledger_queries as ledger_repo
from kernel.types import round_money


async def sales_report(
    org_id: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
) -> dict:
    dim_kw = {"job_id": job_id, "department": department, "billing_entity": billing_entity}

    accounts, top_products, counts, catalog, payment_status = await asyncio.gather(
        ledger_repo.summary_by_account(org_id, start_date=start_date, end_date=end_date, **dim_kw),
        ledger_repo.product_margins(
            org_id, start_date=start_date, end_date=end_date, limit=10, **dim_kw
        ),
        ledger_repo.reference_counts(org_id, start_date=start_date, end_date=end_date),
        list_products(organization_id=org_id),
        ledger_repo.payment_status_breakdown(org_id, start_date=start_date, end_date=end_date),
    )
    product_map = {p.id: p for p in catalog}
    for m in top_products:
        p = product_map.get(m["product_id"])
        m["name"] = p.name if p else "Unknown"
        m["sku"] = p.sku if p else ""

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


async def trends_report(
    org_id: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    group_by: str = "day",
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
) -> dict:
    series = await ledger_repo.trend_series(
        org_id=org_id,
        start_date=start_date,
        end_date=end_date,
        group_by=group_by,
        job_id=job_id,
        department=department,
        billing_entity=billing_entity,
    )
    totals = {
        "revenue": round_money(sum(r["revenue"] for r in series)),
        "cost": round_money(sum(r["cost"] for r in series)),
        "profit": round_money(sum(r["profit"] for r in series)),
    }
    return {"series": series, "totals": totals}


async def product_margins_report(
    org_id: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
) -> dict:
    margin_data, catalog = await asyncio.gather(
        ledger_repo.product_margins(
            org_id=org_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            job_id=job_id,
            department=department,
            billing_entity=billing_entity,
        ),
        list_products(organization_id=org_id),
    )
    product_map = {p.id: p for p in catalog}
    for m in margin_data:
        p = product_map.get(m["product_id"])
        m["name"] = p.name if p else "Unknown"
        m["sku"] = p.sku if p else ""
    return {"products": margin_data}


async def job_pl_report(
    org_id: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
    search: str | None = None,
) -> dict:
    result = await ledger_repo.summary_by_job(
        org_id=org_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
        search=search,
    )
    jobs = result["rows"]
    total_revenue = sum(j["revenue"] for j in jobs)
    total_cost = sum(j["cost"] for j in jobs)
    total_profit = total_revenue - total_cost

    return {
        "jobs": jobs,
        "total": result["total"],
        "total_revenue": round_money(total_revenue),
        "total_cost": round_money(total_cost),
        "total_profit": round_money(total_profit),
        "total_margin_pct": round(
            (total_profit / total_revenue * 100) if total_revenue > 0 else 0, 1
        ),
    }


async def pl_report(
    org_id: str,
    *,
    group_by: str = "overall",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
    search: str | None = None,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
) -> dict:
    date_kw = {"start_date": start_date, "end_date": end_date}
    dim_kw = {"job_id": job_id, "department": department, "billing_entity": billing_entity}
    total_rows = None

    if group_by == "overall":
        accounts = await ledger_repo.summary_by_account(org_id, **date_kw, **dim_kw)
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

    all_revenue_override = None
    all_cost_override = None

    if group_by == "job":
        result = await ledger_repo.summary_by_job(
            org_id,
            **date_kw,
            limit=limit,
            offset=offset,
            search=search,
        )
        rows = result["rows"]
        total_rows = result["total"]
        all_revenue_override = result["all_revenue"]
        all_cost_override = result["all_cost"]
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
        pmap = {p.id: p for p in catalog}
        for m in rows:
            p = pmap.get(m["product_id"])
            m["name"] = p.name if p else "Unknown"
        label_key = "name"
    else:
        rows = []
        label_key = "name"

    total_revenue = (
        all_revenue_override
        if all_revenue_override is not None
        else sum(r.get("revenue", 0) for r in rows)
    )
    total_cost = (
        all_cost_override if all_cost_override is not None else sum(r.get("cost", 0) for r in rows)
    )
    total_profit = round_money(total_revenue - total_cost)

    resp = {
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
    if total_rows is not None:
        resp["total_rows"] = total_rows
    return resp


async def ar_aging_report(
    org_id: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list:
    return await ledger_repo.ar_aging(org_id, start_date=start_date, end_date=end_date)
