"""Stub Xero adapter — used in dev/test when no Xero credentials are configured."""
from identity.domain.org_settings import OrgSettings
from finance.ports.xero_port import XeroSyncResult


class StubXeroAdapter:
    async def sync_invoice(self, invoice: dict, _settings: OrgSettings) -> XeroSyncResult:
        inv_id = invoice.get("id", "unknown")
        return XeroSyncResult(
            success=True,
            xero_invoice_id=f"XERO-STUB-{inv_id}",
            xero_journal_id=f"XERO-STUB-JNL-{inv_id}",
        )

    async def sync_po_receipt(self, po: dict, _cost_total: float, _settings: OrgSettings) -> XeroSyncResult:
        return XeroSyncResult(
            success=True,
            xero_journal_id=f"XERO-STUB-PO-{po.get('id', 'unknown')}",
        )

    async def list_tracking_categories(self, _settings: OrgSettings) -> list[dict]:
        return [{"TrackingCategoryID": "stub-cat-id", "Name": "Job", "Status": "ACTIVE"}]

    async def refresh_token(self, settings: OrgSettings) -> OrgSettings:
        return settings

    async def get_tenants(self, _access_token: str) -> list[dict]:
        return [{"tenantId": "stub-tenant", "tenantName": "Stub Organisation"}]
