"""
OpsAgent: contractors, withdrawals, jobs, material requests.
Tools: get_contractor_history, get_job_materials, list_recent_withdrawals,
       list_pending_material_requests.
"""
import json
import logging
from datetime import datetime, timezone, timedelta

from config import ANTHROPIC_MODEL, ANTHROPIC_FAST_MODEL, AGENT_THINKING_BUDGET
from db import get_connection
from services.agents.base import run_agent, _build_conversation

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an operations specialist for SKU-Ops, a hardware store management system.

TOOLS — use them when the user asks about field operations, contractors, or jobs:
- get_contractor_history(name, limit): withdrawal history for a specific contractor
- get_job_materials(job_id): all materials pulled for a specific job
- list_recent_withdrawals(days, limit): recent material withdrawals across all jobs
- list_pending_material_requests(limit): material requests awaiting approval

WHEN TO USE EACH TOOL:
- "what has [contractor] taken / history for [name]" → get_contractor_history
- "what was pulled for job [ID] / job materials" → get_job_materials
- "recent withdrawals / last week's activity / what's been pulled lately" → list_recent_withdrawals
- "pending requests / awaiting approval / material requests" → list_pending_material_requests

FORMAT — respond in GitHub-flavored markdown:
- For withdrawal lists, use a markdown table with a separator row:

| Date | Contractor | Job | Total | Status |
|------|-----------|-----|-------|--------|
| 2026-03-01 | John Smith | JOB-123 | $150.00 | unpaid |

- Use **bold** for key names, unpaid totals, and anything needing attention
- Use bullet lists for summaries; save tables for 3+ row datasets
- Lead with the pattern ("**3 of 5 jobs unpaid, $420 outstanding**") before listing rows

Never make up operational data — always use a tool.
Amounts in dollars rounded to 2 decimal places.

REASONING — think before acting:
1. Identify what the question is really asking — contractor profile? single job? recent trends?
2. If a question has multiple parts, call independent tools together in the same turn
3. After results, assess completeness — if a contractor has many jobs, note the pattern, not just raw rows
4. For vague names (e.g. "John"), use partial matching and clarify if multiple contractors match
5. Summarise patterns in results (total spend, most active job, payment status spread) rather than
   dumping raw rows — give the user insight, not just data"""

TOOL_SCHEMAS = [
    {
        "name": "get_contractor_history",
        "description": "Withdrawal history for a contractor (by name). Shows jobs, materials pulled, amounts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Contractor name (partial match supported)"},
                "limit": {"type": "integer", "description": "Max results", "default": 20},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_job_materials",
        "description": "All materials pulled for a specific job ID. Shows each item, quantity, cost.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID or job reference"},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "list_recent_withdrawals",
        "description": "Recent material withdrawals across all jobs. Filter by last N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Lookback window in days", "default": 7},
                "limit": {"type": "integer", "description": "Max results", "default": 20},
            },
        },
    },
    {
        "name": "list_pending_material_requests",
        "description": "Material requests from contractors that are awaiting approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results", "default": 20},
            },
        },
    },
]


async def execute_tool(name: str, args: dict, ctx: dict) -> str:
    org_id = ctx.get("org_id", "default")
    try:
        if name == "get_contractor_history":
            return await _get_contractor_history(args, org_id)
        if name == "get_job_materials":
            return await _get_job_materials(args, org_id)
        if name == "list_recent_withdrawals":
            return await _list_recent_withdrawals(args, org_id)
        if name == "list_pending_material_requests":
            return await _list_pending_material_requests(args, org_id)
        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        logger.warning(f"OpsAgent tool {name} error: {e}")
        return json.dumps({"error": str(e)})


async def _get_contractor_history(args: dict, org_id: str) -> str:
    from repositories import withdrawal_repo
    name = (args.get("name") or "").strip()
    limit = min(int(args.get("limit") or 20), 100)
    all_withdrawals = await withdrawal_repo.list_withdrawals(
        limit=500,
        organization_id=org_id,
    )
    # Filter by contractor name (case-insensitive partial match)
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
    from repositories import withdrawal_repo
    job_id = (args.get("job_id") or "").strip()
    all_withdrawals = await withdrawal_repo.list_withdrawals(limit=1000, organization_id=org_id)
    job_withdrawals = [w for w in all_withdrawals if (w.get("job_id") or "").lower() == job_id.lower()]
    if not job_withdrawals:
        # Partial match fallback
        job_withdrawals = [w for w in all_withdrawals if job_id.lower() in (w.get("job_id") or "").lower()]
    if not job_withdrawals:
        return json.dumps({"error": f"No withdrawals found for job '{job_id}'"})
    # Aggregate items across all withdrawals for this job
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
    items_out = [
        {**v, "subtotal": round(v["subtotal"], 2)}
        for v in item_map.values()
    ]
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
    from repositories import withdrawal_repo
    days = min(int(args.get("days") or 7), 365)
    limit = min(int(args.get("limit") or 20), 100)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=since,
        limit=limit,
        organization_id=org_id,
    )
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
    return json.dumps({
        "period_days": days,
        "count": len(out),
        "total_value": round(total_value, 2),
        "withdrawals": out,
    })


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


async def chat(
    messages: list[dict],
    user_message: str,
    history: list[dict] | None,
    ctx: dict,
) -> dict:
    from config import ANTHROPIC_AVAILABLE, ANTHROPIC_API_KEY
    if not ANTHROPIC_AVAILABLE:
        return {"response": "Ops agent requires ANTHROPIC_API_KEY.", "tool_calls": [], "history": [], "thinking": []}
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    thinking_budget = AGENT_THINKING_BUDGET
    model = ANTHROPIC_MODEL if thinking_budget > 0 else ANTHROPIC_FAST_MODEL
    conversation = _build_conversation(messages, history, user_message)
    result = await run_agent(
        client, model, SYSTEM_PROMPT, TOOL_SCHEMAS, execute_tool, conversation, ctx,
        thinking_budget=thinking_budget,
    )
    return {
        "response": result["response"],
        "tool_calls": result["tool_calls"],
        "thinking": result.get("thinking", []),
        "history": result["conversation"],
        "agent": "ops",
    }
