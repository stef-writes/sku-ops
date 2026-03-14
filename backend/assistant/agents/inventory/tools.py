"""Inventory agent tool implementations — facade-backed queries and search helpers."""

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from assistant.agents.tools.registry import register as _reg
from assistant.agents.tools.search import get_index
from catalog.application.queries import (
    count_all_skus as catalog_count_all,
)
from catalog.application.queries import (
    count_low_stock as catalog_count_low_stock,
)
from catalog.application.queries import (
    find_sku_by_sku_code as catalog_find_by_sku,
)
from catalog.application.queries import (
    get_department_by_code as catalog_get_dept_by_code,
)
from catalog.application.queries import (
    get_sku_counters,
)
from catalog.application.queries import (
    list_departments as catalog_list_departments,
)
from catalog.application.queries import (
    list_low_stock as catalog_list_low_stock,
)
from catalog.application.queries import (
    list_skus as catalog_list_skus,
)
from catalog.application.queries import (
    list_vendors as catalog_list_vendors,
)
from inventory.application.queries import withdrawal_velocity
from operations.application.queries import list_withdrawals
from shared.infrastructure.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)


async def _search_products(args: dict) -> str:
    query = (args.get("query") or "").strip()
    limit = min(int(args.get("limit") or 20), 50)
    items = await catalog_list_skus(search=query, limit=limit)
    out = [
        {
            "sku": p.sku,
            "name": p.name,
            "quantity": p.quantity,
            "sell_uom": p.sell_uom,
            "min_stock": p.min_stock,
            "department": p.category_name,
        }
        for p in items
    ]
    return json.dumps({"count": len(out), "products": out})


async def _search_semantic(args: dict) -> str:
    query = (args.get("query") or "").strip()
    limit = min(int(args.get("limit") or 10), 30)
    index = await get_index()
    if OPENAI_API_KEY and index._embeddings is not None:
        results = await index.search_semantic(query, limit=limit, api_key=OPENAI_API_KEY)
        method = "embedding"
    else:
        results = index.search_bm25(query, limit=limit)
        method = "bm25"
    out = [
        {
            "sku": p.sku,
            "name": p.name,
            "quantity": p.quantity,
            "sell_uom": p.sell_uom or "each",
            "min_stock": p.min_stock,
            "department": p.category_name,
        }
        for p in results
    ]
    return json.dumps({"count": len(out), "products": out, "method": method})


async def _get_product_details(args: dict) -> str:
    sku = (args.get("sku") or "").strip().upper()
    p = await catalog_find_by_sku(sku)
    if not p:
        return json.dumps({"error": f"Product with SKU '{sku}' not found"})
    return json.dumps(
        {
            "sku": p.sku,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "cost": p.cost,
            "quantity": p.quantity,
            "min_stock": p.min_stock,
            "department": p.category_name,
            "barcode": p.barcode,
            "base_unit": p.base_unit,
            "sell_uom": p.sell_uom,
            "pack_qty": p.pack_qty,
            "purchase_uom": p.purchase_uom,
            "purchase_pack_qty": p.purchase_pack_qty,
        }
    )


async def _get_inventory_stats() -> str:
    total_skus = await catalog_count_all()
    low_count = await catalog_count_low_stock()
    products = await catalog_list_skus()
    total_value = round(sum(p.quantity * p.cost for p in products), 2)
    out_of_stock = sum(1 for p in products if p.quantity == 0)
    return json.dumps(
        {
            "total_skus": total_skus,
            "_note": "total_skus is the count of distinct product lines. No meaningful total unit count exists because products are measured in different units (each, gallon, box, etc.).",
            "total_cost_value": total_value,
            "low_stock_count": low_count,
            "out_of_stock_count": out_of_stock,
        }
    )


async def _list_low_stock(args: dict) -> str:
    limit = min(int(args.get("limit") or 20), 50)
    items = await catalog_list_low_stock(limit=limit)
    out = [
        {
            "sku": p.sku,
            "name": p.name,
            "quantity": p.quantity,
            "sell_uom": p.sell_uom,
            "min_stock": p.min_stock,
            "department": p.category_name,
        }
        for p in items
    ]
    return json.dumps({"count": len(out), "products": out})


async def _list_departments() -> str:
    depts = await catalog_list_departments()
    counters = await get_sku_counters()
    out = []
    for d in depts:
        code = d.code
        next_num = counters.get(code, 0) + 1
        next_sku = f"{code}-ITM-{str(next_num).zfill(6)}"
        out.append(
            {
                "name": d.name,
                "code": code,
                "sku_count": d.sku_count,
                "next_sku": next_sku,
            }
        )
    return json.dumps({"departments": out})


async def _list_vendors() -> str:
    vendors = await catalog_list_vendors()
    out = [{"name": v.name} for v in vendors]
    return json.dumps({"vendors": out})


