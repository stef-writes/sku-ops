"""Authentication service — pure helpers + use-case orchestration.

Pure functions (hash_password, verify_password, create_token) have no IO deps.
Use-case functions (register_user, login_user, etc.) coordinate infra.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from identity.domain.user import AdminUserCreate, User, UserCreate, UserLogin
from identity.infrastructure.refresh_token_repo import refresh_token_repo
from identity.infrastructure.user_repo import user_repo
from shared.infrastructure.config import (
    ALLOW_RESET,
    DEFAULT_ORG_ID,
    JWT_ACCESS_EXPIRATION_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET,
)
from shared.infrastructure.db import get_org_id


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id: str, email: str, role: str, organization_id: str = "") -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "organization_id": organization_id or get_org_id(),
        "exp": datetime.now(UTC) + timedelta(minutes=JWT_ACCESS_EXPIRATION_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Use-case orchestration
# ---------------------------------------------------------------------------


async def register_user(data: UserCreate) -> dict:
    """Register a new admin user. Returns {token, refresh_token, user}.

    Raises ValueError if registration is disabled or email is taken.
    """
    if not ALLOW_RESET:
        raise ValueError("Public registration is disabled. Contact your administrator.")

    existing = await user_repo.get_by_email(data.email)
    if existing:
        raise ValueError("Email already registered")

    user = User(
        email=data.email,
        name=data.name,
        role="admin",
        company=data.company,
        billing_entity=data.billing_entity,
        phone=data.phone,
    )
    user_dict = user.model_dump()
    user_dict["password"] = hash_password(data.password)
    user_dict["organization_id"] = DEFAULT_ORG_ID

    await user_repo.insert(user_dict)

    org_id = DEFAULT_ORG_ID
    token = create_token(user.id, user.email, user.role, org_id)
    raw_refresh, _ = await refresh_token_repo.create(user.id)
    return {
        "token": token,
        "refresh_token": raw_refresh,
        "user": {**user.model_dump(), "organization_id": org_id},
    }


async def admin_create_user(data: AdminUserCreate) -> dict:
    """Admin creates a user in their organization.

    Returns user dict (without password). Raises ValueError if email is taken.
    """
    existing = await user_repo.get_by_email(data.email)
    if existing:
        raise ValueError("Email already registered")

    user = User(
        email=data.email,
        name=data.name,
        role=data.role,
        company=data.company,
        billing_entity=data.billing_entity,
        phone=data.phone,
    )
    user_dict = user.model_dump()
    user_dict["password"] = hash_password(data.password)
    user_dict["organization_id"] = get_org_id()

    await user_repo.insert(user_dict)

    return {k: v for k, v in user_dict.items() if k != "password"}


async def login_user(data: UserLogin) -> dict:
    """Authenticate user. Returns {token, refresh_token, user}.

    Raises ValueError on invalid credentials or disabled account.
    """
    user = await user_repo.get_by_email(data.email)
    if not user or not verify_password(data.password, user.get("password", "")):
        raise ValueError("Invalid credentials")
    if not user.get("is_active", True):
        raise ValueError("Account is disabled")

    org_id = user.get("organization_id") or DEFAULT_ORG_ID
    token = create_token(user["id"], user["email"], user["role"], org_id)
    raw_refresh, _ = await refresh_token_repo.create(user["id"])
    user_response = {k: v for k, v in user.items() if k != "password"}
    user_response["organization_id"] = org_id
    return {"token": token, "refresh_token": raw_refresh, "user": user_response}


async def refresh_tokens(refresh_token: str) -> dict:
    """Rotate refresh token. Returns {token, refresh_token}.

    Raises ValueError on invalid/expired token or disabled account.
    """
    result = await refresh_token_repo.validate_and_rotate(refresh_token)
    if not result:
        raise ValueError("Invalid or expired refresh token")

    user = await user_repo.get_by_id(result["user_id"])
    if not user:
        raise ValueError("User not found")
    if not user.is_active:
        raise ValueError("Account is disabled")

    org_id = user.organization_id or DEFAULT_ORG_ID
    token = create_token(user.id, user.email, user.role, org_id)
    new_refresh, _ = await refresh_token_repo.create(user.id)
    return {"token": token, "refresh_token": new_refresh}


async def logout(refresh_token: str) -> None:
    """Revoke a refresh token."""
    await refresh_token_repo.revoke(refresh_token)
