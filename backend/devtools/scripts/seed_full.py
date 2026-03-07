"""
Comprehensive seed: wipe DB, create realistic products, then layer on
contractors, withdrawals, invoices, returns, purchase orders, stock
transactions, material requests, credit notes, and financial ledger entries.

Run standalone:  cd backend && python -m devtools.scripts.seed_full
Or via API:      POST /api/seed/seed-full
"""
import asyncio
import contextlib
import json
import logging
import random as _random_mod
from datetime import UTC, datetime, timedelta
from uuid import uuid4

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_rng = _random_mod.Random(42)

TAX_RATE = 0.10

CONTRACTORS = [
    {"name": "Mike Brennan", "email": "mike@brennanbuilders.com", "company": "Brennan Builders LLC", "billing_entity": "Brennan Builders LLC", "phone": "555-1001"},
    {"name": "Jessica Tran", "email": "jtran@tranconstruction.com", "company": "Tran Construction Inc", "billing_entity": "Tran Construction Inc", "phone": "555-1002"},
    {"name": "Carlos Medina", "email": "carlos@medinahomes.com", "company": "Medina Custom Homes", "billing_entity": "Medina Custom Homes", "phone": "555-1003"},
    {"name": "Anita Kapoor", "email": "anita@kapoorenergy.com", "company": "Kapoor Energy Solutions", "billing_entity": "Kapoor Energy Solutions", "phone": "555-1004"},
    {"name": "Ray Dubois", "email": "ray@duboismaintenance.com", "company": "DuBois Property Maintenance", "billing_entity": "DuBois Property Maintenance", "phone": "555-1005"},
    {"name": "Sandra Walsh", "email": "swalsh@walshplumbing.com", "company": "Walsh Plumbing & Heating", "billing_entity": "Walsh Plumbing & Heating", "phone": "555-1006"},
    {"name": "Derek Okonkwo", "email": "derek@deobuilds.com", "company": "DEO Builds", "billing_entity": "DEO Builds", "phone": "555-1007"},
    {"name": "Linda Park", "email": "linda@parkrenovations.com", "company": "Park Renovations", "billing_entity": "Park Renovations", "phone": "555-1008"},
]

JOBS = [
    {"id": "JOB-2026-0050", "address": "310 Evergreen Terrace"},
    {"id": "JOB-2026-0051", "address": "742 Willow Springs Rd"},
    {"id": "JOB-2026-0052", "address": "18 Granite Falls Ct"},
    {"id": "JOB-2026-0053", "address": "5600 Lakeshore Blvd"},
    {"id": "JOB-2026-0054", "address": "203 Cedar Ridge Ln"},
    {"id": "JOB-2026-0055", "address": "880 Industrial Pkwy Unit 4"},
    {"id": "JOB-2026-0056", "address": "1215 Sycamore Ave"},
    {"id": "JOB-2026-0057", "address": "44 Harbor View Dr"},
    {"id": "JOB-2026-0058", "address": "999 Pine Crest Loop"},
    {"id": "JOB-2026-0059", "address": "66 Brookside Way"},
    {"id": "JOB-2026-0060", "address": "2300 Mission Hill Rd"},
    {"id": "JOB-2026-0061", "address": "411 Orchard Park Dr"},
]

RETURN_REASONS = ["wrong_item", "defective", "overorder", "job_cancelled", "other"]


def _round(v: float) -> float:
    return round(v, 2)


async def _clear_all_tables(conn) -> None:
    """Delete all data from core tables in FK-safe order."""
    tables = [
        "financial_ledger", "credit_note_line_items", "credit_notes",
        "return_items", "returns",
        "invoice_line_items", "invoice_withdrawals", "invoices", "invoice_counters",
        "material_requests", "withdrawal_items", "withdrawals",
        "purchase_order_items", "purchase_orders",
        "stock_transactions", "products", "sku_counters",
        "vendors", "departments",
        "refresh_tokens", "users", "organizations",
    ]
    for t in tables:
        with contextlib.suppress(Exception):
            await conn.execute("DELETE FROM " + t)
    await conn.commit()


