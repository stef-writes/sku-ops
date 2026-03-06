"""Per-org settings model (Xero config, account codes)."""
from typing import Optional

from pydantic import BaseModel


class OrgSettings(BaseModel):
    organization_id: str
    default_tax_rate: float = 0.10          # 10% GST (NZ/AU default)
    xero_client_id: str | None = None
    xero_client_secret: str | None = None
    xero_tenant_id: str | None = None
    xero_access_token: str | None = None
    xero_refresh_token: str | None = None
    xero_token_expiry: str | None = None
    # Xero account codes for financial posting
    xero_sales_account_code: str = "200"
    xero_cogs_account_code: str = "500"
    xero_inventory_account_code: str = "630"
    xero_ap_account_code: str = "800"       # Trade Creditors / Accounts Payable
    xero_tracking_category_id: str | None = None  # Tracking category for job_id tagging
    xero_tax_type: str = ""                 # e.g. "OUTPUT2" (NZ/AU GST), "" = no tagging


class OrgSettingsUpdate(BaseModel):
    """Payload for updating org and Xero settings."""
    default_tax_rate: float | None = None
    xero_sales_account_code: str | None = None
    xero_cogs_account_code: str | None = None
    xero_inventory_account_code: str | None = None
    xero_ap_account_code: str | None = None
    xero_client_id: str | None = None
    xero_client_secret: str | None = None
    xero_tracking_category_id: str | None = None
    xero_tax_type: str | None = None
