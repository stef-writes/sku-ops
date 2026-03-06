"""Stub Xero adapter — used in dev/test when no Xero credentials are configured."""
from finance.ports.invoicing_port import InvoiceSyncResult
from identity.domain.org_settings import OrgSettings


class StubXeroAdapter:
    async def sync_invoice(self, invoice: dict, _settings: OrgSettings) -> InvoiceSyncResult:
        inv_id = invoice.get("id", "unknown")
        return InvoiceSyncResult(
            success=True,
            xero_invoice_id=f"XERO-STUB-{inv_id}",
            xero_journal_id=f"XERO-STUB-JNL-{inv_id}",
        )

    async def sync_po_receipt(self, po: dict, _cost_total: float, _settings: OrgSettings) -> InvoiceSyncResult:
        return InvoiceSyncResult(
            success=True,
            xero_invoice_id=f"XERO-STUB-BILL-{po.get('id', 'unknown')}",
        )

    async def sync_credit_note(self, credit_note: dict, _settings: OrgSettings) -> InvoiceSyncResult:
        cn_id = credit_note.get("id", "unknown")
        return InvoiceSyncResult(
            success=True,
            xero_invoice_id=f"XERO-STUB-CN-{cn_id}",
        )

    async def repost_cogs_journal(self, invoice: dict, _settings: OrgSettings, old_journal_id=None) -> str:
        inv_id = invoice.get("id", "unknown")
        return f"XERO-STUB-COGS-REPOST-{inv_id}"

    async def fetch_invoice(self, xero_invoice_id: str, _settings: OrgSettings) -> dict:
        return {"total": 0.0, "line_count": 0, "status": "STUB"}

    async def fetch_credit_note(self, xero_credit_note_id: str, _settings: OrgSettings) -> dict:
        return {"total": 0.0, "line_count": 0, "status": "STUB"}

    async def list_tracking_categories(self, _settings: OrgSettings) -> list[dict]:
        return [{"TrackingCategoryID": "stub-cat-id", "Name": "Job", "Status": "ACTIVE"}]

    async def refresh_token(self, settings: OrgSettings) -> OrgSettings:
        return settings

    async def get_tenants(self, _access_token: str) -> list[dict]:
        return [{"tenantId": "stub-tenant", "tenantName": "Stub Organisation"}]
