"""Xero OAuth 2.0 routes — connect, callback, disconnect, tenants."""
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from identity.application.auth_service import require_role
from shared.infrastructure.config import XERO_CLIENT_ID, XERO_CLIENT_SECRET, XERO_REDIRECT_URI
from identity.infrastructure.org_settings_repo import (
    clear_xero_tokens,
    get_org_settings,
    upsert_org_settings,
)

router = APIRouter(prefix="/xero", tags=["xero"])

XERO_AUTH_URL = "https://login.xero.com/identity/connect/authorize"
XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_SCOPES = "openid profile email accounting.transactions accounting.contacts offline_access"

# Simple in-process state store for CSRF protection (process-scoped, sufficient for single-instance)
_pending_states: dict[str, str] = {}  # state -> org_id


def _require_xero_configured():
    if not XERO_CLIENT_ID or not XERO_CLIENT_SECRET or not XERO_REDIRECT_URI:
        raise HTTPException(
            status_code=503,
            detail="Xero OAuth not configured. Set XERO_CLIENT_ID, XERO_CLIENT_SECRET, and XERO_REDIRECT_URI.",
        )


@router.get("/connect")
async def xero_connect(current_user: dict = Depends(require_role("admin"))):
    """Initiate Xero OAuth 2.0 Authorization Code flow. Redirects to Xero consent page."""
    _require_xero_configured()
    org_id = current_user.get("organization_id") or "default"
    state = secrets.token_urlsafe(32)
    _pending_states[state] = org_id

    params = {
        "response_type": "code",
        "client_id": XERO_CLIENT_ID,
        "redirect_uri": XERO_REDIRECT_URI,
        "scope": XERO_SCOPES,
        "state": state,
    }
    return RedirectResponse(url=f"{XERO_AUTH_URL}?{urlencode(params)}")


@router.get("/callback")
async def xero_callback(code: str = "", state: str = "", error: str = ""):
    """Xero OAuth callback. Exchanges code for tokens, saves to org_settings."""
    _require_xero_configured()

    if error:
        raise HTTPException(status_code=400, detail=f"Xero OAuth error: {error}")

    org_id = _pending_states.pop(state, None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    import requests

    resp = requests.post(
        XERO_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": XERO_REDIRECT_URI,
            "client_id": XERO_CLIENT_ID,
            "client_secret": XERO_CLIENT_SECRET,
        },
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status_code=502, detail=f"Xero token exchange failed: {resp.text}")

    token_data = resp.json()
    expiry_ts = datetime.now(timezone.utc).timestamp() + token_data.get("expires_in", 1800)
    expiry_iso = datetime.fromtimestamp(expiry_ts, tz=timezone.utc).isoformat()

    settings = await get_org_settings(org_id)
    updated = settings.model_copy(update={
        "xero_access_token": token_data["access_token"],
        "xero_refresh_token": token_data.get("refresh_token"),
        "xero_token_expiry": expiry_iso,
    })
    await upsert_org_settings(updated)

    # Return to frontend settings page
    return RedirectResponse(url="/settings?xero=connected")


@router.get("/tenants")
async def list_xero_tenants(current_user: dict = Depends(require_role("admin"))):
    """List Xero organisations the connected token can access. Use to select tenant_id."""
    org_id = current_user.get("organization_id") or "default"
    settings = await get_org_settings(org_id)
    if not settings.xero_access_token:
        raise HTTPException(status_code=400, detail="Xero not connected for this org")

    from adapters.xero_adapter import XeroAdapter
    adapter = XeroAdapter()
    try:
        tenants = await adapter.get_tenants(settings.xero_access_token)
        return {"tenants": tenants}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch Xero tenants: {e}")


@router.post("/select-tenant")
async def select_xero_tenant(
    tenant_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    """Save the chosen Xero tenant (organisation) ID for this org."""
    org_id = current_user.get("organization_id") or "default"
    settings = await get_org_settings(org_id)
    if not settings.xero_access_token:
        raise HTTPException(status_code=400, detail="Xero not connected for this org")
    updated = settings.model_copy(update={"xero_tenant_id": tenant_id})
    saved = await upsert_org_settings(updated)
    return {"xero_tenant_id": saved.xero_tenant_id}


@router.post("/disconnect")
async def xero_disconnect(current_user: dict = Depends(require_role("admin"))):
    """Remove Xero OAuth tokens for this org."""
    org_id = current_user.get("organization_id") or "default"
    await clear_xero_tokens(org_id)
    return {"disconnected": True}


@router.get("/tracking-categories")
async def list_tracking_categories(current_user: dict = Depends(require_role("admin"))):
    """List Xero tracking categories for the connected org."""
    org_id = current_user.get("organization_id") or "default"
    settings = await get_org_settings(org_id)
    if not settings.xero_access_token:
        raise HTTPException(status_code=400, detail="Xero not connected for this org")

    from adapters.xero_factory import get_xero_gateway
    gateway = get_xero_gateway(settings)
    try:
        categories = await gateway.list_tracking_categories(settings)
        return {"tracking_categories": categories}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch tracking categories: {e}")


@router.post("/select-tracking-category")
async def select_tracking_category(
    tracking_category_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    """Save the chosen Xero tracking category ID for job_id tagging on invoice lines."""
    org_id = current_user.get("organization_id") or "default"
    settings = await get_org_settings(org_id)
    updated = settings.model_copy(update={"xero_tracking_category_id": tracking_category_id})
    saved = await upsert_org_settings(updated)
    return {"xero_tracking_category_id": saved.xero_tracking_category_id}