async def _get_usage_velocity(args: dict) -> str:
    sku = (args.get("sku") or "").strip().upper()
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    p = await catalog_find_by_sku(sku)
    if not p:
        return json.dumps({"error": f"Product '{sku}' not found"})
    vel = await withdrawal_velocity([p.id], since)
    total_used = float(vel.get(p.id, 0))
    avg_daily = round(total_used / days, 2)
    days_until_zero = round(p.quantity / avg_daily, 1) if avg_daily > 0 else None
    return json.dumps(
        {
            "sku": sku,
            "name": p.name,
            "sell_uom": p.sell_uom or "each",
            "current_quantity": p.quantity,
            "period_days": days,
            "total_withdrawn": total_used,
            "avg_daily_use": avg_daily,
            "days_until_stockout": days_until_zero,
            "_note": None
            if days_until_zero is not None
            else "days_until_stockout is null because avg_daily_use=0 — no withdrawals recorded in this period, not a data error.",
        }
    )


async def _get_reorder_suggestions(args: dict) -> str:
    limit = min(int(args.get("limit") or 20), 50)
    since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    low_stock = await catalog_list_low_stock(limit=100)
    if not low_stock:
        return json.dumps({"count": 0, "suggestions": []})
    product_ids = [p.id for p in low_stock]
    velocity_map = await withdrawal_velocity(product_ids, since)
    suggestions = []
    for p in low_stock:
        total_used = float(velocity_map.get(p.id, 0))
        avg_daily = total_used / 30
        qty = p.quantity
        days_until_zero = round(qty / avg_daily, 1) if avg_daily > 0 else None
        urgency = (
            "critical"
            if days_until_zero is not None and days_until_zero <= 3
            else "high"
            if days_until_zero is not None and days_until_zero <= 7
            else "medium"
            if days_until_zero is not None
            else "no_velocity_data"
        )
        suggestions.append(
            {
                "sku": p.sku,
                "name": p.name,
                "quantity": qty,
                "sell_uom": p.sell_uom,
                "min_stock": p.min_stock,
                "avg_daily_use": round(avg_daily, 2),
                "days_until_stockout": days_until_zero,
                "urgency": urgency,
            }
        )
    suggestions.sort(
        key=lambda x: (
            x["days_until_stockout"] is None,
            x["days_until_stockout"] if x["days_until_stockout"] is not None else 9999,
        )
    )
    return json.dumps(
        {
            "count": len(suggestions),
            "suggestions": suggestions[:limit],
            "_note": "urgency='no_velocity_data' means the product has no withdrawal history in the last 30 days — it is still below reorder point and may need restocking.",
        }
    )


async def _get_department_health() -> str:
    depts = await catalog_list_departments()
    all_products = await catalog_list_skus()
    by_dept: dict[str, list] = defaultdict(list)
    for p in all_products:
        if p.category_id:
            by_dept[p.category_id].append(p)
    rows = []
    for d in depts:
        dept_products = by_dept.get(d.id, [])
        out_of_stock = sum(1 for p in dept_products if p.quantity == 0)
        low_stock = sum(1 for p in dept_products if p.quantity > 0 and p.quantity <= p.min_stock)
        healthy = sum(1 for p in dept_products if p.quantity > p.min_stock)
        rows.append(
            {
                "name": d.name,
                "code": d.code,
                "sku_count": len(dept_products),
                "out_of_stock": out_of_stock,
                "low_stock": low_stock,
                "healthy": healthy,
            }
        )
    rows.sort(key=lambda r: r["out_of_stock"] + r["low_stock"], reverse=True)
    return json.dumps({"departments": rows})


async def _get_top_products(args: dict) -> str:
    days = min(int(args.get("days") or 30), 365)
    by = args.get("by", "revenue").lower()
    if by not in ("volume", "revenue"):
        by = "revenue"
    limit = min(int(args.get("limit") or 10), 50)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    withdrawals = await list_withdrawals(start_date=since, limit=10000)
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
    sort_key = "total_revenue" if by == "revenue" else "total_units"
    ranked = sorted(product_map.values(), key=lambda x: x[sort_key], reverse=True)[:limit]
    for r in ranked:
        r["total_revenue"] = round(r["total_revenue"], 2)
    return json.dumps(
        {"period_days": days, "ranked_by": by, "count": len(ranked), "products": ranked}
    )


async def _get_department_activity(args: dict) -> str:
    dept_code = (args.get("dept_code") or "").strip().upper()
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    dept = await catalog_get_dept_by_code(dept_code)
    if not dept:
        return json.dumps({"error": f"Department '{dept_code}' not found or has no products"})
    products = await catalog_list_skus(category_id=dept.id)
    if not products:
        return json.dumps({"error": f"Department '{dept_code}' not found or has no products"})
    product_ids = [p.id for p in products]
    vel = await withdrawal_velocity(product_ids, since)
    total_withdrawn = sum(float(v) for v in vel.values())
    low_stock_count = sum(1 for p in products if p.quantity <= p.min_stock)
    return json.dumps(
        {
            "dept_code": dept_code,
            "period_days": days,
            "sku_count": len(products),
            "low_stock_count": low_stock_count,
            "withdrawals": {"units": total_withdrawn},
        }
    )


