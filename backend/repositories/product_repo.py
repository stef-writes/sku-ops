"""Product repository."""
from typing import Optional

from db import get_connection

# Whitelist for get_by_id(columns=) to prevent SQL injection
_PRODUCT_COLUMNS = frozenset({
    "id", "sku", "name", "description", "price", "cost", "quantity", "min_stock",
    "department_id", "department_name", "vendor_id", "vendor_name", "original_sku",
    "barcode", "vendor_barcode", "base_unit", "sell_uom", "pack_qty", "organization_id", "created_at", "updated_at",
})


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
    limit: Optional[int] = None,
    offset: int = 0,
    organization_id: Optional[str] = None,
) -> list:
    conn = get_connection()
    org_id = organization_id or "default"
    base = "SELECT * FROM products WHERE (organization_id = ? OR organization_id IS NULL)"
    params: list = [org_id]
    if department_id:
        base += " AND department_id = ?"
        params.append(department_id)
    if search:
        base += " AND (name LIKE ? OR sku LIKE ? OR barcode LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
    if low_stock:
        base += " AND quantity <= min_stock"
    base += " ORDER BY name"
    if limit is not None:
        base += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    cursor = await conn.execute(base, params)
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def count_products(
    department_id: Optional[str] = None,
    search: Optional[str] = None,
    low_stock: bool = False,
    organization_id: Optional[str] = None,
) -> int:
    conn = get_connection()
    org_id = organization_id or "default"
    query = "SELECT COUNT(*) FROM products WHERE (organization_id = ? OR organization_id IS NULL)"
    params: list = [org_id]
    if department_id:
        query += " AND department_id = ?"
        params.append(department_id)
    if search:
        query += " AND (name LIKE ? OR sku LIKE ? OR barcode LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
    if low_stock:
        query += " AND quantity <= min_stock"
    cursor = await conn.execute(query, params)
    row = await cursor.fetchone()
    return row[0] if row else 0


def _sanitize_columns(columns: str) -> str:
    """Return validated column list for SELECT. Raises ValueError if invalid."""
    if columns == "*":
        return "*"
    parts = [p.strip() for p in columns.split(",") if p.strip()]
    invalid = [p for p in parts if p not in _PRODUCT_COLUMNS]
    if invalid:
        raise ValueError(f"Invalid product columns: {invalid}")
    return ", ".join(parts)