async def main():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

    from shared.infrastructure.database import get_connection, init_db
    await init_db()

    from catalog.application.product_lifecycle import create_product
    from catalog.application.queries import list_departments
    from catalog.infrastructure.vendor_repo import vendor_repo
    from finance.application.ledger_service import (
        record_adjustment,
        record_payment,
        record_po_receipt,
        record_return,
        record_withdrawal,
    )
    from finance.infrastructure.credit_note_repo import credit_note_repo
    from finance.infrastructure.invoice_repo import invoice_repo, set_withdrawal_getter
    from identity.application.auth_service import hash_password
    from identity.infrastructure.org_repo import organization_repo
    from identity.infrastructure.user_repo import user_repo
    from inventory.application.inventory_service import process_import_stock_changes
    from inventory.domain.stock import StockTransaction, StockTransactionType
    from inventory.infrastructure.stock_repo import stock_repo
    from operations.domain.material_request import MaterialRequest
    from operations.domain.returns import MaterialReturn, ReturnItem
    from operations.domain.withdrawal import MaterialWithdrawal, WithdrawalItem
    from operations.infrastructure.material_request_repo import material_request_repo
    from operations.infrastructure.return_repo import return_repo
    from operations.infrastructure.withdrawal_repo import withdrawal_repo
    from purchasing.domain.purchase_order import PurchaseOrder, PurchaseOrderItem
    from purchasing.infrastructure.po_repo import po_repo

    set_withdrawal_getter(withdrawal_repo.get_by_id)

    org_id = "default"
    conn = get_connection()
    now = datetime.now(UTC)

    # ══════════════════════════════════════════════════════════════════════
    # 0. RESET — wipe everything and bootstrap org + admin + departments
    # ══════════════════════════════════════════════════════════════════════
    logger.info("=== RESET: clearing all tables ===")
    await _clear_all_tables(conn)

    now_iso = now.isoformat()
    await organization_repo.insert({"id": org_id, "name": "Default", "slug": "default", "created_at": now_iso})

    from devtools.scripts.seed import seed_mock_user, seed_standard_departments
    await seed_mock_user(org_id)
    await seed_standard_departments(org_id)

    admin = await user_repo.get_by_email("admin@demo.local")
    demo_contractor = await user_repo.get_by_email("contractor@demo.local")
    if not admin or not demo_contractor:
        logger.error("Failed to create demo users")
        return None

    departments = await list_departments(org_id)
    dept_by_code = {d["code"]: d for d in departments}
    dept_name_map = {d["id"]: d["name"] for d in departments}

    # ══════════════════════════════════════════════════════════════════════
    # 1. VENDORS (from seed_realistic)
    # ══════════════════════════════════════════════════════════════════════
    from devtools.scripts.seed_realistic import PRODUCTS, VENDORS
    logger.info("--- Creating vendors ---")
    vendor_ids = []
    for v in VENDORS:
        vid = str(uuid4())
        vendor_ids.append(vid)
        await vendor_repo.insert({
            "id": vid, **v, "product_count": 0,
            "created_at": now_iso, "organization_id": org_id,
        })
        logger.info("  %s", v["name"])

    # ══════════════════════════════════════════════════════════════════════
    # 2. PRODUCTS (from seed_realistic)
    # ══════════════════════════════════════════════════════════════════════
    logger.info("--- Creating products ---")
    products_by_name: dict[str, dict] = {}
    all_products: list[dict] = []

    for p in PRODUCTS:
        dept = dept_by_code.get(p["dept"])
        if not dept:
            continue
        vid = vendor_ids[p["vendor"]]
        vname = VENDORS[p["vendor"]]["name"]
        try:
            product = await create_product(
                department_id=dept["id"], department_name=dept["name"],
                name=p["name"], price=p["price"], cost=p["cost"],
                quantity=p["qty"], min_stock=p["min"],
                vendor_id=vid, vendor_name=vname,
                base_unit=p["unit"], sell_uom=p["unit"],
                user_id=admin["id"], user_name=admin.get("name", "Admin"),
                organization_id=org_id,
                on_stock_import=process_import_stock_changes,
            )
            prod_dict = {"id": product.id, "sku": product.sku, "name": product.name,
                         "price": product.price, "cost": product.cost,
                         "quantity": p["qty"], "min_stock": p["min"],
                         "department_id": dept["id"]}
            if p["name"] not in products_by_name:
                products_by_name[p["name"]] = prod_dict
            all_products.append(prod_dict)
            logger.info("  %s | %s", product.sku, p["name"])
        except (ValueError, RuntimeError, OSError) as e:
            logger.warning("  Skip %s: %s", p["name"], e)

    logger.info("  %d unique products", len(products_by_name))

    # ══════════════════════════════════════════════════════════════════════
    # 3. CONTRACTORS (8 new + original demo contractor)
    # ══════════════════════════════════════════════════════════════════════
    logger.info("--- Creating contractors ---")
    from identity.domain.user import User
    contractor_users = []

    # Original demo contractor
    dc = await user_repo.get_by_email("contractor@demo.local")
    if dc:
        contractor_users.append(dc)

    for c in CONTRACTORS:
        user = User(
            email=c["email"], name=c["name"], role="contractor",
            company=c["company"], billing_entity=c["billing_entity"], phone=c["phone"],
        )
        user_dict = user.model_dump()
        user_dict["password"] = hash_password("demo123")
        user_dict["organization_id"] = org_id
        await user_repo.insert(user_dict)
        u = await user_repo.get_by_id(user.id)
        if u:
            contractor_users.append(u)
        logger.info("  %s — %s (%s)", c["name"], c["email"], c["company"])

    # ══════════════════════════════════════════════════════════════════════
    # 4. WITHDRAWALS — 60 across contractors/jobs over 120 days
    # ══════════════════════════════════════════════════════════════════════
    logger.info("--- Creating withdrawals ---")
    product_names = list(products_by_name.keys())
    withdrawal_records: list[dict] = []

    for i in range(60):
        contractor = _rng.choice(contractor_users)
        job = _rng.choice(JOBS)
        days_ago = _rng.randint(1, 120)
        created_at = (now - timedelta(days=days_ago, hours=_rng.randint(6, 17))).isoformat()

        pick_count = _rng.randint(2, 5)
        picked_names = _rng.sample(product_names, min(pick_count, len(product_names)))
        items = []
        for pname in picked_names:
            prod = products_by_name[pname]
            qty = _rng.randint(1, 20)
            items.append(WithdrawalItem(
                product_id=prod["id"], sku=prod["sku"], name=prod["name"],
                quantity=qty, unit_price=prod["price"], cost=prod["cost"],
            ))

        withdrawal = MaterialWithdrawal(
            items=items, job_id=job["id"], service_address=job["address"], notes="",
            subtotal=0, tax=0, total=0, cost_total=0,
            contractor_id=contractor["id"],
            contractor_name=contractor.get("name", ""),
            contractor_company=contractor.get("company", ""),
            billing_entity=contractor.get("billing_entity") or contractor.get("company", ""),
            payment_status="unpaid",
            processed_by_id=admin["id"],
            processed_by_name=admin.get("name", ""),
        )
        withdrawal.compute_totals(TAX_RATE)

        w_dict = withdrawal.model_dump()
        w_dict["organization_id"] = org_id
        w_dict["created_at"] = created_at
        await withdrawal_repo.insert(w_dict)

        for item in items:
            prod = products_by_name.get(item.name, {})
            qty_before = max(0, prod.get("quantity", 0))
            qty_after = max(0, qty_before - item.quantity)
            await conn.execute(
                "UPDATE products SET quantity = MAX(0, quantity - ?) WHERE id = ?",
                (item.quantity, item.product_id),
            )
            tx = StockTransaction(
                product_id=item.product_id, sku=item.sku, product_name=item.name,
                quantity_delta=-item.quantity, quantity_before=qty_before, quantity_after=qty_after,
                unit="each", transaction_type=StockTransactionType.WITHDRAWAL,
                reason=f"Withdrawal for {job['id']}",
                user_id=admin["id"], user_name=admin.get("name", ""),
                reference_id=withdrawal.id,
            )
            tx.organization_id = org_id
            tx.created_at = created_at
            await stock_repo.insert_transaction(tx)
            prod["quantity"] = qty_after
        await conn.commit()

        ledger_items = [{
            "product_id": it.product_id, "sku": it.sku, "name": it.name,
            "quantity": it.quantity, "unit_price": it.unit_price, "cost": it.cost,
            "department_name": dept_name_map.get(products_by_name.get(it.name, {}).get("department_id")),
        } for it in items]
        await record_withdrawal(
            withdrawal_id=withdrawal.id, items=ledger_items,
            tax=withdrawal.tax, total=withdrawal.total,
            job_id=job["id"],
            billing_entity=contractor.get("billing_entity") or "",
            contractor_id=contractor["id"],
            organization_id=org_id,
            performed_by_user_id=admin["id"],
            created_at=created_at,
        )

        withdrawal_records.append({
            "id": withdrawal.id, "contractor": contractor, "job": job,
            "items": items, "days_ago": days_ago,
            "total": withdrawal.total, "tax": withdrawal.tax, "subtotal": withdrawal.subtotal,
        })
        if i < 3 or i % 15 == 0:
            logger.info("  [%d/60] %s | %s | $%.2f", i + 1, job["id"], contractor.get("company", "")[:25], withdrawal.total)

    logger.info("  %d withdrawals created", len(withdrawal_records))

    # ══════════════════════════════════════════════════════════════════════
    # 5. STOCK ADJUSTMENTS — 15 manual adjustments
    # ══════════════════════════════════════════════════════════════════════
    logger.info("--- Creating stock adjustments ---")
    adj_reasons = ["Physical count correction", "Damaged goods", "Cycle count", "Shrinkage"]
    for _ in range(15):
        prod = _rng.choice(all_products)
        delta = _rng.choice([-5, -3, -1, 2, 5, 10, 20])
        qty_before = max(0, prod["quantity"])
        qty_after = max(0, qty_before + delta)
        reason = _rng.choice(adj_reasons)
        tx = StockTransaction(
            product_id=prod["id"], sku=prod["sku"], product_name=prod["name"],
            quantity_delta=delta, quantity_before=qty_before, quantity_after=qty_after,
            unit="each", transaction_type=StockTransactionType.ADJUSTMENT,
            reason=reason,
            user_id=admin["id"], user_name=admin.get("name", ""),
        )
        tx.organization_id = org_id
        adj_created = (now - timedelta(days=_rng.randint(1, 90))).isoformat()
        tx.created_at = adj_created
        await stock_repo.insert_transaction(tx)
        await conn.execute("UPDATE products SET quantity = ? WHERE id = ?", (qty_after, prod["id"]))

        dept_name = dept_name_map.get(prod.get("department_id"))
        ledger_reason = "damage" if "Damaged" in reason else "shrinkage"
        await record_adjustment(
            adjustment_ref_id=tx.id, product_id=prod["id"],
            product_cost=prod["cost"], quantity_delta=delta,
            department=dept_name, organization_id=org_id,
            reason=ledger_reason, performed_by_user_id=admin["id"],
            created_at=adj_created,
        )
    await conn.commit()
    logger.info("  15 stock adjustments")

    # ══════════════════════════════════════════════════════════════════════
    # 6. PURCHASE ORDERS — 8 POs with mixed statuses
    # ══════════════════════════════════════════════════════════════════════
    logger.info("--- Creating purchase orders ---")
    cur = await conn.execute("SELECT id, name FROM vendors WHERE organization_id = ?", (org_id,))
    vendors = [dict(v) for v in await cur.fetchall()]

    po_scenarios = [
        {"days_ago": 90, "status": "received"},
        {"days_ago": 60, "status": "received"},
        {"days_ago": 45, "status": "received"},
        {"days_ago": 30, "status": "received"},
        {"days_ago": 21, "status": "partial"},
        {"days_ago": 14, "status": "partial"},
        {"days_ago": 7,  "status": "ordered"},
        {"days_ago": 3,  "status": "ordered"},
        {"days_ago": 1,  "status": "ordered"},
    ]

    for idx, scenario in enumerate(po_scenarios):
        vendor = vendors[idx % len(vendors)]
        po_prods = _rng.sample(all_products, min(_rng.randint(2, 5), len(all_products)))
        po_date = (now - timedelta(days=scenario["days_ago"])).isoformat()
        is_received = scenario["status"] == "received"
        received_at = (now - timedelta(days=scenario["days_ago"] - 3)).isoformat() if is_received else None

        po = PurchaseOrder(
            vendor_id=vendor["id"], vendor_name=vendor["name"],
            document_date=po_date, total=0, status=scenario["status"],
            created_by_id=admin["id"], created_by_name=admin.get("name", ""),
            received_at=received_at,
            received_by_id=admin["id"] if is_received else None,
            received_by_name=admin.get("name", "") if is_received else None,
            organization_id=org_id,
        )
        po.created_at = po_date

        items = []
        po_total = 0.0
        for prod in po_prods:
            ordered = _rng.randint(5, 50)
            if is_received:
                delivered, item_status = ordered, "arrived"
            elif scenario["status"] == "partial":
                delivered = _rng.randint(0, ordered - 1)
                item_status = "pending" if delivered > 0 else "ordered"
            else:
                delivered, item_status = 0, "ordered"

            po_total += _round(prod["cost"] * ordered)
            items.append(PurchaseOrderItem(
                po_id=po.id, name=prod["name"], original_sku=prod["sku"],
                ordered_qty=ordered, delivered_qty=delivered,
                unit_price=prod["price"], cost=prod["cost"],
                status=item_status, product_id=prod["id"], organization_id=org_id,
            ))
            if delivered > 0:
                await conn.execute(
                    "UPDATE products SET quantity = quantity + ? WHERE id = ?",
                    (delivered, prod["id"]),
                )

        po.total = _round(po_total)
        await po_repo.insert_po(po)
        await po_repo.insert_items(items)

        if is_received:
            ledger_items = [{
                "product_id": it.product_id, "cost": it.cost,
                "delivered_qty": it.delivered_qty,
                "suggested_department": dept_name_map.get(
                    products_by_name.get(it.name, {}).get("department_id"), ""),
            } for it in items if it.delivered_qty > 0]
            await record_po_receipt(
                po_id=po.id, items=ledger_items,
                vendor_name=vendor["name"], organization_id=org_id,
                performed_by_user_id=admin["id"],
                created_at=received_at,
            )

        logger.info("  PO %s... | %s | %s | $%.2f", po.id[:8], vendor["name"][:25], scenario["status"], po_total)

    await conn.commit()

    # ══════════════════════════════════════════════════════════════════════
    # 7. INVOICES — group older withdrawals by billing entity
    # ══════════════════════════════════════════════════════════════════════
    logger.info("--- Creating invoices ---")
    by_entity: dict[str, list] = {}
    for wr in withdrawal_records:
        be = wr["contractor"].get("billing_entity") or wr["contractor"].get("company", "Unknown")
        by_entity.setdefault(be, []).append(wr)

    invoice_count = 0
    paid_withdrawal_ids = []
    for entity, wrs in by_entity.items():
        wrs.sort(key=lambda w: w["days_ago"], reverse=True)
        old_wrs = [w for w in wrs if w["days_ago"] > 10]
        if not old_wrs:
            continue

        batch_size = max(1, len(old_wrs) // 2)
        for batch_start in range(0, len(old_wrs), batch_size):
            batch = old_wrs[batch_start:batch_start + batch_size]
            wids = [w["id"] for w in batch]
            try:
                inv = await invoice_repo.create_from_withdrawals(wids, organization_id=org_id)
                invoice_count += 1
                logger.info("  INV %s | %s | %d w/d | $%.2f", inv.get("invoice_number", "?"), entity[:30], len(wids), inv.get("total", 0))

                if _rng.random() < 0.4:
                    paid_at = (now - timedelta(days=_rng.randint(1, 8))).isoformat()
                    for wid in wids:
                        await withdrawal_repo.mark_paid(wid, paid_at)
                        paid_withdrawal_ids.append(wid)
                        await record_payment(
                            withdrawal_id=wid,
                            amount=next(w["total"] for w in batch if w["id"] == wid),
                            billing_entity=entity,
                            contractor_id=batch[0]["contractor"]["id"],
                            organization_id=org_id,
                            performed_by_user_id=admin["id"],
                            created_at=paid_at,
                        )
                    if inv.get("id"):
                        await conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (inv["id"],))
                        await conn.commit()
            except (ValueError, RuntimeError, OSError) as e:
                logger.warning("  Invoice skip (%s): %s", entity[:20], e)

    logger.info("  %d invoices, %d paid", invoice_count, len(paid_withdrawal_ids))

    # ══════════════════════════════════════════════════════════════════════
    # 8. RETURNS — 5 partial returns against older withdrawals
    # ══════════════════════════════════════════════════════════════════════
    logger.info("--- Creating returns ---")
    return_candidates = [w for w in withdrawal_records if w["days_ago"] > 5]
    _rng.shuffle(return_candidates)

    for wr in return_candidates[:5]:
        picked_items = _rng.sample(list(wr["items"]), _rng.randint(1, min(2, len(wr["items"]))))
        return_items = []
        for item in picked_items:
            return_items.append(ReturnItem(
                product_id=item.product_id, sku=item.sku, name=item.name,
                quantity=_rng.randint(1, max(1, int(item.quantity) // 2)),
                unit_price=item.unit_price, cost=item.cost,
                reason=_rng.choice(RETURN_REASONS), notes="",
            ))

        contractor = wr["contractor"]
        ret = MaterialReturn(
            withdrawal_id=wr["id"], contractor_id=contractor["id"],
            contractor_name=contractor.get("name", ""),
            billing_entity=contractor.get("billing_entity") or contractor.get("company", ""),
            job_id=wr["job"]["id"], items=return_items,
            processed_by_id=admin["id"], processed_by_name=admin.get("name", ""),
        )
        ret.compute_totals(TAX_RATE)
        ret_dict = ret.model_dump()
        ret_dict["organization_id"] = org_id
        ret_dict["created_at"] = (now - timedelta(days=wr["days_ago"] - 2)).isoformat()
        await return_repo.insert(ret_dict)

        for ri in return_items:
            await conn.execute("UPDATE products SET quantity = quantity + ? WHERE id = ?", (ri.quantity, ri.product_id))
        await conn.commit()

        ledger_items = [{
            "product_id": ri.product_id, "sku": ri.sku, "name": ri.name,
            "quantity": ri.quantity, "unit_price": ri.unit_price, "cost": ri.cost,
            "department_name": dept_name_map.get(products_by_name.get(ri.name, {}).get("department_id")),
        } for ri in return_items]
        return_created_at = (now - timedelta(days=wr["days_ago"] - 2)).isoformat()
        await record_return(
            return_id=ret.id, items=ledger_items,
            tax=ret.tax, total=ret.total,
            job_id=wr["job"]["id"],
            billing_entity=contractor.get("billing_entity") or "",
            contractor_id=contractor["id"],
            organization_id=org_id,
            performed_by_user_id=admin["id"],
            created_at=return_created_at,
        )
        items_str = ", ".join(f"{ri.name[:20]} x{ri.quantity}" for ri in return_items)
        logger.info("  Return | %s | $%.2f | %s", contractor.get("company", "")[:25], ret.total, items_str)

    # ══════════════════════════════════════════════════════════════════════
    # 9. MATERIAL REQUESTS — 8 (pending / approved / fulfilled)
    # ══════════════════════════════════════════════════════════════════════
    logger.info("--- Creating material requests ---")
    mr_count = 0
    for i in range(8):
        contractor = _rng.choice(contractor_users)
        job = _rng.choice(JOBS)
        picked = _rng.sample(product_names, _rng.randint(2, 4))
        items = []
        for pname in picked:
            prod = products_by_name[pname]
            qty = _rng.randint(1, 10)
            items.append(WithdrawalItem(
                product_id=prod["id"], sku=prod["sku"], name=prod["name"],
                quantity=qty, unit_price=prod["price"], cost=prod["cost"],
            ))

        days_ago = _rng.randint(0, 20)
        if i < 3:
            status, processed_at, processed_by = "pending", None, None
        elif i < 6:
            status = "approved"
            processed_at = (now - timedelta(days=max(0, days_ago - 1))).isoformat()
            processed_by = admin["id"]
        else:
            status = "fulfilled"
            processed_at = (now - timedelta(days=max(0, days_ago - 1))).isoformat()
            processed_by = admin["id"]

        mr = MaterialRequest(
            contractor_id=contractor["id"],
            contractor_name=contractor.get("name", ""),
            items=items, status=status,
            job_id=job["id"], service_address=job["address"],
            notes=_rng.choice(["", "Urgent", "Need by tomorrow", "For phase 2", ""]),
            processed_at=processed_at, processed_by_id=processed_by,
        )
        mr_dict = mr.model_dump()
        mr_dict["organization_id"] = org_id
        mr_dict["created_at"] = (now - timedelta(days=days_ago)).isoformat()
        await material_request_repo.insert(mr_dict)
        mr_count += 1

    logger.info("  %d material requests", mr_count)

    # ══════════════════════════════════════════════════════════════════════
    # 10. CREDIT NOTES — one per return
    # ══════════════════════════════════════════════════════════════════════
    logger.info("--- Creating credit notes ---")
    cur = await conn.execute(
        "SELECT id, billing_entity, subtotal, tax, total, items, withdrawal_id "
        "FROM returns WHERE organization_id = ? AND credit_note_id IS NULL", (org_id,),
    )
    return_rows = await cur.fetchall()
    cn_count = 0
    for ret_row in return_rows:
        r = dict(ret_row)
        items_data = json.loads(r["items"]) if isinstance(r["items"], str) else r["items"]

        invoice_id = None
        cur2 = await conn.execute("SELECT invoice_id FROM withdrawals WHERE id = ?", (r["withdrawal_id"],))
        w_row = await cur2.fetchone()
        if w_row:
            invoice_id = dict(w_row).get("invoice_id")

        try:
            cn = await credit_note_repo.insert_credit_note(
                return_id=r["id"], invoice_id=invoice_id,
                items=items_data, subtotal=r["subtotal"], tax=r["tax"], total=r["total"],
                organization_id=org_id,
            )
            cn_count += 1
            logger.info("  %s | %s | $%.2f", cn.get("credit_note_number", "?"), r["billing_entity"][:25], r["total"])
        except (ValueError, RuntimeError, OSError) as e:
            logger.warning("  Credit note skip: %s", e)

    # ══════════════════════════════════════════════════════════════════════
    # 11. LOW-STOCK ALERTS — force a few products critically low
    # ══════════════════════════════════════════════════════════════════════
    logger.info("--- Setting low-stock alerts ---")
    low_stock_names = [
        "4x8 3/4in Sanded Plywood", "GFCI Outlet 15A White",
        "5 Gal Interior Eggshell White", "20V Cordless Drill Kit",
        "SharkBite 1/2in Push Fitting", "Deadbolt Single Cyl Satin Nickel",
    ]
    for name in low_stock_names:
        prod = products_by_name.get(name)
        if prod:
            low_qty = _rng.randint(1, prod["min_stock"])
            await conn.execute("UPDATE products SET quantity = ? WHERE id = ?", (low_qty, prod["id"]))
            logger.info("  %s | %s → qty=%d (min=%d)", prod["sku"], name, low_qty, prod["min_stock"])
    await conn.commit()

    # ══════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════
    counts = {}
    for table in ["users", "products", "vendors", "departments", "withdrawals",
                   "invoices", "returns", "purchase_orders", "purchase_order_items",
                   "material_requests", "credit_notes", "stock_transactions", "financial_ledger"]:
        try:
            cur = await conn.execute("SELECT COUNT(*) FROM " + table + " WHERE organization_id = ?", (org_id,))
            counts[table] = (await cur.fetchone())[0]
        except (RuntimeError, OSError):
            counts[table] = "?"

    logger.info("\n" + "=" * 60)
    logger.info("  FULL SEED COMPLETE")
    logger.info("=" * 60)
    for table, count in counts.items():
        logger.info("  %-25s %s", table, count)
    logger.info("-" * 60)
    logger.info("  Logins (password: demo123):")
    logger.info("    %-40s Admin", "admin@demo.local")
    logger.info("    %-40s Demo Contractor", "contractor@demo.local")
    for c in CONTRACTORS:
        logger.info("    %-40s %s", c["email"], c["company"])
    logger.info("=" * 60)

    return counts


if __name__ == "__main__":
    asyncio.run(main())
