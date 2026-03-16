"""
Seed helpers: departments, users, and CSV-based inventory import.

Used by devtools/api/seed.py for HTTP reset/seed endpoints.
"""

import logging
import os
from datetime import UTC, datetime
from uuid import uuid4

import bcrypt

from catalog.application.queries import (
    count_all_skus,
    get_department_by_code,
    insert_department,
    list_departments,
)
from catalog.application.sku_lifecycle import create_product_with_sku as lifecycle_create
from catalog.domain.department import Department
from devtools.scripts.seed_data import (
    ADMIN_USER,
    CONTRACTOR_USER,
    DEPARTMENTS,
    TENANT_USERS,
    TENANTS,
)
from documents.application.import_parser import infer_uom, parse_csv_products, suggest_department
from inventory.application.inventory_service import process_import_stock_changes
from shared.infrastructure.database import get_connection
from shared.infrastructure.logging_config import org_id_var
from shared.infrastructure.org_repo import organization_repo

logger = logging.getLogger(__name__)

DEMO_USER_EMAIL = ADMIN_USER.email
DEMO_USER_PASSWORD = ADMIN_USER.password

DEMO_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "SY Inventory - Enhanced.csv")
DEMO_PRODUCT_LIMIT = 2000
DEMO_PRODUCT_PER_ORG = 80


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def _get_user_by_email(email: str) -> dict | None:
    conn = get_connection()
    cursor = await conn.execute("SELECT * FROM users WHERE email = $1", (email,))
    row = await cursor.fetchone()
    return dict(row) if row and hasattr(row, "keys") else None


async def _insert_user(user_dict: dict) -> None:
    conn = get_connection()
    await conn.execute(
        "INSERT INTO users (id, email, password, name, role, company, billing_entity, phone, is_active, organization_id, created_at)"
        " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1, $9, $10)",
        (
            user_dict["id"],
            user_dict["email"],
            user_dict["password"],
            user_dict["name"],
            user_dict.get("role", "admin"),
            user_dict.get("company", ""),
            user_dict.get("billing_entity", ""),
            user_dict.get("phone", ""),
            user_dict.get("organization_id", "default"),
            user_dict.get("created_at", datetime.now(UTC).isoformat()),
        ),
    )
    await conn.commit()


async def seed_standard_departments(organization_id: str = "default") -> None:
    """Create standard departments if not already present."""
    for d in DEPARTMENTS:
        if not await get_department_by_code(d.code):
            dept = Department(name=d.name, code=d.code, description=d.description)
            d_dict = dept.model_dump()
            d_dict["organization_id"] = organization_id
            await insert_department(d_dict)


async def seed_demo_inventory(organization_id: str = "default") -> None:
    """Seed products from CSV for a full demo experience."""
    try:
        org_id_var.set(organization_id)
        count = await count_all_skus()
        if count > 0:
            return
        if not os.path.exists(DEMO_CSV_PATH):
            logger.warning("Demo CSV not found: %s", DEMO_CSV_PATH)
            return

        await seed_standard_departments(organization_id)
        demo_user = await _get_user_by_email(DEMO_USER_EMAIL)
        if not demo_user:
            logger.warning("Demo user not found, skipping inventory seed")
            return

        with open(DEMO_CSV_PATH, "rb") as f:
            content = f.read()
        rows = parse_csv_products(content)
        all_depts_raw = await list_departments()
        all_depts = [d.model_dump() if hasattr(d, "model_dump") else d for d in all_depts_raw]
        dept_by_code = {d["code"]: d for d in all_depts}

        imported = 0
        for item in rows:
            if imported >= DEMO_PRODUCT_LIMIT:
                break
            try:
                dept = None
                if item.get("department"):
                    raw = item["department"].strip()
                    key = raw.upper()[:3] if len(raw) >= 3 else raw.lower()
                    dept = next(
                        (
                            d
                            for d in all_depts
                            if d["code"] == key or d["name"].lower() == raw.lower()
                        ),
                        None,
                    )
                if not dept:
                    suggested = suggest_department(item["name"], dept_by_code)
                    dept = dept_by_code.get(suggested) if suggested else None
                if not dept:
                    dept = all_depts[0]

                bu, su, pq = infer_uom(item["name"])
                await lifecycle_create(
                    category_id=dept["id"],
                    category_name=dept["name"],
                    name=item["name"],
                    description="",
                    price=item["price"],
                    cost=item["cost"],
                    quantity=item["quantity"],
                    min_stock=max(5, item["min_stock"]),
                    barcode=item.get("barcode"),
                    base_unit=bu,
                    sell_uom=su,
                    pack_qty=pq,
                    user_id=demo_user["id"],
                    user_name=demo_user.get("name", "Demo"),
                    on_stock_import=process_import_stock_changes,
                )
                imported += 1
            except (ValueError, RuntimeError, OSError, KeyError) as e:
                logger.debug("Demo seed skip %s: %s", item.get("name"), e)

        logger.info("Demo inventory seeded: %d products", imported)
    except (ValueError, RuntimeError, OSError) as e:
        logger.warning("Demo inventory seed: %s", e)


