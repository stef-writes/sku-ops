"""Authentication routes."""
from fastapi import APIRouter, HTTPException, Depends

from auth import hash_password, verify_password, create_token, get_current_user
from models import ROLES, User, UserCreate, UserLogin
from repositories import user_repo

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

    await user_repo.insert(user_dict)

    token = create_token(user.id, user.email, user.role)
    return {"token": token, "user": user.model_dump()}


@router.post("/login")
async def login(data: UserLogin):
    user = await user_repo.get_by_email(data.email)
    if not user or not verify_password(data.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="Account is disabled")

    token = create_token(user["id"], user["email"], user["role"])
    user_response = {k: v for k, v in user.items() if k not in ["password"]}
    return {"token": token, "user": user_response}


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
