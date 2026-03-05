"""
Accounting standards tests — verify the financial integrity layer.

Tests cover:
  1. Ledger journal grouping (all entries for one event share a journal_id)
  2. Complete double-entry: withdrawal produces REVENUE + COGS + INVENTORY + TAX + AR
  3. Trial balance integrity (debits ≈ credits across account categories)
  4. round_money precision (banker's rounding, float round-trip)
  5. Invoice lifecycle (draft → approved → sent → paid, forbidden transitions)
  6. Credit note application reduces invoice balance_due
  7. Fiscal period enforcement (closed periods reject entries)
  8. Invoice compliance fields (due_date, payment_terms, balance_due)
"""
import pytest
from uuid import uuid4

from kernel.types import round_money
from finance.domain.ledger import Account, FinancialEntry, ReferenceType
from finance.domain.invoice import (
    Invoice, InvoiceLineItem, compute_due_date,
    PAYMENT_TERMS_DAYS,
)
from finance.infrastructure.ledger_repo import insert_entries, get_journal, trial_balance
from shared.infrastructure.database import get_connection


# ── 1. round_money precision ─────────────────────────────────────────────────

class TestRoundMoney:

    def test_basic_two_decimal(self):
        assert round_money(10.005) == 10.0

    def test_bankers_rounding_half_even(self):
        assert round_money(0.125) == 0.12
        assert round_money(0.135) == 0.14

    def test_negative_values(self):
        assert round_money(-3.456) == -3.46

    def test_zero(self):
        assert round_money(0) == 0.0

    def test_large_value_precision(self):
        assert round_money(123456.789) == 123456.79

    def test_returns_float(self):
        result = round_money(10.5)
        assert isinstance(result, float)

    def test_repeating_decimal(self):
        assert round_money(1 / 3) == 0.33

    def test_subtotal_multiplication(self):
        assert round_money(2.5 * 4.0) == 10.0
        assert round_money(3 * 7.33) == 21.99


# ── 2. Ledger journal grouping ───────────────────────────────────────────────

class TestJournalGrouping:

    @pytest.mark.asyncio
    async def test_journal_id_groups_related_entries(self, db):
        journal_id = str(uuid4())
        entries = [
            FinancialEntry(
                journal_id=journal_id, account=Account.REVENUE, amount=100.0,
                reference_type=ReferenceType.WITHDRAWAL, reference_id="w-j1",
                organization_id="default",
            ),
            FinancialEntry(
                journal_id=journal_id, account=Account.COGS, amount=60.0,
                reference_type=ReferenceType.WITHDRAWAL, reference_id="w-j1",
                organization_id="default",
            ),
            FinancialEntry(
                journal_id=journal_id, account=Account.ACCOUNTS_RECEIVABLE, amount=100.0,
                reference_type=ReferenceType.WITHDRAWAL, reference_id="w-j1",
                organization_id="default",
            ),
        ]
        await insert_entries(entries)

        journal = await get_journal(journal_id)
        assert len(journal) == 3
        assert all(e["journal_id"] == journal_id for e in journal)

    @pytest.mark.asyncio
    async def test_different_journals_isolated(self, db):
        j1, j2 = str(uuid4()), str(uuid4())
        await insert_entries([
            FinancialEntry(
                journal_id=j1, account=Account.REVENUE, amount=50.0,
                reference_type=ReferenceType.WITHDRAWAL, reference_id="w-iso1",
                organization_id="default",
            ),
        ])
        await insert_entries([
            FinancialEntry(
                journal_id=j2, account=Account.REVENUE, amount=75.0,
                reference_type=ReferenceType.WITHDRAWAL, reference_id="w-iso2",
                organization_id="default",
            ),
        ])

        j1_entries = await get_journal(j1)
        j2_entries = await get_journal(j2)
        assert len(j1_entries) == 1
        assert j1_entries[0]["amount"] == 50.0
        assert len(j2_entries) == 1
        assert j2_entries[0]["amount"] == 75.0


# ── 3. Complete ledger entries for a sale ─────────────────────────────────────

