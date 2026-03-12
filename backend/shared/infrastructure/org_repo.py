"""Organization (tenant) repository — shared infrastructure.

Organizations are the tenancy boundary. Every bounded context
filters by organization_id but none owns the concept — it is
cross-cutting infrastructure.
"""

from pydantic import BaseModel

from shared.infrastructure.database import get_connection


class Organization(BaseModel):
    id: str
    name: str
    slug: str
    created_at: str = ""


def _row_to_model(row) -> Organization | None:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if not d:
        return None
    d.pop("organization_id", None)
    return Organization.model_validate(d)


async def get_by_id(org_id: str) -> Organization | None:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, name, slug, created_at FROM organizations WHERE id = ?",
        (org_id,),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def get_by_slug(slug: str) -> Organization | None:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, name, slug, created_at FROM organizations WHERE slug = ?",
        (slug,),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


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


async def list_all() -> list[Organization]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, name, slug, created_at FROM organizations ORDER BY name"
    )
    rows = await cursor.fetchall()
    return [_row_to_model(r) for r in rows]


class OrganizationRepo:
    get_by_id = staticmethod(get_by_id)
    get_by_slug = staticmethod(get_by_slug)
    insert = staticmethod(insert)
    list_all = staticmethod(list_all)


organization_repo = OrganizationRepo()
