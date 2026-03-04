"""Authentication routes."""
from fastapi import APIRouter, HTTPException, Depends

from identity.application.auth_service import hash_password, verify_password, create_token, get_current_user
from identity.domain.user import ROLES, User, UserCreate, UserLogin
from identity.infrastructure.user_repo import user_repo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(data: UserCreate):
    existing = await user_repo.get_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    if data.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {ROLES}")

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
    user_dict["organization_id"] = data.organization_id or "default"

    await user_repo.insert(user_dict)

    org_id = user_dict.get("organization_id") or "default"
    token = create_token(user.id, user.email, user.role, org_id)
    return {"token": token, "user": {**user.model_dump(), "organization_id": org_id}}


@router.post("/login")
async def login(data: UserLogin):
    user = await user_repo.get_by_email(data.email)
    if not user or not verify_password(data.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="Account is disabled")

    org_id = user.get("organization_id") or "default"
    token = create_token(user["id"], user["email"], user["role"], org_id)
    user_response = {k: v for k, v in user.items() if k not in ["password"]}
    user_response["organization_id"] = org_id
    return {"token": token, "user": user_response}


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
