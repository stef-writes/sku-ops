"""SKU repository — read queries and class wrapper."""

from catalog.domain.product import Sku
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_sku(row) -> Sku | None:
    if row is None:
        return None
    d = dict(row)
    if "quantity" in d:
        d["quantity"] = float(d["quantity"])
    if "min_stock" in d:
        d["min_stock"] = int(d["min_stock"])
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return Sku.model_validate(d)


async def list_skus(
    category_id: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    limit: int | None = None,
    offset: int = 0,
    product_id: str | None = None,
) -> list[Sku]:
    conn = get_connection()
    org_id = get_org_id()
    base = "SELECT * FROM skus WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL"
    params: list = [org_id]
    if category_id:
        base += " AND category_id = ?"
        params.append(category_id)
    if product_id:
        base += " AND product_id = ?"
        params.append(product_id)
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
    return [s for r in rows if (s := _row_to_sku(r)) is not None]


async def count_skus(
    category_id: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    product_id: str | None = None,
) -> int:
    conn = get_connection()
    org_id = get_org_id()
    query = "SELECT COUNT(*) FROM skus WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL"
    params: list = [org_id]
    if category_id:
        query += " AND category_id = ?"
        params.append(category_id)
    if product_id:
        query += " AND product_id = ?"
        params.append(product_id)
    if search:
        query += " AND (name LIKE ? OR sku LIKE ? OR barcode LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
    if low_stock:
        query += " AND quantity <= min_stock"
    cursor = await conn.execute(query, params)
    row = await cursor.fetchone()
    return row[0] if row else 0


async def get_by_id(sku_id: str) -> Sku | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM skus WHERE id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (sku_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_sku(row)


async def find_by_sku(sku: str) -> Sku | None:
    """Exact case-insensitive SKU lookup."""
    s = sku.strip().upper() if sku else ""
    if not s:
        return None
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM skus WHERE UPPER(sku) = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (s, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_sku(row)


async def find_by_barcode(
    barcode: str,
    exclude_sku_id: str | None = None,
) -> Sku | None:
    """Find SKU by barcode. Optionally exclude a SKU (for update uniqueness check)."""
    b = barcode.strip() if barcode else ""
    if not b:
        return None
    c = get_connection()
    org_id = get_org_id()
    if exclude_sku_id:
        cursor = await c.execute(
            "SELECT * FROM skus WHERE (barcode = ? OR sku = ? OR vendor_barcode = ?) AND id != ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
            (b, b, b, exclude_sku_id, org_id),
        )
    else:
        cursor = await c.execute(
            "SELECT * FROM skus WHERE (barcode = ? OR sku = ? OR vendor_barcode = ?) AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
            (b, b, b, org_id),
        )
    row = await cursor.fetchone()
    return _row_to_sku(row)


async def find_by_name_and_vendor(name: str, vendor_id: str) -> Sku | None:
    """Find SKU by name + vendor via vendor_items join.
    Name-based fallback when vendor_sku is absent — prevents duplicate SKU creation."""
    if not name or not str(name).strip() or not vendor_id:
        return None
    norm = str(name).strip().lower()
    org_id = get_org_id()
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT s.* FROM skus s
           INNER JOIN vendor_items vi ON vi.sku_id = s.id AND vi.deleted_at IS NULL
           WHERE vi.vendor_id = ? AND TRIM(LOWER(s.name)) = ?
           AND (s.organization_id = ? OR s.organization_id IS NULL) AND s.deleted_at IS NULL""",
        (vendor_id, norm, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_sku(row)


async def find_by_product_id(product_id: str) -> list[Sku]:
    """Return all SKUs belonging to a product parent."""
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM skus WHERE product_id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL ORDER BY name",
        (product_id, org_id),
    )
    rows = await cursor.fetchall()
    return [s for r in rows if (s := _row_to_sku(r)) is not None]


async def count_all() -> int:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM skus WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (org_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def count_low_stock() -> int:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM skus WHERE quantity <= min_stock AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (org_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def list_low_stock(limit: int = 10) -> list[Sku]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM skus WHERE quantity <= min_stock AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL ORDER BY quantity LIMIT ?",
        (org_id, limit),
    )
    rows = await cursor.fetchall()
    return [s for r in rows if (s := _row_to_sku(r)) is not None]


# --- Mutation re-exports from sub-module ---
from catalog.infrastructure.sku_mutations import (  # noqa: E402
    add_quantity,
    atomic_adjust,
    atomic_decrement,
    delete,
    increment_quantity,
    insert,
    update,
)


class SkuRepo:
    list_skus = staticmethod(list_skus)
    count_skus = staticmethod(count_skus)
    get_by_id = staticmethod(get_by_id)
    find_by_sku = staticmethod(find_by_sku)
    find_by_barcode = staticmethod(find_by_barcode)
    find_by_name_and_vendor = staticmethod(find_by_name_and_vendor)
    find_by_product_id = staticmethod(find_by_product_id)
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


sku_repo = SkuRepo()
