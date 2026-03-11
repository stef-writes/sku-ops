"""Xero invoice sync mixin — create/update ACCREC invoices."""

import logging

import httpx

from finance.adapters.xero._base import XERO_API, _xero_status
from finance.domain.invoice import InvoiceWithDetails
from finance.domain.xero_settings import XeroSettings
from finance.ports.invoicing_port import InvoiceSyncResult

logger = logging.getLogger(__name__)


class XeroInvoiceSyncMixin:
    async def sync_invoice(
        self, invoice: InvoiceWithDetails, settings: XeroSettings
    ) -> InvoiceSyncResult:
        if self._is_token_expired(settings):
            settings = await self.refresh_token(settings)

        inv = invoice.model_dump()
        line_items = inv.get("line_items", [])

        async with httpx.AsyncClient() as client:
            if settings.xero_tracking_category_id:
                job_ids = {li["job_id"] for li in line_items if li.get("job_id")}
                for job_id in job_ids:
                    try:
                        await self._ensure_tracking_option(
                            settings.xero_tracking_category_id, job_id, settings, client
                        )
                    except Exception as e:
                        logger.warning("Could not ensure tracking option %r: %s", job_id, e)

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
                    line["Tracking"] = [
                        {
                            "TrackingCategoryID": settings.xero_tracking_category_id,
                            "Option": li["job_id"],
                        }
                    ]
                xero_line_items.append(line)

            xero_invoice: dict = {
                "Type": "ACCREC",
                "Contact": {"Name": inv.get("billing_entity", "")},
                "InvoiceNumber": inv.get("invoice_number", ""),
                "Status": _xero_status(inv.get("status", "draft")),
                "CurrencyCode": inv.get("currency", "USD"),
                "LineItems": xero_line_items,
                "SubTotal": inv.get("subtotal", 0),
                "TotalTax": inv.get("tax", 0),
                "Total": inv.get("total", 0),
            }
            if inv.get("due_date"):
                xero_invoice["DueDate"] = inv["due_date"][:10]
            if inv.get("invoice_date"):
                xero_invoice["Date"] = inv["invoice_date"][:10]
            if inv.get("po_reference"):
                xero_invoice["Reference"] = inv["po_reference"]

            headers = self._auth_headers(settings)
            existing_xero_id = inv.get("xero_invoice_id")

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
                return InvoiceSyncResult(
                    success=False, error="Xero returned no invoice in response"
                )

            xero_invoice_id = invoices[0].get("InvoiceID")

            first_job_id = next((li.get("job_id") for li in line_items if li.get("job_id")), None)
            journal_id = await self._post_cogs_journal(
                inv, settings, xero_invoice_id, first_job_id, client
            )

        return InvoiceSyncResult(
            success=True,
            external_id=xero_invoice_id,
            external_journal_id=journal_id,
        )
