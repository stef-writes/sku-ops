"""Per-org settings repository."""
from datetime import datetime, timezone
from typing import Optional

from shared.infrastructure.database import get_connection
from identity.domain.org_settings import OrgSettings


async def get_org_settings(org_id: str) -> OrgSettings:
    """Return org settings, or defaults if not yet configured."""
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM org_settings WHERE organization_id = ?",
        (org_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return OrgSettings(organization_id=org_id)
    return OrgSettings(**dict(row))


async def upsert_org_settings(settings: OrgSettings) -> OrgSettings:
    """Insert or replace org settings."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    await conn.execute(
        """INSERT INTO org_settings (
               organization_id, xero_client_id, xero_client_secret,
               xero_tenant_id, xero_access_token, xero_refresh_token,
               xero_token_expiry, xero_sales_account_code,
               xero_cogs_account_code, xero_inventory_account_code,
               xero_ap_account_code, xero_tracking_category_id,
               xero_tax_type, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(organization_id) DO UPDATE SET
               xero_client_id = excluded.xero_client_id,
               xero_client_secret = excluded.xero_client_secret,
               xero_tenant_id = excluded.xero_tenant_id,
               xero_access_token = excluded.xero_access_token,
               xero_refresh_token = excluded.xero_refresh_token,
               xero_token_expiry = excluded.xero_token_expiry,
               xero_sales_account_code = excluded.xero_sales_account_code,
               xero_cogs_account_code = excluded.xero_cogs_account_code,
               xero_inventory_account_code = excluded.xero_inventory_account_code,
               xero_ap_account_code = excluded.xero_ap_account_code,
               xero_tracking_category_id = excluded.xero_tracking_category_id,
               xero_tax_type = excluded.xero_tax_type,
               updated_at = excluded.updated_at
        """,
        (
            settings.organization_id,
            settings.xero_client_id,
            settings.xero_client_secret,
            settings.xero_tenant_id,
            settings.xero_access_token,
            settings.xero_refresh_token,
            settings.xero_token_expiry,
            settings.xero_sales_account_code,
            settings.xero_cogs_account_code,
            settings.xero_inventory_account_code,
            settings.xero_ap_account_code,
            settings.xero_tracking_category_id,
            settings.xero_tax_type,
            now,
        ),
    )
    await conn.commit()
    return await get_org_settings(settings.organization_id)


async def clear_xero_tokens(org_id: str) -> None:
    """Remove Xero OAuth tokens for an org (disconnect)."""
    conn = get_connection()
    await conn.execute(
        """UPDATE org_settings
           SET xero_access_token = NULL, xero_refresh_token = NULL,
               xero_tenant_id = NULL, xero_token_expiry = NULL,
               updated_at = ?
           WHERE organization_id = ?""",
        (datetime.now(timezone.utc).isoformat(), org_id),
    )
    await conn.commit()


class OrgSettingsRepo:
    get_org_settings = staticmethod(get_org_settings)
    upsert_org_settings = staticmethod(upsert_org_settings)
    clear_xero_tokens = staticmethod(clear_xero_tokens)


org_settings_repo = OrgSettingsRepo()
