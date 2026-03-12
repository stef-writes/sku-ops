"""Authentication routes — thin controllers delegating to auth_service."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from identity.application.auth_service import (
    admin_create_user as _admin_create_user,
)
from identity.application.auth_service import (
    login_user,
    logout,
    refresh_tokens,
    register_user,
)
from identity.domain.user import AdminUserCreate, UserCreate, UserLogin
from shared.api.deps import AdminDep, CurrentUserDep
from shared.infrastructure.middleware.audit import audit_log

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/register")
async def register(data: UserCreate, request: Request):
    try:
        result = await register_user(data)
    except ValueError as e:
        status = 403 if "disabled" in str(e).lower() else 400
        raise HTTPException(status_code=status, detail=str(e)) from e
    await audit_log(
        user_id=result["user"]["id"],
        action="auth.register",
        resource_type="user",
        resource_id=result["user"]["id"],
        request=request,
        org_id=result["user"].get("organization_id"),
    )
    return result


@router.post("/users")
async def admin_create_user_route(
    data: AdminUserCreate,
    request: Request,
    current_user: AdminDep,
):
    """Admin-only: create a user with explicit role in the admin's organization."""
    try:
        user_dict = await _admin_create_user(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await audit_log(
        user_id=current_user.id,
        action="auth.admin_create_user",
        resource_type="user",
        resource_id=user_dict.get("id"),
        request=request,
        org_id=current_user.organization_id,
    )
    return user_dict


@router.post("/login")
async def login(data: UserLogin, request: Request):
    try:
        result = await login_user(data)
    except ValueError as e:
        detail = str(e)
        status = 401
        raise HTTPException(status_code=status, detail=detail) from e
    await audit_log(
        user_id=result["user"]["id"],
        action="auth.login",
        resource_type="user",
        resource_id=result["user"]["id"],
        request=request,
        org_id=result["user"].get("organization_id"),
    )
    return result


@router.post("/refresh")
async def refresh(data: RefreshRequest, _request: Request):
    """Exchange a valid refresh token for a new access + refresh token pair (rotation)."""
    try:
        return await refresh_tokens(data.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.post("/logout")
async def logout_route(data: LogoutRequest, _request: Request):
    """Revoke the refresh token."""
    await logout(data.refresh_token)
    return {"detail": "Logged out"}


@router.get("/me")
async def get_me(current_user: CurrentUserDep):
    return current_user
