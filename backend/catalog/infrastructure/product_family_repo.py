"""Product (parent concept) repository."""

from datetime import UTC, datetime

from catalog.domain.product_family import Product
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_product(row) -> Product | None:
    if row is None:
        return None
    d = dict(row)
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return Product.model_validate(d)


async def insert(product: Product) -> None:
    p = product.model_dump()
    conn = get_connection()
    org_id = p.get("organization_id") or get_org_id()
    await conn.execute(
        """INSERT INTO products (id, name, description, category_id, category_name,
           sku_count, organization_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            p["id"],
            p["name"],
            p.get("description", ""),
            p["category_id"],
            p.get("category_name", ""),
            p.get("sku_count", 0),
            org_id,
            p.get("created_at", ""),
            p.get("updated_at", ""),
        ),
    )
    await conn.commit()


async def get_by_id(product_id: str) -> Product | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM products WHERE id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (product_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_product(row)


async def list_all(
    category_id: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Product]:
    conn = get_connection()
    org_id = get_org_id()
    base = "SELECT * FROM products WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL"
    params: list = [org_id]
    if category_id:
        base += " AND category_id = ?"
        params.append(category_id)
    if search:
        base += " AND name LIKE ?"
        params.append(f"%{search}%")
    base += " ORDER BY name"
    if limit is not None:
        base += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    cursor = await conn.execute(base, params)
    rows = await cursor.fetchall()
    return [p for r in rows if (p := _row_to_product(r)) is not None]


async def count(
    category_id: str | None = None,
    search: str | None = None,
) -> int:
    conn = get_connection()
    org_id = get_org_id()
    query = "SELECT COUNT(*) FROM products WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL"
    params: list = [org_id]
    if category_id:
        query += " AND category_id = ?"
        params.append(category_id)
    if search:
        query += " AND name LIKE ?"
        params.append(f"%{search}%")
    cursor = await conn.execute(query, params)
    row = await cursor.fetchone()
    return row[0] if row else 0


async def update(product_id: str, updates: dict) -> Product | None:
    conn = get_connection()
    org_id = get_org_id()
    set_parts = ["updated_at = ?"]
    values: list = [updates.get("updated_at", datetime.now(UTC).isoformat())]
    for key in ("name", "description", "category_id", "category_name"):
        if key in updates and updates[key] is not None:
            set_parts.append(f"{key} = ?")
            values.append(updates[key])
    if len(set_parts) <= 1:
        return await get_by_id(product_id)
    values.append(product_id)
    values.append(org_id)
    query = f"UPDATE products SET {', '.join(set_parts)} WHERE id = ? AND organization_id = ?"
    await conn.execute(query, values)
    await conn.commit()
    return await get_by_id(product_id)


async def soft_delete(product_id: str) -> int:
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    cursor = await conn.execute(
        "UPDATE products SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL AND organization_id = ?",
        (now, product_id, org_id),
    )
    await conn.commit()
    return cursor.rowcount


async def increment_sku_count(product_id: str, delta: int) -> None:
    conn = get_connection()
    org_id = get_org_id()
    await conn.execute(
        "UPDATE products SET sku_count = sku_count + ? WHERE id = ? AND organization_id = ?",
        (delta, product_id, org_id),
    )
    await conn.commit()


class ProductFamilyRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_all = staticmethod(list_all)
    count = staticmethod(count)
    update = staticmethod(update)
    soft_delete = staticmethod(soft_delete)
    increment_sku_count = staticmethod(increment_sku_count)


product_family_repo = ProductFamilyRepo()
