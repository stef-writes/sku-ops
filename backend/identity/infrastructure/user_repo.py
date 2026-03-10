"""User repository."""

from shared.infrastructure.config import DEFAULT_ORG_ID
from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if d and "is_active" in d:
        d["is_active"] = bool(d["is_active"])
    return d


async def get_by_id(user_id: str) -> dict | None:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, email, name, role, company, billing_entity, phone, is_active, organization_id, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def get_by_email(email: str) -> dict | None:
    conn = get_connection()
    cursor = await conn.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def insert(user_dict: dict) -> None:
    conn = get_connection()
    org_id = user_dict.get("organization_id") or DEFAULT_ORG_ID
    cols = "id, email, password, name, role, company, billing_entity, phone, is_active, organization_id, created_at"
    ins_q = "INSERT INTO users ("
    ins_q += cols
    ins_q += ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    await conn.execute(
        ins_q,
        (
            user_dict["id"],
            user_dict["email"],
            user_dict["password"],
            user_dict["name"],
            user_dict.get("role", "admin"),
            user_dict.get("company") or "",
            user_dict.get("billing_entity") or "",
            user_dict.get("phone") or "",
            1 if user_dict.get("is_active", True) else 0,
            org_id,
            user_dict.get("created_at", ""),
        ),
    )
    await conn.commit()


async def update(user_id: str, updates: dict, organization_id: str | None = None) -> dict | None:
    conn = get_connection()
    set_clauses = []
    values = []
    if "name" in updates and updates["name"] is not None:
        set_clauses.append("name = ?")
        values.append(updates["name"])
    if "company" in updates and updates["company"] is not None:
        set_clauses.append("company = ?")
        values.append(updates["company"])
    if "billing_entity" in updates and updates["billing_entity"] is not None:
        set_clauses.append("billing_entity = ?")
        values.append(updates["billing_entity"])
    if "phone" in updates and updates["phone"] is not None:
        set_clauses.append("phone = ?")
        values.append(updates["phone"])
    if "is_active" in updates and updates["is_active"] is not None:
        set_clauses.append("is_active = ?")
        values.append(1 if updates["is_active"] else 0)
    if not set_clauses:
        return await get_by_id(user_id)
    values.append(user_id)
    where = "WHERE id = ?"
    if organization_id:
        where += " AND organization_id = ?"
        values.append(organization_id)
    upd_q = "UPDATE users SET "
    upd_q += ", ".join(set_clauses)
    upd_q += " " + where
    await conn.execute(upd_q, values)
    await conn.commit()
    return await get_by_id(user_id)


async def list_contractors(organization_id: str | None = None, search: str | None = None) -> list:
    conn = get_connection()
    org_id = organization_id or DEFAULT_ORG_ID
    base = """SELECT id, email, name, role, company, billing_entity, phone, is_active, organization_id, created_at
              FROM users WHERE role = 'contractor' AND (organization_id = ? OR organization_id IS NULL)"""
    params: list = [org_id]
    if search and search.strip():
        term = f"%{search.strip()}%"
        base += " AND (name LIKE ? OR email LIKE ? OR company LIKE ? OR billing_entity LIKE ? OR phone LIKE ?)"
        params.extend([term, term, term, term, term])
    base += " ORDER BY name"
    cursor = await conn.execute(base, params)
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def count_contractors(organization_id: str | None = None) -> int:
    conn = get_connection()
    org_id = organization_id or DEFAULT_ORG_ID
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'contractor' AND (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def delete_contractor(contractor_id: str, organization_id: str | None = None) -> int:
    conn = get_connection()
    where = "WHERE id = ? AND role = 'contractor'"
    params: list = [contractor_id]
    if organization_id:
        where += " AND organization_id = ?"
        params.append(organization_id)
    del_q = "DELETE FROM users "
    del_q += where
    cursor = await conn.execute(del_q, params)
    await conn.commit()
    return cursor.rowcount


class UserRepo:
    get_by_id = staticmethod(get_by_id)
    get_by_email = staticmethod(get_by_email)
    insert = staticmethod(insert)
    update = staticmethod(update)
    list_contractors = staticmethod(list_contractors)
    count_contractors = staticmethod(count_contractors)
    delete_contractor = staticmethod(delete_contractor)


user_repo = UserRepo()
