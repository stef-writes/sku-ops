"""Vendor repository."""
from typing import Optional

from db import get_connection


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    return dict(row) if hasattr(row, "keys") else {}


async def list_all() -> list:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, name, contact_name, email, phone, address, product_count, created_at FROM vendors"
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_by_id(vendor_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, name, contact_name, email, phone, address, product_count, created_at FROM vendors WHERE id = ?",
        (vendor_id,),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def insert(vendor_dict: dict) -> None:
    conn = get_connection()
    await conn.execute(
        """INSERT INTO vendors (id, name, contact_name, email, phone, address, product_count, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            vendor_dict["id"],
            vendor_dict["name"],
            vendor_dict.get("contact_name", ""),
            vendor_dict.get("email", ""),
            vendor_dict.get("phone", ""),
            vendor_dict.get("address", ""),
            vendor_dict.get("product_count", 0),
            vendor_dict.get("created_at", ""),
        ),
    )
    await conn.commit()


async def update(vendor_id: str, vendor_dict: dict) -> Optional[dict]:
    conn = get_connection()
    await conn.execute(
        """UPDATE vendors SET name = ?, contact_name = ?, email = ?, phone = ?, address = ?
           WHERE id = ?""",
        (
            vendor_dict.get("name", ""),
            vendor_dict.get("contact_name", ""),
            vendor_dict.get("email", ""),
            vendor_dict.get("phone", ""),
            vendor_dict.get("address", ""),
            vendor_id,
        ),
    )
    await conn.commit()
    return await get_by_id(vendor_id)


async def delete(vendor_id: str) -> int:
    conn = get_connection()
    cursor = await conn.execute("DELETE FROM vendors WHERE id = ?", (vendor_id,))
    await conn.commit()
    return cursor.rowcount


async def count() -> int:
    conn = get_connection()
    cursor = await conn.execute("SELECT COUNT(*) FROM vendors")
    row = await cursor.fetchone()
    return row[0] if row else 0


async def increment_product_count(vendor_id: str, delta: int) -> None:
    conn = get_connection()
    await conn.execute(
        "UPDATE vendors SET product_count = product_count + ? WHERE id = ?",
        (delta, vendor_id),
    )
    await conn.commit()


class VendorRepo:
    list_all = staticmethod(list_all)
    get_by_id = staticmethod(get_by_id)
    insert = staticmethod(insert)
    update = staticmethod(update)
    delete = staticmethod(delete)
    count = staticmethod(count)
    increment_product_count = staticmethod(increment_product_count)


vendor_repo = VendorRepo()
