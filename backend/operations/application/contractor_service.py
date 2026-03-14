"""Contractor management service.

Owns all contractor CRUD and queries. Cross-context consumers import
from here for contractor lookups. When Supabase arrives, the auth parts
(password, JWT) move to Supabase; profile data stays here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import bcrypt
from pydantic import BaseModel

from finance.application.billing_entity_service import ensure_billing_entity
from shared.infrastructure.database import get_connection, get_org_id


def _make_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Contractor(BaseModel):
    """Read model for contractor data."""

    id: str
    email: str
    name: str
    role: str = "contractor"
    company: str = ""
    billing_entity: str = ""
    billing_entity_id: str | None = None
    phone: str | None = ""
    is_active: bool = True
    organization_id: str = ""
    created_at: str = ""


class UpdateContractorCommand(BaseModel):
    """Typed input for updating a contractor's profile fields."""

    name: str | None = None
    company: str | None = None
    billing_entity: str | None = None
    phone: str | None = None
    is_active: bool | None = None


class ContractorCreateResult(BaseModel):
    id: str
    email: str
    name: str
    role: str = "contractor"
    company: str = ""
    billing_entity: str = ""
    billing_entity_id: str | None = None
    phone: str | None = ""
    is_active: bool = True
    organization_id: str = ""
    created_at: str = ""


def _row_to_model(row) -> Contractor | None:
    if row is None:
        return None
    d = dict(row)
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


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def get_contractor_by_id(user_id: str) -> Contractor | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        f"SELECT {_SELECT_COLS} FROM users WHERE id = ? AND organization_id = ?",
        (user_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def get_users_by_ids(user_ids: list[str]) -> dict[str, Contractor]:
    """Return {user_id: Contractor} for a batch of IDs. Missing IDs are omitted."""
    if not user_ids:
        return {}
    conn = get_connection()
    org_id = get_org_id()
    placeholders = ",".join("?" * len(user_ids))
    cursor = await conn.execute(
        f"SELECT {_SELECT_COLS} FROM users WHERE id IN ({placeholders}) AND organization_id = ?",
        (*user_ids, org_id),
    )
    rows = await cursor.fetchall()
    result: dict[str, Contractor] = {}
    for row in rows:
        user = _row_to_model(row)
        if user:
            result[user.id] = user
    return result


async def list_contractors(search: str | None = None) -> list[Contractor]:
    conn = get_connection()
    org_id = get_org_id()
    base = (
        f"SELECT {_SELECT_COLS} FROM users"
        " WHERE role = 'contractor' AND (organization_id = ? OR organization_id IS NULL)"
    )
    params: list = [org_id]
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


async def count_contractors() -> int:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'contractor'"
        " AND (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


async def create_contractor(
    email: str,
    password: str,
    name: str,
    company: str | None = None,
    billing_entity_name: str | None = None,
    phone: str | None = None,
) -> ContractorCreateResult:
    """Create a contractor user with associated billing entity.

    Raises ValueError if email is already registered.
    """
    conn = get_connection()
    org_id = get_org_id()

    cursor = await conn.execute("SELECT id FROM users WHERE email = ?", (email,))
    if await cursor.fetchone():
        raise ValueError("Email already registered")

    billing_name = billing_entity_name or company or "Independent"
    be = await ensure_billing_entity(billing_name)

    contractor_id = _make_id()
    now = _now_iso()
    hashed_pw = _hash_password(password)
    company_val = company or "Independent"

    cols = (
        "id, email, password, name, role, company, billing_entity, billing_entity_id, "
        "phone, is_active, organization_id, created_at"
    )
    await conn.execute(
        f"INSERT INTO users ({cols}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            contractor_id,
            email,
            hashed_pw,
            name,
            "contractor",
            company_val,
            billing_name,
            be.id if be else None,
            phone or "",
            1,
            org_id,
            now,
        ),
    )
    await conn.commit()

    return ContractorCreateResult(
        id=contractor_id,
        email=email,
        name=name,
        company=company_val,
        billing_entity=billing_name,
        billing_entity_id=be.id if be else None,
        phone=phone or "",
        organization_id=org_id,
        created_at=now,
    )


async def update_contractor(
    contractor_id: str, updates: UpdateContractorCommand
) -> Contractor | None:
    """Update contractor profile fields. Returns updated contractor or None."""
    contractor = await get_contractor_by_id(contractor_id)
    if not contractor or contractor.role != "contractor":
        return None
    org_id = get_org_id()
    if contractor.organization_id != org_id:
        return None

    conn = get_connection()
    set_clauses = []
    values = []
    for key in ("name", "company", "billing_entity", "phone"):
        val = getattr(updates, key, None)
        if val is not None:
            set_clauses.append(f"{key} = ?")
            values.append(val)
    if updates.is_active is not None:
        set_clauses.append("is_active = ?")
        values.append(1 if updates.is_active else 0)
    if not set_clauses:
        return contractor
    values.extend([contractor_id, org_id])
    await conn.execute(
        f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ? AND organization_id = ?",
        values,
    )
    await conn.commit()
    return await get_contractor_by_id(contractor_id)


async def delete_contractor(contractor_id: str) -> int:
    """Delete a contractor. Returns number of rows deleted (0 or 1)."""
    contractor = await get_contractor_by_id(contractor_id)
    if not contractor or contractor.role != "contractor":
        return 0
    org_id = get_org_id()
    if contractor.organization_id != org_id:
        return 0

    conn = get_connection()
    cursor = await conn.execute(
        "DELETE FROM users WHERE id = ? AND role = 'contractor' AND organization_id = ?",
        (contractor_id, org_id),
    )
    await conn.commit()
    return cursor.rowcount