class TestCompleteSaleEntries:

    @pytest.mark.asyncio
    async def test_withdrawal_produces_all_five_accounts(self, db):
        """A withdrawal must produce REVENUE, COGS, INVENTORY, TAX, and AR entries."""
        from finance.application.ledger_service import record_withdrawal

        wid = str(uuid4())
        items = [{"quantity": 2, "unit_price": 10.0, "cost": 5.0, "product_id": "p1"}]
        await record_withdrawal(
            withdrawal_id=wid, items=items,
            tax=1.60, total=21.60,
            job_id="J1", billing_entity="ACME",
            contractor_id="c1", organization_id="default",
        )

        tb = await trial_balance("default")
        assert Account.REVENUE.value in tb
        assert Account.COGS.value in tb
        assert Account.INVENTORY.value in tb
        assert Account.TAX_COLLECTED.value in tb
        assert Account.ACCOUNTS_RECEIVABLE.value in tb

    @pytest.mark.asyncio
    async def test_withdrawal_inventory_entry_is_negative(self, db):
        """On sale, INVENTORY should decrease (negative amount)."""
        from finance.application.ledger_service import record_withdrawal

        wid = str(uuid4())
        items = [{"quantity": 3, "unit_price": 8.0, "cost": 4.0, "product_id": "p1"}]
        await record_withdrawal(
            withdrawal_id=wid, items=items,
            tax=1.92, total=25.92,
            job_id="J1", billing_entity="ACME",
            contractor_id="c1", organization_id="default",
        )

        tb = await trial_balance("default")
        assert tb[Account.INVENTORY.value] < 0, "Inventory should decrease on sale"

    @pytest.mark.asyncio
    async def test_return_reverses_withdrawal_entries(self, db):
        """A return should reduce net revenue/COGS/AR and increase inventory."""
        from finance.application.ledger_service import record_withdrawal, record_return

        items = [{"quantity": 5, "unit_price": 10.0, "cost": 5.0, "product_id": "p1"}]
        await record_withdrawal(
            withdrawal_id=str(uuid4()), items=items,
            tax=4.0, total=54.0,
            job_id="J1", billing_entity="ACME",
            contractor_id="c1", organization_id="default",
        )
        await record_return(
            return_id=str(uuid4()), items=items,
            tax=4.0, total=54.0,
            job_id="J1", billing_entity="ACME",
            contractor_id="c1", organization_id="default",
        )

        tb = await trial_balance("default")
        assert tb.get(Account.REVENUE.value, 0) == pytest.approx(0.0)
        assert tb.get(Account.COGS.value, 0) == pytest.approx(0.0)
        assert tb.get(Account.ACCOUNTS_RECEIVABLE.value, 0) == pytest.approx(0.0)
        assert tb.get(Account.INVENTORY.value, 0) == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_idempotent_withdrawal_recording(self, db):
        """Recording the same withdrawal twice should not duplicate entries."""
        from finance.application.ledger_service import record_withdrawal

        wid = str(uuid4())
        items = [{"quantity": 1, "unit_price": 100.0, "cost": 50.0, "product_id": "p1"}]
        kwargs = dict(
            withdrawal_id=wid, items=items, tax=8.0, total=108.0,
            job_id="J1", billing_entity="ACME",
            contractor_id="c1", organization_id="default",
        )
        await record_withdrawal(**kwargs)
        await record_withdrawal(**kwargs)

        tb = await trial_balance("default")
        assert tb[Account.REVENUE.value] == pytest.approx(100.0)


# ── 4. Trial balance ─────────────────────────────────────────────────────────

class TestTrialBalance:

    @pytest.mark.asyncio
    async def test_empty_org_returns_empty(self, db):
        tb = await trial_balance("org-with-no-entries")
        assert tb == {}

    @pytest.mark.asyncio
    async def test_po_receipt_balances_inventory_and_ap(self, db):
        from finance.application.ledger_service import record_po_receipt

        await record_po_receipt(
            po_id=str(uuid4()),
            items=[{"cost": 20.0, "delivered_qty": 5, "product_id": "p1"}],
            vendor_name="Vendor A",
            organization_id="default",
        )

        tb = await trial_balance("default")
        assert tb[Account.INVENTORY.value] == pytest.approx(100.0)
        assert tb[Account.ACCOUNTS_PAYABLE.value] == pytest.approx(100.0)


# ── 5. Invoice lifecycle ─────────────────────────────────────────────────────

class TestInvoiceLifecycle:

    def test_allowed_transitions_draft(self):
        inv = Invoice(invoice_number="INV-001", status="draft")
        assert inv.can_transition_to("approved") is True
        assert inv.can_transition_to("sent") is True
        assert inv.can_transition_to("paid") is True

    def test_allowed_transitions_approved(self):
        inv = Invoice(invoice_number="INV-001", status="approved")
        assert inv.can_transition_to("sent") is True
        assert inv.can_transition_to("paid") is True
        assert inv.can_transition_to("draft") is False

    def test_paid_is_terminal(self):
        inv = Invoice(invoice_number="INV-001", status="paid")
        assert inv.can_transition_to("draft") is False
        assert inv.can_transition_to("approved") is False
        assert inv.can_transition_to("sent") is False

    def test_sent_can_only_go_to_paid(self):
        inv = Invoice(invoice_number="INV-001", status="sent")
        assert inv.can_transition_to("paid") is True
        assert inv.can_transition_to("draft") is False
        assert inv.can_transition_to("approved") is False


