"""Finance helper functions — DB query implementations for the finance agent."""

import json
import logging
from datetime import UTC, datetime, timedelta

from assistant.agents.tools.registry import register as _reg
from finance.application.invoice_service import list_invoices
from operations.application.queries import list_withdrawals
from shared.infrastructure.db import get_org_id

logger = logging.getLogger(__name__)


async def _get_invoice_summary() -> str:
    invoices = await list_invoices(limit=10000, organization_id=get_org_id())
    summary: dict[str, dict] = {}
    for inv in invoices:
        status = inv.status or "unknown"
        if status not in summary:
            summary[status] = {"count": 0, "total": 0.0}
        summary[status]["count"] += 1
        summary[status]["total"] += inv.total
    for s in summary.values():
        s["total"] = round(s["total"], 2)
    grand_total = round(sum(inv.total for inv in invoices), 2)
    return json.dumps(
        {"total_invoices": len(invoices), "grand_total": grand_total, "by_status": summary}
    )


async def _get_outstanding_balances(args: dict) -> str:
    limit = min(int(args.get("limit") or 20), 100)
    withdrawals = await list_withdrawals(
        payment_status="unpaid", limit=10000, organization_id=get_org_id()
    )
    entity_map: dict[str, dict] = {}
    for w in withdrawals:
        entity = w.billing_entity or w.contractor_name or "Unknown"
        if entity not in entity_map:
            entity_map[entity] = {
                "balance": 0.0,
                "withdrawal_count": 0,
                "oldest": w.created_at or "",
            }
        entity_map[entity]["balance"] += w.total
        entity_map[entity]["withdrawal_count"] += 1
    sorted_entities = sorted(entity_map.items(), key=lambda x: x[1]["balance"], reverse=True)
    out = [
        {
            "entity": entity,
            "balance": round(data["balance"], 2),
            "withdrawal_count": data["withdrawal_count"],
            "oldest_unpaid": data["oldest"][:10],
        }
        for entity, data in sorted_entities[:limit]
    ]
    total_outstanding = sum(w.total for w in withdrawals)
    return json.dumps(
        {
            "total_outstanding": round(total_outstanding, 2),
            "entity_count": len(entity_map),
            "balances": out,
        }
    )


async def _get_revenue_summary(args: dict) -> str:
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    withdrawals = await list_withdrawals(start_date=since, limit=10000, organization_id=get_org_id())
    total_revenue = sum(w.total for w in withdrawals)
    total_tax = sum(w.tax for w in withdrawals)
    paid = sum(w.total for w in withdrawals if w.payment_status == "paid")
    unpaid = sum(w.total for w in withdrawals if w.payment_status == "unpaid")
    invoiced = sum(w.total for w in withdrawals if w.payment_status == "invoiced")
    return json.dumps(
        {
            "period_days": days,
            "transaction_count": len(withdrawals),
            "total_revenue": round(total_revenue, 2),
            "total_tax": round(total_tax, 2),
            "revenue_ex_tax": round(total_revenue - total_tax, 2),
            "paid": round(paid, 2),
            "unpaid": round(unpaid, 2),
            "invoiced": round(invoiced, 2),
        }
    )


async def _get_pl_summary(args: dict) -> str:
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    withdrawals = await list_withdrawals(start_date=since, limit=10000, organization_id=get_org_id())
    total_revenue = sum(w.total for w in withdrawals)
    total_cost = sum(w.cost_total for w in withdrawals)
    gross_profit = total_revenue - total_cost
    margin_pct = round((gross_profit / total_revenue * 100), 1) if total_revenue > 0 else 0
    return json.dumps(
        {
            "period_days": days,
            "transaction_count": len(withdrawals),
            "revenue": round(total_revenue, 2),
            "cost_of_goods": round(total_cost, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_margin_pct": margin_pct,
        }
    )


async def _get_top_products(args: dict) -> str:
    days = min(int(args.get("days") or 7), 365)
    limit = min(int(args.get("limit") or 10), 50)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    withdrawals = await list_withdrawals(start_date=since, limit=10000, organization_id=get_org_id())
    product_map: dict[str, dict] = {}
    for w in withdrawals:
        for item in w.items:
            sku = item.sku or item.name or "unknown"
            name = item.name or sku
            qty = item.quantity
            revenue = item.subtotal
            if sku not in product_map:
                product_map[sku] = {
                    "sku": sku,
                    "name": name,
                    "total_units": 0,
                    "total_revenue": 0.0,
                }
            product_map[sku]["total_units"] += qty
            product_map[sku]["total_revenue"] += revenue
    ranked = sorted(product_map.values(), key=lambda x: x["total_revenue"], reverse=True)[:limit]
    for r in ranked:
        r["total_revenue"] = round(r["total_revenue"], 2)
    return json.dumps({"period_days": days, "count": len(ranked), "products": ranked})


# ── Registry ──────────────────────────────────────────────────────────────────

_reg("get_invoice_summary", "finance", _get_invoice_summary, takes_args=False)
_reg("get_outstanding_balances", "finance", _get_outstanding_balances, lookup_key="outstanding")
_reg("get_revenue_summary", "finance", _get_revenue_summary)
_reg("get_pl_summary", "finance", _get_pl_summary)
_reg("get_top_products_fin", "finance", _get_top_products)
