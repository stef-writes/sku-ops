"""Vendor repository."""
from typing import Optional, Union

from catalog.domain.vendor import Vendor
from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    return dict(row) if hasattr(row, "keys") else {}


async def list_all(organization_id: Optional[str] = None) -> list:
    conn = get_connection()
    org_id = organization_id or "default"
    cursor = await conn.execute(
        """SELECT id, name, contact_name, email, phone, address, product_count, organization_id, created_at FROM vendors
           WHERE organization_id = ? OR organization_id IS NULL""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_by_id(vendor_id: str, organization_id: Optional[str] = None) -> Optional[dict]:
    conn = get_connection()
    if organization_id:
        cursor = await conn.execute(
            """SELECT id, name, contact_name, email, phone, address, product_count, organization_id, created_at FROM vendors
               WHERE id = ? AND (organization_id = ? OR organization_id IS NULL)""",
            (vendor_id, organization_id),
        )
    else:
        cursor = await conn.execute(
            "SELECT id, name, contact_name, email, phone, address, product_count, organization_id, created_at FROM vendors WHERE id = ?",
            (vendor_id,),
        )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def find_by_name(name: str, organization_id: Optional[str] = None) -> Optional[dict]:
    """Case-insensitive lookup by vendor name."""
    if not name or not name.strip():
        return None
    normalized = name.strip().lower()
    conn = get_connection()
    org_id = organization_id or "default"
    cursor = await conn.execute(
        """SELECT id, name, contact_name, email, phone, address, product_count, organization_id, created_at FROM vendors
           WHERE TRIM(LOWER(name)) = ? AND (organization_id = ? OR organization_id IS NULL)""",
        (normalized, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def insert(vendor: Union[Vendor, dict]) -> None:
    vendor_dict = vendor if isinstance(vendor, dict) else vendor.model_dump()
    conn = get_connection()
    org_id = vendor_dict.get("organization_id") or "default"
    await conn.execute(
        """INSERT INTO vendors (id, name, contact_name, email, phone, address, product_count, organization_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            vendor_dict["id"],
            vendor_dict["name"],
            vendor_dict.get("contact_name", ""),
            vendor_dict.get("email", ""),
            vendor_dict.get("phone", ""),
            vendor_dict.get("address", ""),
            vendor_dict.get("product_count", 0),
            org_id,
            vendor_dict.get("created_at", ""),
        ),
    )
    await conn.commit()


async def update(vendor_id: str, vendor_dict: dict, conn=None) -> Optional[dict]:
    in_transaction = conn is not None
    conn = conn or get_connection()
    new_name = vendor_dict.get("name", "")
    await conn.execute(
        """UPDATE vendors SET name = ?, contact_name = ?, email = ?, phone = ?, address = ?
           WHERE id = ?""",
        (
            new_name,
            vendor_dict.get("contact_name", ""),
            vendor_dict.get("email", ""),
            vendor_dict.get("phone", ""),
            vendor_dict.get("address", ""),
            vendor_id,
        ),
    )
    await conn.execute(
        "UPDATE products SET vendor_name = ? WHERE vendor_id = ?",
        (new_name, vendor_id),
    )
    if not in_transaction:
        await conn.commit()
    return await get_by_id(vendor_id)


async def delete(vendor_id: str) -> int:
    conn = get_connection()
    cursor = await conn.execute("DELETE FROM vendors WHERE id = ?", (vendor_id,))
    await conn.commit()
    return cursor.rowcount


async def count(organization_id: Optional[str] = None) -> int:
    conn = get_connection()
    if organization_id:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM vendors WHERE organization_id = ? OR organization_id IS NULL",
            (organization_id,),
        )
    else:
        cursor = await conn.execute("SELECT COUNT(*) FROM vendors")
    row = await cursor.fetchone()
    return row[0] if row else 0


async def increment_product_count(vendor_id: str, delta: int, conn=None) -> None:
    in_transaction = conn is not None
    conn = conn or get_connection()
    await conn.execute(
        "UPDATE vendors SET product_count = product_count + ? WHERE id = ?",
        (delta, vendor_id),
    )
    if not in_transaction:
        await conn.commit()


class VendorRepo:
    list_all = staticmethod(list_all)
    get_by_id = staticmethod(get_by_id)
    find_by_name = staticmethod(find_by_name)
    insert = staticmethod(insert)
    update = staticmethod(update)
    delete = staticmethod(delete)
    count = staticmethod(count)
    increment_product_count = staticmethod(increment_product_count)


vendor_repo = VendorRepo()
