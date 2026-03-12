"""Product repository — read queries and class wrapper."""

from catalog.domain.product import Product
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_product(row) -> Product | None:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if not d:
        return None
    if "quantity" in d:
        d["quantity"] = float(d["quantity"])
    if "min_stock" in d:
        d["min_stock"] = int(d["min_stock"])
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return Product.model_validate(d)


async def list_products(
    department_id: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    limit: int | None = None,
    offset: int = 0,
    product_group: str | None = None,
) -> list[Product]:
    conn = get_connection()
    org_id = get_org_id()
    base = "SELECT * FROM products WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL"
    params: list = [org_id]
    if department_id:
        base += " AND department_id = ?"
        params.append(department_id)
    if product_group:
        base += " AND product_group = ?"
        params.append(product_group)
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
    return [p for r in rows if (p := _row_to_product(r)) is not None]


async def count_products(
    department_id: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    product_group: str | None = None,
) -> int:
    conn = get_connection()
    org_id = get_org_id()
    query = "SELECT COUNT(*) FROM products WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL"
    params: list = [org_id]
    if department_id:
        query += " AND department_id = ?"
        params.append(department_id)
    if product_group:
        query += " AND product_group = ?"
        params.append(product_group)
    if search:
        query += " AND (name LIKE ? OR sku LIKE ? OR barcode LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
    if low_stock:
        query += " AND quantity <= min_stock"
    cursor = await conn.execute(query, params)
    row = await cursor.fetchone()
    return row[0] if row else 0


async def get_by_id(product_id: str) -> Product | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM products WHERE id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (product_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_product(row)


async def list_by_vendor(vendor_id: str, limit: int = 200) -> list[Product]:
    if not vendor_id:
        return []
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM products WHERE vendor_id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL ORDER BY name LIMIT ?",
        (vendor_id, org_id, limit),
    )
    rows = await cursor.fetchall()
    return [p for r in rows if (p := _row_to_product(r)) is not None]


async def find_by_sku(sku: str) -> Product | None:
    """Exact case-insensitive SKU lookup."""
    s = sku.strip().upper() if sku else ""
    if not s:
        return None
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM products WHERE UPPER(sku) = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (s, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_product(row)


async def find_by_barcode(
    barcode: str,
    exclude_product_id: str | None = None,
) -> Product | None:
    """Find product by barcode. Optionally exclude a product (for update uniqueness check)."""
    b = barcode.strip() if barcode else ""
    if not b:
        return None
    c = get_connection()
    org_id = get_org_id()
    if exclude_product_id:
        cursor = await c.execute(
            "SELECT * FROM products WHERE (barcode = ? OR sku = ? OR vendor_barcode = ?) AND id != ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
            (b, b, b, exclude_product_id, org_id),
        )
    else:
        cursor = await c.execute(
            "SELECT * FROM products WHERE (barcode = ? OR sku = ? OR vendor_barcode = ?) AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
            (b, b, b, org_id),
        )
    row = await cursor.fetchone()
    return _row_to_product(row)


async def find_by_original_sku_and_vendor(
    original_sku: str, vendor_id: str
) -> Product | None:
    """Find existing product by vendor's SKU and vendor. For matching incoming orders to inventory."""
    if not original_sku or not str(original_sku).strip() or not vendor_id:
        return None
    norm = str(original_sku).strip().lower()
    org_id = get_org_id()
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT * FROM products
           WHERE vendor_id = ? AND TRIM(LOWER(COALESCE(original_sku, ''))) = ?
           AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL""",
        (vendor_id, norm, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_product(row)


async def find_by_name_and_vendor(
    name: str, vendor_id: str
) -> Product | None:
    """Find existing product by exact name (case-insensitive) and vendor.
    Name-based fallback when original_sku is absent — prevents duplicate product creation."""
    if not name or not str(name).strip() or not vendor_id:
        return None
    norm = str(name).strip().lower()
    org_id = get_org_id()
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT * FROM products
           WHERE vendor_id = ? AND TRIM(LOWER(name)) = ?
           AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL""",
        (vendor_id, norm, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_product(row)


async def count_all() -> int:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (org_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def count_low_stock() -> int:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE quantity <= min_stock AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (org_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def list_low_stock(limit: int = 10) -> list[Product]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM products WHERE quantity <= min_stock AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL ORDER BY quantity LIMIT ?",
        (org_id, limit),
    )
    rows = await cursor.fetchall()
    return [p for r in rows if (p := _row_to_product(r)) is not None]


async def list_product_groups() -> list[dict]:
    """Return distinct product groups with their product count."""
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT product_group, COUNT(*) as product_count,
                  SUM(quantity) as total_quantity
           FROM products
           WHERE product_group IS NOT NULL
             AND (organization_id = ? OR organization_id IS NULL)
             AND deleted_at IS NULL
           GROUP BY product_group
           ORDER BY product_group""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# --- Mutation re-exports from sub-module ---
from catalog.infrastructure.product_mutations import (  # noqa: E402
    add_quantity,
    atomic_adjust,
    atomic_decrement,
    delete,
    increment_quantity,
    insert,
    update,
)


class ProductRepo:
    list_products = staticmethod(list_products)
    count_products = staticmethod(count_products)
    get_by_id = staticmethod(get_by_id)
    find_by_sku = staticmethod(find_by_sku)
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
    list_product_groups = staticmethod(list_product_groups)


product_repo = ProductRepo()
