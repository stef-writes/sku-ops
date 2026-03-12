"""Contractor management service.

Wraps user operations for contractor-specific queries. In Phase 3 this
will be backed by Supabase Admin API. For now it delegates to the user
repo which will be replaced.

Cross-context consumers use these functions for contractor lookups.
"""

from __future__ import annotations

from pydantic import BaseModel

from shared.infrastructure.config import DEFAULT_ORG_ID
from shared.infrastructure.database import get_connection


class Contractor(BaseModel):
    """Read model for contractor data."""

    id: str
    email: str
    name: str
    role: str = "contractor"
    company: str = ""
    billing_entity: str = ""
    billing_entity_id: str | None = None
    phone: str = ""
    is_active: bool = True
    organization_id: str = DEFAULT_ORG_ID
    created_at: str = ""


def _row_to_model(row) -> Contractor | None:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if not d:
        return None
    if "is_active" in d:
        d["is_active"] = bool(d["is_active"])
    d.pop("password", None)
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return Contractor.model_validate(d)


_SELECT_COLS = (
    "id, email, name, role, company, billing_entity, billing_entity_id, "
    "phone, is_active, organization_id, created_at"
)


async def get_contractor_by_id(user_id: str) -> Contractor | None:
    conn = get_connection()
    cursor = await conn.execute(
        f"SELECT {_SELECT_COLS} FROM users WHERE id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def get_users_by_ids(user_ids: list[str]) -> dict[str, Contractor]:
    """Return {{user_id: Contractor}} for a batch of IDs. Missing IDs are omitted."""
    if not user_ids:
        return {}
    conn = get_connection()
    placeholders = ",".join("?" * len(user_ids))
    cursor = await conn.execute(
        f"SELECT {_SELECT_COLS} FROM users WHERE id IN ({placeholders})",
        tuple(user_ids),
    )
    rows = await cursor.fetchall()
    result: dict[str, Contractor] = {}
    for row in rows:
        user = _row_to_model(row)
        if user:
            result[user.id] = user
    return result


async def list_contractors(org_id: str, search: str | None = None) -> list[Contractor]:
    conn = get_connection()
    org = org_id or DEFAULT_ORG_ID
    base = (
        f"SELECT {_SELECT_COLS} FROM users"
        " WHERE role = 'contractor' AND (organization_id = ? OR organization_id IS NULL)"
    )
    params: list = [org]
    if search and search.strip():
        term = f"%{search.strip()}%"
        base += (
            " AND (name LIKE ? OR email LIKE ? OR company LIKE ?"
            " OR billing_entity LIKE ? OR phone LIKE ?)"
        )
        params.extend([term, term, term, term, term])
    base += " ORDER BY name"
    cursor = await conn.execute(base, params)
    rows = await cursor.fetchall()
    return [u for r in rows if (u := _row_to_model(r)) is not None]


async def count_contractors(org_id: str) -> int:
    conn = get_connection()
    org = org_id or DEFAULT_ORG_ID
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'contractor'"
        " AND (organization_id = ? OR organization_id IS NULL)",
        (org,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0
