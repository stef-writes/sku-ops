"""Authentication helpers and dependencies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from identity.infrastructure.user_repo import user_repo
from kernel.types import CurrentUser
from shared.infrastructure.config import (
    DEFAULT_ORG_ID,
    JWT_ACCESS_EXPIRATION_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET,
)
from shared.infrastructure.logging_config import org_id_var, user_id_var

security = HTTPBearer()

BearerToken = Annotated[HTTPAuthorizationCredentials, Depends(security)]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id: str, email: str, role: str, organization_id: str = DEFAULT_ORG_ID) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "organization_id": organization_id or DEFAULT_ORG_ID,
        "exp": datetime.now(UTC) + timedelta(minutes=JWT_ACCESS_EXPIRATION_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(
    credentials: BearerToken,
) -> CurrentUser:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await user_repo.get_by_id(payload["user_id"])
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        if not user.get("is_active", True):
            raise HTTPException(status_code=401, detail="User account is disabled")
        org_id = user.get("organization_id") or payload.get("organization_id") or DEFAULT_ORG_ID
        user["organization_id"] = org_id
        user_id_var.set(user.get("id", ""))
        org_id_var.set(org_id)
        return CurrentUser(**user)
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="Token expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e


def require_role(*roles):
    async def role_checker(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return role_checker
