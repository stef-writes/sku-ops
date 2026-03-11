"""Xero reconciliation fetch mixin — read-only calls for verification."""

import httpx

from finance.adapters.xero._base import XERO_API
from finance.domain.xero_settings import XeroSettings


class XeroReconcileMixin:
    async def fetch_invoice_by_number(
        self, invoice_number: str, settings: XeroSettings
    ) -> dict | None:
        """Look up a Xero invoice by InvoiceNumber. Returns the first match or None."""
        if self._is_token_expired(settings):
            settings = await self.refresh_token(settings)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{XERO_API}/Invoices",
                headers=self._auth_headers(settings),
                params={"InvoiceNumbers": invoice_number},
                timeout=15,
            )
        resp.raise_for_status()
        invoices = resp.json().get("Invoices", [])
        return invoices[0] if invoices else None

    async def fetch_invoice(self, xero_invoice_id: str, settings: XeroSettings) -> dict:
        """Fetch an invoice from Xero for reconciliation verification."""
        if self._is_token_expired(settings):
            settings = await self.refresh_token(settings)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{XERO_API}/Invoices/{xero_invoice_id}",
                headers=self._auth_headers(settings),
                timeout=15,
            )
        resp.raise_for_status()
        invoices = resp.json().get("Invoices", [])
        if not invoices:
            return {}
        inv = invoices[0]
        return {
            "total": float(inv.get("Total", 0)),
            "line_count": len(inv.get("LineItems", [])),
            "status": inv.get("Status", ""),
        }

    async def fetch_credit_note(self, xero_credit_note_id: str, settings: XeroSettings) -> dict:
        """Fetch a credit note from Xero for reconciliation verification."""
        if self._is_token_expired(settings):
            settings = await self.refresh_token(settings)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{XERO_API}/CreditNotes/{xero_credit_note_id}",
                headers=self._auth_headers(settings),
                timeout=15,
            )
        resp.raise_for_status()
        credit_notes = resp.json().get("CreditNotes", [])
        if not credit_notes:
            return {}
        cn = credit_notes[0]
        return {
            "total": float(cn.get("Total", 0)),
            "line_count": len(cn.get("LineItems", [])),
            "status": cn.get("Status", ""),
        }

    async def list_tracking_categories(self, settings: XeroSettings) -> list[dict]:
        if self._is_token_expired(settings):
            settings = await self.refresh_token(settings)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{XERO_API}/TrackingCategories",
                headers=self._auth_headers(settings),
                timeout=15,
            )
        resp.raise_for_status()
        return resp.json().get("TrackingCategories", [])