async def _forecast_stockout(args: dict) -> str:
    limit = min(int(args.get("limit") or 15), 50)
    since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    products = await catalog_list_skus()
    in_stock = [p for p in products if p.quantity > 0]
    in_stock.sort(key=lambda p: p.quantity)
    in_stock = in_stock[:200]
    if not in_stock:
        return json.dumps({"count": 0, "forecast": []})
    product_ids = [p.id for p in in_stock]
    velocity_map = await withdrawal_velocity(product_ids, since)
    forecast = []
    for p in in_stock:
        total_used = float(velocity_map.get(p.id, 0))
        avg_daily = total_used / 30
        if avg_daily <= 0:
            continue
        days_until_zero = round(p.quantity / avg_daily, 1)
        forecast.append(
            {
                "sku": p.sku,
                "name": p.name,
                "department": p.category_name,
                "quantity": p.quantity,
                "min_stock": p.min_stock,
                "avg_daily_use": round(avg_daily, 2),
                "days_until_stockout": days_until_zero,
                "risk": "critical"
                if days_until_zero <= 3
                else "high"
                if days_until_zero <= 7
                else "medium",
            }
        )
    forecast.sort(key=lambda x: x["days_until_stockout"])
    return json.dumps({"count": len(forecast), "forecast": forecast[:limit]})


async def _get_slow_movers(args: dict) -> str:
    limit = min(int(args.get("limit") or 20), 100)
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    products = await catalog_list_skus()
    in_stock = [p for p in products if p.quantity > 0]
    if not in_stock:
        return json.dumps({"period_days": days, "count": 0, "slow_movers": []})
    product_ids = [p.id for p in in_stock]
    velocity_map = await withdrawal_velocity(product_ids, since)
    ranked = []
    for p in in_stock:
        withdrawn = float(velocity_map.get(p.id, 0))
        ranked.append((withdrawn, -p.quantity, p, withdrawn))
    ranked.sort(key=lambda t: (t[0], t[1]))
    out = [
        {
            "sku": p.sku,
            "name": p.name,
            "quantity": p.quantity,
            "sell_uom": p.sell_uom or "each",
            "department": p.category_name,
            "units_withdrawn_30d": withdrawn,
        }
        for _, _, p, withdrawn in ranked[:limit]
    ]
    return json.dumps({"period_days": days, "count": len(out), "slow_movers": out})


async def _search_vendors_semantic(args: dict) -> str:
    query = (args.get("query") or "").strip()
    limit = min(int(args.get("limit") or 10), 30)
    index = await get_index()
    results = await index.search_entity(query, "vendor", limit=limit)
    out = [{"id": r.entity_id, "score": round(r.score, 3), **r.data} for r in results]
    return json.dumps({"count": len(out), "vendors": out})


async def _search_pos_semantic(args: dict) -> str:
    query = (args.get("query") or "").strip()
    limit = min(int(args.get("limit") or 10), 30)
    index = await get_index()
    results = await index.search_entity(query, "purchase_order", limit=limit)
    out = [{"id": r.entity_id, "score": round(r.score, 3), **r.data} for r in results]
    return json.dumps({"count": len(out), "purchase_orders": out})


async def _search_jobs_semantic(args: dict) -> str:
    query = (args.get("query") or "").strip()
    limit = min(int(args.get("limit") or 10), 30)
    index = await get_index()
    results = await index.search_entity(query, "job", limit=limit)
    out = [{"job_id": r.entity_id, "score": round(r.score, 3), **r.data} for r in results]
    return json.dumps({"count": len(out), "jobs": out})


# ── Registry ──────────────────────────────────────────────────────────────────

_reg("search_products", "inventory", _search_products, lookup_key="search_products")
_reg("search_semantic", "inventory", _search_semantic)
_reg("get_product_details", "inventory", _get_product_details, lookup_key="product_details")
_reg("get_inventory_stats", "inventory", _get_inventory_stats, takes_args=False, lookup_key="stats")
_reg("list_low_stock", "inventory", _list_low_stock, lookup_key="low_stock")
_reg("list_departments", "inventory", _list_departments, takes_args=False, lookup_key="departments")
_reg("list_vendors", "inventory", _list_vendors, takes_args=False, lookup_key="vendors")
_reg("get_usage_velocity", "inventory", _get_usage_velocity)
_reg("get_reorder_suggestions", "inventory", _get_reorder_suggestions)
_reg("get_department_health", "inventory", _get_department_health, takes_args=False)
_reg("get_slow_movers", "inventory", _get_slow_movers)
_reg("get_top_products", "inventory", _get_top_products)
_reg("get_department_activity", "inventory", _get_department_activity)
_reg("forecast_stockout", "inventory", _forecast_stockout)
_reg("search_vendors_semantic", "inventory", _search_vendors_semantic)
_reg("search_pos_semantic", "inventory", _search_pos_semantic)
_reg("search_jobs_semantic", "inventory", _search_jobs_semantic)