# ── 6. Invoice compliance fields ─────────────────────────────────────────────

class TestInvoiceComplianceFields:

    def test_compute_due_date_net_30(self):
        due = compute_due_date("2025-01-15", "net_30")
        assert due.startswith("2025-02-14")

    def test_compute_due_date_due_on_receipt(self):
        due = compute_due_date("2025-03-01", "due_on_receipt")
        assert due.startswith("2025-03-01")

    def test_compute_due_date_net_90(self):
        due = compute_due_date("2025-01-01", "net_90")
        assert due.startswith("2025-04-01")

    def test_balance_due_with_credits(self):
        inv = Invoice(
            invoice_number="INV-001", total=500.0, amount_credited=150.0,
        )
        assert inv.balance_due == 350.0

    def test_balance_due_fully_credited(self):
        inv = Invoice(
            invoice_number="INV-001", total=200.0, amount_credited=200.0,
        )
        assert inv.balance_due == 0.0

    def test_balance_due_no_credits(self):
        inv = Invoice(invoice_number="INV-001", total=1000.0)
        assert inv.balance_due == 1000.0

    def test_payment_terms_days_mapping(self):
        assert PAYMENT_TERMS_DAYS["net_30"] == 30
        assert PAYMENT_TERMS_DAYS["due_on_receipt"] == 0
        assert PAYMENT_TERMS_DAYS["net_15"] == 15
        assert PAYMENT_TERMS_DAYS["net_60"] == 60
        assert PAYMENT_TERMS_DAYS["net_90"] == 90

    def test_invoice_line_item_margin(self):
        li = InvoiceLineItem(
            quantity=3.0, unit_price=10.0, amount=30.0, cost=6.0,
        )
        assert li.margin == pytest.approx(12.0)
        assert li.margin_pct == pytest.approx(40.0)


# ── 7. Fiscal period enforcement ─────────────────────────────────────────────

class TestFiscalPeriodEnforcement:

    @pytest.mark.asyncio
    async def test_check_open_period_passes(self, db):
        """No closed periods → should not raise."""
        from finance.api.fiscal_periods import check_period_open
        await check_period_open("2025-06-15T00:00:00Z", "default")

    @pytest.mark.asyncio
    async def test_closed_period_blocks_entries(self, db):
        """An entry falling in a closed period should raise ValueError."""
        from finance.api.fiscal_periods import check_period_open
        conn = get_connection()
        period_id = str(uuid4())
        now = "2025-01-01T00:00:00Z"
        await conn.execute(
            """INSERT INTO fiscal_periods (id, name, start_date, end_date, status, organization_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (period_id, "Jan 2025", "2025-01-01", "2025-01-31", "closed", "default", now),
        )
        await conn.commit()

        with pytest.raises(ValueError, match="closed fiscal period"):
            await check_period_open("2025-01-15T00:00:00Z", "default")

    @pytest.mark.asyncio
    async def test_open_period_does_not_block(self, db):
        """An entry falling in an *open* period should pass."""
        from finance.api.fiscal_periods import check_period_open
        conn = get_connection()
        period_id = str(uuid4())
        now = "2025-02-01T00:00:00Z"
        await conn.execute(
            """INSERT INTO fiscal_periods (id, name, start_date, end_date, status, organization_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (period_id, "Feb 2025", "2025-02-01", "2025-02-28", "open", "default", now),
        )
        await conn.commit()

        await check_period_open("2025-02-15T00:00:00Z", "default")


# ── 8. Payment AR reduction ──────────────────────────────────────────────────

class TestPaymentAR:

    @pytest.mark.asyncio
    async def test_payment_reduces_ar(self, db):
        """After withdrawal + payment, net AR should be zero."""
        from finance.application.ledger_service import record_withdrawal, record_payment

        wid = str(uuid4())
        items = [{"quantity": 1, "unit_price": 100.0, "cost": 50.0, "product_id": "p1"}]
        await record_withdrawal(
            withdrawal_id=wid, items=items, tax=0, total=100.0,
            job_id="J1", billing_entity="ACME",
            contractor_id="c1", organization_id="default",
        )
        await record_payment(
            withdrawal_id=wid, amount=100.0, billing_entity="ACME",
            contractor_id="c1", organization_id="default",
        )

        tb = await trial_balance("default")
        assert tb.get(Account.ACCOUNTS_RECEIVABLE.value, 0) == pytest.approx(0.0)
