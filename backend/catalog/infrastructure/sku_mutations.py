"""SKU write/mutation operations."""

from datetime import UTC, datetime

from catalog.domain.product import Sku
from catalog.infrastructure.sku_repo import get_by_id
from shared.infrastructure.database import get_connection, get_org_id


async def insert(sku: Sku) -> None:
    sku_dict = sku.model_dump()
    conn = get_connection()
    org_id = sku_dict.get("organization_id") or get_org_id()
    await conn.execute(
        """INSERT INTO skus (id, sku, product_id, name, description, price, cost, quantity, min_stock,
           category_id, category_name, barcode, vendor_barcode,
           base_unit, sell_uom, pack_qty, purchase_uom, purchase_pack_qty,
           organization_id, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)""",
        (
            sku_dict["id"],
            sku_dict["sku"],
            sku_dict["product_id"],
            sku_dict["name"],
            sku_dict.get("description", ""),
            sku_dict["price"],
            sku_dict.get("cost", 0),
            sku_dict.get("quantity", 0),
            sku_dict.get("min_stock", 5),
            sku_dict["category_id"],
            sku_dict.get("category_name", ""),
            sku_dict.get("barcode"),
            sku_dict.get("vendor_barcode"),
            sku_dict.get("base_unit", "each"),
            sku_dict.get("sell_uom", "each"),
            sku_dict.get("pack_qty", 1),
            sku_dict.get("purchase_uom", "each"),
            sku_dict.get("purchase_pack_qty", 1),
            org_id,
            sku_dict.get("created_at", ""),
            sku_dict.get("updated_at", ""),
        ),
    )
    await conn.commit()


async def update(sku_id: str, updates: dict) -> Sku | None:
    conn = get_connection()
    org_id = get_org_id()
    n = 1
    set_parts = [f"updated_at = ${n}"]
    values = [updates.get("updated_at", "")]
    n += 1
    for key in (
        "name",
        "description",
        "price",
        "cost",
        "quantity",
        "min_stock",
        "category_id",
        "category_name",
        "product_id",
        "barcode",
        "vendor_barcode",
        "base_unit",
        "sell_uom",
        "pack_qty",
        "purchase_uom",
        "purchase_pack_qty",
    ):
        if key in updates and updates[key] is not None:
            set_parts.append(f"{key} = ${n}")
            values.append(updates[key])
            n += 1
    if len(set_parts) <= 1:
        return await get_by_id(sku_id)
    values.append(sku_id)
    where = f"WHERE id = ${n} AND organization_id = ${n + 1}"
    values.append(org_id)
    query = "UPDATE skus SET "
    query += ", ".join(set_parts)
    query += " " + where
    await conn.execute(query, values)
    await conn.commit()
    return await get_by_id(sku_id)


async def delete(sku_id: str) -> int:
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    params: list = [now, sku_id]
    where = "WHERE id = $2 AND deleted_at IS NULL AND organization_id = $3"
    params.append(org_id)
    query = "UPDATE skus SET deleted_at = $1 "
    query += where
    cursor = await conn.execute(query, params)
    await conn.commit()
    return cursor.rowcount


async def atomic_decrement(sku_id: str, quantity: float, updated_at: str) -> Sku | None:
    """Decrement quantity only if >= requested. Returns updated row or None if insufficient."""
    conn = get_connection()
    org_id = get_org_id()
    params: list = [quantity, updated_at, sku_id, quantity]
    where = "WHERE id = $3 AND quantity >= $4 AND organization_id = $5"
    params.append(org_id)
    query = "UPDATE skus SET quantity = quantity - $1, updated_at = $2 "
    query += where
    cursor = await conn.execute(query, params)
    await conn.commit()
    if cursor.rowcount == 0:
        return None
    return await get_by_id(sku_id)


async def increment_quantity(sku_id: str, quantity: float, updated_at: str) -> None:
    """Rollback: add quantity back."""
    conn = get_connection()
    org_id = get_org_id()
    params: list = [quantity, updated_at, sku_id]
    where = "WHERE id = $3 AND organization_id = $4"
    params.append(org_id)
    query = "UPDATE skus SET quantity = quantity + $1, updated_at = $2 "
    query += where
    await conn.execute(query, params)
    await conn.commit()


async def add_quantity(sku_id: str, quantity: float, updated_at: str) -> Sku | None:
    """Add quantity (receiving) and return updated row."""
    conn = get_connection()
    org_id = get_org_id()
    params: list = [quantity, updated_at, sku_id]
    where = "WHERE id = $3 AND organization_id = $4"
    params.append(org_id)
    query = "UPDATE skus SET quantity = quantity + $1, updated_at = $2 "
    query += where
    await conn.execute(query, params)
    await conn.commit()
    return await get_by_id(sku_id)


async def atomic_adjust(
    sku_id: str,
    quantity_delta: float,
    updated_at: str,
) -> Sku | None:
    """Atomically adjust quantity by delta (+ or -).
    Returns updated row or None if adjustment would result in negative stock.
    """
    conn = get_connection()
    org_id = get_org_id()
    params: list = [quantity_delta, updated_at, sku_id, quantity_delta]
    where = "WHERE id = $3 AND quantity + $4 >= 0 AND organization_id = $5"
    params.append(org_id)
    query = "UPDATE skus SET quantity = quantity + $1, updated_at = $2 "
    query += where
    cursor = await conn.execute(query, params)
    await conn.commit()
    if cursor.rowcount == 0:
        return None
    return await get_by_id(sku_id)
