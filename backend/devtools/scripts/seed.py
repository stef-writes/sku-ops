"""
Seed logic: demo users, departments, inventory.
Lives in scripts/ to avoid cross-domain imports inside identity/.
"""
import os
import logging
from datetime import datetime, timezone
from uuid import uuid4

from identity.application.auth_service import hash_password
from shared.infrastructure.config import (
    DEMO_USER_EMAIL as MOCK_USER_EMAIL,
    DEMO_USER_PASSWORD as MOCK_USER_PASSWORD,
)
from catalog.domain.department import Department
from catalog.application.queries import (
    list_departments, get_department_by_code, insert_department, count_all_products,
)
from identity.infrastructure.org_repo import organization_repo
from identity.infrastructure.user_repo import user_repo
from documents.application.import_parser import infer_uom, parse_csv_products, suggest_department
from catalog.application.product_lifecycle import create_product as lifecycle_create
from inventory.application.inventory_service import process_import_stock_changes

logger = logging.getLogger(__name__)

DEMO_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "SY Inventory - Sheet1 (1).csv")
DEMO_PRODUCT_LIMIT = 2000
DEMO_PRODUCT_PER_ORG = 80

DEMO_TENANTS = [
    {"id": "north", "name": "Supply Yard North", "slug": "north"},
    {"id": "south", "name": "Supply Yard South", "slug": "south"},
]
DEMO_USERS_PER_ORG = [
    {"email": "admin@{slug}.demo", "name": "Admin", "role": "admin"},
    {"email": "wm@{slug}.demo", "name": "Warehouse Manager", "role": "warehouse_manager"},
    {"email": "contractor@{slug}.demo", "name": "Contractor", "role": "contractor"},
]
DEMO_CONTRACTOR_EMAIL = "contractor@demo.local"


async def seed_standard_departments(organization_id: str = "default") -> None:
    """Seed standard departments if not present."""
    standard = [
        {"name": "Lumber", "code": "LUM", "description": "Wood, plywood, boards"},
        {"name": "Plumbing", "code": "PLU", "description": "Pipes, fittings, fixtures"},
        {"name": "Electrical", "code": "ELE", "description": "Wiring, outlets, switches"},
        {"name": "Paint", "code": "PNT", "description": "Paint, stains, brushes"},
        {"name": "Tools", "code": "TOL", "description": "Hand tools, power tools"},
        {"name": "Hardware", "code": "HDW", "description": "Fasteners, hinges, locks"},
        {"name": "Garden", "code": "GDN", "description": "Plants, soil, fertilizers"},
        {"name": "Appliances", "code": "APP", "description": "Home appliances"},
    ]
    for d in standard:
        if not await get_department_by_code(d["code"], organization_id):
            dept = Department(name=d["name"], code=d["code"], description=d.get("description", ""))
            d_dict = dept.model_dump()
            d_dict["organization_id"] = organization_id
            await insert_department(d_dict)


async def seed_demo_inventory(organization_id: str = "default") -> None:
    """Seed ~150 products from CSV on first run for full demo experience."""
    if not MOCK_USER_EMAIL:
        return
    try:
        count = await count_all_products(organization_id)
        if count > 0:
            return
        if not os.path.exists(DEMO_CSV_PATH):
            logger.warning(f"Demo CSV not found: {DEMO_CSV_PATH}")
            return

        await seed_standard_departments(organization_id)
        demo_user = await user_repo.get_by_email(MOCK_USER_EMAIL)
        if not demo_user:
            logger.warning("Demo user not found, skipping inventory seed")
            return

        with open(DEMO_CSV_PATH, "rb") as f:
            content = f.read()
        rows = parse_csv_products(content)
        all_depts = await list_departments(organization_id)
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
                    dept = next((d for d in all_depts if d["code"] == key or d["name"].lower() == raw.lower()), None)
                if not dept:
                    suggested = suggest_department(item["name"], dept_by_code)
                    dept = dept_by_code.get(suggested) if suggested else None
                if not dept:
                    dept = all_depts[0]

                bu, su, pq = infer_uom(item["name"])

                await lifecycle_create(
                    department_id=dept["id"],
                    department_name=dept["name"],
                    name=item["name"],
                    description="",
                    price=item["price"],
                    cost=item["cost"],
                    quantity=item["quantity"],
                    min_stock=max(5, item["min_stock"]),
                    vendor_id=None,
                    vendor_name="",
                    original_sku=item.get("original_sku"),
                    barcode=item.get("barcode"),
                    base_unit=bu,
                    sell_uom=su,
                    pack_qty=pq,
                    user_id=demo_user["id"],
                    user_name=demo_user.get("name", "Demo"),
                    organization_id=organization_id,
                    on_stock_import=process_import_stock_changes,
                )
                imported += 1
            except Exception as e:
                logger.debug(f"Demo seed skip {item.get('name')}: {e}")

        logger.info(f"Demo inventory seeded: {imported} products")
    except Exception as e:
        logger.warning(f"Demo inventory seed: {e}")


