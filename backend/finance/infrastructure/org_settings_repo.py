"""Per-org settings repository."""

from datetime import UTC, datetime

from finance.domain.org_settings import OrgSettings
from shared.infrastructure.database import get_connection, get_org_id


async def get_org_settings() -> OrgSettings:
    """Return org settings, or defaults if not yet configured."""
    org_id = get_org_id()
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM org_settings WHERE organization_id = $1",
        (org_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return OrgSettings(organization_id=org_id)
    return OrgSettings(**dict(row))


async def upsert_org_settings(settings: OrgSettings) -> OrgSettings:
    """Insert or replace org settings."""
    conn = get_connection()
    now = datetime.now(UTC).isoformat()
    auto_invoice_int = 1 if settings.auto_invoice else 0
    await conn.execute(
        """INSERT INTO org_settings (
               organization_id, auto_invoice, default_tax_rate,
               xero_tenant_id, xero_access_token, xero_refresh_token,
               xero_token_expiry, xero_sales_account_code,
               xero_cogs_account_code, xero_inventory_account_code,
               xero_ap_account_code, xero_tracking_category_id,
               xero_tax_type, updated_at
           ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
           ON CONFLICT(organization_id) DO UPDATE SET
               auto_invoice = excluded.auto_invoice,
               default_tax_rate = excluded.default_tax_rate,
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
            auto_invoice_int,
            settings.default_tax_rate,
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
    return await get_org_settings()


async def clear_xero_tokens() -> None:
    """Remove Xero OAuth tokens for an org (disconnect)."""
    org_id = get_org_id()
    conn = get_connection()
    await conn.execute(
        """UPDATE org_settings
           SET xero_access_token = NULL, xero_refresh_token = NULL,
               xero_tenant_id = NULL, xero_token_expiry = NULL,
               updated_at = $1
           WHERE organization_id = $2""",
        (datetime.now(UTC).isoformat(), org_id),
    )
    await conn.commit()


class OrgSettingsRepo:
    get_org_settings = staticmethod(get_org_settings)
    upsert_org_settings = staticmethod(upsert_org_settings)
    clear_xero_tokens = staticmethod(clear_xero_tokens)


org_settings_repo = OrgSettingsRepo()
