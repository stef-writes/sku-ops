"""
Xero adapter unit tests — no network, no DB.

Tests validate:
  1. Payload shape — correct Xero document types and field mapping
  2. Verb selection — PUT for create, POST for update
  3. Bill vs journal — PO receipts must create ACCPAY Bills, never ManualJournals
  4. Credit note sync — correct ACCREC credit note shape
  5. Reconcile fetch — normalised dict returned from Xero response
  6. Token refresh — expired token triggers refresh before API call
  7. Idempotency contract — existing xero_invoice_id uses InvoiceID in payload
"""
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from finance.adapters.xero_adapter import XeroAdapter
from identity.domain.org_settings import OrgSettings

# ── Fixtures ─────────────────────────────────────────────────────────────────

def _settings(**overrides) -> OrgSettings:
    base = dict(
        organization_id="org-1",
        xero_access_token="tok-valid",
        xero_refresh_token="refresh-valid",
        xero_tenant_id="tenant-abc",
        xero_token_expiry=(
            datetime.now(UTC) + timedelta(hours=1)
        ).isoformat(),
        xero_sales_account_code="200",
        xero_cogs_account_code="500",
        xero_inventory_account_code="630",
        xero_ap_account_code="800",
    )
    base.update(overrides)
    return OrgSettings(**base)


def _expired_settings() -> OrgSettings:
    return _settings(
        xero_token_expiry=(
            datetime.now(UTC) - timedelta(hours=1)
        ).isoformat()
    )


def _invoice(xero_invoice_id=None) -> dict:
    return {
        "id": "inv-local-1",
        "invoice_number": "INV-00001",
        "billing_entity": "On Point LLC",
        "status": "approved",
        "invoice_date": "2025-03-01T00:00:00Z",
        "due_date": "2025-03-31T00:00:00Z",
        "subtotal": 100.0,
        "tax": 10.0,
        "total": 110.0,
        "currency": "USD",
        "xero_invoice_id": xero_invoice_id,
        "line_items": [
            {
                "description": "2x16 Lumber",
                "quantity": 10,
                "unit_price": 10.0,
                "amount": 100.0,
                "cost": 6.0,
                "product_id": "prod-1",
                "job_id": "JOB-42",
            }
        ],
    }


def _po(xero_bill_id=None) -> dict:
    return {
        "id": "po-local-1",
        "vendor_name": "Lumberyard Inc",
        "document_date": "2025-03-01",
        "xero_bill_id": xero_bill_id,
        "items": [
            {"name": "2x4 Pine", "delivered_qty": 50, "ordered_qty": 50, "cost": 4.0},
            {"name": "Drywall Sheet", "delivered_qty": 20, "ordered_qty": 20, "cost": 8.50},
        ],
    }


def _credit_note() -> dict:
    return {
        "id": "cn-local-1",
        "credit_note_number": "CN-00001",
        "billing_entity": "On Point LLC",
        "status": "applied",
        "created_at": "2025-03-05T00:00:00Z",
        "xero_credit_note_id": None,
        "line_items": [
            {
                "description": "Returned lumber",
                "quantity": 3,
                "unit_price": 10.0,
                "amount": 30.0,
                "cost": 6.0,
            }
        ],
    }


def _mock_resp(response_json: dict):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = response_json
    return resp


def _mock_http_client(response_json: dict, journal_json: dict | None = None):
    """Return a patched httpx.AsyncClient.

    If journal_json is given, put() will return response_json on the first
    call and journal_json on the second (for the COGS ManualJournals call).
    Otherwise put() always returns response_json.
    """
    inv_resp = _mock_resp(response_json)
    jnl_resp = _mock_resp(journal_json or {"ManualJournals": []})

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    # First call = Invoices endpoint, second call = ManualJournals endpoint
    mock_client.put = AsyncMock(side_effect=[inv_resp, jnl_resp])
    mock_client.post = AsyncMock(side_effect=[inv_resp, jnl_resp])
    mock_client.get = AsyncMock(return_value=inv_resp)
    return mock_client


# ── 1. Invoice sync — new invoice uses PUT ────────────────────────────────────

