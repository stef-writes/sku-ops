"""Inventory agent tool implementations — DB queries and search helpers."""
import json
import logging
from datetime import UTC, datetime, timedelta, timezone

from assistant.agents.tools.registry import register as _reg
from assistant.agents.tools.search import get_index
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
    list_products as catalog_list_products,
)
from catalog.application.queries import (
    list_vendors as catalog_list_vendors,
)
from operations.application.queries import list_withdrawals
from shared.infrastructure.config import OPENAI_API_KEY
from shared.infrastructure.database import get_connection

logger = logging.getLogger(__name__)


async def _search_products(args: dict, org_id: str) -> str:
    query = (args.get("query") or "").strip()
    limit = min(int(args.get("limit") or 20), 50)
    items = await catalog_list_products(search=query, limit=limit, organization_id=org_id)
    out = [
        {
            "sku": p.get("sku"),
            "name": p.get("name"),
            "quantity": p.get("quantity"),
            "sell_uom": p.get("sell_uom", "each"),
            "min_stock": p.get("min_stock"),
            "department": p.get("department_name"),
        }
        for p in items
    ]
    return json.dumps({"count": len(out), "products": out})


async def _search_semantic(args: dict, org_id: str) -> str:
    query = (args.get("query") or "").strip()
    limit = min(int(args.get("limit") or 10), 30)
    index = await get_index(org_id)
    if OPENAI_API_KEY and index._embeddings is not None:
        results = await index.search_semantic(query, limit=limit, api_key=OPENAI_API_KEY)
        method = "embedding"
    else:
        results = index.search_bm25(query, limit=limit)
        method = "bm25"
    out = [
        {
            "sku": p.get("sku"),
            "name": p.get("name"),
            "quantity": p.get("quantity"),
            "sell_uom": p.get("sell_uom", "each"),
            "min_stock": p.get("min_stock"),
            "department": p.get("department_name"),
        }
        for p in results
    ]
    return json.dumps({"count": len(out), "products": out, "method": method})


async def _get_product_details(args: dict, org_id: str) -> str:
    sku = (args.get("sku") or "").strip().upper()
    conn = get_connection()
    cur = await conn.execute(
        "SELECT * FROM products WHERE UPPER(sku) = ? AND (organization_id = ? OR organization_id IS NULL)",
        (sku, org_id),
    )
    row = await cur.fetchone()
    if not row:
        return json.dumps({"error": f"Product with SKU '{sku}' not found"})
    p = dict(row)
    return json.dumps({
        "sku": p.get("sku"),
        "name": p.get("name"),
        "description": p.get("description"),
        "price": p.get("price"),
        "cost": p.get("cost"),
        "quantity": p.get("quantity"),
        "min_stock": p.get("min_stock"),
        "department": p.get("department_name"),
        "vendor": p.get("vendor_name"),
        "original_sku": p.get("original_sku"),
        "barcode": p.get("barcode"),
        "base_unit": p.get("base_unit"),
        "sell_uom": p.get("sell_uom"),
        "pack_qty": p.get("pack_qty"),
    })


