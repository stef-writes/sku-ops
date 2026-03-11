"""Xero API constants, auth helpers, and shared utilities."""

import logging
from datetime import UTC, datetime

import httpx

from finance.domain.xero_settings import XeroSettings

logger = logging.getLogger(__name__)

XERO_API = "https://api.xero.com/api.xro/2.0"
XERO_OAUTH_ENDPOINT = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"


class XeroBaseMixin:
    def _auth_headers(self, settings: XeroSettings) -> dict:
        return {
            "Authorization": f"Bearer {settings.xero_access_token}",
            "Xero-tenant-id": settings.xero_tenant_id or "",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _is_token_expired(self, settings: XeroSettings) -> bool:
        if not settings.xero_token_expiry:
            return True
        try:
            expiry = datetime.fromisoformat(settings.xero_token_expiry)
            # Treat as expired 60 s before actual expiry to avoid edge races
            return datetime.now(UTC).timestamp() >= expiry.timestamp() - 60
        except (ValueError, TypeError):
            return True

    async def _ensure_tracking_option(
        self,
        category_id: str,
        option_name: str,
        settings: XeroSettings,
        client: httpx.AsyncClient,
    ) -> None:
        """Upsert a tracking option in Xero so it can be referenced on line items.

        Xero rejects invoices and journals that reference a tracking Option value
        that does not already exist in the category. Because job IDs are created
        dynamically in this app, we must ensure the option exists before use.

        GET to fetch existing options, PUT only when the option is absent — making
        this call idempotent and low-overhead for the common (already-exists) case.
        """
        resp = await client.get(
            f"{XERO_API}/TrackingCategories/{category_id}",
            headers=self._auth_headers(settings),
            timeout=15,
        )
        resp.raise_for_status()
        categories = resp.json().get("TrackingCategories", [])
        existing_names = {
            opt.get("Name", "")
            for cat in categories
            for opt in cat.get("Options", [])
            if opt.get("Status") == "ACTIVE"
        }
        if option_name not in existing_names:
            create_resp = await client.put(
                f"{XERO_API}/TrackingCategories/{category_id}/Options",
                headers=self._auth_headers(settings),
                json={"Options": [{"Name": option_name}]},
                timeout=15,
            )
            create_resp.raise_for_status()
            logger.info("Created Xero tracking option %r in category %s", option_name, category_id)


def _xero_status(sku_status: str) -> str:
    return {
        "draft": "DRAFT",
        "approved": "SUBMITTED",
        "sent": "SUBMITTED",
        "paid": "AUTHORISED",
    }.get(sku_status, "DRAFT")
