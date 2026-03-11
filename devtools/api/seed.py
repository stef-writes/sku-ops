"""Seed API routes. Business logic lives in scripts/seed.py to avoid cross-domain imports."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from catalog.application.queries import count_all_products
from devtools.scripts.seed import (
    seed_demo_inventory,
    seed_demo_tenants,
    seed_mock_user,
    seed_standard_departments,
)
from identity.infrastructure.org_repo import organization_repo
from shared.api.deps import AdminDep
from shared.infrastructure.config import ALLOW_RESET
from shared.infrastructure.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/seed", tags=["seed"])


@router.post("/departments")
async def seed_departments(current_user: AdminDep):
    org_id = getattr(current_user, "organization_id", None) or (
        current_user.get("organization_id") if isinstance(current_user, dict) else "default"
    )
    await seed_standard_departments(org_id)
    return {"message": "Departments ready"}


async def _clear_all_tables(conn) -> None:
    """Delete all data from core tables (FK order)."""
    await conn.execute("DELETE FROM financial_ledger")
    await conn.execute("DELETE FROM credit_note_line_items")
    await conn.execute("DELETE FROM credit_notes")
    await conn.execute("DELETE FROM returns")
    await conn.execute("DELETE FROM invoice_line_items")
    await conn.execute("DELETE FROM invoice_withdrawals")
    await conn.execute("DELETE FROM invoices")
    await conn.execute("DELETE FROM invoice_counters")
    await conn.execute("DELETE FROM material_requests")
    await conn.execute("DELETE FROM withdrawals")
    await conn.execute("DELETE FROM purchase_order_items")
    await conn.execute("DELETE FROM purchase_orders")
    await conn.execute("DELETE FROM stock_transactions")
    await conn.execute("DELETE FROM products")
    await conn.execute("DELETE FROM sku_counters")
    await conn.execute("DELETE FROM vendors")
    await conn.execute("DELETE FROM departments")
    await conn.execute("DELETE FROM users")
    await conn.execute("DELETE FROM organizations")
    await conn.commit()


@router.post("/reset")
async def reset_all():
    """Reset core tables and reseed demo tenants."""
    if not ALLOW_RESET:
        raise HTTPException(
            status_code=403, detail="Reset not allowed. Set ALLOW_RESET=true or ENV=development."
        )
    conn = get_connection()
    try:
        await _clear_all_tables(conn)
        logger.info("Full reset complete")
    except Exception as e:
        logger.exception("Reset failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    await seed_demo_tenants()
    return {
        "message": "Reset complete. Demo tenants (North, South) seeded with users and inventory."
    }


@router.post("/reset-empty")
async def reset_empty():
    """Clear all data and reseed minimal (default org, demo user, departments)."""
    if not ALLOW_RESET:
        raise HTTPException(
            status_code=403, detail="Reset not allowed. Set ALLOW_RESET=true or ENV=development."
        )
    conn = get_connection()
    try:
        await _clear_all_tables(conn)
        logger.info("Full reset complete (empty)")
    except Exception as e:
        logger.exception("Reset failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    now = datetime.now(UTC).isoformat()
    await organization_repo.insert(
        {"id": "default", "name": "Default", "slug": "default", "created_at": now}
    )
    await seed_mock_user()
    await seed_standard_departments("default")
    return {
        "message": "Reset complete. Empty state. Log in with demo credentials (admin@demo.local / demo123)."
    }


@router.post("/backfill-ledger")
async def backfill_ledger(current_user: AdminDep):
    """Replay all historical events into the financial_ledger for existing data."""
    from catalog.application.queries import list_products
    from finance.application.ledger_service import (
        record_adjustment,
        record_payment,
        record_po_receipt,
        record_return,
        record_withdrawal,
    )
    from operations.application.queries import list_returns, list_withdrawals

    org_id = getattr(current_user, "organization_id", None) or "default"
    conn = get_connection()

    await conn.execute("DELETE FROM financial_ledger WHERE organization_id = ?", (org_id,))
    await conn.commit()

    products = await list_products(organization_id=org_id)
    dept_map = {p["id"]: p.get("department_name") for p in products}
    cost_map = {p["id"]: p.get("cost", 0) for p in products}

    withdrawals = await list_withdrawals(limit=100000, organization_id=org_id)
    for w in withdrawals:
        items = [
            {**i, "department_name": dept_map.get(i.get("product_id"))} for i in w.get("items", [])
        ]
        await record_withdrawal(
            withdrawal_id=w["id"],
            items=items,
            tax=w.get("tax", 0),
            total=w.get("total", 0),
            job_id=w.get("job_id", ""),
            billing_entity=w.get("billing_entity", ""),
            contractor_id=w.get("contractor_id", ""),
            organization_id=org_id,
            performed_by_user_id=w.get("processed_by_id"),
        )
        if w.get("payment_status") == "paid":
            await record_payment(
                withdrawal_id=w["id"],
                amount=w.get("total", 0),
                billing_entity=w.get("billing_entity", ""),
                contractor_id=w.get("contractor_id", ""),
                organization_id=org_id,
                performed_by_user_id=w.get("processed_by_id"),
            )

    returns = await list_returns(limit=100000, organization_id=org_id)
    for r in returns:
        items = [
            {**i, "department_name": dept_map.get(i.get("product_id"))} for i in r.get("items", [])
        ]
        await record_return(
            return_id=r["id"],
            items=items,
            tax=r.get("tax", 0),
            total=r.get("total", 0),
            job_id=r.get("job_id", ""),
            billing_entity=r.get("billing_entity", ""),
            contractor_id=r.get("contractor_id", ""),
            organization_id=org_id,
            performed_by_user_id=r.get("processed_by_id"),
        )

    cursor = await conn.execute(
        """SELECT po.id, po.vendor_name, po.received_by_id,
                  poi.cost, poi.delivered_qty, poi.product_id, poi.suggested_department
           FROM purchase_orders po
           JOIN purchase_order_items poi ON po.id = poi.po_id
           WHERE po.organization_id = ? AND poi.status = 'arrived'""",
        (org_id,),
    )
    po_rows = await cursor.fetchall()
    po_items: dict[str, list] = {}
    po_vendors: dict[str, str] = {}
    po_receivers: dict[str, str] = {}
    for row in po_rows:
        r = dict(row)
        po_id = r["id"]
        po_vendors[po_id] = r["vendor_name"]
        po_receivers[po_id] = r.get("received_by_id") or ""
        po_items.setdefault(po_id, []).append(r)
    for po_id, items in po_items.items():
        await record_po_receipt(
            po_id=po_id,
            items=items,
            vendor_name=po_vendors.get(po_id, ""),
            organization_id=org_id,
            performed_by_user_id=po_receivers.get(po_id) or None,
        )

    cursor = await conn.execute(
        """SELECT product_id, quantity_delta, reason, user_id
           FROM stock_transactions
           WHERE (organization_id = ? OR organization_id IS NULL)
             AND transaction_type = 'adjustment'""",
        (org_id,),
    )
    adj_rows = await cursor.fetchall()
    for row in adj_rows:
        r = dict(row)
        pid = r["product_id"]
        await record_adjustment(
            adjustment_ref_id=pid,
            product_id=pid,
            product_cost=cost_map.get(pid, 0),
            quantity_delta=r["quantity_delta"],
            department=dept_map.get(pid),
            organization_id=org_id,
            performed_by_user_id=r.get("user_id"),
        )

    total_entries = 0
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM financial_ledger WHERE organization_id = ?", (org_id,)
    )
    row = await cursor.fetchone()
    total_entries = row[0] if row else 0

    return {
        "message": "Ledger backfill complete",
        "withdrawals": len(withdrawals),
        "returns": len(returns),
        "po_receipts": len(po_items),
        "adjustments": len(adj_rows),
        "total_ledger_entries": total_entries,
    }


@router.post("/seed-full")
async def seed_full():
    """Full reset + seed: wipes DB, creates vendors, products, contractors,
    withdrawals, POs, invoices, returns, credit notes, material requests,
    stock transactions, and financial ledger entries."""
    if not ALLOW_RESET:
        raise HTTPException(
            status_code=403, detail="Seed not allowed. Set ALLOW_RESET=true or ENV=development."
        )
    try:
        from devtools.scripts.seed_full import main as run_full_seed

        counts = await run_full_seed()
        return {"message": "Full seed complete", "counts": counts or {}}
    except Exception as e:
        logger.exception("Full seed failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/reset-inventory")
async def reset_and_reseed_inventory(current_user: AdminDep):
    """Reset products and stock, then re-run demo seed."""
    org_id = getattr(current_user, "organization_id", None) or (
        current_user.get("organization_id") if isinstance(current_user, dict) else "default"
    )
    conn = get_connection()
    try:
        await conn.execute("DELETE FROM stock_transactions")
        await conn.execute("DELETE FROM products")
        await conn.execute("DELETE FROM sku_counters")
        await conn.execute("UPDATE departments SET product_count = 0")
        await conn.execute("UPDATE vendors SET product_count = 0")
        await conn.commit()
        logger.info("Inventory reset complete")
        await seed_demo_inventory(org_id)
        count = await count_all_products(org_id)
        return {"message": f"Inventory reset and reseeded with {count} products"}
    except Exception as e:
        logger.exception("Reset inventory failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
