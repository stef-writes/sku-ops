"""Xero API adapter — real Xero API v2 via OAuth 2.0."""
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

from models.org_settings import OrgSettings
from ports.xero import XeroSyncResult

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
            return datetime.now(timezone.utc).timestamp() >= expiry.timestamp() - 60
        except Exception:
            return True

    async def refresh_token(self, settings: OrgSettings) -> OrgSettings:
        from config import XERO_CLIENT_ID, XERO_CLIENT_SECRET
        from repositories.org_settings_repo import upsert_org_settings

        resp = requests.post(
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

        expiry = datetime.now(timezone.utc).timestamp() + token_data.get("expires_in", 1800)
        updated = settings.model_copy(update={
            "xero_access_token": token_data["access_token"],
            "xero_refresh_token": token_data.get("refresh_token", settings.xero_refresh_token),
            "xero_token_expiry": datetime.fromtimestamp(expiry, tz=timezone.utc).isoformat(),
        })
        return await upsert_org_settings(updated)

    async def get_tenants(self, access_token: str) -> list[dict]:
        resp = requests.get(
            XERO_CONNECTIONS_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    async def sync_invoice(self, invoice: dict, settings: OrgSettings) -> XeroSyncResult:
        if self._is_token_expired(settings):
            settings = await self.refresh_token(settings)

        line_items = invoice.get("line_items", [])
        xero_line_items = [
            {
                "Description": li.get("description", ""),
                "Quantity": li.get("quantity", 1),
                "UnitAmount": li.get("unit_price", 0),
                "LineAmount": li.get("amount", 0),
                "AccountCode": settings.xero_sales_account_code,
            }
            for li in line_items
        ]

        xero_invoice = {
            "Type": "ACCREC",
            "Contact": {"Name": invoice.get("billing_entity", "")},
            "InvoiceNumber": invoice.get("invoice_number", ""),
            "Status": _xero_status(invoice.get("status", "draft")),
            "SubTotal": invoice.get("subtotal", 0),
            "TotalTax": invoice.get("tax", 0),
            "Total": invoice.get("total", 0),
            "LineItems": xero_line_items,
        }

        headers = self._auth_headers(settings)
        existing_xero_id = invoice.get("xero_invoice_id")

        if existing_xero_id:
            xero_invoice["InvoiceID"] = existing_xero_id
            resp = requests.post(
                f"{XERO_API}/Invoices",
                headers=headers,
                json={"Invoices": [xero_invoice]},
                timeout=20,
            )
        else:
            resp = requests.put(
                f"{XERO_API}/Invoices",
                headers=headers,
                json={"Invoices": [xero_invoice]},
                timeout=20,
            )

        resp.raise_for_status()
        result = resp.json()
        invoices = result.get("Invoices", [])
        if not invoices:
            return XeroSyncResult(success=False, error="Xero returned no invoice in response")

        xero_invoice_id = invoices[0].get("InvoiceID")

        # Post COGS journal: Debit COGS, Credit Inventory
        journal_id = await self._post_cogs_journal(invoice, settings, xero_invoice_id)

        return XeroSyncResult(
            success=True,
            xero_invoice_id=xero_invoice_id,
            xero_journal_id=journal_id,
        )

    async def _post_cogs_journal(
        self, invoice: dict, settings: OrgSettings, xero_invoice_id: Optional[str]
    ) -> Optional[str]:
        line_items = invoice.get("line_items", [])
        cost_total = sum(
            float(li.get("cost", 0)) * float(li.get("quantity", 1))
            for li in line_items
        )
        if cost_total <= 0:
            return None

        narration = f"COGS for invoice {invoice.get('invoice_number', '')} (Xero ID: {xero_invoice_id})"
        journal = {
            "Narration": narration,
            "JournalLines": [
                {
                    "AccountCode": settings.xero_cogs_account_code,
                    "Description": narration,
                    "LineAmount": cost_total,
                },
                {
                    "AccountCode": settings.xero_inventory_account_code,
                    "Description": narration,
                    "LineAmount": -cost_total,
                },
            ],
        }
        resp = requests.put(
            f"{XERO_API}/ManualJournals",
            headers=self._auth_headers(settings),
            json={"ManualJournals": [journal]},
            timeout=20,
        )
        resp.raise_for_status()
        journals = resp.json().get("ManualJournals", [])
        return journals[0].get("ManualJournalID") if journals else None


def _xero_status(sku_status: str) -> str:
    return {"draft": "DRAFT", "sent": "SUBMITTED", "paid": "AUTHORISED"}.get(sku_status, "DRAFT")