class TestSyncInvoiceNew:

    @pytest.mark.asyncio
    async def test_new_invoice_uses_put(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "xero-inv-new", "LineItems": [{}]}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.sync_invoice(_invoice(), settings)

        # First put call must be to /Invoices (second may be ManualJournals for COGS)
        first_put_url = mock_client.put.call_args_list[0][0][0]
        assert "/Invoices" in first_put_url
        mock_client.post.assert_not_called()
        assert result.success is True
        assert result.xero_invoice_id == "xero-inv-new"

    @pytest.mark.asyncio
    async def test_new_invoice_payload_type_is_accrec(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "xero-inv-new", "LineItems": [{}]}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_invoice(_invoice(), settings)

        # First put call is the invoice
        payload = mock_client.put.call_args_list[0][1]["json"]
        assert payload["Invoices"][0]["Type"] == "ACCREC"

    @pytest.mark.asyncio
    async def test_new_invoice_contact_name_is_billing_entity(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "x", "LineItems": [{}]}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_invoice(_invoice(), settings)

        payload = mock_client.put.call_args_list[0][1]["json"]
        assert payload["Invoices"][0]["Contact"]["Name"] == "On Point LLC"

    @pytest.mark.asyncio
    async def test_new_invoice_line_items_mapped(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "x", "LineItems": [{}]}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_invoice(_invoice(), settings)

        payload = mock_client.put.call_args_list[0][1]["json"]
        li = payload["Invoices"][0]["LineItems"][0]
        assert li["Description"] == "2x16 Lumber"
        assert li["Quantity"] == 10
        assert li["UnitAmount"] == 10.0
        assert li["AccountCode"] == "200"  # sales account code


# ── 2. Invoice sync — existing invoice uses POST with InvoiceID ───────────────

class TestSyncInvoiceUpdate:

    @pytest.mark.asyncio
    async def test_existing_invoice_uses_post(self):
        """If xero_invoice_id already set, the invoice must POST (update), not PUT (create new)."""
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "xero-existing-id", "LineItems": [{}]}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.sync_invoice(
                _invoice(xero_invoice_id="xero-existing-id"), settings
            )

        # The invoice call must use POST. Any put() calls are the COGS journal (ManualJournals).
        mock_client.post.assert_called()
        first_post_url = mock_client.post.call_args_list[0][0][0]
        assert "/Invoices" in first_post_url, (
            f"Expected POST to /Invoices, got {first_post_url!r}"
        )
        # No PUT to /Invoices — only the COGS journal may use PUT
        invoice_put_calls = [
            c for c in mock_client.put.call_args_list
            if "/Invoices" in str(c[0][0] if c[0] else "")
        ]
        assert len(invoice_put_calls) == 0, (
            "Existing invoice must not use PUT to /Invoices — that creates a duplicate"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_existing_invoice_payload_includes_invoice_id(self):
        """The InvoiceID must be in the payload when updating."""
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "xero-existing-id", "LineItems": [{}]}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_invoice(
                _invoice(xero_invoice_id="xero-existing-id"), settings
            )

        payload = mock_client.post.call_args[1]["json"]
        assert payload["Invoices"][0].get("InvoiceID") == "xero-existing-id"


# ── 3. PO receipt — must send ACCPAY Bill, never ManualJournals ───────────────

class TestSyncPOReceipt:

    @pytest.mark.asyncio
    async def test_po_receipt_sends_bill_not_journal(self):
        """This is the critical regression test — manual journal was the old (wrong) behaviour."""
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "xero-bill-1"}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.sync_po_receipt(_po(), 375.0, settings)

        # Must NOT hit ManualJournals
        for c in mock_client.put.call_args_list + mock_client.post.call_args_list:
            url = c[0][0] if c[0] else c[1].get("url", "")
            assert "ManualJournals" not in str(url), (
                "PO receipt must send a Bill to /Invoices, not a ManualJournal"
            )

        assert result.success is True
        assert result.xero_invoice_id == "xero-bill-1"

    @pytest.mark.asyncio
    async def test_po_receipt_type_is_accpay(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "xero-bill-1"}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_po_receipt(_po(), 375.0, settings)

        payload = mock_client.put.call_args[1]["json"]
        assert payload["Invoices"][0]["Type"] == "ACCPAY"

    @pytest.mark.asyncio
    async def test_po_receipt_contact_is_vendor(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "xero-bill-1"}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_po_receipt(_po(), 375.0, settings)

        payload = mock_client.put.call_args[1]["json"]
        assert payload["Invoices"][0]["Contact"]["Name"] == "Lumberyard Inc"

    @pytest.mark.asyncio
    async def test_po_receipt_per_line_items_when_available(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "xero-bill-1"}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_po_receipt(_po(), 375.0, settings)

        payload = mock_client.put.call_args[1]["json"]
        line_items = payload["Invoices"][0]["LineItems"]
        assert len(line_items) == 2
        descriptions = [li["Description"] for li in line_items]
        assert "2x4 Pine" in descriptions
        assert "Drywall Sheet" in descriptions

    @pytest.mark.asyncio
    async def test_po_receipt_fallback_to_single_line_when_no_items(self):
        """When items list is empty, falls back to a single total line."""
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "xero-bill-1"}]}
        )
        po_no_items = {**_po(), "items": []}
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_po_receipt(po_no_items, 500.0, settings)

        payload = mock_client.put.call_args[1]["json"]
        line_items = payload["Invoices"][0]["LineItems"]
        assert len(line_items) == 1
        assert line_items[0]["UnitAmount"] == 500.0

    @pytest.mark.asyncio
    async def test_po_receipt_existing_bill_id_uses_post(self):
        """If xero_bill_id already exists, must POST (update) not PUT (duplicate)."""
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "existing-bill-id"}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_po_receipt(
                _po(xero_bill_id="existing-bill-id"), 375.0, settings
            )

        mock_client.post.assert_called_once()
        mock_client.put.assert_not_called()
        payload = mock_client.post.call_args[1]["json"]
        assert payload["Invoices"][0]["InvoiceID"] == "existing-bill-id"


