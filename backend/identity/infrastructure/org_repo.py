"""Organization repository."""
from typing import Optional

from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    return dict(row) if hasattr(row, "keys") else {}


async def get_by_id(org_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, name, slug, created_at FROM organizations WHERE id = ?",
        (org_id,),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def get_by_slug(slug: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, name, slug, created_at FROM organizations WHERE slug = ?",
        (slug,),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def insert(org_dict: dict) -> None:
    conn = get_connection()
    await conn.execute(
        """INSERT INTO organizations (id, name, slug, created_at)
           VALUES (?, ?, ?, ?)""",
        (
            org_dict["id"],
            org_dict["name"],
            org_dict["slug"],
            org_dict.get("created_at", ""),
        ),
    )
    await conn.commit()


async def list_all() -> list:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, name, slug, created_at FROM organizations ORDER BY name"
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


class OrganizationRepo:
    get_by_id = staticmethod(get_by_id)
    get_by_slug = staticmethod(get_by_slug)
    insert = staticmethod(insert)
    list_all = staticmethod(list_all)


organization_repo = OrganizationRepo()
