"""Tests for invoice link guard — prevents double-linking withdrawals.

Verifies that link_to_invoice uses a conditional UPDATE (AND invoice_id IS NULL)
so that a withdrawal already linked to one invoice cannot be silently re-linked
to another, which would orphan the first invoice's withdrawal references.
"""

from uuid import uuid4

import pytest

from finance.application.invoice_service import create_invoice_from_withdrawals
from operations.domain.withdrawal import MaterialWithdrawal, WithdrawalItem
from operations.infrastructure.withdrawal_repo import withdrawal_repo


async def _create_withdrawal(billing_entity="ACME Inc") -> str:
    wid = str(uuid4())
    items = [
        WithdrawalItem(
            product_id="p1",
            sku="SKU-001",
            name="Widget",
            quantity=3,
            unit_price=10.0,
            cost=5.0,
        )
    ]
    w = MaterialWithdrawal(
        id=wid,
        items=items,
        job_id="JOB-TEST",
        service_address="123 Test St",
        subtotal=30.0,
        tax=3.0,
        total=33.0,
        cost_total=15.0,
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


@pytest.mark.asyncio
async def test_link_to_invoice_rejects_already_linked(db):
    """A withdrawal already linked to invoice A cannot be linked to invoice B."""
    wid = await _create_withdrawal()

    inv_a = await create_invoice_from_withdrawals([wid])
    assert inv_a is not None

    w = await withdrawal_repo.get_by_id(wid)
    assert w.invoice_id == inv_a.id, "Withdrawal should be linked to invoice A"

    linked = await withdrawal_repo.link_to_invoice(wid, str(uuid4()))
    assert linked is False, "Second link_to_invoice should return False"

    w_after = await withdrawal_repo.get_by_id(wid)
    assert w_after.invoice_id == inv_a.id, "Withdrawal should still be linked to invoice A"


@pytest.mark.asyncio
async def test_create_second_invoice_for_same_withdrawal_raises(db):
    """Creating a second invoice from an already-invoiced withdrawal raises ValueError."""
    wid = await _create_withdrawal()

    await create_invoice_from_withdrawals([wid])

    with pytest.raises(ValueError, match=r"not unpaid|already"):
        await create_invoice_from_withdrawals([wid])


@pytest.mark.asyncio
async def test_link_to_invoice_succeeds_when_unlinked(db):
    """link_to_invoice returns True for an unlinked withdrawal."""
    wid = await _create_withdrawal()

    linked = await withdrawal_repo.link_to_invoice(wid, str(uuid4()))
    assert linked is True, "First link_to_invoice should succeed"
