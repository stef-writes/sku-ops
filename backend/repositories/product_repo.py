"""Product repository."""
import json
from typing import Optional

from db import get_connection


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if d and "quantity" in d:
        d["quantity"] = int(d["quantity"])
    if d and "min_stock" in d:
        d["min_stock"] = int(d["min_stock"])
    return d


async def list_products(
    department_id: Optional[str] = None,
    search: Optional[str] = None,
    low_stock: bool = False,
) -> list:
    conn = get_connection()
    query = "SELECT * FROM products WHERE 1=1"
    params: list = []
    if department_id:
        query += " AND department_id = ?"
        params.append(department_id)
    if search:
        query += " AND (name LIKE ? OR sku LIKE ? OR barcode LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
    if low_stock:
        query += " AND quantity <= min_stock"
    query += " ORDER BY name"
    cursor = await conn.execute(query, params)
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_by_id(product_id: str, columns: Optional[str] = "*") -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        f"SELECT {columns} FROM products WHERE id = ?",
        (product_id,),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def insert(product_dict: dict) -> None:
    conn = get_connection()
    await conn.execute(
        """INSERT INTO products (id, sku, name, description, price, cost, quantity, min_stock,
           department_id, department_name, vendor_id, vendor_name, original_sku, barcode,
           base_unit, sell_uom, pack_qty, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            product_dict.get("base_unit", "each"),
            product_dict.get("sell_uom", "each"),
            product_dict.get("pack_qty", 1),
            product_dict.get("created_at", ""),
            product_dict.get("updated_at", ""),
        ),
    )
    await conn.commit()


async def update(product_id: str, updates: dict) -> Optional[dict]:
    conn = get_connection()
    set_parts = ["updated_at = ?"]
    values = [updates.get("updated_at", "")]
    for key in ("name", "description", "price", "cost", "quantity", "min_stock",
                 "department_id", "department_name", "vendor_id", "vendor_name", "barcode",
                 "base_unit", "sell_uom", "pack_qty"):
        if key in updates and updates[key] is not None:
            set_parts.append(f"{key} = ?")
            values.append(updates[key])
    if "vendor_id" in updates and updates["vendor_id"] is None:
        set_parts.append("vendor_id = NULL")
        set_parts.append("vendor_name = ?")
        values.append("")
    if len(set_parts) <= 1:
        return await get_by_id(product_id)
    values.append(product_id)
    await conn.execute(
        f"UPDATE products SET {', '.join(set_parts)} WHERE id = ?",
        values,
    )
    await conn.commit()
    return await get_by_id(product_id)


async def delete(product_id: str) -> int:
    conn = get_connection()
    cursor = await conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    await conn.commit()
    return cursor.rowcount


async def atomic_decrement(product_id: str, quantity: int, updated_at: str) -> Optional[dict]:
    """Decrement quantity only if >= requested. Returns updated row or None if insufficient."""
    conn = get_connection()
    cursor = await conn.execute(
        """UPDATE products SET quantity = quantity - ?, updated_at = ?
           WHERE id = ? AND quantity >= ?""",
        (quantity, updated_at, product_id, quantity),
    )
    await conn.commit()
    if cursor.rowcount == 0:
        return None
    return await get_by_id(product_id)


async def increment_quantity(product_id: str, quantity: int, updated_at: str) -> None:
    """Rollback: add quantity back."""
    conn = get_connection()
    await conn.execute(
        "UPDATE products SET quantity = quantity + ?, updated_at = ? WHERE id = ?",
        (quantity, updated_at, product_id),
    )
    await conn.commit()


async def add_quantity(product_id: str, quantity: int, updated_at: str) -> Optional[dict]:
    """Add quantity (receiving) and return updated row."""
    conn = get_connection()
    await conn.execute(
        "UPDATE products SET quantity = quantity + ?, updated_at = ? WHERE id = ?",
        (quantity, updated_at, product_id),
    )
    await conn.commit()
    return await get_by_id(product_id)


async def count_all() -> int:
    conn = get_connection()
    cursor = await conn.execute("SELECT COUNT(*) FROM products")
    row = await cursor.fetchone()
    return row[0] if row else 0


async def count_low_stock() -> int:
    conn = get_connection()
    cursor = await conn.execute("SELECT COUNT(*) FROM products WHERE quantity <= min_stock")
    row = await cursor.fetchone()
    return row[0] if row else 0


async def list_low_stock(limit: int = 10) -> list:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM products WHERE quantity <= min_stock ORDER BY quantity LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


class ProductRepo:
    list_products = staticmethod(list_products)
    get_by_id = staticmethod(get_by_id)
    insert = staticmethod(insert)
    update = staticmethod(update)
    delete = staticmethod(delete)
    atomic_decrement = staticmethod(atomic_decrement)
    increment_quantity = staticmethod(increment_quantity)
    add_quantity = staticmethod(add_quantity)
    count_all = staticmethod(count_all)
    count_low_stock = staticmethod(count_low_stock)
    list_low_stock = staticmethod(list_low_stock)


product_repo = ProductRepo()
