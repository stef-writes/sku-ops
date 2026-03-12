"""Ops agent helper functions — facade-backed queries for operations data."""

import json
import logging
from datetime import UTC, datetime, timedelta

from assistant.agents.tools.registry import register as _reg
from operations.application.queries import list_pending_material_requests, list_withdrawals
from shared.infrastructure.db import get_org_id

logger = logging.getLogger(__name__)


async def _get_contractor_history(args: dict) -> str:
    name = (args.get("name") or "").strip()
    limit = min(int(args.get("limit") or 20), 100)
    all_withdrawals = await list_withdrawals(limit=500, organization_id=get_org_id())
    name_lower = name.lower()
    matched = [
        w
        for w in all_withdrawals
        if name_lower in (w.contractor_name or "").lower()
        or name_lower in (w.contractor_company or "").lower()
    ]
    out = [
        {
            "date": (w.created_at or "")[:10],
            "job_id": w.job_id,
            "service_address": w.service_address,
            "contractor": w.contractor_name,
            "company": w.contractor_company,
            "total": round(w.total, 2),
            "cost_total": round(w.cost_total, 2),
            "payment_status": w.payment_status,
            "item_count": len(w.items),
        }
        for w in matched[:limit]
    ]
    total_spent = sum(w.total for w in matched)
    unpaid = sum(w.total for w in matched if w.payment_status == "unpaid")
    return json.dumps(
        {
            "contractor_search": name,
            "count": len(out),
            "total_spent": round(total_spent, 2),
            "unpaid_balance": round(unpaid, 2),
            "withdrawals": out,
        }
    )


async def _get_job_materials(args: dict) -> str:
    job_id = (args.get("job_id") or "").strip()
    all_withdrawals = await list_withdrawals(limit=1000, organization_id=get_org_id())
    job_withdrawals = [w for w in all_withdrawals if (w.job_id or "").lower() == job_id.lower()]
    if not job_withdrawals:
        job_withdrawals = [w for w in all_withdrawals if job_id.lower() in (w.job_id or "").lower()]
    if not job_withdrawals:
        return json.dumps({"error": f"No withdrawals found for job '{job_id}'"})
    item_map: dict = {}
    for w in job_withdrawals:
        for item in w.items:
            sku = item.sku
            if sku in item_map:
                item_map[sku]["quantity"] += item.quantity
                item_map[sku]["subtotal"] += item.subtotal
            else:
                item_map[sku] = {
                    "sku": sku,
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "price": item.unit_price,
                    "subtotal": round(item.subtotal, 2),
                }
    items_out = [{**v, "subtotal": round(v["subtotal"], 2)} for v in item_map.values()]
    total = sum(w.total for w in job_withdrawals)
    return json.dumps(
        {
            "job_id": job_id,
            "service_address": job_withdrawals[0].service_address,
            "contractor": job_withdrawals[0].contractor_name,
            "withdrawal_count": len(job_withdrawals),
            "total": round(total, 2),
            "items": items_out,
        }
    )


async def _list_recent_withdrawals(args: dict) -> str:
    days = min(int(args.get("days") or 7), 365)
    limit = min(int(args.get("limit") or 20), 100)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    withdrawals = await list_withdrawals(
        start_date=since, limit=limit, organization_id=get_org_id()
    )
    out = [
        {
            "date": (w.created_at or "")[:10],
            "job_id": w.job_id,
            "contractor": w.contractor_name,
            "service_address": w.service_address,
            "total": round(w.total, 2),
            "payment_status": w.payment_status,
            "item_count": len(w.items),
        }
        for w in withdrawals
    ]
    total_value = sum(w.total for w in withdrawals)
    return json.dumps(
        {
            "period_days": days,
            "count": len(out),
            "total_value": round(total_value, 2),
            "withdrawals": out,
        }
    )


async def _list_pending_material_requests(args: dict) -> str:
    limit = min(int(args.get("limit") or 20), 100)
    rows = await list_pending_material_requests(organization_id=get_org_id(), limit=limit)
    out = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "contractor": r.contractor_name,
                "job_id": r.job_id,
                "service_address": r.service_address,
                "notes": r.notes,
                "item_count": len(r.items),
                "requested_at": (r.created_at or "")[:16],
            }
        )
    return json.dumps({"count": len(out), "pending_requests": out})


# ── Registry ──────────────────────────────────────────────────────────────────

_reg("get_contractor_history", "ops", _get_contractor_history, lookup_key="contractor_history")
_reg("get_job_materials", "ops", _get_job_materials, lookup_key="job_materials")
_reg("list_recent_withdrawals", "ops", _list_recent_withdrawals)
_reg(
    "list_pending_material_requests",
    "ops",
    _list_pending_material_requests,
    lookup_key="pending_requests",
)
