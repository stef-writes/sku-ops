"""Auth HTTP surface — login, /me, register.

In production, Supabase owns the auth surface (signIn, signUp, session refresh).
The backend only validates the JWT that Supabase issues.

These endpoints exist for two purposes:
  1. Dev/test: local demo users can log in without Supabase running.
  2. Supabase JWT bridge: /me returns the enriched profile (name, role, org)
     by looking up the users table after the Supabase JWT is verified.

The login and register routes are ONLY mounted in development/test environments
(gated in routes.py). The /me route is always mounted — Supabase-issued JWTs
will hit it on every page load to hydrate the user profile.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import bcrypt
import jwt as pyjwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared.api.deps import CurrentUserDep
from shared.infrastructure.config import (
    JWT_ACCESS_EXPIRATION_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET,
)
from shared.infrastructure.user_repo import fetch_by_email as _fetch_user_by_email_repo
from shared.infrastructure.user_repo import fetch_by_id as _fetch_user_by_id_repo
from shared.infrastructure.user_repo import insert_user as _insert_user_repo
from shared.kernel.constants import DEFAULT_ORG_ID

router = APIRouter(prefix="/auth", tags=["auth"])

# Routes that are only safe in dev/test — login and register use the local
# users table and a shared JWT secret. In production, Supabase owns this surface.
dev_router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request / Response models ─────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    organization_id: str
    company: str
    billing_entity: str
    phone: str


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


# ── Helpers ───────────────────────────────────────────────────────────────────


def _issue_token(user_row: dict) -> str:
    import time  # stdlib — no cycle risk, kept inline for locality

    payload = {
        "sub": user_row["id"],
        "user_id": user_row["id"],
        "email": user_row["email"],
        "name": user_row["name"],
        "role": user_row["role"],
        "organization_id": user_row.get("organization_id") or DEFAULT_ORG_ID,
        "exp": int(time.time()) + JWT_ACCESS_EXPIRATION_MINUTES * 60,
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _row_to_user(row) -> UserResponse:
    return UserResponse(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        role=row["role"],
        organization_id=row["organization_id"] or DEFAULT_ORG_ID,
        company=row["company"] or "",
        billing_entity=row["billing_entity"] or "",
        phone=row["phone"] or "",
    )


async def _fetch_user_by_email(email: str):
    return await _fetch_user_by_email_repo(email)


async def _fetch_user_by_id(user_id: str):
    return await _fetch_user_by_id_repo(user_id)


# ── Routes ────────────────────────────────────────────────────────────────────


def _user_from_claims(current_user) -> UserResponse:
    """Build a UserResponse directly from JWT claims (no DB lookup)."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
        organization_id=current_user.organization_id,
        company="",
        billing_entity="",
        phone="",
    )


@router.get("/me")
async def me(current_user: CurrentUserDep) -> UserResponse:
    """Return the enriched user profile for the authenticated caller.

    Works with both dev-issued JWTs and Supabase-issued JWTs — looks up the
    users table by sub/user_id so profile fields (company, billing_entity, etc.)
    are always populated from the source of truth.

    Falls back to JWT claims if the user row doesn't exist (Supabase-first new
    users not yet in the local profile table) or if the DB is not initialised
    (e.g. smoke-test context).
    """
    try:
        row = await _fetch_user_by_id(current_user.id)
        if not row and current_user.email:
            row = await _fetch_user_by_email(current_user.email)
    except RuntimeError:
        return _user_from_claims(current_user)
    if not row:
        return _user_from_claims(current_user)
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    return _row_to_user(row)


@dev_router.post("/refresh")
async def refresh(current_user: CurrentUserDep) -> AuthResponse:
    """Dev-only: issue a fresh JWT for the currently authenticated user.

    Called by the frontend before the current token expires to keep the
    session alive without forcing a re-login.
    """
    try:
        row = await _fetch_user_by_id(current_user.id)
    except RuntimeError:
        row = None
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    token = _issue_token(dict(row))
    return AuthResponse(token=token, user=_row_to_user(row))


@dev_router.post("/login")
async def login(body: LoginRequest) -> AuthResponse:
    """Dev-only: authenticate with email + password against the local users table.

    Not mounted in production. In production, Supabase handles login and issues
    the JWT directly to the frontend.
    """
    try:
        row = await _fetch_user_by_email(body.email)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail="Database not available") from e
    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    if not bcrypt.checkpw(body.password.encode("utf-8"), row["password"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _issue_token(dict(row))
    return AuthResponse(token=token, user=_row_to_user(row))


@dev_router.post("/register")
async def register(body: RegisterRequest) -> AuthResponse:
    """Dev-only: create a new admin user in the local users table.

    Not mounted in production. In production, Supabase handles registration.
    Admin creates contractors via the contractors endpoint.
    """
    try:
        existing = await _fetch_user_by_email(body.email)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail="Database not available") from e
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    hashed = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    await _insert_user_repo(
        user_id=user_id,
        email=body.email,
        password_hash=hashed,
        name=body.name,
        organization_id=DEFAULT_ORG_ID,
        created_at=now,
    )

    row = await _fetch_user_by_id(user_id)
    token = _issue_token(dict(row))
    return AuthResponse(token=token, user=_row_to_user(row))
