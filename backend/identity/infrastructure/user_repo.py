"""User repository."""

from identity.domain.user import User
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> User | None:
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
    return User.model_validate(d)


async def get_by_id(user_id: str) -> User | None:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, email, name, role, company, billing_entity, phone, is_active, organization_id, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def get_by_ids(user_ids: list[str]) -> dict[str, User]:
    """Return {user_id: User} for a batch of IDs. Missing IDs are omitted."""
    if not user_ids:
        return {}
    conn = get_connection()
    placeholders = ",".join("?" * len(user_ids))
    cursor = await conn.execute(
        f"SELECT id, email, name, role, company, billing_entity, phone, is_active, organization_id, created_at FROM users WHERE id IN ({placeholders})",
        tuple(user_ids),
    )
    rows = await cursor.fetchall()
    result: dict[str, User] = {}
    for row in rows:
        user = _row_to_model(row)
        if user:
            result[user.id] = user
    return result


async def get_by_email(email: str) -> dict | None:
    """Returns raw dict including password hash — for auth only."""
    conn = get_connection()
    cursor = await conn.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = await cursor.fetchone()
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if d and "is_active" in d:
        d["is_active"] = bool(d["is_active"])
    return d


async def insert(user_dict: dict) -> None:
    conn = get_connection()
    org_id = user_dict.get("organization_id") or get_org_id()
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


async def update(user_id: str, updates: dict) -> User | None:
    conn = get_connection()
    org_id = get_org_id()
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
    where += " AND organization_id = ?"
    values.append(org_id)
    upd_q = "UPDATE users SET "
    upd_q += ", ".join(set_clauses)
    upd_q += " " + where
    await conn.execute(upd_q, values)
    await conn.commit()
    return await get_by_id(user_id)


async def list_contractors(search: str | None = None) -> list[User]:
    conn = get_connection()
    org_id = get_org_id()
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
    return [u for r in rows if (u := _row_to_model(r)) is not None]


async def count_contractors() -> int:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'contractor' AND (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def delete_contractor(contractor_id: str) -> int:
    conn = get_connection()
    org_id = get_org_id()
    where = "WHERE id = ? AND role = 'contractor'"
    params: list = [contractor_id]
    where += " AND organization_id = ?"
    params.append(org_id)
    del_q = "DELETE FROM users "
    del_q += where
    cursor = await conn.execute(del_q, params)
    await conn.commit()
    return cursor.rowcount


class UserRepo:
    get_by_id = staticmethod(get_by_id)
    get_by_ids = staticmethod(get_by_ids)
    get_by_email = staticmethod(get_by_email)
    insert = staticmethod(insert)
    update = staticmethod(update)
    list_contractors = staticmethod(list_contractors)
    count_contractors = staticmethod(count_contractors)
    delete_contractor = staticmethod(delete_contractor)


user_repo = UserRepo()
