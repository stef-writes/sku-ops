"""Org settings API — Xero account codes and connection status."""
from fastapi import APIRouter, Depends

from identity.application.auth_service import require_role
from identity.domain.org_settings import OrgSettings, OrgSettingsUpdate
from identity.infrastructure.org_settings_repo import get_org_settings, upsert_org_settings

router = APIRouter(prefix="/settings", tags=["settings"])


def _mask(settings: OrgSettings) -> dict:
    """Return settings dict with secrets masked."""
    d = settings.model_dump()
    if d.get("xero_client_secret"):
        d["xero_client_secret"] = "***"
    if d.get("xero_access_token"):
        d["xero_access_token"] = "***"
    if d.get("xero_refresh_token"):
        d["xero_refresh_token"] = "***"
    d["xero_connected"] = bool(settings.xero_tenant_id and settings.xero_access_token)
    return d


@router.get("/xero")
async def get_xero_settings(current_user: dict = Depends(require_role("admin"))):
    """Return Xero config for the org. Secrets are masked in the response."""
    org_id = current_user.get("organization_id") or "default"
    settings = await get_org_settings(org_id)
    return _mask(settings)


@router.put("/xero")
async def update_xero_settings(
    data: OrgSettingsUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    """Update Xero account codes and/or API credentials."""
    org_id = current_user.get("organization_id") or "default"
    settings = await get_org_settings(org_id)

    update = data.model_dump(exclude_none=True)
    merged = settings.model_copy(update=update)
    saved = await upsert_org_settings(merged)
    return _mask(saved)
