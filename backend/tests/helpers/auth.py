"""Shared auth helpers for tests."""

import time

import jwt

from shared.infrastructure.config import JWT_ALGORITHM, JWT_SECRET
from shared.kernel.constants import DEFAULT_ORG_ID


def make_token(
    user_id: str = "user-1",
    org_id: str = DEFAULT_ORG_ID,
    role: str = "admin",
    name: str = "Test User",
    email: str = "",
    expired: bool = False,
) -> str:
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "email": email or f"{user_id}@test.com",
        "organization_id": org_id,
        "role": role,
        "name": name,
        "exp": int(time.time()) + (-3600 if expired else 3600),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def admin_headers() -> dict:
    token = make_token("user-1", role="admin", email="test@test.com")
    return {"Authorization": f"Bearer {token}"}


def contractor_headers() -> dict:
    token = make_token("contractor-1", role="contractor", email="contractor@test.com")
    return {"Authorization": f"Bearer {token}"}


def admin_token() -> str:
    return make_token("user-1", role="admin", email="test@test.com")


def contractor_token() -> str:
    return make_token("contractor-1", role="contractor", email="contractor@test.com")


def expired_token() -> str:
    return make_token(expired=True)
