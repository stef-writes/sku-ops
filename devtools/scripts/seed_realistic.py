"""
Demo seed — run once after a clean deploy to populate the database with
realistic supply-yard data.

Creates:
  - 1 organization (default)
  - 1 admin user + 1 contractor user
  - 8 departments
  - 6 vendors
  - ~50 SKUs with vendor items
  - 6 material withdrawals across 4 job sites
  - 4 invoices (2 marked paid)
  - Low-stock alerts on 4 SKUs

Usage:
    ./bin/dev seed
    # or directly:
    cd backend && python -m devtools.scripts.seed_realistic
"""

import argparse
import asyncio
import logging
import random as _random_mod
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from devtools.scripts.seed_data import (
    ADMIN_USER,
    CONTRACTOR_USER,
    DEPARTMENTS,
    LOW_STOCK_NAMES,
    ORG,
    PRODUCTS,
    VENDORS,
    WITHDRAWAL_SCENARIOS,
    SeedOrg,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_rng = _random_mod.Random(42)

# Mutable copy — may be overridden via CLI args
_org = ORG


def _hash_password(pw: str) -> str:
    import bcrypt

    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def _get_user_by_email(conn, email: str) -> dict | None:
    cursor = await conn.execute("SELECT * FROM users WHERE email = $1", (email,))
    row = await cursor.fetchone()
    return dict(row) if row and hasattr(row, "keys") else None


# ---------------------------------------------------------------------------
# Seed steps
# ---------------------------------------------------------------------------


async def seed_org(conn, org_id: str) -> None:
    cursor = await conn.execute("SELECT id FROM organizations WHERE id = $1", (org_id,))
    if await cursor.fetchone():
        logger.info("  Org '%s' already exists — skipping", org_id)
        return
    await conn.execute(
        "INSERT INTO organizations (id, name, slug, created_at) VALUES ($1, $2, $3, $4)",
        (org_id, _org.name, _org.slug, datetime.now(UTC).isoformat()),
    )
    await conn.commit()
    logger.info("  Created org: %s", _org.name)


async def seed_users(conn, org_id: str) -> tuple[dict, dict]:
    """Create admin and contractor users. Returns (admin, contractor) dicts."""
    now = datetime.now(UTC).isoformat()
    admin = await _get_user_by_email(conn, ADMIN_USER.email)
    if not admin:
        user_id = str(uuid4())
        await conn.execute(
            "INSERT INTO users (id, email, password, name, role, company, billing_entity, phone, is_active, organization_id, created_at)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1, $9, $10)",
            (
                user_id,
                ADMIN_USER.email,
                _hash_password(ADMIN_USER.password),
                ADMIN_USER.name,
                ADMIN_USER.role,
                "",
                "",
                "",
                org_id,
                now,
            ),
        )
        await conn.commit()
        logger.info("  Created user: %s (%s)", ADMIN_USER.email, ADMIN_USER.role)
        admin = await _get_user_by_email(conn, ADMIN_USER.email)

    contractor = await _get_user_by_email(conn, CONTRACTOR_USER.email)
    if not contractor:
        user_id = str(uuid4())
        await conn.execute(
            "INSERT INTO users (id, email, password, name, role, company, billing_entity, phone, is_active, organization_id, created_at)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1, $9, $10)",
            (
                user_id,
                CONTRACTOR_USER.email,
                _hash_password(CONTRACTOR_USER.password),
                CONTRACTOR_USER.name,
                CONTRACTOR_USER.role,
                CONTRACTOR_USER.company,
                CONTRACTOR_USER.billing_entity,
                "",
                org_id,
                now,
            ),
        )
        await conn.commit()
        logger.info("  Created user: %s (%s)", CONTRACTOR_USER.email, CONTRACTOR_USER.role)
        contractor = await _get_user_by_email(conn, CONTRACTOR_USER.email)

    return admin, contractor


async def seed_departments(org_id: str) -> dict:
    """Create standard departments. Returns dept_code -> dept object map."""
    from catalog.application.queries import (
        get_department_by_code,
        insert_department,
        list_departments,
    )
    from catalog.domain.department import Department

    for d in DEPARTMENTS:
        existing = await get_department_by_code(d.code)
        if not existing:
            dept = Department(name=d.name, code=d.code, description=d.description)
            dept_dict = dept.model_dump()
            dept_dict["organization_id"] = org_id
            await insert_department(dept_dict)
            logger.info("  Department: %s", d.name)

    all_depts = await list_departments()
    return {d.code: d for d in all_depts}


async def seed_vendors(org_id: str) -> list[str]:
    """Create vendors. Returns list of vendor IDs in VENDORS order."""
    from catalog.infrastructure.vendor_repo import insert as insert_vendor
    from shared.infrastructure.database import get_connection

    conn = get_connection()
    now = datetime.now(UTC).isoformat()
    vendor_ids = []
    for v in VENDORS:
        cursor = await conn.execute(
            "SELECT id FROM vendors WHERE name = $1 AND organization_id = $2", (v.name, org_id)
        )
        row = await cursor.fetchone()
        if row:
            vendor_ids.append(row[0])
            continue
        vid = str(uuid4())
        vendor_ids.append(vid)
        await insert_vendor(
            {
                "id": vid,
                "name": v.name,
                "contact_name": v.contact_name,
                "email": v.email,
                "phone": v.phone,
                "address": v.address,
                "created_at": now,
                "organization_id": org_id,
            }
        )
        logger.info("  Vendor: %s", v.name)
    return vendor_ids


async def seed_products(vendor_ids: list[str], dept_map: dict, admin: dict) -> dict:
    """Create products, SKUs, and vendor items. Returns name -> SKU map."""
    from catalog.application.sku_lifecycle import create_product_with_sku
    from catalog.application.vendor_item_lifecycle import add_vendor_item
    from inventory.application.inventory_service import process_import_stock_changes

    sku_map: dict = {}
    for p in PRODUCTS:
        dept = dept_map.get(p.dept)
        if not dept:
            logger.warning("  Skipping %s: dept %s not found", p.name, p.dept)
            continue
        vid = vendor_ids[p.vendor]
        vname = VENDORS[p.vendor].name

        if p.name in sku_map:
            existing_sku = sku_map[p.name]
            await add_vendor_item(
                sku_id=existing_sku.id,
                vendor_id=vid,
                vendor_sku=p.vendor_sku or None,
                purchase_uom=p.purchase_uom or p.unit,
                purchase_pack_qty=p.purchase_pack_qty,
                cost=p.cost,
                is_preferred=False,
            )
            logger.info("  + VendorItem: %s → %s (%s)", p.name, vname, p.vendor_sku)
            continue

        try:
            sku = await create_product_with_sku(
                category_id=dept.id,
                category_name=dept.name,
                name=p.name,
                price=p.price,
                cost=p.cost,
                quantity=p.qty,
                min_stock=p.min,
                base_unit=p.unit,
                sell_uom=p.unit,
                purchase_uom=p.purchase_uom or p.unit,
                purchase_pack_qty=p.purchase_pack_qty,
                user_id=admin["id"],
                user_name=admin.get("name", "Admin"),
                on_stock_import=process_import_stock_changes,
            )
            sku_map[p.name] = sku
            await add_vendor_item(
                sku_id=sku.id,
                vendor_id=vid,
                vendor_sku=p.vendor_sku or None,
                purchase_uom=p.purchase_uom or p.unit,
                purchase_pack_qty=p.purchase_pack_qty,
                cost=p.cost,
                is_preferred=True,
            )
            logger.info(
                "  %s | %s | qty=%d | %s (%s)",
                sku.sku,
                p.name,
                p.qty,
                vname,
                p.vendor_sku,
            )
        except (ValueError, RuntimeError, OSError) as e:
            logger.warning("  Skip %s: %s", p.name, e)

    return sku_map


async def seed_withdrawals(
    conn, org_id: str, sku_map: dict, admin: dict, contractor: dict
) -> list[str]:
    """Create material withdrawals. Returns list of withdrawal IDs."""
    from operations.domain.withdrawal import MaterialWithdrawal, WithdrawalItem
    from operations.infrastructure.withdrawal_repo import withdrawal_repo

    now = datetime.now(UTC)
    withdrawal_ids = []

    for scenario in WITHDRAWAL_SCENARIOS:
        items = []
        for wi in scenario.items:
            sku = sku_map.get(wi.product_name)
            if not sku:
                logger.warning("  Withdrawal skip: SKU '%s' not found", wi.product_name)
                continue
            items.append(
                WithdrawalItem(
                    product_id=sku.id,
                    sku=sku.sku,
                    name=sku.name,
                    quantity=wi.quantity,
                    price=sku.price,
                    cost=sku.cost,
                    subtotal=round(sku.price * wi.quantity, 2),
                )
            )

        if not items:
            continue

        created_at = (now - timedelta(days=scenario.days_ago)).isoformat()
        withdrawal = MaterialWithdrawal(
            items=items,
            job_id=scenario.job_id,
            service_address=scenario.service_address,
            notes="",
            subtotal=0,
            tax=0,
            total=0,
            cost_total=0,
            contractor_id=contractor["id"],
            contractor_name=contractor.get("name", ""),
            contractor_company=contractor.get("company", ""),
            billing_entity=contractor.get("billing_entity", "Demo Co"),
            payment_status="unpaid",
            processed_by_id=admin["id"],
            processed_by_name=admin.get("name", ""),
        )
        withdrawal.compute_totals()
        withdrawal.organization_id = org_id
        withdrawal.created_at = created_at
        await withdrawal_repo.insert(withdrawal)
        withdrawal_ids.append(withdrawal.id)

        for item in items:
            await conn.execute(
                "UPDATE skus SET quantity = MAX(0, quantity - $1), updated_at = $2 WHERE id = $3",
                (item.quantity, created_at, item.product_id),
            )
        await conn.commit()

        item_summary = ", ".join(f"{i.name} x{i.quantity}" for i in items[:3])
        if len(items) > 3:
            item_summary += f" +{len(items) - 3} more"
        logger.info(
            "  %s @ %s | $%.2f | %s",
            scenario.job_id,
            scenario.service_address[:25],
            withdrawal.total,
            item_summary,
        )

    return withdrawal_ids


async def seed_invoices(now: datetime, org_id: str, withdrawal_ids: list[str]) -> None:
    """Create invoices for the first 4 withdrawals; mark first 2 as paid."""
    from finance.application.invoice_service import create_invoice_from_withdrawals
    from operations.infrastructure.withdrawal_repo import withdrawal_repo

    if len(withdrawal_ids) < 4:
        return

    for wid in withdrawal_ids[:4]:
        try:
            inv = await create_invoice_from_withdrawals([wid], organization_id=org_id)
            logger.info("  Invoice %s... for withdrawal %s...", inv["id"][:8], wid[:8])
        except (ValueError, RuntimeError, OSError) as e:
            logger.warning("  Invoice skip: %s", e)

    for wid in withdrawal_ids[:2]:
        try:
            paid_at = (now - timedelta(days=5)).isoformat()
            await withdrawal_repo.mark_paid(wid, paid_at)
            logger.info("  Marked withdrawal %s... as paid", wid[:8])
        except (ValueError, RuntimeError, OSError) as e:
            logger.warning("  Mark paid skip: %s", e)


async def seed_low_stock(conn, sku_map: dict) -> None:
    """Force a few SKUs below min_stock to trigger alerts."""
    for name in LOW_STOCK_NAMES:
        sku = sku_map.get(name)
        if sku:
            low_qty = _rng.randint(1, sku.min_stock)
            await conn.execute("UPDATE skus SET quantity = $1 WHERE id = $2", (low_qty, sku.id))
            logger.info("  %s | %s → qty=%d (min=%d)", sku.sku, name, low_qty, sku.min_stock)
    await conn.commit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main(org_id_arg: str = "", org_name_arg: str = "") -> None:
    global _org
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

    from shared.infrastructure.database import get_connection, init_db
    from shared.infrastructure.logging_config import org_id_var

    if org_id_arg:
        _org = SeedOrg(id=org_id_arg, name=org_name_arg or org_id_arg, slug=org_id_arg)

    await init_db()

    org_id = _org.id
    conn = get_connection()

    cursor = await conn.execute("SELECT COUNT(*) FROM skus WHERE organization_id = $1", (org_id,))
    count = (await cursor.fetchone())[0]
    if count > 0:
        logger.info("Database already seeded (%d SKUs found) — nothing to do.", count)
        logger.info("To re-seed, drop and recreate the database first.")
        return

    token = org_id_var.set(org_id)
    try:
        logger.info("--- Creating organization ---")
        await seed_org(conn, org_id)

        logger.info("--- Creating users ---")
        admin, contractor = await seed_users(conn, org_id)

        logger.info("--- Creating departments ---")
        dept_map = await seed_departments(org_id)

        logger.info("--- Creating vendors ---")
        vendor_ids = await seed_vendors(org_id)

        logger.info("--- Creating products & SKUs ---")
        sku_map = await seed_products(vendor_ids, dept_map, admin)
        logger.info("  %d unique SKUs created", len(sku_map))

        logger.info("--- Creating withdrawals ---")
        withdrawal_ids = await seed_withdrawals(conn, org_id, sku_map, admin, contractor)

        logger.info("--- Creating invoices ---")
        now = datetime.now(UTC)
        await seed_invoices(now, org_id, withdrawal_ids)

        logger.info("--- Setting low-stock alerts ---")
        await seed_low_stock(conn, sku_map)

    finally:
        org_id_var.reset(token)

    cursor = await conn.execute("SELECT COUNT(*) FROM skus WHERE organization_id = $1", (org_id,))
    total_skus = (await cursor.fetchone())[0]
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE organization_id = $1", (org_id,)
    )
    total_products = (await cursor.fetchone())[0]
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM vendor_items WHERE organization_id = $1", (org_id,)
    )
    total_vendor_items = (await cursor.fetchone())[0]
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM vendors WHERE organization_id = $1", (org_id,)
    )
    total_vendors = (await cursor.fetchone())[0]
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM withdrawals WHERE organization_id = $1", (org_id,)
    )
    total_withdrawals = (await cursor.fetchone())[0]
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM invoices WHERE organization_id = $1", (org_id,)
    )
    total_invoices = (await cursor.fetchone())[0]

    logger.info("\n=== SEED COMPLETE ===")
    logger.info("  %d vendors", total_vendors)
    logger.info(
        "  %d products (parent), %d SKUs, %d vendor items",
        total_products,
        total_skus,
        total_vendor_items,
    )
    logger.info("  %d withdrawals", total_withdrawals)
    logger.info("  %d invoices", total_invoices)
    logger.info("  Login: %s / %s", ADMIN_USER.email, ADMIN_USER.password)
    logger.info("  Login: %s / %s", CONTRACTOR_USER.email, CONTRACTOR_USER.password)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed realistic demo data")
    parser.add_argument("--org-id", default="", help="Organization ID (default: 'default')")
    parser.add_argument(
        "--org-name", default="", help="Organization name (default: 'Demo Supply Yard')"
    )
    args = parser.parse_args()
    asyncio.run(main(org_id_arg=args.org_id, org_name_arg=args.org_name))
