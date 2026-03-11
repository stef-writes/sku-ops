"""Xero COGS journal and PO bill sync mixins."""

import logging

import httpx

from finance.adapters.xero._base import XERO_API
from finance.domain.invoice import InvoiceWithDetails
from finance.domain.xero_settings import XeroSettings
from finance.ports.invoicing_port import InvoiceSyncResult

logger = logging.getLogger(__name__)


class XeroJournalSyncMixin:
    def _build_cogs_journal_lines(
        self,
        invoice: dict,
        settings: XeroSettings,
        _xero_invoice_id: str | None,
        first_job_id: str | None = None,
    ) -> tuple[list, float]:
        """Return (journal_lines, cost_total) for a per-line itemized COGS journal.

        Each invoice line item gets its own COGS debit and inventory credit pair,
        using sell_cost when available (sell-unit normalized) and falling back to cost.
        All lines share the same tracking category if configured.
        """
        line_items = invoice.get("line_items", [])
        invoice_number = invoice.get("invoice_number", "")

        tracking: list = []
        if settings.xero_tracking_category_id and first_job_id:
            tracking = [
                {"TrackingCategoryID": settings.xero_tracking_category_id, "Option": first_job_id}
            ]

        journal_lines: list = []
        cost_total = 0.0
        for li in line_items:
            qty = float(li.get("quantity", 1))
            unit_cost = float(li.get("sell_cost") or li.get("cost") or 0)
            line_cost = round(unit_cost * qty, 2)
            if line_cost <= 0:
                continue
            cost_total += line_cost

            description = li.get("description") or li.get("name") or ""
            unit = li.get("unit") or li.get("sell_uom") or "each"
            line_narration = (
                f"{description} — {qty} {unit} @ {unit_cost:.4f} [INV {invoice_number}]"
            ).strip(" —")

            cogs_line: dict = {
                "AccountCode": settings.xero_cogs_account_code,
                "Description": line_narration,
                "LineAmount": line_cost,
            }
            inv_line: dict = {
                "AccountCode": settings.xero_inventory_account_code,
                "Description": line_narration,
                "LineAmount": -line_cost,
            }
            if tracking:
                cogs_line["Tracking"] = tracking
                inv_line["Tracking"] = tracking
            journal_lines.append(cogs_line)
            journal_lines.append(inv_line)

        return journal_lines, round(cost_total, 2)

    async def _post_cogs_journal(
        self,
        invoice: dict,
        settings: XeroSettings,
        xero_invoice_id: str | None,
        first_job_id: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> str | None:
        async def _do_post(_client: httpx.AsyncClient) -> str | None:
            if settings.xero_tracking_category_id and first_job_id:
                try:
                    await self._ensure_tracking_option(
                        settings.xero_tracking_category_id, first_job_id, settings, _client
                    )
                except Exception as e:
                    logger.warning("Could not ensure COGS tracking option %r: %s", first_job_id, e)

            journal_lines, cost_total = self._build_cogs_journal_lines(
                invoice, settings, xero_invoice_id, first_job_id
            )
            if cost_total <= 0:
                return None

            narration = (
                f"COGS for invoice {invoice.get('invoice_number', '')} (Xero ID: {xero_invoice_id})"
            )
            journal = {"Narration": narration, "JournalLines": journal_lines}
            resp = await _client.put(
                f"{XERO_API}/ManualJournals",
                headers=self._auth_headers(settings),
                json={"ManualJournals": [journal]},
                timeout=20,
            )
            resp.raise_for_status()
            journals = resp.json().get("ManualJournals", [])
            return journals[0].get("ManualJournalID") if journals else None

        if client is not None:
            return await _do_post(client)
        async with httpx.AsyncClient() as _client:
            return await _do_post(_client)

    async def repost_cogs_journal(
        self,
        invoice: InvoiceWithDetails,
        settings: XeroSettings,
        old_journal_id: str | None = None,
    ) -> str | None:
        """Void the previous COGS manual journal (if we have its ID) then post a fresh one.

        Xero manual journals cannot be edited once posted, so the correct approach is:
        1. POST to /ManualJournals/{id} with Status=VOIDED to reverse the old journal.
        2. PUT a new manual journal with the updated cost total.
        Returns the new ManualJournalID, or None if cost_total is zero.
        """
        if self._is_token_expired(settings):
            settings = await self.refresh_token(settings)

        inv = invoice.model_dump()

        if old_journal_id:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{XERO_API}/ManualJournals/{old_journal_id}",
                        headers=self._auth_headers(settings),
                        json={"Status": "VOIDED"},
                        timeout=20,
                    )
            except Exception as e:
                logger.warning("Could not void old COGS journal %s: %s", old_journal_id, e)

        first_job_id = next(
            (li.get("job_id") for li in inv.get("line_items", []) if li.get("job_id")),
            None,
        )
        return await self._post_cogs_journal(
            inv, settings, inv.get("xero_invoice_id"), first_job_id
        )

    async def sync_po_receipt(
        self, po: dict, cost_total: float, settings: XeroSettings
    ) -> InvoiceSyncResult:
        """Send a vendor purchase to Xero as an ACCPAY Bill (not a manual journal).

        This creates a real AP liability attached to the vendor contact, which
        appears in aging reports and can be marked paid — unlike a manual journal.
        """
        if self._is_token_expired(settings):
            settings = await self.refresh_token(settings)

        vendor_name = po.get("vendor_name", "")
        po_id = po.get("id", "unknown")
        items = po.get("items", [])

        if items:
            xero_lines = []
            for item in items:
                delivered = float(item.get("delivered_qty") or item.get("ordered_qty") or 1)
                cost = float(item.get("cost") or 0)
                if delivered <= 0 or cost <= 0:
                    continue
                xero_lines.append(
                    {
                        "Description": item.get("name", ""),
                        "Quantity": delivered,
                        "UnitAmount": cost,
                        "LineAmount": round(delivered * cost, 2),
                        "AccountCode": settings.xero_inventory_account_code,
                    }
                )
        else:
            xero_lines = [
                {
                    "Description": f"Inventory receipt — {vendor_name} PO {po_id}",
                    "Quantity": 1,
                    "UnitAmount": cost_total,
                    "LineAmount": cost_total,
                    "AccountCode": settings.xero_inventory_account_code,
                }
            ]

        bill: dict = {
            "Type": "ACCPAY",
            "Contact": {"Name": vendor_name},
            "Reference": po_id,
            "Status": "DRAFT",
            "LineItems": xero_lines,
        }
        if po.get("document_date"):
            bill["Date"] = po["document_date"][:10]

        existing_bill_id = po.get("xero_bill_id")
        async with httpx.AsyncClient() as client:
            if existing_bill_id:
                bill["InvoiceID"] = existing_bill_id
                resp = await client.post(
                    f"{XERO_API}/Invoices",
                    headers=self._auth_headers(settings),
                    json={"Invoices": [bill]},
                    timeout=20,
                )
            else:
                resp = await client.put(
                    f"{XERO_API}/Invoices",
                    headers=self._auth_headers(settings),
                    json={"Invoices": [bill]},
                    timeout=20,
                )
        resp.raise_for_status()
        invoices = resp.json().get("Invoices", [])
        if not invoices:
            return InvoiceSyncResult(success=False, error="Xero returned no bill in response")
        xero_bill_id = invoices[0].get("InvoiceID")
        return InvoiceSyncResult(success=True, external_id=xero_bill_id)
