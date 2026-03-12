"""FastAPI authentication dependencies — transport-layer concern.

Validates JWTs and builds CurrentUser from token claims. No DB
roundtrip required — all user data comes from the token payload.
"""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from shared.infrastructure.config import (
    DEFAULT_ORG_ID,
    JWT_ALGORITHM,
    JWT_SECRET,
)
from shared.infrastructure.logging_config import org_id_var, user_id_var
from shared.kernel.types import CurrentUser

security = HTTPBearer()

BearerToken = Annotated[HTTPAuthorizationCredentials, Depends(security)]


async def get_current_user(
    credentials: BearerToken,
) -> CurrentUser:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id") or payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user_id")
        email = payload.get("email", "")
        name = payload.get("name", "")
        role = payload.get("role", "admin")
        org_id = payload.get("organization_id") or DEFAULT_ORG_ID
        user_id_var.set(user_id)
        org_id_var.set(org_id)
        return CurrentUser(
            id=user_id,
            email=email,
            name=name,
            role=role,
            organization_id=org_id,
        )
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
