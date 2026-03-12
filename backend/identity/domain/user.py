"""User and auth models."""

import re

from pydantic import BaseModel, field_validator

from shared.kernel.entity import Entity

ROLES = ["admin", "contractor"]

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
_MIN_PASSWORD_LENGTH = 8


def _validate_email(v: str) -> str:
    v = v.strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("Invalid email address")
    return v


def _validate_password(v: str) -> str:
    if len(v) < _MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {_MIN_PASSWORD_LENGTH} characters")
    return v


class UserCreate(BaseModel):
    """Public self-registration — no role or org selection allowed."""

    email: str
    password: str
    name: str
    company: str | None = None
    billing_entity: str | None = None
    phone: str | None = None

    _normalize_email = field_validator("email", mode="before")(_validate_email)
    _check_password = field_validator("password", mode="before")(_validate_password)


class AdminUserCreate(BaseModel):
    """Admin-only user creation with explicit role and org assignment."""

    email: str
    password: str
    name: str
    role: str = "admin"
    company: str | None = None
    billing_entity: str | None = None
    phone: str | None = None

    _normalize_email = field_validator("email", mode="before")(_validate_email)
    _check_password = field_validator("password", mode="before")(_validate_password)

    @field_validator("role", mode="before")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError(f"Invalid role. Must be one of: {ROLES}")
        return v


class UserUpdate(BaseModel):
    name: str | None = None
    company: str | None = None
    billing_entity: str | None = None
    phone: str | None = None
    is_active: bool | None = None


class UserLogin(BaseModel):
    email: str
    password: str


class User(Entity):
    email: str
    name: str
    role: str = "admin"
    company: str | None = None
    billing_entity: str | None = None
    phone: str | None = None
    is_active: bool = True
