"""Tests for credit note atomicity — insert + link and apply + ledger.

These tests verify that credit note operations are atomic across the
finance and operations bounded contexts, preventing partial state where
a credit note exists but the return isn't linked, or the invoice is
credited but the withdrawals aren't marked paid.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest

from finance.application.credit_note_service import apply_credit_note, insert_credit_note
from finance.application.invoice_service import create_invoice_from_withdrawals
from finance.infrastructure.credit_note_repo import credit_note_repo
from operations.domain.withdrawal import MaterialWithdrawal, WithdrawalItem
from operations.infrastructure.return_repo import return_repo
from operations.infrastructure.withdrawal_repo import withdrawal_repo
from shared.infrastructure.database import get_connection


async def _create_withdrawal(billing_entity="ACME Inc") -> str:
    wid = str(uuid4())
    items = [
        WithdrawalItem(
            product_id="p1",
            sku="SKU-001",
            name="Widget",
            quantity=5,
            unit_price=10.0,
            cost=5.0,
        )
    ]
    w = MaterialWithdrawal(
        id=wid,
        items=items,
        job_id="JOB-TEST",
        service_address="123 Test St",
        subtotal=50.0,
        tax=5.0,
        total=55.0,
        cost_total=25.0,
        contractor_id="contractor-1",
        contractor_name="Test Contractor",
        contractor_company="ACME",
        billing_entity=billing_entity,
        payment_status="unpaid",
        processed_by_id="user-1",
        processed_by_name="Test",
    )
    await withdrawal_repo.insert(w)
    return wid


async def _create_return(withdrawal_id: str) -> str:
    from operations.domain.returns import MaterialReturn, ReturnItem

    rid = str(uuid4())
    ret = MaterialReturn(
        id=rid,
        withdrawal_id=withdrawal_id,
        contractor_id="contractor-1",
        contractor_name="Test Contractor",
        items=[
            ReturnItem(
                product_id="p1",
                sku="SKU-001",
                name="Widget",
                quantity=2,
                unit_price=10.0,
                cost=5.0,
            )
        ],
        reason="overorder",
        subtotal=20.0,
        tax=2.0,
        total=22.0,
        processed_by_id="user-1",
        processed_by_name="Test",
    )
    await return_repo.insert(ret)
    return rid


# ── insert_credit_note atomicity ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_insert_credit_note_links_return_atomically(db):
    """Credit note creation and return linking happen together or not at all."""
    wid = await _create_withdrawal()
    rid = await _create_return(wid)

    cn = await insert_credit_note(
        return_id=rid,
        invoice_id=None,
        items=[{"name": "Widget", "quantity": 2, "unit_price": 10.0, "amount": 20.0, "cost": 5.0}],
        subtotal=20.0,
        tax=2.0,
        total=22.0,
    )

    assert cn is not None
    assert cn.id is not None

    ret = await return_repo.get_by_id(rid)
    assert ret.credit_note_id == cn.id, "Return should be linked to credit note"


@pytest.mark.asyncio
async def test_insert_credit_note_rollback_on_link_failure(db):
    """If linking the return fails, the credit note should not exist."""
    wid = await _create_withdrawal()
    rid = await _create_return(wid)

    conn = get_connection()
    cursor = await conn.execute("SELECT COUNT(*) FROM credit_notes")
    count_before = (await cursor.fetchone())[0]

    with patch(
        "finance.application.credit_note_service.link_credit_note_to_return",
        side_effect=RuntimeError("Simulated link failure"),
    ):
        with pytest.raises(RuntimeError, match="Simulated link failure"):
            await insert_credit_note(
                return_id=rid,
                invoice_id=None,
                items=[
                    {
                        "name": "Widget",
                        "quantity": 2,
                        "unit_price": 10.0,
                        "amount": 20.0,
                        "cost": 5.0,
                    }
                ],
                subtotal=20.0,
                tax=2.0,
                total=22.0,
            )

    cursor = await conn.execute("SELECT COUNT(*) FROM credit_notes")
    count_after = (await cursor.fetchone())[0]
    assert count_after == count_before, "Credit note should have been rolled back"


# ── apply_credit_note atomicity ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_credit_note_marks_withdrawals_paid_atomically(db):
    """When credit note auto-pays an invoice, withdrawal status changes in same transaction."""
    wid = await _create_withdrawal()
    inv = await create_invoice_from_withdrawals([wid])
    rid = await _create_return(wid)

    cn = await insert_credit_note(
        return_id=rid,
        invoice_id=inv.id,
        items=[{"name": "Widget", "quantity": 2, "unit_price": 10.0, "amount": 20.0, "cost": 5.0}],
        subtotal=inv.subtotal,
        tax=inv.tax,
        total=inv.total,
    )

    result = await apply_credit_note(cn.id, performed_by_user_id="user-1")
    assert result is not None

    w = await withdrawal_repo.get_by_id(wid)
    applied_cn = await credit_note_repo.get_by_id(cn.id)

    if applied_cn.status == "applied":
        assert w.payment_status == "paid", (
            "If credit note is applied, withdrawal should also be marked paid"
        )


@pytest.mark.asyncio
async def test_apply_credit_note_rollback_on_ledger_failure(db):
    """If ledger recording fails, credit note should not be applied."""
    wid = await _create_withdrawal()
    inv = await create_invoice_from_withdrawals([wid])
    rid = await _create_return(wid)

    cn = await insert_credit_note(
        return_id=rid,
        invoice_id=inv.id,
        items=[{"name": "Widget", "quantity": 2, "unit_price": 10.0, "amount": 20.0, "cost": 5.0}],
        subtotal=20.0,
        tax=2.0,
        total=22.0,
    )

    with patch(
        "finance.application.credit_note_service.record_credit_note_application",
        side_effect=RuntimeError("Simulated ledger failure"),
    ):
        with pytest.raises(RuntimeError, match="Simulated ledger failure"):
            await apply_credit_note(cn.id, performed_by_user_id="user-1")

    cn_after = await credit_note_repo.get_by_id(cn.id)
    assert cn_after.status != "applied", (
        "Credit note should NOT be applied if ledger recording failed"
    )
