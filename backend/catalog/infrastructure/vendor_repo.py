"""Vendor repository."""
from datetime import UTC, datetime, timezone
from typing import Optional, Union

from catalog.domain.vendor import Vendor
from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    return dict(row) if hasattr(row, "keys") else {}


async def list_all(organization_id: str | None = None) -> list:
    conn = get_connection()
    org_id = organization_id or "default"
    cursor = await conn.execute(
        """SELECT id, name, contact_name, email, phone, address, product_count, organization_id, created_at FROM vendors
           WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_by_id(vendor_id: str, organization_id: str | None = None) -> dict | None:
    conn = get_connection()
    if organization_id:
        cursor = await conn.execute(
            """SELECT id, name, contact_name, email, phone, address, product_count, organization_id, created_at FROM vendors
               WHERE id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL""",
            (vendor_id, organization_id),
        )
    else:
        cursor = await conn.execute(
            "SELECT id, name, contact_name, email, phone, address, product_count, organization_id, created_at FROM vendors WHERE id = ? AND deleted_at IS NULL",
            (vendor_id,),
        )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def find_by_name(name: str, organization_id: str | None = None) -> dict | None:
    """Case-insensitive lookup by vendor name."""
    if not name or not name.strip():
        return None
    normalized = name.strip().lower()
    conn = get_connection()
    org_id = organization_id or "default"
    cursor = await conn.execute(
        """SELECT id, name, contact_name, email, phone, address, product_count, organization_id, created_at FROM vendors
           WHERE TRIM(LOWER(name)) = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL""",
        (normalized, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def insert(vendor: Vendor | dict) -> None:
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


async def update(vendor_id: str, vendor_dict: dict, conn=None, organization_id: str | None = None) -> dict | None:
    in_transaction = conn is not None
    conn = conn or get_connection()
    new_name = vendor_dict.get("name", "")
    params: list = [
        new_name,
        vendor_dict.get("contact_name", ""),
        vendor_dict.get("email", ""),
        vendor_dict.get("phone", ""),
        vendor_dict.get("address", ""),
        vendor_id,
    ]
    where = "WHERE id = ?"
    if organization_id:
        where += " AND organization_id = ?"
        params.append(organization_id)
    await conn.execute(
        f"UPDATE vendors SET name = ?, contact_name = ?, email = ?, phone = ?, address = ? {where}",
        params,
    )
    await conn.execute(
        "UPDATE products SET vendor_name = ? WHERE vendor_id = ?",
        (new_name, vendor_id),
    )
    if not in_transaction:
        await conn.commit()
    return await get_by_id(vendor_id)


async def delete(vendor_id: str, organization_id: str | None = None) -> int:
    conn = get_connection()
    now = datetime.now(UTC).isoformat()
    params: list = [now, vendor_id]
    where = "WHERE id = ? AND deleted_at IS NULL"
    if organization_id:
        where += " AND organization_id = ?"
        params.append(organization_id)
    cursor = await conn.execute(
        f"UPDATE vendors SET deleted_at = ? {where}",
        params,
    )
    await conn.commit()
    return cursor.rowcount


async def count(organization_id: str | None = None) -> int:
    conn = get_connection()
    if organization_id:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM vendors WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
            (organization_id,),
        )
    else:
        cursor = await conn.execute("SELECT COUNT(*) FROM vendors WHERE deleted_at IS NULL")
    row = await cursor.fetchone()
    return row[0] if row else 0


async def increment_product_count(vendor_id: str, delta: int, conn=None, organization_id: str | None = None) -> None:
    in_transaction = conn is not None
    conn = conn or get_connection()
    params: list = [delta, vendor_id]
    where = "WHERE id = ?"
    if organization_id:
        where += " AND organization_id = ?"
        params.append(organization_id)
    await conn.execute(
        f"UPDATE vendors SET product_count = product_count + ? {where}",
        params,
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
