"""Xero configuration health check — runs at server startup.

Logs warnings for missing or expired config. Never raises — missing Xero
config is non-fatal (StubXeroAdapter handles it). The goal is to surface
misconfiguration immediately at boot, not at the moment the first sync fires.
"""
import logging
from datetime import UTC, datetime, timezone

from identity.application.org_service import get_org_settings

logger = logging.getLogger(__name__)

_REQUIRED_ACCOUNT_CODES = [
    ("xero_sales_account_code", "Sales account code", "invoices will post to wrong account"),
    ("xero_cogs_account_code", "COGS account code", "COGS journal will be skipped"),
    ("xero_inventory_account_code", "Inventory account code", "PO Bills will fail"),
    ("xero_ap_account_code", "AP account code", "vendor bills will have no AP posting"),
]


def _is_token_expired(token_expiry: str) -> bool:
    try:
        expiry = datetime.fromisoformat(token_expiry)
        return datetime.now(UTC).timestamp() >= expiry.timestamp() - 60
    except Exception:
        return True


async def check_xero_configuration(org_id: str) -> list[str]:
    """Return a list of warning strings. Empty list means configuration is clean."""
    warnings: list[str] = []
    try:
        settings = await get_org_settings(org_id)
    except Exception as e:
        warnings.append(f"XERO: Could not load org settings for {org_id}: {e}")
        return warnings

    if not settings.xero_access_token:
        warnings.append(
            "XERO: No access token configured. Xero sync will be skipped (StubAdapter active). "
            "Connect Xero at /settings to enable live sync."
        )
        return warnings  # rest of checks are irrelevant without a token

    if not settings.xero_tenant_id:
        warnings.append(
            "XERO: Access token is set but xero_tenant_id is missing. "
            "All API calls will fail with 403. Re-authorise Xero."
        )

    if settings.xero_token_expiry and _is_token_expired(settings.xero_token_expiry):
        warnings.append(
            "XERO: Access token is expired. The first sync will attempt a refresh. "
            "If refresh_token is also expired, re-authorise Xero immediately."
        )

    if not settings.xero_refresh_token:
        warnings.append(
            "XERO: No refresh token stored. Token refresh will fail when the access token expires."
        )

    for field, label, consequence in _REQUIRED_ACCOUNT_CODES:
        if not getattr(settings, field, None):
            warnings.append(f"XERO: {label} is not configured — {consequence}.")

    return warnings


async def run_startup_check(org_id: str) -> None:
    """Run the check and emit all warnings to the logger. Called from lifespan."""
    warnings = await check_xero_configuration(org_id)
    if not warnings:
        logger.info("Xero configuration OK for org %s", org_id)
    else:
        for w in warnings:
            logger.warning(w)
