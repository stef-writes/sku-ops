"""Product write/mutation operations."""

from datetime import UTC, datetime

from catalog.domain.product import Product
from catalog.infrastructure.product_repo import get_by_id
from shared.infrastructure.database import get_connection, get_org_id


async def insert(product: Product | dict) -> None:
    product_dict = product if isinstance(product, dict) else product.model_dump()
    conn = get_connection()
    org_id = product_dict.get("organization_id") or get_org_id()
    await conn.execute(
        """INSERT INTO products (id, sku, name, description, price, cost, quantity, min_stock,
           department_id, department_name, vendor_id, vendor_name, original_sku, barcode, vendor_barcode,
           base_unit, sell_uom, pack_qty, product_group, organization_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            product_dict["id"],
            product_dict["sku"],
            product_dict["name"],
            product_dict.get("description", ""),
            product_dict["price"],
            product_dict.get("cost", 0),
            product_dict.get("quantity", 0),
            product_dict.get("min_stock", 5),
            product_dict["department_id"],
            product_dict.get("department_name", ""),
            product_dict.get("vendor_id") or "",
            product_dict.get("vendor_name", ""),
            product_dict.get("original_sku"),
            product_dict.get("barcode"),
            product_dict.get("vendor_barcode"),
            product_dict.get("base_unit", "each"),
            product_dict.get("sell_uom", "each"),
            product_dict.get("pack_qty", 1),
            product_dict.get("product_group"),
            org_id,
            product_dict.get("created_at", ""),
            product_dict.get("updated_at", ""),
        ),
    )
    await conn.commit()


async def update(product_id: str, updates: dict) -> Product | None:
    conn = get_connection()
    org_id = get_org_id()
    set_parts = ["updated_at = ?"]
    values = [updates.get("updated_at", "")]
    for key in (
        "name",
        "description",
        "price",
        "cost",
        "quantity",
        "min_stock",
        "department_id",
        "department_name",
        "vendor_id",
        "vendor_name",
        "barcode",
        "vendor_barcode",
        "base_unit",
        "sell_uom",
        "pack_qty",
        "original_sku",
        "product_group",
    ):
        if key in updates and updates[key] is not None:
            set_parts.append(f"{key} = ?")
            values.append(updates[key])
    if "vendor_id" in updates and updates["vendor_id"] is None:
        set_parts.append("vendor_id = NULL")
        set_parts.append("vendor_name = ?")
        values.append("")
    if "product_group" in updates and updates["product_group"] is None:
        set_parts.append("product_group = NULL")
    if len(set_parts) <= 1:
        return await get_by_id(product_id)
    values.append(product_id)
    where = "WHERE id = ? AND organization_id = ?"
    values.append(org_id)
    query = "UPDATE products SET "
    query += ", ".join(set_parts)
    query += " " + where
    await conn.execute(query, values)
    await conn.commit()
    return await get_by_id(product_id)


async def delete(product_id: str) -> int:
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    params: list = [now, product_id]
    where = "WHERE id = ? AND deleted_at IS NULL AND organization_id = ?"
    params.append(org_id)
    query = "UPDATE products SET deleted_at = ? "
    query += where
    cursor = await conn.execute(query, params)
    await conn.commit()
    return cursor.rowcount


async def atomic_decrement(product_id: str, quantity: float, updated_at: str) -> Product | None:
    """Decrement quantity only if >= requested. Returns updated row or None if insufficient."""
    conn = get_connection()
    org_id = get_org_id()
    params: list = [quantity, updated_at, product_id, quantity]
    where = "WHERE id = ? AND quantity >= ? AND organization_id = ?"
    params.append(org_id)
    query = "UPDATE products SET quantity = quantity - ?, updated_at = ? "
    query += where
    cursor = await conn.execute(query, params)
    await conn.commit()
    if cursor.rowcount == 0:
        return None
    return await get_by_id(product_id)


async def increment_quantity(product_id: str, quantity: float, updated_at: str) -> None:
    """Rollback: add quantity back."""
    conn = get_connection()
    org_id = get_org_id()
    params: list = [quantity, updated_at, product_id]
    where = "WHERE id = ? AND organization_id = ?"
    params.append(org_id)
    query = "UPDATE products SET quantity = quantity + ?, updated_at = ? "
    query += where
    await conn.execute(query, params)
    await conn.commit()


async def add_quantity(product_id: str, quantity: float, updated_at: str) -> Product | None:
    """Add quantity (receiving) and return updated row."""
    conn = get_connection()
    org_id = get_org_id()
    params: list = [quantity, updated_at, product_id]
    where = "WHERE id = ? AND organization_id = ?"
    params.append(org_id)
    query = "UPDATE products SET quantity = quantity + ?, updated_at = ? "
    query += where
    await conn.execute(query, params)
    await conn.commit()
    return await get_by_id(product_id)


async def atomic_adjust(
    product_id: str,
    quantity_delta: float,
    updated_at: str,
) -> Product | None:
    """Atomically adjust quantity by delta (+ or -).
    Returns updated row or None if adjustment would result in negative stock.
    """
    conn = get_connection()
    org_id = get_org_id()
    params: list = [quantity_delta, updated_at, product_id, quantity_delta]
    where = "WHERE id = ? AND quantity + ? >= 0 AND organization_id = ?"
    params.append(org_id)
    query = "UPDATE products SET quantity = quantity + ?, updated_at = ? "
    query += where
    cursor = await conn.execute(query, params)
    await conn.commit()
    if cursor.rowcount == 0:
        return None
    return await get_by_id(product_id)
