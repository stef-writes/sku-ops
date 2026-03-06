"""Refresh token repository."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Optional

from shared.infrastructure.config import REFRESH_TOKEN_EXPIRATION_DAYS
from shared.infrastructure.database import get_connection


def generate_refresh_token() -> tuple[str, str]:
    """Return (raw_token, token_hash). Store the hash; return raw to the client."""
    raw = secrets.token_hex(64)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create(user_id: str) -> tuple[str, str]:
    """Create and persist a refresh token. Returns (raw_token, token_id)."""
    raw, hashed = generate_refresh_token()
    token_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    expires = now + timedelta(days=REFRESH_TOKEN_EXPIRATION_DAYS)
    conn = get_connection()
    await conn.execute(
        """INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, revoked, created_at)
           VALUES (?, ?, ?, ?, 0, ?)""",
        (token_id, user_id, hashed, expires.isoformat(), now.isoformat()),
    )
    await conn.commit()
    return raw, token_id


async def validate_and_rotate(raw_token: str) -> dict | None:
    """Validate a refresh token, revoke it, and return user info if valid.

    Returns dict with ``user_id`` or None if invalid/expired/revoked.
    Implements rotation: the old token is revoked on use.
    """
    hashed = hash_token(raw_token)
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT id, user_id, expires_at, revoked FROM refresh_tokens WHERE token_hash = ?",
        (hashed,),
    )
    row = await cursor.fetchone()
    if not row:
        return None

    if row["revoked"]:
        return None

    expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    if expires < datetime.now(UTC):
        return None

    # Revoke old token (rotation)
    await conn.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE id = ?",
        (row["id"],),
    )
    await conn.commit()
    return {"user_id": row["user_id"]}


async def revoke(raw_token: str) -> bool:
    """Revoke a refresh token (logout). Returns True if a token was revoked."""
    hashed = hash_token(raw_token)
    conn = get_connection()
    cursor = await conn.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ? AND revoked = 0",
        (hashed,),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def revoke_all_for_user(user_id: str) -> int:
    """Revoke all refresh tokens for a user (e.g. password change). Returns count."""
    conn = get_connection()
    cursor = await conn.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0",
        (user_id,),
    )
    await conn.commit()
    return cursor.rowcount


class RefreshTokenRepo:
    create = staticmethod(create)
    validate_and_rotate = staticmethod(validate_and_rotate)
    revoke = staticmethod(revoke)
    revoke_all_for_user = staticmethod(revoke_all_for_user)


refresh_token_repo = RefreshTokenRepo()
