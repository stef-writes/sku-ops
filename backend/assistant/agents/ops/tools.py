"""Ops agent helper functions — DB query implementations for operations data."""
import json
import logging
from datetime import UTC, datetime, timedelta, timezone

from assistant.agents.tools.registry import register as _reg
from operations.application.queries import list_withdrawals
from shared.infrastructure.database import get_connection

logger = logging.getLogger(__name__)


async def _get_contractor_history(args: dict, org_id: str) -> str:
    name = (args.get("name") or "").strip()
    limit = min(int(args.get("limit") or 20), 100)
    all_withdrawals = await list_withdrawals(limit=500, organization_id=org_id)
    name_lower = name.lower()
    matched = [
        w for w in all_withdrawals
        if name_lower in (w.get("contractor_name") or "").lower()
        or name_lower in (w.get("contractor_company") or "").lower()
    ]
    out = [
        {
            "date": w.get("created_at", "")[:10],
            "job_id": w.get("job_id"),
            "service_address": w.get("service_address"),
            "contractor": w.get("contractor_name"),
            "company": w.get("contractor_company"),
            "total": round(w.get("total", 0), 2),
            "cost_total": round(w.get("cost_total", 0), 2),
            "payment_status": w.get("payment_status"),
            "item_count": len(w.get("items") or []),
        }
        for w in matched[:limit]
    ]
    total_spent = sum(w.get("total", 0) for w in matched)
    unpaid = sum(w.get("total", 0) for w in matched if w.get("payment_status") == "unpaid")
    return json.dumps({
        "contractor_search": name,
        "count": len(out),
        "total_spent": round(total_spent, 2),
        "unpaid_balance": round(unpaid, 2),
        "withdrawals": out,
    })


async def _get_job_materials(args: dict, org_id: str) -> str:
    job_id = (args.get("job_id") or "").strip()
    all_withdrawals = await list_withdrawals(limit=1000, organization_id=org_id)
    job_withdrawals = [w for w in all_withdrawals if (w.get("job_id") or "").lower() == job_id.lower()]
    if not job_withdrawals:
        job_withdrawals = [w for w in all_withdrawals if job_id.lower() in (w.get("job_id") or "").lower()]
    if not job_withdrawals:
        return json.dumps({"error": f"No withdrawals found for job '{job_id}'"})
    item_map: dict = {}
    for w in job_withdrawals:
        for item in (w.get("items") or []):
            sku = item.get("sku", "")
            if sku in item_map:
                item_map[sku]["quantity"] += item.get("quantity", 0)
                item_map[sku]["subtotal"] += item.get("subtotal", 0)
            else:
                item_map[sku] = {
                    "sku": sku,
                    "name": item.get("name"),
                    "quantity": item.get("quantity", 0),
                    "unit": item.get("unit"),
                    "price": item.get("price"),
                    "subtotal": round(item.get("subtotal", 0), 2),
                }
    items_out = [{**v, "subtotal": round(v["subtotal"], 2)} for v in item_map.values()]
    total = sum(w.get("total", 0) for w in job_withdrawals)
    return json.dumps({
        "job_id": job_id,
        "service_address": job_withdrawals[0].get("service_address"),
        "contractor": job_withdrawals[0].get("contractor_name"),
        "withdrawal_count": len(job_withdrawals),
        "total": round(total, 2),
        "items": items_out,
    })


async def _list_recent_withdrawals(args: dict, org_id: str) -> str:
    days = min(int(args.get("days") or 7), 365)
    limit = min(int(args.get("limit") or 20), 100)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    withdrawals = await list_withdrawals(start_date=since, limit=limit, organization_id=org_id)
    out = [
        {
            "date": w.get("created_at", "")[:10],
            "job_id": w.get("job_id"),
            "contractor": w.get("contractor_name"),
            "service_address": w.get("service_address"),
            "total": round(w.get("total", 0), 2),
            "payment_status": w.get("payment_status"),
            "item_count": len(w.get("items") or []),
        }
        for w in withdrawals
    ]
    total_value = sum(w.get("total", 0) for w in withdrawals)
    return json.dumps({"period_days": days, "count": len(out), "total_value": round(total_value, 2), "withdrawals": out})


async def _list_pending_material_requests(args: dict, org_id: str) -> str:
    limit = min(int(args.get("limit") or 20), 100)
    conn = get_connection()
    cur = await conn.execute(
        """SELECT id, contractor_id, contractor_name, items, job_id,
                  service_address, notes, created_at
           FROM material_requests
           WHERE status = 'pending'
             AND (organization_id = ? OR organization_id IS NULL)
           ORDER BY created_at DESC
           LIMIT ?""",
        (org_id, limit),
    )
    rows = await cur.fetchall()
    out = []
    for r in rows:
        items = json.loads(r["items"]) if r["items"] else []
        out.append({
            "id": r["id"],
            "contractor": r["contractor_name"],
            "job_id": r["job_id"],
            "service_address": r["service_address"],
            "notes": r["notes"],
            "item_count": len(items),
            "requested_at": (r["created_at"] or "")[:16],
        })
    return json.dumps({"count": len(out), "pending_requests": out})


# ── Registry ──────────────────────────────────────────────────────────────────

_reg("get_contractor_history",        "ops", _get_contractor_history,        lookup_key="contractor_history")
_reg("get_job_materials",             "ops", _get_job_materials,             lookup_key="job_materials")
_reg("list_recent_withdrawals",       "ops", _list_recent_withdrawals)
_reg("list_pending_material_requests","ops", _list_pending_material_requests,lookup_key="pending_requests")
