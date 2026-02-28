"""User repository."""
import json
from typing import Optional

from db import get_connection


def _row_to_dict(row) -> dict:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if d and "is_active" in d:
        d["is_active"] = bool(d["is_active"])
    return d


async def get_by_id(user_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, email, name, role, company, billing_entity, phone, is_active, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def get_by_email(email: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def insert(user_dict: dict) -> None:
    conn = get_connection()
    await conn.execute(
        """INSERT INTO users (id, email, password, name, role, company, billing_entity, phone, is_active, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_dict["id"],
            user_dict["email"],
            user_dict["password"],
            user_dict["name"],
            user_dict.get("role", "warehouse_manager"),
            user_dict.get("company") or "",
            user_dict.get("billing_entity") or "",
            user_dict.get("phone") or "",
            1 if user_dict.get("is_active", True) else 0,
            user_dict.get("created_at", ""),
        ),
    )
    await conn.commit()


async def update(user_id: str, updates: dict) -> Optional[dict]:
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
    await conn.execute(
        f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ?",
        values,
    )
    await conn.commit()
    return await get_by_id(user_id)


async def list_contractors() -> list:
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT id, email, name, role, company, billing_entity, phone, is_active, created_at
           FROM users WHERE role = 'contractor'"""
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def count_contractors() -> int:
    conn = get_connection()
    cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE role = 'contractor'")
    row = await cursor.fetchone()
    return row[0] if row else 0


async def delete_contractor(contractor_id: str) -> int:
    conn = get_connection()
    cursor = await conn.execute(
        "DELETE FROM users WHERE id = ? AND role = 'contractor'",
        (contractor_id,),
    )
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
