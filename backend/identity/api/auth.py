"""Authentication routes."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from identity.application.auth_service import (
    create_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from identity.domain.user import AdminUserCreate, User, UserCreate, UserLogin
from identity.infrastructure.refresh_token_repo import refresh_token_repo
from identity.infrastructure.user_repo import user_repo
from kernel.types import CurrentUser
from shared.infrastructure.config import ALLOW_RESET
from shared.infrastructure.middleware.audit import audit_log
from shared.infrastructure.middleware.rate_limit import auth_limit

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/register")
@auth_limit
async def register(data: UserCreate, request: Request):
    if not ALLOW_RESET:
        raise HTTPException(
            status_code=403,
            detail="Public registration is disabled. Contact your administrator.",
        )

    existing = await user_repo.get_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        name=data.name,
        role="warehouse_manager",
        company=data.company,
        billing_entity=data.billing_entity,
        phone=data.phone,
    )
    user_dict = user.model_dump()
    user_dict["password"] = hash_password(data.password)
    user_dict["organization_id"] = "default"

    await user_repo.insert(user_dict)

    org_id = "default"
    token = create_token(user.id, user.email, user.role, org_id)
    raw_refresh, _ = await refresh_token_repo.create(user.id)
    await audit_log(user_id=user.id, action="auth.register", resource_type="user", resource_id=user.id, request=request, org_id=org_id)
    return {
        "token": token,
        "refresh_token": raw_refresh,
        "user": {**user.model_dump(), "organization_id": org_id},
    }


@router.post("/users")
async def admin_create_user(
    data: AdminUserCreate,
    request: Request,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Admin-only: create a user with explicit role in the admin's organization."""
    existing = await user_repo.get_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    org_id = current_user.organization_id
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
    user_dict["organization_id"] = org_id

    await user_repo.insert(user_dict)

    await audit_log(
        user_id=current_user.id, action="auth.admin_create_user",
        resource_type="user", resource_id=user.id, request=request, org_id=org_id,
    )
    return {k: v for k, v in user_dict.items() if k != "password"}


@router.post("/login")
@auth_limit
async def login(data: UserLogin, request: Request):
    user = await user_repo.get_by_email(data.email)
    if not user or not verify_password(data.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="Account is disabled")

    org_id = user.get("organization_id") or "default"
    token = create_token(user["id"], user["email"], user["role"], org_id)
    raw_refresh, _ = await refresh_token_repo.create(user["id"])
    user_response = {k: v for k, v in user.items() if k not in ["password"]}
    user_response["organization_id"] = org_id
    await audit_log(user_id=user["id"], action="auth.login", resource_type="user", resource_id=user["id"], request=request, org_id=org_id)
    return {"token": token, "refresh_token": raw_refresh, "user": user_response}


@router.post("/refresh")
@auth_limit
async def refresh(data: RefreshRequest, request: Request):
    """Exchange a valid refresh token for a new access + refresh token pair (rotation)."""
    result = await refresh_token_repo.validate_and_rotate(data.refresh_token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await user_repo.get_by_id(result["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="Account is disabled")

    org_id = user.get("organization_id") or "default"
    token = create_token(user["id"], user["email"], user["role"], org_id)
    new_refresh, _ = await refresh_token_repo.create(user["id"])
    return {"token": token, "refresh_token": new_refresh}


@router.post("/logout")
@auth_limit
async def logout(data: LogoutRequest, request: Request):
    """Revoke the refresh token."""
    await refresh_token_repo.revoke(data.refresh_token)
    return {"detail": "Logged out"}


@router.get("/me")
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    return current_user