async def _get_inventory_stats(org_id: str) -> str:
    conn = get_connection()
    cur = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    row = await cur.fetchone()
    total_skus = row[0] if row else 0
    cur = await conn.execute(
        "SELECT COALESCE(SUM(quantity * cost), 0) FROM products WHERE (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    row = await cur.fetchone()
    total_value = round(float(row[0] if row else 0), 2)
    cur = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE quantity <= min_stock AND (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    row = await cur.fetchone()
    low_count = row[0] if row else 0
    cur = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE quantity = 0 AND (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    row = await cur.fetchone()
    out_of_stock = row[0] if row else 0
    return json.dumps({
        "total_skus": total_skus,
        "_note": "total_skus is the count of distinct product lines. No meaningful total unit count exists because products are measured in different units (each, gallon, box, etc.).",
        "total_cost_value": total_value,
        "low_stock_count": low_count,
        "out_of_stock_count": out_of_stock,
    })


async def _list_low_stock(args: dict, org_id: str) -> str:
    limit = min(int(args.get("limit") or 20), 50)
    items = await catalog_list_low_stock(limit=limit, organization_id=org_id)
    out = [
        {
            "sku": p.get("sku"),
            "name": p.get("name"),
            "quantity": p.get("quantity"),
            "sell_uom": p.get("sell_uom", "each"),
            "min_stock": p.get("min_stock"),
            "department": p.get("department_name"),
        }
        for p in items
    ]
    return json.dumps({"count": len(out), "products": out})


async def _list_departments(org_id: str) -> str:
    depts = await catalog_list_departments(organization_id=org_id)
    counters = await get_sku_counters()
    out = []
    for d in depts:
        code = d.get("code", "")
        next_num = counters.get(code, 0) + 1
        next_sku = f"{code}-ITM-{str(next_num).zfill(6)}"
        out.append({
            "name": d.get("name"),
            "code": code,
            "product_count": d.get("product_count", 0),
            "next_sku": next_sku,
        })
    return json.dumps({"departments": out})


async def _list_vendors(org_id: str) -> str:
    vendors = await catalog_list_vendors(organization_id=org_id)
    out = [{"name": v.get("name"), "product_count": v.get("product_count", 0)} for v in vendors]
    return json.dumps({"vendors": out})


async def _get_usage_velocity(args: dict, org_id: str) -> str:
    sku = (args.get("sku") or "").strip().upper()
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    conn = get_connection()
    cur = await conn.execute(
        "SELECT id, name, quantity, sell_uom FROM products WHERE UPPER(sku) = ? AND (organization_id = ? OR organization_id IS NULL)",
        (sku, org_id),
    )
    row = await cur.fetchone()
    if not row:
        return json.dumps({"error": f"Product '{sku}' not found"})
    product_id, product_name, current_qty, sell_uom = row["id"], row["name"], row["quantity"], row["sell_uom"] or "each"
    cur = await conn.execute(
        """SELECT COUNT(*) as txn_count, COALESCE(SUM(ABS(quantity_delta)), 0) as total_used
           FROM stock_transactions
           WHERE product_id = ? AND transaction_type = 'WITHDRAWAL' AND created_at >= ?""",
        (product_id, since),
    )
    row = await cur.fetchone()
    txn_count = row["txn_count"] if row else 0
    total_used = float(row["total_used"]) if row else 0
    avg_daily = round(total_used / days, 2)
    days_until_zero = round(current_qty / avg_daily, 1) if avg_daily > 0 else None
    return json.dumps({
        "sku": sku,
        "name": product_name,
        "sell_uom": sell_uom,
        "current_quantity": current_qty,
        "period_days": days,
        "total_withdrawn": total_used,
        "withdrawal_transactions": txn_count,
        "avg_daily_use": avg_daily,
        "days_until_stockout": days_until_zero,
        "_note": None if days_until_zero is not None else "days_until_stockout is null because avg_daily_use=0 — no withdrawals recorded in this period, not a data error.",
    })


async def _get_reorder_suggestions(args: dict, org_id: str) -> str:
    limit = min(int(args.get("limit") or 20), 50)
    since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    conn = get_connection()
    low_stock = await catalog_list_low_stock(limit=100, organization_id=org_id)
    if not low_stock:
        return json.dumps({"count": 0, "suggestions": []})
    product_ids = [p["id"] for p in low_stock]
    placeholders = ",".join("?" * len(product_ids))
    cur = await conn.execute(
        f"""SELECT product_id, COALESCE(SUM(ABS(quantity_delta)), 0) as total_used
            FROM stock_transactions
            WHERE product_id IN ({placeholders}) AND transaction_type = 'WITHDRAWAL' AND created_at >= ?
            GROUP BY product_id""",
        (*product_ids, since),
    )
    velocity_map = {row["product_id"]: row["total_used"] for row in await cur.fetchall()}
    suggestions = []
    for p in low_stock:
        total_used = velocity_map.get(p["id"], 0)
        avg_daily = total_used / 30
        qty = p.get("quantity", 0)
        days_until_zero = round(qty / avg_daily, 1) if avg_daily > 0 else None
        urgency = (
            "critical" if days_until_zero is not None and days_until_zero <= 3
            else "high" if days_until_zero is not None and days_until_zero <= 7
            else "medium" if days_until_zero is not None
            else "no_velocity_data"
        )
        suggestions.append({
            "sku": p.get("sku"),
            "name": p.get("name"),
            "quantity": qty,
            "sell_uom": p.get("sell_uom", "each"),
            "min_stock": p.get("min_stock"),
            "avg_daily_use": round(avg_daily, 2),
            "days_until_stockout": days_until_zero,
            "urgency": urgency,
        })
    suggestions.sort(key=lambda x: (
        x["days_until_stockout"] is None,
        x["days_until_stockout"] if x["days_until_stockout"] is not None else 9999,
    ))
    return json.dumps({
        "count": len(suggestions),
        "suggestions": suggestions[:limit],
        "_note": "urgency='no_velocity_data' means the product has no withdrawal history in the last 30 days — it is still below reorder point and may need restocking.",
    })


async def _get_department_health(org_id: str) -> str:
    conn = get_connection()
    cur = await conn.execute(
        """SELECT d.name, d.code,
                  COUNT(p.id) as product_count,
                  SUM(CASE WHEN p.quantity = 0 THEN 1 ELSE 0 END) as out_of_stock,
                  SUM(CASE WHEN p.quantity > 0 AND p.quantity <= p.min_stock THEN 1 ELSE 0 END) as low_stock,
                  SUM(CASE WHEN p.quantity > p.min_stock THEN 1 ELSE 0 END) as healthy
           FROM departments d
           LEFT JOIN products p ON p.department_id = d.id
             AND (p.organization_id = ? OR p.organization_id IS NULL)
           WHERE (d.organization_id = ? OR d.organization_id IS NULL)
           GROUP BY d.id, d.name, d.code
           ORDER BY (out_of_stock + low_stock) DESC""",
        (org_id, org_id),
    )
    rows = [dict(r) for r in await cur.fetchall()]
    return json.dumps({"departments": rows})


async def _get_top_products(args: dict, org_id: str) -> str:
    days = min(int(args.get("days") or 30), 365)
    by = args.get("by", "revenue").lower()
    if by not in ("volume", "revenue"):
        by = "revenue"
    limit = min(int(args.get("limit") or 10), 50)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    withdrawals = await list_withdrawals(start_date=since, limit=10000, organization_id=org_id)
    product_map: dict[str, dict] = {}
    for w in withdrawals:
        for item in (w.get("items") or []):
            sku = item.get("sku") or item.get("name", "unknown")
            name = item.get("name", sku)
            qty = item.get("quantity", 0)
            revenue = item.get("subtotal", 0)
            if sku not in product_map:
                product_map[sku] = {"sku": sku, "name": name, "total_units": 0, "total_revenue": 0.0}
            product_map[sku]["total_units"] += qty
            product_map[sku]["total_revenue"] += revenue
    sort_key = "total_revenue" if by == "revenue" else "total_units"
    ranked = sorted(product_map.values(), key=lambda x: x[sort_key], reverse=True)[:limit]
    for r in ranked:
        r["total_revenue"] = round(r["total_revenue"], 2)
    return json.dumps({"period_days": days, "ranked_by": by, "count": len(ranked), "products": ranked})


async def _get_department_activity(args: dict, org_id: str) -> str:
    dept_code = (args.get("dept_code") or "").strip().upper()
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    conn = get_connection()
    cur = await conn.execute(
        """SELECT p.id, p.sku, p.name, p.quantity, p.min_stock
           FROM products p
           JOIN departments d ON p.department_id = d.id
           WHERE UPPER(d.code) = ?
             AND (p.organization_id = ? OR p.organization_id IS NULL)""",
        (dept_code, org_id),
    )
    products = [dict(r) for r in await cur.fetchall()]
    if not products:
        return json.dumps({"error": f"Department '{dept_code}' not found or has no products"})
    product_ids = [p["id"] for p in products]
    placeholders = ",".join("?" * len(product_ids))
    cur = await conn.execute(
        f"""SELECT
              transaction_type,
              COUNT(*) as txn_count,
              COALESCE(SUM(ABS(quantity_delta)), 0) as total_units
            FROM stock_transactions
            WHERE product_id IN ({placeholders}) AND created_at >= ?
            GROUP BY transaction_type""",
        (*product_ids, since),
    )
    type_summary: dict[str, dict] = {}
    for row in await cur.fetchall():
        type_summary[row["transaction_type"]] = {"transactions": row["txn_count"], "units": float(row["total_units"])}
    withdrawals = type_summary.get("WITHDRAWAL", {"transactions": 0, "units": 0})
    receiving = type_summary.get("RECEIVING", {"transactions": 0, "units": 0})
    imports = type_summary.get("IMPORT", {"transactions": 0, "units": 0})
    low_stock_count = sum(1 for p in products if p["quantity"] <= p["min_stock"])
    return json.dumps({
        "dept_code": dept_code,
        "period_days": days,
        "product_count": len(products),
        "low_stock_count": low_stock_count,
        "withdrawals": withdrawals,
        "receiving": receiving,
        "imports": imports,
        "net_units": (receiving["units"] + imports["units"]) - withdrawals["units"],
    })


async def _forecast_stockout(args: dict, org_id: str) -> str:
    limit = min(int(args.get("limit") or 15), 50)
    since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    conn = get_connection()
    cur = await conn.execute(
        """SELECT id, sku, name, quantity, min_stock, department_name
           FROM products
           WHERE quantity > 0
             AND (organization_id = ? OR organization_id IS NULL)
           ORDER BY quantity ASC
           LIMIT 200""",
        (org_id,),
    )
    products = [dict(r) for r in await cur.fetchall()]
    if not products:
        return json.dumps({"count": 0, "forecast": []})
    product_ids = [p["id"] for p in products]
    placeholders = ",".join("?" * len(product_ids))
    cur = await conn.execute(
        f"""SELECT product_id, COALESCE(SUM(ABS(quantity_delta)), 0) as total_used
            FROM stock_transactions
            WHERE product_id IN ({placeholders}) AND transaction_type = 'WITHDRAWAL' AND created_at >= ?
            GROUP BY product_id""",
        (*product_ids, since),
    )
    velocity_map = {row["product_id"]: row["total_used"] for row in await cur.fetchall()}
    forecast = []
    for p in products:
        total_used = velocity_map.get(p["id"], 0)
        avg_daily = total_used / 30
        if avg_daily <= 0:
            continue
        days_until_zero = round(p["quantity"] / avg_daily, 1)
        forecast.append({
            "sku": p["sku"],
            "name": p["name"],
            "department": p["department_name"],
            "quantity": p["quantity"],
            "min_stock": p["min_stock"],
            "avg_daily_use": round(avg_daily, 2),
            "days_until_stockout": days_until_zero,
            "risk": "critical" if days_until_zero <= 3 else "high" if days_until_zero <= 7 else "medium",
        })
    forecast.sort(key=lambda x: x["days_until_stockout"])
    return json.dumps({"count": len(forecast), "forecast": forecast[:limit]})


async def _get_slow_movers(args: dict, org_id: str) -> str:
    limit = min(int(args.get("limit") or 20), 100)
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    conn = get_connection()
    cur = await conn.execute(
        """SELECT p.id, p.sku, p.name, p.quantity, p.sell_uom, p.min_stock,
                  p.department_name,
                  COALESCE(txn.total_used, 0) as units_withdrawn
           FROM products p
           LEFT JOIN (
               SELECT product_id, SUM(ABS(quantity_delta)) as total_used
               FROM stock_transactions
               WHERE transaction_type = 'WITHDRAWAL' AND created_at >= ?
               GROUP BY product_id
           ) txn ON p.id = txn.product_id
           WHERE (p.organization_id = ? OR p.organization_id IS NULL)
             AND p.quantity > 0
           ORDER BY COALESCE(txn.total_used, 0) ASC, p.quantity DESC
           LIMIT ?""",
        (since, org_id, limit),
    )
    rows = [dict(r) for r in await cur.fetchall()]
    out = [
        {
            "sku": r["sku"],
            "name": r["name"],
            "quantity": r["quantity"],
            "sell_uom": r["sell_uom"] or "each",
            "department": r["department_name"],
            "units_withdrawn_30d": float(r["units_withdrawn"]),
        }
        for r in rows
    ]
    return json.dumps({"period_days": days, "count": len(out), "slow_movers": out})


# ── Registry ──────────────────────────────────────────────────────────────────

_reg("search_products",        "inventory", _search_products,        lookup_key="search_products")
_reg("search_semantic",        "inventory", _search_semantic)
_reg("get_product_details",    "inventory", _get_product_details,    lookup_key="product_details")
_reg("get_inventory_stats",    "inventory", _get_inventory_stats,    takes_args=False, lookup_key="stats")
_reg("list_low_stock",         "inventory", _list_low_stock,         lookup_key="low_stock")
_reg("list_departments",       "inventory", _list_departments,       takes_args=False, lookup_key="departments")
_reg("list_vendors",           "inventory", _list_vendors,           takes_args=False, lookup_key="vendors")
_reg("get_usage_velocity",     "inventory", _get_usage_velocity)
_reg("get_reorder_suggestions","inventory", _get_reorder_suggestions)
_reg("get_department_health",  "inventory", _get_department_health,  takes_args=False)
_reg("get_slow_movers",        "inventory", _get_slow_movers)
_reg("get_top_products",       "inventory", _get_top_products)
_reg("get_department_activity","inventory", _get_department_activity)
_reg("forecast_stockout",      "inventory", _forecast_stockout)
