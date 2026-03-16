"""Vendor repository."""

from datetime import UTC, datetime

from catalog.domain.vendor import Vendor
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> Vendor | None:
    if row is None:
        return None
    d = dict(row)
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return Vendor.model_validate(d)


async def list_all() -> list[Vendor]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, name, contact_name, email, phone, address, organization_id, created_at FROM vendors
           WHERE (organization_id = $1 OR organization_id IS NULL) AND deleted_at IS NULL""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [v for r in rows if (v := _row_to_model(r)) is not None]


async def get_by_id(vendor_id: str) -> Vendor | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, name, contact_name, email, phone, address, organization_id, created_at FROM vendors
           WHERE id = $1 AND (organization_id = $2 OR organization_id IS NULL) AND deleted_at IS NULL""",
        (vendor_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def find_by_name(name: str) -> Vendor | None:
    """Case-insensitive lookup by vendor name."""
    if not name or not name.strip():
        return None
    normalized = name.strip().lower()
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, name, contact_name, email, phone, address, organization_id, created_at FROM vendors
           WHERE TRIM(LOWER(name)) = $1 AND (organization_id = $2 OR organization_id IS NULL) AND deleted_at IS NULL""",
        (normalized, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def insert(vendor: Vendor) -> None:
    vendor_dict = vendor.model_dump()
    conn = get_connection()
    org_id = vendor_dict.get("organization_id") or get_org_id()
    await conn.execute(
        """INSERT INTO vendors (id, name, contact_name, email, phone, address, organization_id, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
        (
            vendor_dict["id"],
            vendor_dict["name"],
            vendor_dict.get("contact_name", ""),
            vendor_dict.get("email", ""),
            vendor_dict.get("phone", ""),
            vendor_dict.get("address", ""),
            org_id,
            vendor_dict.get("created_at", ""),
        ),
    )
    await conn.commit()


async def update(vendor_id: str, vendor_dict: dict) -> Vendor | None:
    conn = get_connection()
    org_id = get_org_id()
    new_name = vendor_dict.get("name", "")
    params: list = [
        new_name,
        vendor_dict.get("contact_name", ""),
        vendor_dict.get("email", ""),
        vendor_dict.get("phone", ""),
        vendor_dict.get("address", ""),
        vendor_id,
    ]
    where = "WHERE id = $6 AND organization_id = $7"
    params.append(org_id)
    query = "UPDATE vendors SET name = $1, contact_name = $2, email = $3, phone = $4, address = $5 "
    query += where
    await conn.execute(query, params)
    await conn.execute(
        "UPDATE vendor_items SET vendor_name = $1 WHERE vendor_id = $2 AND organization_id = $3",
        (new_name, vendor_id, org_id),
    )
    await conn.commit()
    return await get_by_id(vendor_id)


async def delete(vendor_id: str) -> int:
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    params: list = [now, vendor_id]
    where = "WHERE id = $2 AND deleted_at IS NULL AND organization_id = $3"
    params.append(org_id)
    query = "UPDATE vendors SET deleted_at = $1 "
    query += where
    cursor = await conn.execute(query, params)
    await conn.commit()
    return cursor.rowcount


async def count() -> int:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM vendors WHERE (organization_id = $1 OR organization_id IS NULL) AND deleted_at IS NULL",
        (org_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


class VendorRepo:
    list_all = staticmethod(list_all)
    get_by_id = staticmethod(get_by_id)
    find_by_name = staticmethod(find_by_name)
    insert = staticmethod(insert)
    update = staticmethod(update)
    delete = staticmethod(delete)
    count = staticmethod(count)


vendor_repo = VendorRepo()