async def get_by_id(product_id: str, columns: Optional[str] = "*", organization_id: Optional[str] = None, conn=None) -> Optional[dict]:
    conn = conn or get_connection()
    sel = _sanitize_columns(columns or "*")
    if organization_id:
        cursor = await conn.execute(
            f"SELECT {sel} FROM products WHERE id = ? AND (organization_id = ? OR organization_id IS NULL)",
            (product_id, organization_id),
        )
    else:
        cursor = await conn.execute(
            f"SELECT {sel} FROM products WHERE id = ?",
            (product_id,),
        )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def list_by_vendor(vendor_id: str, limit: int = 200) -> list:
    """List products for a vendor (for LLM enrichment / product alignment)."""
    if not vendor_id:
        return []
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, name, sku, original_sku FROM products WHERE vendor_id = ? ORDER BY name LIMIT ?",
        (vendor_id, limit),
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def find_by_barcode(barcode: str, exclude_product_id: Optional[str] = None, organization_id: Optional[str] = None, conn=None) -> Optional[dict]:
    """Find product by barcode. Optionally exclude a product (for update uniqueness check)."""
    b = barcode.strip() if barcode else ""
    if not b:
        return None
    c = conn or get_connection()
    org_id = organization_id or "default"
    if exclude_product_id:
        cursor = await c.execute(
            "SELECT * FROM products WHERE (barcode = ? OR sku = ? OR vendor_barcode = ?) AND id != ? AND (organization_id = ? OR organization_id IS NULL)",
            (b, b, b, exclude_product_id, org_id),
        )
    else:
        cursor = await c.execute(
            "SELECT * FROM products WHERE (barcode = ? OR sku = ? OR vendor_barcode = ?) AND (organization_id = ? OR organization_id IS NULL)",
            (b, b, b, org_id),
        )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def find_by_original_sku_and_vendor(
    original_sku: str, vendor_id: str, organization_id: Optional[str] = None
) -> Optional[dict]:
    """Find existing product by vendor's SKU and vendor. For matching incoming orders to inventory."""
    if not original_sku or not str(original_sku).strip() or not vendor_id:
        return None
    norm = str(original_sku).strip().lower()
    org_id = organization_id or "default"
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT * FROM products
           WHERE vendor_id = ? AND TRIM(LOWER(COALESCE(original_sku, ''))) = ?
           AND (organization_id = ? OR organization_id IS NULL)""",
        (vendor_id, norm, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def find_by_name_and_vendor(
    name: str, vendor_id: str, organization_id: Optional[str] = None
) -> Optional[dict]:
    """Find existing product by exact name (case-insensitive) and vendor.
    Name-based fallback when original_sku is absent — prevents duplicate product creation."""
    if not name or not str(name).strip() or not vendor_id:
        return None
    norm = str(name).strip().lower()
    org_id = organization_id or "default"
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT * FROM products
           WHERE vendor_id = ? AND TRIM(LOWER(name)) = ?
           AND (organization_id = ? OR organization_id IS NULL)""",
        (vendor_id, norm, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def insert(product_dict: dict, conn=None) -> None:
    in_transaction = conn is not None
    conn = conn or get_connection()
    org_id = product_dict.get("organization_id") or "default"
    await conn.execute(
        """INSERT INTO products (id, sku, name, description, price, cost, quantity, min_stock,
           department_id, department_name, vendor_id, vendor_name, original_sku, barcode, vendor_barcode,
           base_unit, sell_uom, pack_qty, organization_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            org_id,
            product_dict.get("created_at", ""),
            product_dict.get("updated_at", ""),
        ),
    )
    if not in_transaction:
        await conn.commit()


async def update(product_id: str, updates: dict, conn=None) -> Optional[dict]:
    in_transaction = conn is not None
    conn = conn or get_connection()
    set_parts = ["updated_at = ?"]
    values = [updates.get("updated_at", "")]
    for key in ("name", "description", "price", "cost", "quantity", "min_stock",
                 "department_id", "department_name", "vendor_id", "vendor_name", "barcode",
                 "vendor_barcode", "base_unit", "sell_uom", "pack_qty", "original_sku"):
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
    if not in_transaction:
        await conn.commit()
    return await get_by_id(product_id, conn=conn)


async def delete(product_id: str, conn=None) -> int:
    in_transaction = conn is not None
    conn = conn or get_connection()
    cursor = await conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    if not in_transaction:
        await conn.commit()
    return cursor.rowcount


async def atomic_decrement(product_id: str, quantity: int, updated_at: str, conn=None) -> Optional[dict]:
    """Decrement quantity only if >= requested. Returns updated row or None if insufficient."""
    in_transaction = conn is not None
    conn = conn or get_connection()
    cursor = await conn.execute(
        """UPDATE products SET quantity = quantity - ?, updated_at = ?
           WHERE id = ? AND quantity >= ?""",
        (quantity, updated_at, product_id, quantity),
    )
    if not in_transaction:
        await conn.commit()
    if cursor.rowcount == 0:
        return None
    return await get_by_id(product_id, conn=conn)


async def increment_quantity(product_id: str, quantity: int, updated_at: str, conn=None) -> None:
    """Rollback: add quantity back."""
    in_transaction = conn is not None
    conn = conn or get_connection()
    await conn.execute(
        "UPDATE products SET quantity = quantity + ?, updated_at = ? WHERE id = ?",
        (quantity, updated_at, product_id),
    )
    if not in_transaction:
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


async def atomic_adjust(product_id: str, quantity_delta: int, updated_at: str) -> Optional[dict]:
    """
    Atomically adjust quantity by delta (+ or -).
    Returns updated row or None if adjustment would result in negative stock.
    """
    conn = get_connection()
    cursor = await conn.execute(
        """UPDATE products SET quantity = quantity + ?, updated_at = ?
           WHERE id = ? AND quantity + ? >= 0""",
        (quantity_delta, updated_at, product_id, quantity_delta),
    )
    await conn.commit()
    if cursor.rowcount == 0:
        return None
    return await get_by_id(product_id)


async def count_all(organization_id: Optional[str] = None) -> int:
    conn = get_connection()
    org_id = organization_id or "default"
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE organization_id = ? OR organization_id IS NULL",
        (org_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def count_low_stock(organization_id: Optional[str] = None) -> int:
    conn = get_connection()
    org_id = organization_id or "default"
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE quantity <= min_stock AND (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def list_low_stock(limit: int = 10, organization_id: Optional[str] = None) -> list:
    conn = get_connection()
    org_id = organization_id or "default"
    cursor = await conn.execute(
        "SELECT * FROM products WHERE quantity <= min_stock AND (organization_id = ? OR organization_id IS NULL) ORDER BY quantity LIMIT ?",
        (org_id, limit),
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


class ProductRepo:
    list_products = staticmethod(list_products)
    count_products = staticmethod(count_products)
    get_by_id = staticmethod(get_by_id)
    find_by_barcode = staticmethod(find_by_barcode)
    find_by_original_sku_and_vendor = staticmethod(find_by_original_sku_and_vendor)
    find_by_name_and_vendor = staticmethod(find_by_name_and_vendor)
    list_by_vendor = staticmethod(list_by_vendor)
    insert = staticmethod(insert)
    update = staticmethod(update)
    delete = staticmethod(delete)
    atomic_decrement = staticmethod(atomic_decrement)
    increment_quantity = staticmethod(increment_quantity)
    add_quantity = staticmethod(add_quantity)
    atomic_adjust = staticmethod(atomic_adjust)
    count_all = staticmethod(count_all)
    count_low_stock = staticmethod(count_low_stock)
    list_low_stock = staticmethod(list_low_stock)


product_repo = ProductRepo()
