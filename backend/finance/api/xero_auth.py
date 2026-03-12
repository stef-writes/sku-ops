"""Xero OAuth 2.0 routes — connect, callback, disconnect, tenants."""

import secrets
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from finance.adapters.invoicing_factory import get_invoicing_gateway
from finance.adapters.xero_adapter import XeroAdapter
from finance.application.org_settings_service import (
    clear_xero_tokens,
    get_org_settings,
    pop_oauth_state,
    save_oauth_state,
    upsert_org_settings,
)
from finance.domain.xero_settings import XeroSettings
from shared.api.deps import AdminDep
from shared.infrastructure.config import (
    FRONTEND_URL,
    XERO_CLIENT_ID,
    XERO_CLIENT_SECRET,
    XERO_REDIRECT_URI,
)
from shared.infrastructure.logging_config import org_id_var

router = APIRouter(prefix="/xero", tags=["xero"])

XERO_AUTH_URL = "https://login.xero.com/identity/connect/authorize"
XERO_OAUTH_URL = "https://identity.xero.com/connect/token"
XERO_SCOPES = "openid profile email accounting.transactions accounting.contacts offline_access"


def _require_xero_configured():
    if not XERO_CLIENT_ID or not XERO_CLIENT_SECRET or not XERO_REDIRECT_URI:
        raise HTTPException(
            status_code=503,
            detail="Xero OAuth not configured. Set XERO_CLIENT_ID, XERO_CLIENT_SECRET, and XERO_REDIRECT_URI.",
        )


@router.get("/connect")
async def xero_connect(current_user: AdminDep):
    """Initiate Xero OAuth 2.0 Authorization Code flow. Redirects to Xero consent page."""
    _require_xero_configured()
    state = secrets.token_urlsafe(32)
    await save_oauth_state(state)

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

    org_id = await pop_oauth_state(state)
    if not org_id:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    org_id_var.set(org_id)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            XERO_OAUTH_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": XERO_REDIRECT_URI,
                "client_id": XERO_CLIENT_ID,
                "client_secret": XERO_CLIENT_SECRET,
            },
            timeout=15,
        )
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"Xero token exchange failed: {resp.text}")

    token_data = resp.json()
    expiry_ts = datetime.now(UTC).timestamp() + token_data.get("expires_in", 1800)
    expiry_iso = datetime.fromtimestamp(expiry_ts, tz=UTC).isoformat()

    settings = await get_org_settings()
    updated = settings.model_copy(
        update={
            "xero_access_token": token_data["access_token"],
            "xero_refresh_token": token_data.get("refresh_token"),
            "xero_token_expiry": expiry_iso,
        }
    )
    await upsert_org_settings(updated)

    redirect_target = (
        f"{FRONTEND_URL}/settings?xero=connected" if FRONTEND_URL else "/settings?xero=connected"
    )
    return RedirectResponse(url=redirect_target)


@router.get("/tenants")
async def list_xero_tenants(current_user: AdminDep):
    """List Xero organisations the connected token can access. Use to select tenant_id."""
    settings = await get_org_settings()
    if not settings.xero_access_token:
        raise HTTPException(status_code=400, detail="Xero not connected for this org")

    adapter = XeroAdapter()
    try:
        tenants = await adapter.get_tenants(settings.xero_access_token)
        return {"tenants": tenants}
    except (httpx.HTTPError, RuntimeError, OSError) as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch Xero tenants: {e}") from e


@router.post("/select-tenant")
async def select_xero_tenant(
    tenant_id: str,
    current_user: AdminDep,
):
    """Save the chosen Xero tenant (organisation) ID for this org."""
    settings = await get_org_settings()
    if not settings.xero_access_token:
        raise HTTPException(status_code=400, detail="Xero not connected for this org")
    updated = settings.model_copy(update={"xero_tenant_id": tenant_id})
    saved = await upsert_org_settings(updated)
    return {"xero_tenant_id": saved.xero_tenant_id}


@router.post("/disconnect")
async def xero_disconnect(current_user: AdminDep):
    """Remove Xero OAuth tokens for this org."""
    await clear_xero_tokens()
    return {"disconnected": True}


@router.get("/tracking-categories")
async def list_tracking_categories(current_user: AdminDep):
    """List Xero tracking categories for the connected org."""
    settings = await get_org_settings()
    if not settings.xero_access_token:
        raise HTTPException(status_code=400, detail="Xero not connected for this org")

    xero_settings = XeroSettings.model_validate(settings.model_dump())
    gateway = get_invoicing_gateway(xero_settings)
    try:
        categories = await gateway.list_tracking_categories(xero_settings)
        return {"tracking_categories": categories}
    except (httpx.HTTPError, RuntimeError, OSError) as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch tracking categories: {e}"
        ) from e


@router.post("/select-tracking-category")
async def select_tracking_category(
    tracking_category_id: str,
    current_user: AdminDep,
):
    """Save the chosen Xero tracking category ID for job_id tagging on invoice lines."""
    settings = await get_org_settings()
    updated = settings.model_copy(update={"xero_tracking_category_id": tracking_category_id})
    saved = await upsert_org_settings(updated)
    return {"xero_tracking_category_id": saved.xero_tracking_category_id}
