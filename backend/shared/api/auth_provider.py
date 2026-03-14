"""Auth provider abstraction — claim extraction from decoded JWT payloads.

The backend validates JWTs using JWT_SECRET regardless of provider. This
module handles the differences in claim shape between providers.

Configure with AUTH_PROVIDER env var:
  supabase  (default) — role in app_metadata.role, user id in sub
  internal  — role top-level claim, user id in user_id or sub

Adding a new provider:
  1. Add a new branch in resolve_claims() below.
  2. Add the provider name to AUTH_PROVIDER validation in config.py.
  3. No other code changes needed — all callers use resolve_claims().
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.infrastructure.config import AUTH_PROVIDER


@dataclass(frozen=True)
class ResolvedClaims:
    user_id: str
    email: str
    name: str
    role: str
    organization_id: str | None


def resolve_claims(payload: dict) -> ResolvedClaims:
    """Extract standardised claims from a decoded JWT payload.

    Returns ResolvedClaims with organization_id=None when the token has no
    org claim — callers decide whether to reject or apply the dev fallback.

    Raises ValueError if a required claim (role, user_id) is missing.
    """
    if AUTH_PROVIDER == "internal":
        return _resolve_internal(payload)
    return _resolve_supabase(payload)


def _resolve_supabase(payload: dict) -> ResolvedClaims:
    """Supabase JWT shape.

    - user id: sub
    - role: app_metadata.role (custom claim set via Supabase admin API or auth hook)
      Falls back to top-level role claim if app_metadata.role is absent, but
      excludes the Supabase system value "authenticated".
    - name: user_metadata.name
    """
    user_id = payload.get("sub") or payload.get("user_id") or ""
    if not user_id:
        raise ValueError("missing user id (sub)")

    app_role = (payload.get("app_metadata") or {}).get("role") or ""
    top_role = payload.get("role") or ""
    if top_role == "authenticated":
        top_role = ""
    role = app_role or top_role
    if not role:
        raise ValueError("missing role claim")

    email = payload.get("email") or ""
    name = payload.get("name") or (payload.get("user_metadata") or {}).get("name") or ""
    org_id = payload.get("organization_id") or None

    return ResolvedClaims(
        user_id=user_id,
        email=email,
        name=name,
        role=role,
        organization_id=org_id,
    )


def _resolve_internal(payload: dict) -> ResolvedClaims:
    """Internal / dev JWT shape.

    - user id: user_id or sub
    - role: top-level role claim
    - name: top-level name claim
    """
    user_id = payload.get("user_id") or payload.get("sub") or ""
    if not user_id:
        raise ValueError("missing user id")

    role = payload.get("role") or ""
    if not role:
        raise ValueError("missing role claim")

    email = payload.get("email") or ""
    name = payload.get("name") or ""
    org_id = payload.get("organization_id") or None

    return ResolvedClaims(
        user_id=user_id,
        email=email,
        name=name,
        role=role,
        organization_id=org_id,
    )
