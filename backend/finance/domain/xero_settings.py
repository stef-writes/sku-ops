"""Finance-owned configuration shape for the Xero integration.

Finance defines what it needs from org settings. Callers map OrgSettings → XeroSettings
before invoking the InvoicingGateway port.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class XeroSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    organization_id: str
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