async def seed_mock_user(organization_id: str = "default") -> None:
    """Create admin and contractor demo users if they don't exist."""
    try:
        if not await _get_user_by_email(ADMIN_USER.email):
            await _insert_user(
                {
                    "id": str(uuid4()),
                    "email": ADMIN_USER.email,
                    "password": hash_password(ADMIN_USER.password),
                    "name": ADMIN_USER.name,
                    "role": ADMIN_USER.role,
                    "organization_id": organization_id,
                }
            )
            logger.info("Created user: %s", ADMIN_USER.email)

        if not await _get_user_by_email(CONTRACTOR_USER.email):
            await _insert_user(
                {
                    "id": str(uuid4()),
                    "email": CONTRACTOR_USER.email,
                    "password": hash_password(CONTRACTOR_USER.password),
                    "name": CONTRACTOR_USER.name,
                    "role": CONTRACTOR_USER.role,
                    "company": CONTRACTOR_USER.company,
                    "billing_entity": CONTRACTOR_USER.billing_entity,
                    "organization_id": organization_id,
                }
            )
            logger.info("Created user: %s", CONTRACTOR_USER.email)
    except (ValueError, RuntimeError, OSError) as e:
        logger.warning("Mock user seed: %s", e)


async def seed_demo_tenants() -> None:
    """Seed multi-tenant demo: North + South orgs with users, departments, products."""
    try:
        existing = await organization_repo.get_by_slug(TENANTS[0].slug)
        if existing:
            logger.info("Demo tenants already exist, skipping")
            return

        if not os.path.exists(DEMO_CSV_PATH):
            logger.warning("Demo CSV not found: %s, skipping product seed", DEMO_CSV_PATH)

        now = datetime.now(UTC).isoformat()
        if os.path.exists(DEMO_CSV_PATH):
            with open(DEMO_CSV_PATH, "rb") as f:
                rows = parse_csv_products(f.read())
        else:
            rows = []

        for tenant in TENANTS:
            await organization_repo.insert(
                {
                    "id": tenant.id,
                    "name": tenant.name,
                    "slug": tenant.slug,
                    "created_at": now,
                }
            )
            logger.info("Created org: %s", tenant.name)

            await seed_standard_departments(tenant.id)

            for u in TENANT_USERS:
                email = u.email.format(slug=tenant.slug)
                if not await _get_user_by_email(email):
                    await _insert_user(
                        {
                            "id": str(uuid4()),
                            "email": email,
                            "password": hash_password("demo123"),
                            "name": u.name,
                            "role": u.role,
                            "organization_id": tenant.id,
                            "created_at": now,
                        }
                    )
                    logger.info("Created user: %s", email)

            admin_user = await _get_user_by_email(f"admin@{tenant.slug}.demo")
            if admin_user and rows:
                org_id_var.set(tenant.id)
                all_depts_raw = await list_departments()
                all_depts = [
                    d.model_dump() if hasattr(d, "model_dump") else d for d in all_depts_raw
                ]
                dept_by_code = {d["code"]: d for d in all_depts}
                imported = 0
                for item in rows:
                    if imported >= DEMO_PRODUCT_PER_ORG:
                        break
                    try:
                        suggested = (
                            suggest_department(item["name"], dept_by_code) if dept_by_code else None
                        )
                        dept = (
                            dept_by_code.get(suggested)
                            if suggested
                            else (all_depts[0] if all_depts else None)
                        )
                        if not dept:
                            dept = all_depts[0]
                        bu, su, pq = infer_uom(item["name"])
                        await lifecycle_create(
                            category_id=dept["id"],
                            category_name=dept["name"],
                            name=item["name"],
                            description="",
                            price=item["price"],
                            cost=item["cost"],
                            quantity=item["quantity"],
                            min_stock=max(5, item["min_stock"]),
                            barcode=item.get("barcode"),
                            base_unit=bu,
                            sell_uom=su,
                            pack_qty=pq,
                            user_id=admin_user["id"],
                            user_name=admin_user.get("name", "Admin"),
                            on_stock_import=process_import_stock_changes,
                        )
                        imported += 1
                    except (ValueError, RuntimeError, OSError, KeyError) as e:
                        logger.debug("Demo product skip %s: %s", item.get("name"), e)
                logger.info("Seeded %d products for %s", imported, tenant.name)

        logger.info("Demo tenants seeded successfully")
    except (ValueError, RuntimeError, OSError) as e:
        logger.warning("Demo tenants seed: %s", e)
