"""Per-org settings model (Xero config, account codes, tax rate).

Owned by the finance context — this is integration configuration
for Xero and financial defaults, not authentication data.
"""

from pydantic import BaseModel


class OrgSettings(BaseModel):
    organization_id: str
    default_tax_rate: float = 0.10
    xero_tenant_id: str | None = None
    xero_access_token: str | None = None
    xero_refresh_token: str | None = None
    xero_token_expiry: str | None = None
    xero_sales_account_code: str = "200"
    xero_cogs_account_code: str = "500"
    xero_inventory_account_code: str = "630"
    xero_ap_account_code: str = "800"
    xero_tracking_category_id: str | None = None
    xero_tax_type: str = ""


class OrgSettingsUpdate(BaseModel):
    """Payload for updating org and Xero settings."""

    default_tax_rate: float | None = None
    xero_sales_account_code: str | None = None
    xero_cogs_account_code: str | None = None
    xero_inventory_account_code: str | None = None
    xero_ap_account_code: str | None = None
    xero_tracking_category_id: str | None = None
    xero_tax_type: str | None = None
