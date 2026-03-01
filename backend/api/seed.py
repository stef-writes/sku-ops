"""Seed data routes and helpers."""
import os

from fastapi import APIRouter, Depends, HTTPException

from auth import hash_password, require_role
from db import get_connection
from models import Department, User
from repositories import department_repo, product_repo, user_repo
from services.document_import import infer_uom, parse_csv_products, suggest_department
from services.product_lifecycle import create_product as lifecycle_create

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/seed", tags=["seed"])

MOCK_USER_EMAIL = "admin@demo.local"
MOCK_USER_PASSWORD = "demo123"
DEMO_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "SY Inventory - Sheet1 (1).csv")
DEMO_PRODUCT_LIMIT = 2000


async def seed_standard_departments() -> None:
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
        if not await department_repo.get_by_code(d["code"]):
            await department_repo.insert(Department(**d).model_dump())


async def seed_demo_inventory() -> None:
    """Seed ~150 products from CSV on first run for full demo experience."""
    try:
        count = await product_repo.count_all()
        if count > 0:
            return
        if not os.path.exists(DEMO_CSV_PATH):
            logger.warning(f"Demo CSV not found: {DEMO_CSV_PATH}")
            return

        await seed_standard_departments()
        demo_user = await user_repo.get_by_email(MOCK_USER_EMAIL)
        if not demo_user:
            logger.warning("Demo user not found, skipping inventory seed")
            return

        with open(DEMO_CSV_PATH, "rb") as f:
            content = f.read()
        rows = parse_csv_products(content)
        all_depts = await department_repo.list_all()
        dept_by_code = {d["code"]: d for d in all_depts}

        imported = 0
        for i, item in enumerate(rows):
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

                product = await lifecycle_create(
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
                )
                imported += 1
            except Exception as e:
                logger.debug(f"Demo seed skip {item.get('name')}: {e}")

        logger.info(f"Demo inventory seeded: {imported} products")
    except Exception as e:
        logger.warning(f"Demo inventory seed: {e}")


async def seed_mock_user():
    """Create a demo admin user if none exists."""
    try:
        existing = await user_repo.get_by_email(MOCK_USER_EMAIL)
        if not existing:
            user = User(
                email=MOCK_USER_EMAIL,
                name="Demo Admin",
                role="admin",
            )
            user_dict = user.model_dump()
            user_dict["password"] = hash_password(MOCK_USER_PASSWORD)
            await user_repo.insert(user_dict)
            logger.info(f"Mock user created: {MOCK_USER_EMAIL}")
    except Exception as e:
        logger.warning(f"Mock user seed: {e}")


@router.post("/departments")
async def seed_departments():
    await seed_standard_departments()
    return {"message": "Departments ready"}


@router.post("/reset-inventory")
async def reset_and_reseed_inventory(current_user: dict = Depends(require_role("admin"))):
    """Reset products and stock, then re-run demo seed. For assessment with fresh data."""
    conn = get_connection()
    try:
        await conn.execute("DELETE FROM stock_transactions")
        await conn.execute("DELETE FROM products")
        await conn.execute("DELETE FROM sku_counters")
        await conn.execute("UPDATE departments SET product_count = 0")
        await conn.execute("UPDATE vendors SET product_count = 0")
        await conn.commit()
        logger.info("Inventory reset complete")
        await seed_demo_inventory()
        count = await product_repo.count_all()
        return {"message": f"Inventory reset and reseeded with {count} products"}
    except Exception as e:
        logger.error(f"Reset inventory failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
