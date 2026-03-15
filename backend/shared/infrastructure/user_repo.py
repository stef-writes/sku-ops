"""User repository — pure persistence for the users table.

Owns all direct SQL access to the users table. Auth routes and any other
consumer that needs user lookups must go through this module.
"""

from shared.infrastructure.database import get_connection

_SELECT_COLS = (
    "id, email, password, name, role, company, billing_entity, phone, is_active, organization_id"
)

_SELECT_COLS_SAFE = (
    "id, email, name, role, company, billing_entity, phone, is_active, organization_id"
)


async def fetch_by_email(email: str) -> dict | None:
    """Fetch user row by email. Returns dict with password included (for auth)."""
    conn = get_connection()
    cursor = await conn.execute(
        f"SELECT {_SELECT_COLS} FROM users WHERE email = $1",
        (email,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def fetch_by_id(user_id: str) -> dict | None:
    """Fetch user row by ID. Returns dict without password (safe for profiles)."""
    conn = get_connection()
    cursor = await conn.execute(
        f"SELECT {_SELECT_COLS_SAFE} FROM users WHERE id = $1",
        (user_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def insert_user(
    *,
    user_id: str,
    email: str,
    password_hash: str,
    name: str,
    role: str = "admin",
    organization_id: str,
    created_at: str,
) -> None:
    """Insert a new user row."""
    conn = get_connection()
    await conn.execute(
        "INSERT INTO users (id, email, password, name, role, is_active, organization_id, created_at)"
        " VALUES ($1, $2, $3, $4, $5, 1, $6, $7)",
        (user_id, email, password_hash, name, role, organization_id, created_at),
    )
    await conn.commit()
