"""Xero credit note sync mixin — ACCREC credit notes."""

import httpx

from finance.adapters.xero._base import XERO_API
from finance.domain.xero_settings import XeroSettings
from finance.ports.invoicing_port import InvoiceSyncResult


class XeroCreditNoteSyncMixin:
    async def sync_credit_note(self, credit_note, settings: XeroSettings) -> InvoiceSyncResult:
        """Send a credit note to Xero as an ACCREC credit note.

        Returns/credits are reflected here so Xero Revenue/COGS/Inventory reverse correctly.
        """
        if self._is_token_expired(settings):
            settings = await self.refresh_token(settings)

        line_items = credit_note.line_items if hasattr(credit_note, "line_items") else []
        xero_lines = []
        for li in line_items:
            line: dict = {
                "Description": li.description if hasattr(li, "description") else "",
                "Quantity": li.quantity if hasattr(li, "quantity") else 1,
                "UnitAmount": li.unit_price if hasattr(li, "unit_price") else 0,
                "LineAmount": li.amount if hasattr(li, "amount") else 0,
                "AccountCode": settings.xero_sales_account_code,
            }
            if settings.xero_tax_type:
                line["TaxType"] = settings.xero_tax_type
            xero_lines.append(line)

        xero_cn: dict = {
            "Type": "ACCREC",
            "Contact": {"Name": credit_note.billing_entity},
            "CreditNoteNumber": credit_note.credit_note_number,
            "Status": "AUTHORISED",
            "CurrencyCode": "USD",
            "LineItems": xero_lines,
        }
        if credit_note.created_at:
            xero_cn["Date"] = credit_note.created_at[:10]

        existing_cn_id = credit_note.xero_credit_note_id
        async with httpx.AsyncClient() as client:
            if existing_cn_id:
                xero_cn["CreditNoteID"] = existing_cn_id
                resp = await client.post(
                    f"{XERO_API}/CreditNotes",
                    headers=self._auth_headers(settings),
                    json={"CreditNotes": [xero_cn]},
                    timeout=20,
                )
            else:
                resp = await client.put(
                    f"{XERO_API}/CreditNotes",
                    headers=self._auth_headers(settings),
                    json={"CreditNotes": [xero_cn]},
                    timeout=20,
                )
        resp.raise_for_status()
        credit_notes = resp.json().get("CreditNotes", [])
        if not credit_notes:
            return InvoiceSyncResult(
                success=False, error="Xero returned no credit note in response"
            )
        xero_cn_id = credit_notes[0].get("CreditNoteID")
        return InvoiceSyncResult(success=True, external_id=xero_cn_id)
