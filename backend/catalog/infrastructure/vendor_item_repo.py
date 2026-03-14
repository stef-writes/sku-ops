"""VendorItem repository — links vendors to SKUs with vendor-specific data."""

from datetime import UTC, datetime

from catalog.domain.vendor_item import VendorItem
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> VendorItem | None:
    if row is None:
        return None
    d = dict(row)
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    if "is_preferred" in d:
        d["is_preferred"] = bool(d["is_preferred"])
    return VendorItem.model_validate(d)


async def insert(item: VendorItem) -> None:
    d = item.model_dump()
    conn = get_connection()
    org_id = d.get("organization_id") or get_org_id()
    await conn.execute(
        """INSERT INTO vendor_items (id, vendor_id, sku_id, vendor_sku, vendor_name,
           purchase_uom, purchase_pack_qty, cost, lead_time_days, moq, is_preferred, notes,
           organization_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d["id"],
            d["vendor_id"],
            d["sku_id"],
            d.get("vendor_sku"),
            d.get("vendor_name", ""),
            d.get("purchase_uom", "each"),
            d.get("purchase_pack_qty", 1),
            d.get("cost", 0),
            d.get("lead_time_days"),
            d.get("moq"),
            int(d.get("is_preferred", False)),
            d.get("notes"),
            org_id,
            d.get("created_at", ""),
            d.get("updated_at", ""),
        ),
    )
    await conn.commit()


async def get_by_id(item_id: str) -> VendorItem | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM vendor_items WHERE id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (item_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def list_by_sku(sku_id: str) -> list[VendorItem]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT * FROM vendor_items
           WHERE sku_id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL
           ORDER BY is_preferred DESC, vendor_name""",
        (sku_id, org_id),
    )
    rows = await cursor.fetchall()
    return [vi for r in rows if (vi := _row_to_model(r)) is not None]


async def list_by_vendor(vendor_id: str) -> list[VendorItem]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT * FROM vendor_items
           WHERE vendor_id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL
           ORDER BY vendor_sku""",
        (vendor_id, org_id),
    )
    rows = await cursor.fetchall()
    return [vi for r in rows if (vi := _row_to_model(r)) is not None]


async def find_by_vendor_and_vendor_sku(vendor_id: str, vendor_sku: str) -> VendorItem | None:
    """Find a VendorItem by vendor + vendor's part number (case-insensitive)."""
    if not vendor_sku or not str(vendor_sku).strip() or not vendor_id:
        return None
    norm = str(vendor_sku).strip().lower()
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT * FROM vendor_items
           WHERE vendor_id = ? AND TRIM(LOWER(COALESCE(vendor_sku, ''))) = ?
           AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL""",
        (vendor_id, norm, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def find_by_sku_and_vendor(sku_id: str, vendor_id: str) -> VendorItem | None:
    """Find the VendorItem for a specific SKU + vendor combination."""
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT * FROM vendor_items
           WHERE sku_id = ? AND vendor_id = ?
           AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL""",
        (sku_id, vendor_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def find_preferred_for_sku(sku_id: str) -> VendorItem | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT * FROM vendor_items
           WHERE sku_id = ? AND is_preferred = 1
           AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL""",
        (sku_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def update(item_id: str, updates: dict) -> VendorItem | None:
    conn = get_connection()
    org_id = get_org_id()
    set_parts = ["updated_at = ?"]
    values: list = [updates.get("updated_at", datetime.now(UTC).isoformat())]
    for key in (
        "vendor_sku",
        "vendor_name",
        "purchase_uom",
        "purchase_pack_qty",
        "cost",
        "lead_time_days",
        "moq",
        "is_preferred",
        "notes",
    ):
        if key in updates and updates[key] is not None:
            val = updates[key]
            if key == "is_preferred":
                val = int(val)
            set_parts.append(f"{key} = ?")
            values.append(val)
    if len(set_parts) <= 1:
        return await get_by_id(item_id)
    values.append(item_id)
    values.append(org_id)
    query = f"UPDATE vendor_items SET {', '.join(set_parts)} WHERE id = ? AND organization_id = ?"
    await conn.execute(query, values)
    await conn.commit()
    return await get_by_id(item_id)


async def soft_delete(item_id: str) -> int:
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    cursor = await conn.execute(
        "UPDATE vendor_items SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL AND (organization_id = ? OR organization_id IS NULL)",
        (now, item_id, org_id),
    )
    await conn.commit()
    return cursor.rowcount


async def soft_delete_by_sku(sku_id: str) -> int:
    """Soft-delete all vendor items for a given SKU."""
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    cursor = await conn.execute(
        "UPDATE vendor_items SET deleted_at = ? WHERE sku_id = ? AND deleted_at IS NULL AND (organization_id = ? OR organization_id IS NULL)",
        (now, sku_id, org_id),
    )
    await conn.commit()
    return cursor.rowcount


async def clear_preferred_for_sku(sku_id: str) -> None:
    """Clear is_preferred flag on all vendor items for a SKU."""
    conn = get_connection()
    org_id = get_org_id()
    await conn.execute(
        "UPDATE vendor_items SET is_preferred = 0 WHERE sku_id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (sku_id, org_id),
    )
    await conn.commit()


class VendorItemRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_by_sku = staticmethod(list_by_sku)
    list_by_vendor = staticmethod(list_by_vendor)
    find_by_vendor_and_vendor_sku = staticmethod(find_by_vendor_and_vendor_sku)
    find_by_sku_and_vendor = staticmethod(find_by_sku_and_vendor)
    find_preferred_for_sku = staticmethod(find_preferred_for_sku)
    update = staticmethod(update)
    soft_delete = staticmethod(soft_delete)
    soft_delete_by_sku = staticmethod(soft_delete_by_sku)
    clear_preferred_for_sku = staticmethod(clear_preferred_for_sku)


vendor_item_repo = VendorItemRepo()
