"""Xero API adapter — real Xero API v2 via OAuth 2.0."""
import logging
from datetime import UTC, datetime, timezone
from typing import Optional

import httpx

from finance.ports.invoicing_port import InvoiceSyncResult
from identity.application.org_service import upsert_org_settings
from identity.domain.org_settings import OrgSettings
from shared.infrastructure.config import XERO_CLIENT_ID, XERO_CLIENT_SECRET

logger = logging.getLogger(__name__)

XERO_API = "https://api.xero.com/api.xro/2.0"
XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"


class XeroAdapter:
    def _auth_headers(self, settings: OrgSettings) -> dict:
        return {
            "Authorization": f"Bearer {settings.xero_access_token}",
            "Xero-tenant-id": settings.xero_tenant_id or "",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _is_token_expired(self, settings: OrgSettings) -> bool:
        if not settings.xero_token_expiry:
            return True
        try:
            expiry = datetime.fromisoformat(settings.xero_token_expiry)
            # Treat as expired 60 s before actual expiry to avoid edge races
            return datetime.now(UTC).timestamp() >= expiry.timestamp() - 60
        except Exception:
            return True

    async def refresh_token(self, settings: OrgSettings) -> OrgSettings:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                XERO_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": settings.xero_refresh_token,
                    "client_id": XERO_CLIENT_ID,
                    "client_secret": XERO_CLIENT_SECRET,
                },
                timeout=15,
            )
        resp.raise_for_status()
        token_data = resp.json()

        expiry = datetime.now(UTC).timestamp() + token_data.get("expires_in", 1800)
        updated = settings.model_copy(update={
            "xero_access_token": token_data["access_token"],
            "xero_refresh_token": token_data.get("refresh_token", settings.xero_refresh_token),
            "xero_token_expiry": datetime.fromtimestamp(expiry, tz=UTC).isoformat(),
        })
        return await upsert_org_settings(updated)

    async def get_tenants(self, access_token: str) -> list[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                XERO_CONNECTIONS_URL,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                timeout=15,
            )
        resp.raise_for_status()
        return resp.json()

    async def sync_invoice(self, invoice: dict, settings: OrgSettings) -> InvoiceSyncResult:
        if self._is_token_expired(settings):
            settings = await self.refresh_token(settings)

        line_items = invoice.get("line_items", [])
        xero_line_items = []
        for li in line_items:
            line: dict = {
                "Description": li.get("description", ""),
                "Quantity": li.get("quantity", 1),
                "UnitAmount": li.get("unit_price", 0),
                "LineAmount": li.get("amount", 0),
                "AccountCode": settings.xero_sales_account_code,
            }
            if settings.xero_tax_type:
                line["TaxType"] = settings.xero_tax_type
            if settings.xero_tracking_category_id and li.get("job_id"):
                line["Tracking"] = [{
                    "TrackingCategoryID": settings.xero_tracking_category_id,
                    "Name": li["job_id"],
                }]
            xero_line_items.append(line)

        xero_invoice: dict = {
            "Type": "ACCREC",
            "Contact": {"Name": invoice.get("billing_entity", "")},
            "InvoiceNumber": invoice.get("invoice_number", ""),
            "Status": _xero_status(invoice.get("status", "draft")),
            "CurrencyCode": invoice.get("currency", "USD"),
            "LineItems": xero_line_items,
        }
        if invoice.get("due_date"):
            xero_invoice["DueDate"] = invoice["due_date"][:10]
        if invoice.get("invoice_date"):
            xero_invoice["Date"] = invoice["invoice_date"][:10]
        if invoice.get("po_reference"):
            xero_invoice["Reference"] = invoice["po_reference"]
        if not settings.xero_tax_type:
            xero_invoice["SubTotal"] = invoice.get("subtotal", 0)
            xero_invoice["TotalTax"] = invoice.get("tax", 0)
            xero_invoice["Total"] = invoice.get("total", 0)

        headers = self._auth_headers(settings)
        existing_xero_id = invoice.get("xero_invoice_id")

        async with httpx.AsyncClient() as client:
            if existing_xero_id:
                xero_invoice["InvoiceID"] = existing_xero_id
                resp = await client.post(
                    f"{XERO_API}/Invoices",
                    headers=headers,
                    json={"Invoices": [xero_invoice]},
                    timeout=20,
                )
            else:
                resp = await client.put(
                    f"{XERO_API}/Invoices",
                    headers=headers,
                    json={"Invoices": [xero_invoice]},
                    timeout=20,
                )

            resp.raise_for_status()
            result = resp.json()
            invoices = result.get("Invoices", [])
            if not invoices:
                return InvoiceSyncResult(success=False, error="Xero returned no invoice in response")

            xero_invoice_id = invoices[0].get("InvoiceID")

            # Post COGS journal within the same client session
            first_job_id = next((li.get("job_id") for li in line_items if li.get("job_id")), None)
            journal_id = await self._post_cogs_journal(invoice, settings, xero_invoice_id, first_job_id, client)

        return InvoiceSyncResult(
            success=True,
            xero_invoice_id=xero_invoice_id,
            xero_journal_id=journal_id,
        )

    def _build_cogs_journal_lines(
        self,
        invoice: dict,
        settings: OrgSettings,
        xero_invoice_id: str | None,
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
            tracking = [{"TrackingCategoryID": settings.xero_tracking_category_id, "Name": first_job_id}]

        journal_lines: list = []
        cost_total = 0.0
        for li in line_items:
            qty = float(li.get("quantity", 1))
            # Prefer sell_cost (sell-unit normalized); fall back to legacy cost field
            unit_cost = float(li.get("sell_cost") or li.get("cost") or 0)
            line_cost = round(unit_cost * qty, 2)
            if line_cost <= 0:
                continue
            cost_total += line_cost

            description = li.get("description") or li.get("name") or ""
            unit = li.get("unit") or li.get("sell_uom") or "each"
            line_narration = (
                f"{description} — {qty} {unit} @ {unit_cost:.4f} "
                f"[INV {invoice_number}]"
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
        self, invoice: dict, settings: OrgSettings, xero_invoice_id: str | None,
        first_job_id: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> str | None:
        journal_lines, cost_total = self._build_cogs_journal_lines(
            invoice, settings, xero_invoice_id, first_job_id
        )
        if cost_total <= 0:
            return None

        narration = f"COGS for invoice {invoice.get('invoice_number', '')} (Xero ID: {xero_invoice_id})"
        journal = {
            "Narration": narration,
            "JournalLines": journal_lines,
        }
        if client is not None:
            resp = await client.put(
                f"{XERO_API}/ManualJournals",
                headers=self._auth_headers(settings),
                json={"ManualJournals": [journal]},
                timeout=20,
            )
            resp.raise_for_status()
            journals = resp.json().get("ManualJournals", [])
        else:
            async with httpx.AsyncClient() as _client:
                resp = await _client.put(
                    f"{XERO_API}/ManualJournals",
                    headers=self._auth_headers(settings),
                    json={"ManualJournals": [journal]},
                    timeout=20,
                )
            resp.raise_for_status()
            journals = resp.json().get("ManualJournals", [])
        return journals[0].get("ManualJournalID") if journals else None

    async def repost_cogs_journal(
        self,
        invoice: dict,
        settings: OrgSettings,
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
            (li.get("job_id") for li in invoice.get("line_items", []) if li.get("job_id")),
            None,
        )
        return await self._post_cogs_journal(
            invoice, settings, invoice.get("xero_invoice_id"), first_job_id
        )

    async def sync_po_receipt(self, po: dict, cost_total: float, settings: OrgSettings) -> InvoiceSyncResult:
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
                xero_lines.append({
                    "Description": item.get("name", ""),
                    "Quantity": delivered,
                    "UnitAmount": cost,
                    "LineAmount": round(delivered * cost, 2),
                    "AccountCode": settings.xero_inventory_account_code,
                })
        else:
            xero_lines = [{
                "Description": f"Inventory receipt — {vendor_name} PO {po_id}",
                "Quantity": 1,
                "UnitAmount": cost_total,
                "LineAmount": cost_total,
                "AccountCode": settings.xero_inventory_account_code,
            }]

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
        return InvoiceSyncResult(success=True, xero_invoice_id=xero_bill_id)

    async def sync_credit_note(self, credit_note: dict, settings: OrgSettings) -> InvoiceSyncResult:
        """Send a credit note to Xero as an ACCREC credit note.

        Returns/credits are reflected here so Xero Revenue/COGS/Inventory reverse correctly.
        """
        if self._is_token_expired(settings):
            settings = await self.refresh_token(settings)

        line_items = credit_note.get("line_items", [])
        xero_lines = []
        for li in line_items:
            line: dict = {
                "Description": li.get("description", ""),
                "Quantity": li.get("quantity", 1),
                "UnitAmount": li.get("unit_price", 0),
                "LineAmount": li.get("amount", 0),
                "AccountCode": settings.xero_sales_account_code,
            }
            if settings.xero_tax_type:
                line["TaxType"] = settings.xero_tax_type
            xero_lines.append(line)

        xero_cn: dict = {
            "Type": "ACCREC",
            "Contact": {"Name": credit_note.get("billing_entity", "")},
            "CreditNoteNumber": credit_note.get("credit_note_number", ""),
            "Status": "AUTHORISED",
            "CurrencyCode": "USD",
            "LineItems": xero_lines,
        }
        if credit_note.get("created_at"):
            xero_cn["Date"] = credit_note["created_at"][:10]

        existing_cn_id = credit_note.get("xero_credit_note_id")
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
            return InvoiceSyncResult(success=False, error="Xero returned no credit note in response")
        xero_cn_id = credit_notes[0].get("CreditNoteID")
        return InvoiceSyncResult(success=True, xero_invoice_id=xero_cn_id)

    async def fetch_invoice(self, xero_invoice_id: str, settings: OrgSettings) -> dict:
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

    async def fetch_credit_note(self, xero_credit_note_id: str, settings: OrgSettings) -> dict:
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

    async def list_tracking_categories(self, settings: OrgSettings) -> list[dict]:
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


def _xero_status(sku_status: str) -> str:
    return {"draft": "DRAFT", "approved": "SUBMITTED", "sent": "SUBMITTED", "paid": "AUTHORISED"}.get(sku_status, "DRAFT")
