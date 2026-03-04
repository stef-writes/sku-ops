"""Per-org settings model (Xero config, account codes)."""
from typing import Optional
from pydantic import BaseModel


class OrgSettings(BaseModel):
    organization_id: str
    xero_client_id: Optional[str] = None
    xero_client_secret: Optional[str] = None
    xero_tenant_id: Optional[str] = None
    xero_access_token: Optional[str] = None
    xero_refresh_token: Optional[str] = None
    xero_token_expiry: Optional[str] = None
    # Xero account codes for financial posting
    xero_sales_account_code: str = "200"
    xero_cogs_account_code: str = "500"
    xero_inventory_account_code: str = "630"
    xero_ap_account_code: str = "800"       # Trade Creditors / Accounts Payable
    xero_tracking_category_id: Optional[str] = None  # Tracking category for job_id tagging
    xero_tax_type: str = ""                 # e.g. "OUTPUT2" (NZ/AU GST), "" = no tagging


class OrgSettingsUpdate(BaseModel):
    """Payload for updating Xero account code settings."""
    xero_sales_account_code: Optional[str] = None
    xero_cogs_account_code: Optional[str] = None
    xero_inventory_account_code: Optional[str] = None
    xero_ap_account_code: Optional[str] = None
    xero_client_id: Optional[str] = None
    xero_client_secret: Optional[str] = None
    xero_tracking_category_id: Optional[str] = None
    xero_tax_type: Optional[str] = None
