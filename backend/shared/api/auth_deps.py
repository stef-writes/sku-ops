"""FastAPI authentication dependencies — transport-layer concern.

Validates JWTs and builds CurrentUser from token claims. No DB
roundtrip required — all user data comes from the token payload.

AUTH_PROVIDER in config controls the JWT claim shape:
  supabase  (default) — role in app_metadata.role, user id in sub
  internal  — role top-level claim, user id in user_id or sub

In deployed environments, tokens without an explicit organization_id
claim are rejected with 401. In development/test the DEFAULT_ORG_ID
fallback is applied so local tooling and seeds work without org claims.
"""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from shared.api.auth_provider import resolve_claims
from shared.infrastructure.config import (
    JWT_ALGORITHM,
    JWT_SECRET,
    is_deployed,
)
from shared.infrastructure.logging_config import org_id_var, user_id_var
from shared.kernel.constants import DEFAULT_ORG_ID
from shared.kernel.types import CurrentUser

security = HTTPBearer()

BearerToken = Annotated[HTTPAuthorizationCredentials, Depends(security)]


async def get_current_user(
    credentials: BearerToken,
) -> CurrentUser:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        claims = resolve_claims(payload)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="Token expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e

    if is_deployed and claims.organization_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid token: missing organization_id claim",
        )
    org_id = claims.organization_id or DEFAULT_ORG_ID

    user_id_var.set(claims.user_id)
    org_id_var.set(org_id)

    return CurrentUser(
        id=claims.user_id,
        email=claims.email,
        name=claims.name,
        role=claims.role,
        organization_id=org_id,
    )


def require_role(*roles):
    async def role_checker(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return role_checker
