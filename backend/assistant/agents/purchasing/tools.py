"""Purchasing agent tool implementations — vendor analytics and procurement planning."""

import json
import logging

from assistant.agents.tools.registry import register as _reg
from catalog.application.queries import (
    find_vendor_by_name,
    get_vendor_by_id,
    list_vendors,
    sku_vendor_options,
)
from purchasing.application.queries import (
    po_summary_by_status,
    purchase_history,
    reorder_with_vendor_context,
    vendor_catalog,
    vendor_performance,
)

logger = logging.getLogger(__name__)


async def _get_vendor_catalog(args: dict) -> str:
    vendor_id = (args.get("vendor_id") or "").strip()
    if not vendor_id:
        name = (args.get("name") or "").strip()
        if name:
            vendor = await find_vendor_by_name(name)
            if vendor:
                vendor_id = vendor.id
            else:
                return json.dumps({"error": f"Vendor '{name}' not found"})
        else:
            return json.dumps({"error": "vendor_id or name required"})

    vendor = await get_vendor_by_id(vendor_id)
    items = await vendor_catalog(vendor_id)
    return json.dumps(
        {
            "vendor_id": vendor_id,
            "vendor_name": vendor.name if vendor else "",
            "sku_count": len(items),
            "items": items,
        }
    )


async def _get_vendor_performance(args: dict) -> str:
    vendor_id = (args.get("vendor_id") or "").strip()
    days = min(int(args.get("days") or 90), 365)
    if not vendor_id:
        name = (args.get("name") or "").strip()
        if name:
            vendor = await find_vendor_by_name(name)
            if vendor:
                vendor_id = vendor.id
            else:
                return json.dumps({"error": f"Vendor '{name}' not found"})
        else:
            return json.dumps({"error": "vendor_id or name required"})

    vendor = await get_vendor_by_id(vendor_id)
    perf = await vendor_performance(vendor_id, days, vendor_name=vendor.name if vendor else "")
    return json.dumps(
        {
            "vendor_id": perf.vendor_id,
            "vendor_name": perf.vendor_name,
            "days": perf.days,
            "po_count": perf.po_count,
            "total_spend": perf.total_spend,
            "received_count": perf.received_count,
            "avg_lead_time_days": perf.avg_lead_time_days,
            "fill_rate": perf.fill_rate,
        }
    )


async def _get_sku_vendor_options(args: dict) -> str:
    sku_id = (args.get("sku_id") or "").strip()
    if not sku_id:
        return json.dumps({"error": "sku_id required"})
    options = await sku_vendor_options(sku_id)
    return json.dumps(
        {
            "sku_id": sku_id,
            "vendor_count": len(options),
            "vendors": options,
        }
    )


async def _get_purchase_history(args: dict) -> str:
    vendor_id = (args.get("vendor_id") or "").strip()
    days = min(int(args.get("days") or 90), 365)
    limit = min(int(args.get("limit") or 20), 50)
    if not vendor_id:
        name = (args.get("name") or "").strip()
        if name:
            vendor = await find_vendor_by_name(name)
            if vendor:
                vendor_id = vendor.id
            else:
                return json.dumps({"error": f"Vendor '{name}' not found"})
        else:
            return json.dumps({"error": "vendor_id or name required"})

    vendor = await get_vendor_by_id(vendor_id)
    history = await purchase_history(vendor_id, days, limit)
    return json.dumps(
        {
            "vendor_id": vendor_id,
            "vendor_name": vendor.name if vendor else "",
            "period_days": days,
            "po_count": len(history),
            "purchase_orders": history,
        }
    )


async def _get_po_summary() -> str:
    summary = await po_summary_by_status()
    total_count = sum(v["count"] for v in summary.values())
    total_value = round(sum(v["total"] for v in summary.values()), 2)
    return json.dumps(
        {
            "total_pos": total_count,
            "total_value": total_value,
            "by_status": summary,
        }
    )


async def _get_reorder_with_vendor_context(args: dict) -> str:
    limit = min(int(args.get("limit") or 30), 50)
    items = await reorder_with_vendor_context(limit)
    return json.dumps(
        {
            "count": len(items),
            "items": items,
        }
    )


async def _list_all_vendors() -> str:
    vendors = await list_vendors()
    out = [
        {
            "id": v.id,
            "name": v.name,
            "contact_name": v.contact_name,
            "email": v.email,
            "phone": v.phone,
        }
        for v in vendors
    ]
    return json.dumps({"count": len(out), "vendors": out})


# ── Registry ──────────────────────────────────────────────────────────────────

_reg("get_vendor_catalog", "purchasing", _get_vendor_catalog)
_reg("get_vendor_performance", "purchasing", _get_vendor_performance)
_reg("get_sku_vendor_options", "purchasing", _get_sku_vendor_options)
_reg("get_purchase_history", "purchasing", _get_purchase_history)
_reg("get_po_summary", "purchasing", _get_po_summary, takes_args=False)
_reg("get_reorder_with_vendor_context", "purchasing", _get_reorder_with_vendor_context)
_reg("list_all_vendors", "purchasing", _list_all_vendors, takes_args=False)
