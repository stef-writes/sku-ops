"""FastAPI authentication dependencies — transport-layer concern."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from identity.application.queries import user_repo
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
        user = await user_repo.get_by_id(payload["user_id"])
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        if not user.is_active:
            raise HTTPException(status_code=401, detail="User account is disabled")
        org_id = user.organization_id or payload.get("organization_id") or DEFAULT_ORG_ID
        user_id_var.set(user.id)
        org_id_var.set(org_id)
        return CurrentUser(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
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