# ── 4. Credit note sync ───────────────────────────────────────────────────────

class TestSyncCreditNote:

    @pytest.mark.asyncio
    async def test_credit_note_type_is_accrec(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"CreditNotes": [{"CreditNoteID": "xero-cn-1"}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.sync_credit_note(_credit_note(), settings)

        payload = mock_client.put.call_args[1]["json"]
        assert payload["CreditNotes"][0]["Type"] == "ACCREC"
        assert result.success is True
        assert result.xero_invoice_id == "xero-cn-1"

    @pytest.mark.asyncio
    async def test_credit_note_is_authorised(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"CreditNotes": [{"CreditNoteID": "xero-cn-1"}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_credit_note(_credit_note(), settings)

        payload = mock_client.put.call_args[1]["json"]
        assert payload["CreditNotes"][0]["Status"] == "AUTHORISED"

    @pytest.mark.asyncio
    async def test_credit_note_contact_is_billing_entity(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"CreditNotes": [{"CreditNoteID": "xero-cn-1"}]}
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_credit_note(_credit_note(), settings)

        payload = mock_client.put.call_args[1]["json"]
        assert payload["CreditNotes"][0]["Contact"]["Name"] == "On Point LLC"

    @pytest.mark.asyncio
    async def test_credit_note_existing_id_uses_post(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client(
            {"CreditNotes": [{"CreditNoteID": "existing-cn-id"}]}
        )
        cn = {**_credit_note(), "xero_credit_note_id": "existing-cn-id"}
        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.sync_credit_note(cn, settings)

        mock_client.post.assert_called_once()
        mock_client.put.assert_not_called()


# ── 5. Reconcile fetch methods ────────────────────────────────────────────────

class TestFetchMethods:

    @pytest.mark.asyncio
    async def test_fetch_invoice_normalises_response(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client({
            "Invoices": [{
                "InvoiceID": "xero-inv-1",
                "Total": 110.0,
                "Status": "AUTHORISED",
                "LineItems": [{}, {}],
            }]
        })
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.fetch_invoice("xero-inv-1", settings)

        assert result["total"] == 110.0
        assert result["line_count"] == 2
        assert result["status"] == "AUTHORISED"

    @pytest.mark.asyncio
    async def test_fetch_invoice_empty_response_returns_empty_dict(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client({"Invoices": []})
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.fetch_invoice("xero-inv-missing", settings)

        assert result == {}

    @pytest.mark.asyncio
    async def test_fetch_credit_note_normalises_response(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client({
            "CreditNotes": [{
                "CreditNoteID": "xero-cn-1",
                "Total": 30.0,
                "Status": "AUTHORISED",
                "LineItems": [{}],
            }]
        })
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.fetch_credit_note("xero-cn-1", settings)

        assert result["total"] == 30.0
        assert result["line_count"] == 1
        assert result["status"] == "AUTHORISED"


# ── 6. Token refresh ──────────────────────────────────────────────────────────

class TestTokenRefresh:

    def test_is_token_expired_true_when_past_expiry(self):
        adapter = XeroAdapter()
        settings = _expired_settings()
        assert adapter._is_token_expired(settings) is True

    def test_is_token_expired_false_when_future_expiry(self):
        adapter = XeroAdapter()
        settings = _settings()
        assert adapter._is_token_expired(settings) is False

    def test_is_token_expired_true_when_no_expiry(self):
        adapter = XeroAdapter()
        settings = _settings(xero_token_expiry=None)
        assert adapter._is_token_expired(settings) is True

    @pytest.mark.asyncio
    async def test_expired_token_triggers_refresh_before_sync(self):
        """When token is expired, refresh must be called before the API request."""
        adapter = XeroAdapter()
        settings = _expired_settings()

        refreshed_settings = _settings()

        mock_client = _mock_http_client(
            {"Invoices": [{"InvoiceID": "xero-inv-after-refresh", "LineItems": [{}]}]}
        )
        with patch.object(adapter, "refresh_token", AsyncMock(return_value=refreshed_settings)) as mock_refresh:
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await adapter.sync_invoice(_invoice(), settings)

        mock_refresh.assert_called_once()
        assert result.success is True


# ── 7. Error handling ─────────────────────────────────────────────────────────

class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_sync_invoice_empty_xero_response_returns_failure(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client({"Invoices": []})
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.sync_invoice(_invoice(), settings)

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_sync_po_receipt_empty_xero_response_returns_failure(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client({"Invoices": []})
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.sync_po_receipt(_po(), 375.0, settings)

        assert result.success is False

    @pytest.mark.asyncio
    async def test_sync_credit_note_empty_response_returns_failure(self):
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = _mock_http_client({"CreditNotes": []})
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.sync_credit_note(_credit_note(), settings)

        assert result.success is False


# ── 8. COGS repost ────────────────────────────────────────────────────────────

class TestRepostCogsJournal:

    def _make_mock_client_for_repost(self, void_response=None):
        """Return a mock client for a repost: POST to void + PUT to create new journal."""
        void_resp = MagicMock()
        void_resp.raise_for_status = MagicMock()
        void_resp.json.return_value = void_response or {}

        new_jnl_resp = MagicMock()
        new_jnl_resp.raise_for_status = MagicMock()
        new_jnl_resp.json.return_value = {"ManualJournals": [{"ManualJournalID": "new-jnl-id"}]}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=void_resp)
        mock_client.put = AsyncMock(return_value=new_jnl_resp)
        mock_client.get = AsyncMock()
        return mock_client

    @pytest.mark.asyncio
    async def test_repost_voids_old_journal_then_posts_new(self):
        """repost_cogs_journal must POST to void the old journal, then PUT a new one."""
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = self._make_mock_client_for_repost()

        with patch("httpx.AsyncClient", return_value=mock_client):
            new_id = await adapter.repost_cogs_journal(
                _invoice(xero_invoice_id="xero-inv-1"),
                settings,
                old_journal_id="old-jnl-id",
            )

        # Must have POSTed to void the old journal
        void_call_urls = [c[0][0] for c in mock_client.post.call_args_list]
        assert any("ManualJournals/old-jnl-id" in url for url in void_call_urls), (
            f"Expected POST to ManualJournals/old-jnl-id to void it, got: {void_call_urls}"
        )
        # Must have PUT a new journal
        put_urls = [c[0][0] for c in mock_client.put.call_args_list]
        assert any("ManualJournals" in url for url in put_urls), (
            "Expected PUT to ManualJournals for the new COGS journal"
        )
        assert new_id == "new-jnl-id"

    @pytest.mark.asyncio
    async def test_repost_without_old_journal_id_skips_void(self):
        """When old_journal_id is None, no void call must be made."""
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = self._make_mock_client_for_repost()

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.repost_cogs_journal(
                _invoice(xero_invoice_id="xero-inv-1"),
                settings,
                old_journal_id=None,
            )

        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_repost_void_failure_is_non_fatal(self):
        """If voiding the old journal fails, repost must still post the new journal."""
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = self._make_mock_client_for_repost()
        mock_client.post = AsyncMock(side_effect=Exception("Xero 404 — journal not found"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            new_id = await adapter.repost_cogs_journal(
                _invoice(xero_invoice_id="xero-inv-1"),
                settings,
                old_journal_id="gone-jnl-id",
            )

        # Despite void failure, a new journal was still posted
        assert new_id == "new-jnl-id", (
            "New COGS journal must be posted even if voiding the old one failed"
        )

    @pytest.mark.asyncio
    async def test_repost_returns_none_when_cost_total_is_zero(self):
        """If all line item costs are zero, no journal should be posted."""
        adapter = XeroAdapter()
        settings = _settings()
        mock_client = self._make_mock_client_for_repost()

        zero_cost_invoice = {
            **_invoice(xero_invoice_id="xero-inv-1"),
            "line_items": [
                {"description": "Free item", "quantity": 5, "unit_price": 10.0,
                 "amount": 50.0, "cost": 0.0, "product_id": "p1", "job_id": None}
            ],
        }

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.repost_cogs_journal(
                zero_cost_invoice, settings, old_journal_id=None
            )

        assert result is None
        mock_client.put.assert_not_called()
