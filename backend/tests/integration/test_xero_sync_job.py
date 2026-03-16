"""
Xero sync job integration tests — real DB (Postgres), stub adapter.

Every test uses the `call` fixture from the integration conftest so the full
schema is bootstrapped and all repos run for real. The Xero adapter is always
the StubXeroAdapter (no network calls).

Tests cover the three most dangerous failure modes:
  1. Idempotency — running the sync job twice must not create duplicate
     Xero records or duplicate financial entries.
  2. Status gating — draft invoices must never sync; only approved/sent.
  3. Adjustment bug — two adjustments on the same product must both record
     separate financial ledger entries (the pre-fix behaviour silently dropped
     the second one).
  4. Correct status transitions — sync sets 'synced', reconcile mismatch sets
     'mismatch', failed sync sets 'failed'.
  5. PO queuing — receiving stock sets xero_sync_status = 'pending' on the PO.
  6. Credit note sync — applied credit notes get a xero_credit_note_id.
  7. Health endpoint returns correct counts matching DB state.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from finance.application.invoice_service import (
    create_invoice_from_withdrawals,
    update_invoice,
)
from finance.infrastructure.credit_note_repo import credit_note_repo
from finance.infrastructure.invoice_repo import invoice_repo
from operations.infrastructure.withdrawal_repo import withdrawal_repo
from shared.infrastructure.database import get_connection

_STUB_XERO_TOKEN = "stub-" + "token"
_STUB_TENANT = "stub-tenant"

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_withdrawal(billing_entity="On Point LLC") -> str:
    from operations.domain.withdrawal import MaterialWithdrawal, WithdrawalItem

    wid = str(uuid4())
    await withdrawal_repo.insert(
        MaterialWithdrawal(
            id=wid,
            items=[
                WithdrawalItem(
                    product_id="p1",
                    sku="SKU-1",
                    name="Lumber",
                    quantity=2,
                    unit_price=10.0,
                    cost=6.0,
                )
            ],
            job_id="JOB-1",
            service_address="1 Main St",
            subtotal=20.0,
            tax=1.6,
            total=21.6,
            cost_total=12.0,
            contractor_id="contractor-1",
            contractor_name="Test Contractor",
            contractor_company=billing_entity,
            billing_entity=billing_entity,
            payment_status="unpaid",
            processed_by_id="user-1",
            processed_by_name="Test",
            created_at="2025-01-01T00:00:00Z",
            organization_id="default",
        )
    )
    return wid


async def _make_approved_invoice(billing_entity="On Point LLC"):
    wid = await _make_withdrawal(billing_entity)
    inv = await create_invoice_from_withdrawals([wid])
    return await update_invoice(inv.id, status="approved")


async def _run_sync_with_stub():
    """Run the sync job with StubXeroAdapter injected at every call site."""
    from finance.adapters.stub_xero import StubXeroAdapter
    from finance.application.xero_sync_job import run_sync
    from finance.domain.xero_settings import XeroSettings

    stub_settings = XeroSettings(
        organization_id="default",
        xero_access_token=_STUB_XERO_TOKEN,
        xero_tenant_id="stub-tenant",
    )
    stub_gateway = StubXeroAdapter()

    with (
        patch(
            "finance.application.xero_sync_job.get_xero_settings",
            AsyncMock(return_value=stub_settings),
        ),
        patch("finance.application.xero_sync_job.get_invoicing_gateway", return_value=stub_gateway),
        patch(
            "finance.application.invoice_sync.get_xero_settings",
            AsyncMock(return_value=stub_settings),
        ),
        patch("finance.application.invoice_sync.get_invoicing_gateway", return_value=stub_gateway),
    ):
        return await run_sync(reconcile=False)


# ── 1. Idempotency ────────────────────────────────────────────────────────────


class TestSyncJobIdempotency:
    def test_running_sync_twice_does_not_change_xero_invoice_id(self, call):
        """The xero_invoice_id stored after first sync must be identical after second sync."""

        async def _body():
            inv = await _make_approved_invoice()
            inv_id = inv.id

            await _run_sync_with_stub()
            inv_after_1 = await invoice_repo.get_by_id(inv_id)
            xero_id_1 = inv_after_1.xero_invoice_id
            assert xero_id_1 is not None, "First sync should set xero_invoice_id"

            await _run_sync_with_stub()
            inv_after_2 = await invoice_repo.get_by_id(inv_id)
            xero_id_2 = inv_after_2.xero_invoice_id

            assert xero_id_1 == xero_id_2, (
                f"xero_invoice_id changed between syncs: {xero_id_1!r} → {xero_id_2!r}. "
                "This would create a duplicate invoice in Xero."
            )

        call(_body)

    def test_running_sync_twice_does_not_call_put_twice(self, call):
        """StubXeroAdapter.sync_invoice should only be called once per invoice."""
        from finance.adapters.stub_xero import StubXeroAdapter
        from finance.application.xero_sync_job import run_sync
        from finance.domain.xero_settings import XeroSettings

        stub_settings = XeroSettings(
            organization_id="default",
            xero_access_token=_STUB_XERO_TOKEN,
            xero_tenant_id="stub-tenant",
        )
        stub_gateway = StubXeroAdapter()
        call_count = 0
        original_sync = stub_gateway.sync_invoice

        async def counting_sync(invoice, settings):
            nonlocal call_count
            call_count += 1
            return await original_sync(invoice, settings)

        stub_gateway.sync_invoice = counting_sync

        with (
            patch(
                "finance.application.xero_sync_job.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.xero_sync_job.get_invoicing_gateway", return_value=stub_gateway
            ),
            patch(
                "finance.application.invoice_sync.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.invoice_sync.get_invoicing_gateway",
                return_value=stub_gateway,
            ),
        ):

            async def _body():
                await _make_approved_invoice()
                await run_sync(reconcile=False)
                await run_sync(reconcile=False)

            call(_body)

        assert call_count == 1, (
            f"sync_invoice called {call_count} times — should be called exactly once. "
            "A second call would create a duplicate Xero invoice."
        )

    def test_sync_sets_status_to_synced(self, call):
        async def _body():
            inv = await _make_approved_invoice()
            await _run_sync_with_stub()
            inv_after = await invoice_repo.get_by_id(inv.id)
            assert inv_after.xero_sync_status == "synced"

        call(_body)


# ── 2. Status gating ──────────────────────────────────────────────────────────


class TestSyncStatusGating:
    def test_draft_invoice_is_not_synced(self, call):
        """A draft invoice must never be pushed to Xero."""

        async def _body():
            wid = await _make_withdrawal()
            inv = await create_invoice_from_withdrawals([wid])
            assert inv.status == "draft"

            await _run_sync_with_stub()

            inv_after = await invoice_repo.get_by_id(inv.id)
            assert inv_after.xero_invoice_id is None, "Draft invoice must not be synced to Xero"
            assert inv_after.xero_sync_status == "pending"

        call(_body)

    def test_approved_invoice_is_synced(self, call):
        async def _body():
            inv = await _make_approved_invoice()
            await _run_sync_with_stub()
            inv_after = await invoice_repo.get_by_id(inv.id)
            assert inv_after.xero_invoice_id is not None

        call(_body)

    def test_paid_invoice_already_synced_is_not_re_synced(self, call):
        """A paid invoice that already has a xero_invoice_id must not be touched."""
        from finance.adapters.stub_xero import StubXeroAdapter
        from finance.application.xero_sync_job import run_sync
        from finance.domain.xero_settings import XeroSettings

        stub_settings = XeroSettings(
            organization_id="default", xero_access_token=_STUB_XERO_TOKEN, xero_tenant_id="t"
        )
        stub_gateway = StubXeroAdapter()
        call_count = 0
        original = stub_gateway.sync_invoice

        async def counting(inv, s):
            nonlocal call_count
            call_count += 1
            return await original(inv, s)

        stub_gateway.sync_invoice = counting

        with (
            patch(
                "finance.application.xero_sync_job.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.xero_sync_job.get_invoicing_gateway", return_value=stub_gateway
            ),
            patch(
                "finance.application.invoice_sync.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.invoice_sync.get_invoicing_gateway",
                return_value=stub_gateway,
            ),
        ):

            async def _body():
                inv = await _make_approved_invoice()
                inv_id = inv.id
                conn = get_connection()
                # Manually set it as already synced + paid
                await conn.execute(
                    "UPDATE invoices SET xero_invoice_id = 'already-synced', xero_sync_status = 'synced', status = 'paid' WHERE id = $1",
                    (inv_id,),
                )
                await conn.commit()
                await run_sync(reconcile=False)

            call(_body)

        assert call_count == 0, "Already-synced invoice must not trigger another sync call"


# ── 3. Adjustment idempotency bug fix ─────────────────────────────────────────


class TestAdjustmentIdempotencyFix:
    """
    Before the fix, adjustment_ref_id=product_id meant the second adjustment
    on any product silently skipped financial recording (entries_exist returned True).
    After the fix, each adjustment generates a unique ID, so both are recorded.
    """

    def test_two_adjustments_on_same_product_both_record_ledger_entries(self, call):
        async def _body():
            from catalog.application.sku_lifecycle import create_product_with_sku
            from inventory.application.inventory_service import (
                process_adjustment_stock_changes,
                process_import_stock_changes,
            )

            product = await create_product_with_sku(
                category_id="dept-1",
                category_name="Hardware",
                name="Test Adjust Product",
                quantity=100.0,
                price=10.0,
                cost=5.0,
                user_id="user-1",
                user_name="Test",
                on_stock_import=process_import_stock_changes,
            )

            await process_adjustment_stock_changes(
                product_id=product.id,
                quantity_delta=+5.0,
                reason="found",
                user_id="user-1",
                user_name="Test",
            )
            await process_adjustment_stock_changes(
                product_id=product.id,
                quantity_delta=-3.0,
                reason="damage",
                user_id="user-1",
                user_name="Test",
            )

            conn = get_connection()
            cursor = await conn.execute(
                """SELECT COUNT(*) FROM financial_ledger
                   WHERE reference_type = 'adjustment' AND product_id = $1""",
                (product.id,),
            )
            row = await cursor.fetchone()
            count = row[0]

            # 2 entries per adjustment (INVENTORY + offset account) × 2 adjustments = 4
            assert count == 4, (
                f"Expected 4 ledger entries for 2 adjustments, got {count}. "
                "The adjustment idempotency bug is likely re-introduced — "
                "adjustment_ref_id must be a unique ID per adjustment, not product_id."
            )

        call(_body)

    def test_adjustment_ref_ids_are_unique(self, call):
        """Each adjustment must produce a distinct reference_id in the ledger."""

        async def _body():
            from catalog.application.sku_lifecycle import create_product_with_sku
            from inventory.application.inventory_service import (
                process_adjustment_stock_changes,
                process_import_stock_changes,
            )

            product = await create_product_with_sku(
                category_id="dept-1",
                category_name="Hardware",
                name="Test Unique Refs",
                quantity=50.0,
                price=10.0,
                cost=5.0,
                user_id="user-1",
                user_name="Test",
                on_stock_import=process_import_stock_changes,
            )

            for i in range(3):
                await process_adjustment_stock_changes(
                    product_id=product.id,
                    quantity_delta=float(i + 1),
                    reason="found",
                    user_id="user-1",
                    user_name="Test",
                )

            conn = get_connection()
            cursor = await conn.execute(
                """SELECT DISTINCT reference_id FROM financial_ledger
                   WHERE reference_type = 'adjustment' AND product_id = $1""",
                (product.id,),
            )
            rows = await cursor.fetchall()
            distinct_ref_ids = [r[0] for r in rows]

            assert len(distinct_ref_ids) == 3, (
                f"Expected 3 distinct adjustment reference_ids, got {len(distinct_ref_ids)}: {distinct_ref_ids}. "
                "Each adjustment must have its own unique reference_id for correct idempotency."
            )

        call(_body)


# ── 4. Reconciliation mismatch detection ─────────────────────────────────────


class TestReconciliationMismatch:
    def test_total_mismatch_sets_mismatch_status(self, call):
        """When Xero returns a different total, xero_sync_status must become 'mismatch'."""
        from finance.adapters.stub_xero import StubXeroAdapter
        from finance.application.xero_sync_job import run_sync
        from finance.domain.xero_settings import XeroSettings

        stub_settings = XeroSettings(
            organization_id="default", xero_access_token=_STUB_XERO_TOKEN, xero_tenant_id="t"
        )
        stub_gateway = StubXeroAdapter()

        # For the first sync pass
        with (
            patch(
                "finance.application.xero_sync_job.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.xero_sync_job.get_invoicing_gateway", return_value=stub_gateway
            ),
            patch(
                "finance.application.invoice_sync.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.invoice_sync.get_invoicing_gateway",
                return_value=stub_gateway,
            ),
        ):

            async def _body_sync():
                inv = await _make_approved_invoice()
                await run_sync(reconcile=False)
                inv_synced = await invoice_repo.get_by_id(inv.id)
                assert inv_synced.xero_invoice_id is not None
                return inv.id

            inv_id = call(_body_sync)

        # Now run reconcile with a stub that returns a wrong total
        mismatch_gateway = StubXeroAdapter()
        mismatch_gateway.fetch_invoice = AsyncMock(
            return_value={
                "total": 9999.99,  # clearly wrong
                "line_count": 1,
                "status": "AUTHORISED",
            }
        )

        with (
            patch(
                "finance.application.xero_sync_job.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.xero_sync_job.get_invoicing_gateway",
                return_value=mismatch_gateway,
            ),
        ):

            async def _body_reconcile():
                await run_sync(reconcile=True)
                inv_after = await invoice_repo.get_by_id(inv_id)
                assert inv_after.xero_sync_status == "mismatch", (
                    f"Expected xero_sync_status='mismatch', got {inv_after.xero_sync_status!r}"
                )

            call(_body_reconcile)

    def test_matching_totals_keeps_synced_status(self, call):
        """When Xero total matches local total, status stays 'synced'."""
        from finance.adapters.stub_xero import StubXeroAdapter
        from finance.application.xero_sync_job import run_sync
        from finance.domain.xero_settings import XeroSettings

        stub_settings = XeroSettings(
            organization_id="default", xero_access_token=_STUB_XERO_TOKEN, xero_tenant_id="t"
        )

        # First sync
        stub_gateway = StubXeroAdapter()
        with (
            patch(
                "finance.application.xero_sync_job.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.xero_sync_job.get_invoicing_gateway", return_value=stub_gateway
            ),
            patch(
                "finance.application.invoice_sync.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.invoice_sync.get_invoicing_gateway",
                return_value=stub_gateway,
            ),
        ):

            async def _body_sync():
                inv = await _make_approved_invoice()
                await run_sync(reconcile=False)
                inv_synced = await invoice_repo.get_by_id(inv.id)
                return inv.id, inv_synced.total, len(inv_synced.line_items)

            inv_id, local_total, local_line_count = call(_body_sync)

        # Reconcile with matching data
        matching_gateway = StubXeroAdapter()
        matching_gateway.fetch_invoice = AsyncMock(
            return_value={
                "total": local_total,
                "line_count": local_line_count,
                "status": "AUTHORISED",
            }
        )

        with (
            patch(
                "finance.application.xero_sync_job.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.xero_sync_job.get_invoicing_gateway",
                return_value=matching_gateway,
            ),
        ):

            async def _body_reconcile():
                await run_sync(reconcile=True)
                inv_final = await invoice_repo.get_by_id(inv_id)
                assert inv_final.xero_sync_status == "synced"

            call(_body_reconcile)


# ── 5. Credit note sync ───────────────────────────────────────────────────────


class TestCreditNoteSync:
    def test_applied_credit_note_gets_xero_id(self, call):
        """An applied credit note must receive a xero_credit_note_id after sync."""

        async def _body():
            cn_id = str(uuid4())
            cn_number = "CN-00001"
            conn = get_connection()
            now = "2025-01-01T00:00:00Z"
            await conn.execute(
                """INSERT INTO credit_notes
                   (id, credit_note_number, invoice_id, return_id, billing_entity,
                    status, subtotal, tax, total, notes, xero_credit_note_id,
                    xero_sync_status, organization_id, created_at, updated_at)
                   VALUES ($1, $2, NULL, NULL, 'On Point LLC',
                           'applied', 30.0, 0.0, 30.0, NULL, NULL,
                           'pending', 'default', $3, $4)""",
                (cn_id, cn_number, now, now),
            )
            await conn.execute(
                """INSERT INTO credit_note_line_items
                   (id, credit_note_id, description, quantity, unit_price, amount, cost, product_id)
                   VALUES ($1, $2, 'Returned lumber', 3, 10.0, 30.0, 6.0, NULL)""",
                (str(uuid4()), cn_id),
            )
            await conn.commit()

            await _run_sync_with_stub()

            cn_after = await credit_note_repo.get_by_id(cn_id)
            assert cn_after.xero_credit_note_id is not None, (
                "Applied credit note must be synced to Xero"
            )
            assert cn_after.xero_sync_status == "synced"

        call(_body)

    def test_draft_credit_note_is_not_synced(self, call):
        """A draft credit note must not be pushed to Xero."""

        async def _body():
            cn_id = str(uuid4())
            conn = get_connection()
            now = "2025-01-01T00:00:00Z"
            await conn.execute(
                """INSERT INTO credit_notes
                   (id, credit_note_number, invoice_id, return_id, billing_entity,
                    status, subtotal, tax, total, notes, xero_credit_note_id,
                    xero_sync_status, organization_id, created_at, updated_at)
                   VALUES ($1, 'CN-DRAFT', NULL, NULL, 'On Point LLC',
                           'draft', 30.0, 0.0, 30.0, NULL, NULL,
                           'pending', 'default', $2, $3)""",
                (cn_id, now, now),
            )
            await conn.commit()

            await _run_sync_with_stub()

            cn_after = await credit_note_repo.get_by_id(cn_id)
            assert cn_after.xero_credit_note_id is None

        call(_body)


# ── 6. PO queuing ─────────────────────────────────────────────────────────────


class TestPOQueuing:
    def test_queue_po_for_sync_sets_pending_status(self, call):
        async def _body():
            from finance.application.po_sync_service import queue_po_for_sync
            from purchasing.domain.purchase_order import POStatus, PurchaseOrder
            from purchasing.infrastructure.po_repo import po_repo

            po = PurchaseOrder(
                vendor_id="v1",
                vendor_name="Acme Corp",
                status=POStatus.RECEIVED,
                created_by_id="user-1",
                created_by_name="Test",
                organization_id="default",
            )
            await po_repo.insert_po(po)

            await queue_po_for_sync(po.id)

            po_after = await po_repo.get_po(po.id)
            assert po_after.xero_sync_status == "pending"

        call(_body)

    def test_po_bill_sync_stores_xero_bill_id(self, call):
        from finance.adapters.stub_xero import StubXeroAdapter
        from finance.domain.xero_settings import XeroSettings

        stub_settings = XeroSettings(
            organization_id="default", xero_access_token=_STUB_XERO_TOKEN, xero_tenant_id="t"
        )
        stub_gateway = StubXeroAdapter()

        with (
            patch(
                "finance.application.po_sync_service.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.po_sync_service.get_invoicing_gateway",
                return_value=stub_gateway,
            ),
        ):

            async def _body():
                from finance.application.po_sync_service import queue_po_for_sync, sync_po_bill
                from purchasing.domain.purchase_order import (
                    POItemStatus,
                    POStatus,
                    PurchaseOrder,
                    PurchaseOrderItem,
                )
                from purchasing.infrastructure.po_repo import po_repo

                po = PurchaseOrder(
                    vendor_id="v1",
                    vendor_name="Acme Corp",
                    status=POStatus.RECEIVED,
                    created_by_id="user-1",
                    created_by_name="Test",
                    organization_id="default",
                )
                await po_repo.insert_po(po)

                item = PurchaseOrderItem(
                    po_id=po.id,
                    name="2x4 Pine",
                    ordered_qty=50,
                    delivered_qty=50,
                    unit_price=5.0,
                    cost=4.0,
                    base_unit="each",
                    sell_uom="each",
                    pack_qty=1,
                    suggested_department="HDW",
                    status=POItemStatus.ARRIVED,
                    organization_id="default",
                )
                await po_repo.insert_items([item])
                await queue_po_for_sync(po.id)

                result = await sync_po_bill(po.id)

                assert result.success is True
                po_after = await po_repo.get_po(po.id)
                assert po_after.xero_bill_id is not None
                assert po_after.xero_sync_status == "synced"

            call(_body)

    def test_po_bill_sync_idempotent(self, call):
        """Calling sync_po_bill twice must not change the stored xero_bill_id."""
        from finance.adapters.stub_xero import StubXeroAdapter
        from finance.domain.xero_settings import XeroSettings

        stub_settings = XeroSettings(
            organization_id="default", xero_access_token=_STUB_XERO_TOKEN, xero_tenant_id="t"
        )
        stub_gateway = StubXeroAdapter()

        with (
            patch(
                "finance.application.po_sync_service.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.po_sync_service.get_invoicing_gateway",
                return_value=stub_gateway,
            ),
        ):

            async def _body():
                from finance.application.po_sync_service import sync_po_bill
                from purchasing.domain.purchase_order import (
                    POItemStatus,
                    POStatus,
                    PurchaseOrder,
                    PurchaseOrderItem,
                )
                from purchasing.infrastructure.po_repo import po_repo

                po = PurchaseOrder(
                    vendor_id="v1",
                    vendor_name="Acme Corp",
                    status=POStatus.RECEIVED,
                    created_by_id="user-1",
                    created_by_name="Test",
                    organization_id="default",
                )
                await po_repo.insert_po(po)
                item = PurchaseOrderItem(
                    po_id=po.id,
                    name="Widget",
                    ordered_qty=10,
                    delivered_qty=10,
                    unit_price=5.0,
                    cost=4.0,
                    base_unit="each",
                    sell_uom="each",
                    pack_qty=1,
                    suggested_department="HDW",
                    status=POItemStatus.ARRIVED,
                    organization_id="default",
                )
                await po_repo.insert_items([item])

                r1 = await sync_po_bill(po.id)
                r2 = await sync_po_bill(po.id)

                po_after = await po_repo.get_po(po.id)
                assert r1.xero_bill_id == r2.xero_bill_id == po_after.xero_bill_id

            call(_body)


# ── 7. Sync summary counts ────────────────────────────────────────────────────


class TestSyncSummaryCounts:
    def test_sync_summary_reflects_synced_count(self, call):
        async def _body():
            await _make_approved_invoice()
            await _make_approved_invoice()

            summary = await _run_sync_with_stub()

            assert summary.invoices_synced == 2
            assert summary.invoices_failed == 0

        call(_body)

    def test_failed_sync_increments_failed_count(self, call):
        """A gateway that raises must increment failed count and set 'failed' status."""
        from finance.adapters.stub_xero import StubXeroAdapter
        from finance.application.xero_sync_job import run_sync
        from finance.domain.xero_settings import XeroSettings
        from finance.ports.invoicing_port import InvoiceSyncResult

        failing_gateway = StubXeroAdapter()
        failing_gateway.sync_invoice = AsyncMock(
            return_value=InvoiceSyncResult(success=False, error="Xero API unavailable")
        )

        stub_settings = XeroSettings(
            organization_id="default", xero_access_token=_STUB_XERO_TOKEN, xero_tenant_id="t"
        )
        with (
            patch(
                "finance.application.xero_sync_job.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.xero_sync_job.get_invoicing_gateway",
                return_value=failing_gateway,
            ),
            patch(
                "finance.application.invoice_sync.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.invoice_sync.get_invoicing_gateway",
                return_value=failing_gateway,
            ),
        ):

            async def _body():
                inv = await _make_approved_invoice()
                summary = await run_sync(reconcile=False)

                assert summary.invoices_failed == 1
                inv_after = await invoice_repo.get_by_id(inv.id)
                assert inv_after.xero_sync_status == "failed"
                assert inv_after.xero_invoice_id is None

            call(_body)

    def test_sync_summary_includes_cogs_repost_keys(self, call):
        """run_sync summary must always include cogs_reposted / cogs_repost_failed keys."""

        async def _body():
            summary = await _run_sync_with_stub()
            assert hasattr(summary, "cogs_reposted")
            assert hasattr(summary, "cogs_repost_failed")

        call(_body)


# ── 8. COGS re-post on line item edit ─────────────────────────────────────────


class TestCogsRepost:
    def test_editing_line_items_on_synced_invoice_sets_cogs_stale(self, call):
        """After a successful sync, editing line items must set xero_sync_status='cogs_stale'."""

        async def _body():
            inv = await _make_approved_invoice()
            inv_id = inv.id

            # Sync it first
            await _run_sync_with_stub()
            inv_synced = await invoice_repo.get_by_id(inv_id)
            assert inv_synced.xero_invoice_id is not None
            assert inv_synced.xero_sync_status == "synced"

            # Now edit the line items
            new_items = [
                {
                    "description": "Modified lumber",
                    "quantity": 5,
                    "unit_price": 12.0,
                    "amount": 60.0,
                    "cost": 7.0,
                    "product_id": "p1",
                    "job_id": "JOB-1",
                }
            ]
            await update_invoice(inv_id, line_items=new_items)

            inv_after_edit = await invoice_repo.get_by_id(inv_id)
            assert inv_after_edit.xero_sync_status == "cogs_stale", (
                f"Expected 'cogs_stale' after line item edit, got {inv_after_edit.xero_sync_status!r}"
            )

        call(_body)

    def test_editing_line_items_on_unsynced_invoice_does_not_set_cogs_stale(self, call):
        """Editing a draft/unsynced invoice must NOT set cogs_stale — it was never in Xero."""

        async def _body():
            wid = await _make_withdrawal()
            inv = await create_invoice_from_withdrawals([wid])
            assert inv.xero_invoice_id is None

            new_items = [
                {
                    "description": "Draft edit",
                    "quantity": 1,
                    "unit_price": 5.0,
                    "amount": 5.0,
                    "cost": 3.0,
                    "product_id": "p1",
                    "job_id": None,
                }
            ]
            await update_invoice(inv.id, line_items=new_items)

            inv_after = await invoice_repo.get_by_id(inv.id)
            assert inv_after.xero_sync_status != "cogs_stale", (
                "Unsynced invoice must not be marked cogs_stale — it was never sent to Xero"
            )

        call(_body)

    def test_sync_job_repost_stale_cogs_updates_status_to_synced(self, call):
        """The sync job must re-post the COGS journal and mark status back to 'synced'."""
        from finance.adapters.stub_xero import StubXeroAdapter
        from finance.application.xero_sync_job import run_sync
        from finance.domain.xero_settings import XeroSettings

        stub_settings = XeroSettings(
            organization_id="default", xero_access_token=_STUB_XERO_TOKEN, xero_tenant_id="t"
        )
        stub_gateway = StubXeroAdapter()
        repost_called = []
        original_repost = stub_gateway.repost_cogs_journal

        async def tracking_repost(invoice, settings, old_journal_id=None):
            repost_called.append(invoice.id)
            return await original_repost(invoice, settings, old_journal_id)

        stub_gateway.repost_cogs_journal = tracking_repost

        with (
            patch(
                "finance.application.xero_sync_job.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.xero_sync_job.get_invoicing_gateway", return_value=stub_gateway
            ),
            patch(
                "finance.application.invoice_sync.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.invoice_sync.get_invoicing_gateway",
                return_value=stub_gateway,
            ),
        ):

            async def _body():
                inv = await _make_approved_invoice()
                inv_id = inv.id

                # First sync
                await _run_sync_with_stub()
                inv_synced = await invoice_repo.get_by_id(inv_id)
                assert inv_synced.xero_sync_status == "synced"

                # Edit line items -> triggers cogs_stale
                await update_invoice(
                    inv_id,
                    line_items=[
                        {
                            "description": "Updated item",
                            "quantity": 3,
                            "unit_price": 15.0,
                            "amount": 45.0,
                            "cost": 9.0,
                            "product_id": "p1",
                            "job_id": "JOB-1",
                        }
                    ],
                )
                inv_stale = await invoice_repo.get_by_id(inv_id)
                assert inv_stale.xero_sync_status == "cogs_stale"

                # Run sync again — the repost pass should fix it
                summary = await run_sync(reconcile=False)

                assert inv_id in repost_called, (
                    "repost_cogs_journal must be called for the stale invoice"
                )
                assert summary.cogs_reposted == 1
                assert summary.cogs_repost_failed == 0

                inv_final = await invoice_repo.get_by_id(inv_id)
                assert inv_final.xero_sync_status == "synced", (
                    f"After COGS re-post, status must be 'synced', got {inv_final.xero_sync_status!r}"
                )
                assert inv_final.xero_cogs_journal_id is not None

            call(_body)

    def test_sync_job_skips_repost_when_no_stale_invoices(self, call):
        """When no invoices are cogs_stale, cogs_reposted must be 0."""

        async def _body():
            await _make_approved_invoice()
            await _run_sync_with_stub()

            # No line item edits after sync — nothing should be stale
            summary = await _run_sync_with_stub()
            assert summary.cogs_reposted == 0
            assert summary.cogs_repost_failed == 0

        call(_body)

    def test_cogs_repost_failure_increments_failed_count(self, call):
        """When repost_cogs_journal raises, the job must increment cogs_repost_failed."""
        from finance.adapters.stub_xero import StubXeroAdapter
        from finance.application.xero_sync_job import run_sync
        from finance.domain.xero_settings import XeroSettings

        stub_settings = XeroSettings(
            organization_id="default", xero_access_token=_STUB_XERO_TOKEN, xero_tenant_id="t"
        )
        failing_gateway = StubXeroAdapter()
        failing_gateway.repost_cogs_journal = AsyncMock(side_effect=Exception("Xero journal error"))

        with (
            patch(
                "finance.application.xero_sync_job.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.xero_sync_job.get_invoicing_gateway",
                return_value=failing_gateway,
            ),
            patch(
                "finance.application.invoice_sync.get_xero_settings",
                AsyncMock(return_value=stub_settings),
            ),
            patch(
                "finance.application.invoice_sync.get_invoicing_gateway",
                return_value=failing_gateway,
            ),
        ):

            async def _body():
                inv = await _make_approved_invoice()
                await _run_sync_with_stub()

                # Edit to make it stale
                await update_invoice(
                    inv.id,
                    line_items=[
                        {
                            "description": "Edit",
                            "quantity": 1,
                            "unit_price": 5.0,
                            "amount": 5.0,
                            "cost": 3.0,
                            "product_id": "p1",
                            "job_id": None,
                        }
                    ],
                )

                summary = await run_sync(reconcile=False)

                assert summary.cogs_repost_failed == 1
                assert summary.cogs_reposted == 0

            call(_body)