async def seed_mock_user(organization_id: str = "default"):
    """Create demo admin and contractor users if none exist."""
    if not MOCK_USER_EMAIL:
        return
    try:
        existing = await user_repo.get_by_email(MOCK_USER_EMAIL)
        if not existing:
            from identity.domain.user import User
            user = User(email=MOCK_USER_EMAIL, name="Demo Admin", role="admin")
            user_dict = user.model_dump()
            user_dict["password"] = hash_password(MOCK_USER_PASSWORD)
            user_dict["organization_id"] = organization_id
            await user_repo.insert(user_dict)
            logger.info(f"Mock user created: {MOCK_USER_EMAIL}")

        existing_contractor = await user_repo.get_by_email(DEMO_CONTRACTOR_EMAIL)
        if not existing_contractor:
            from identity.domain.user import User
            contractor = User(
                email=DEMO_CONTRACTOR_EMAIL,
                name="Demo Contractor",
                role="contractor",
                company="Demo Co",
                billing_entity="Demo Co",
            )
            contractor_dict = contractor.model_dump()
            contractor_dict["password"] = hash_password(MOCK_USER_PASSWORD)
            contractor_dict["organization_id"] = organization_id
            await user_repo.insert(contractor_dict)
            logger.info(f"Demo contractor created: {DEMO_CONTRACTOR_EMAIL}")
    except Exception as e:
        logger.warning(f"Mock user seed: {e}")


async def seed_demo_tenants() -> None:
    """Seed multi-tenant demo: North + South orgs with users, departments, products."""
    try:
        existing = await organization_repo.get_by_slug("north")
        if existing:
            logger.info("Demo tenants already exist, skipping")
            return

        if not os.path.exists(DEMO_CSV_PATH):
            logger.warning(f"Demo CSV not found: {DEMO_CSV_PATH}, skipping product seed")

        now = datetime.now(timezone.utc).isoformat()
        rows = parse_csv_products(open(DEMO_CSV_PATH, "rb").read()) if os.path.exists(DEMO_CSV_PATH) else []

        for org in DEMO_TENANTS:
            org_id = org["id"]
            await organization_repo.insert({
                "id": org_id,
                "name": org["name"],
                "slug": org["slug"],
                "created_at": now,
            })
            logger.info(f"Created org: {org['name']}")

            await seed_standard_departments(org_id)

            for u in DEMO_USERS_PER_ORG:
                email = u["email"].format(slug=org["slug"])
                existing_user = await user_repo.get_by_email(email)
                if not existing_user:
                    user_dict = {
                        "id": str(uuid4()),
                        "email": email,
                        "password": hash_password("demo123"),
                        "name": u["name"],
                        "role": u["role"],
                        "organization_id": org_id,
                        "created_at": now,
                    }
                    await user_repo.insert(user_dict)
                    logger.info(f"Created user: {email}")

            admin_user = await user_repo.get_by_email(f"admin@{org['slug']}.demo")
            if admin_user and rows:
                all_depts = await list_departments(org_id)
                dept_by_code = {d["code"]: d for d in all_depts}
                imported = 0
                for item in rows:
                    if imported >= DEMO_PRODUCT_PER_ORG:
                        break
                    try:
                        suggested = suggest_department(item["name"], dept_by_code) if dept_by_code else None
                        dept = dept_by_code.get(suggested) if suggested else (all_depts[0] if all_depts else None)
                        if not dept:
                            dept = all_depts[0]
                        bu, su, pq = infer_uom(item["name"])
                        await lifecycle_create(
                            department_id=dept["id"],
                            department_name=dept["name"],
                            name=item["name"],
                            description="",
                            price=item["price"],
                            cost=item["cost"],
                            quantity=item["quantity"],
                            min_stock=max(5, item["min_stock"]),
                            vendor_id=None,
                            vendor_name="",
                            original_sku=item.get("original_sku"),
                            barcode=item.get("barcode"),
                            base_unit=bu,
                            sell_uom=su,
                            pack_qty=pq,
                            user_id=admin_user["id"],
                            user_name=admin_user.get("name", "Admin"),
                            organization_id=org_id,
                            on_stock_import=process_import_stock_changes,
                        )
                        imported += 1
                    except Exception as e:
                        logger.debug(f"Demo product skip {item.get('name')}: {e}")
                logger.info(f"Seeded {imported} products for {org['name']}")

        logger.info("Demo tenants seeded successfully")
    except Exception as e:
        logger.warning(f"Demo tenants seed: {e}")
