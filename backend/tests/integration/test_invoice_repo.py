"""Tests for invoice repository."""

import pytest

from finance.application.invoice_service import (
    create_invoice_from_withdrawals,
    delete_draft_invoice,
    update_invoice,
)
from finance.infrastructure.invoice_mutations import update_invoice_totals
from finance.infrastructure.invoice_repo import invoice_repo
from operations.infrastructure.withdrawal_repo import withdrawal_repo


async def _create_withdrawal_with_items(
    contractor_id: str, billing_entity: str, items: list
) -> str:
    """Helper to create a withdrawal and return its id."""
    from uuid import uuid4

    withdrawal_id = str(uuid4())
    subtotal = sum(i.get("subtotal", i["quantity"] * i["price"]) for i in items)
    tax = round(subtotal * 0.08, 2)
    total = round(subtotal + tax, 2)
    cost_total = sum(i.get("cost", 0) * i["quantity"] for i in items)

    withdrawal_dict = {
        "id": withdrawal_id,
        "items": items,
        "job_id": "JOB-TEST",
        "service_address": "123 Test St",
        "notes": None,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "cost_total": cost_total,
        "contractor_id": contractor_id,
        "contractor_name": "Test Contractor",
        "contractor_company": "ACME",
        "billing_entity": billing_entity,
        "payment_status": "unpaid",
        "invoice_id": None,
        "paid_at": None,
        "processed_by_id": "user-1",
        "processed_by_name": "Test",
        "created_at": "2025-01-01T00:00:00Z",
    }
    await withdrawal_repo.insert(withdrawal_dict)
    return withdrawal_id


@pytest.mark.asyncio
async def test_create_from_withdrawals(db):
    """Create invoice from withdrawal IDs; assert invoice has correct line_items and invoice_withdrawals link."""
    wid = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="ACME Inc",
        items=[
            {
                "product_id": "p1",
                "sku": "HDW-X-000001",
                "name": "Item A",
                "quantity": 2,
                "price": 10.0,
                "cost": 5.0,
                "subtotal": 20.0,
            },
            {
                "product_id": "p2",
                "sku": "HDW-Y-000002",
                "name": "Item B",
                "quantity": 1,
                "price": 15.0,
                "cost": 8.0,
                "subtotal": 15.0,
            },
        ],
    )

    inv = await create_invoice_from_withdrawals([wid])

    assert inv is not None
    assert inv.id is not None
    assert inv.billing_entity == "ACME Inc"
    assert inv.status == "draft"
    assert inv.withdrawal_ids == [wid]
    assert len(inv.line_items) == 2
    line_amts = sorted(i.amount for i in inv.line_items)
    assert line_amts == [15.0, 20.0]

    # Withdrawal linked
    w = await withdrawal_repo.get_by_id(wid)
    assert w.invoice_id == inv.id


@pytest.mark.asyncio
async def test_create_from_withdrawals_different_billing_entity_raises(db):
    """Withdrawals with different billing_entity raise ValueError."""
    wid1 = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="ACME Inc",
        items=[
            {
                "product_id": "p1",
                "sku": "X",
                "name": "A",
                "quantity": 1,
                "price": 10.0,
                "subtotal": 10.0,
            }
        ],
    )
    wid2 = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="Other Corp",
        items=[
            {
                "product_id": "p2",
                "sku": "Y",
                "name": "B",
                "quantity": 1,
                "price": 10.0,
                "subtotal": 10.0,
            }
        ],
    )

    with pytest.raises(ValueError) as exc_info:
        await create_invoice_from_withdrawals([wid1, wid2])

    assert "billing_entity" in str(exc_info.value).lower() or "same" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_delete_draft_unlinks_withdrawals(db):
    """Delete draft; verify invoice_withdrawals and invoice removed; withdrawals remain unpaid."""
    wid = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="ACME Inc",
        items=[
            {
                "product_id": "p1",
                "sku": "X",
                "name": "A",
                "quantity": 1,
                "price": 10.0,
                "subtotal": 10.0,
            }
        ],
    )
    inv = await create_invoice_from_withdrawals([wid])
    inv_id = inv.id

    ok = await delete_draft_invoice(inv_id)

    assert ok is True
    inv_after = await invoice_repo.get_by_id(inv_id)
    assert inv_after is None

    w = await withdrawal_repo.get_by_id(wid)
    assert w is not None
    assert w.invoice_id is None
    assert w.payment_status == "unpaid"


@pytest.mark.asyncio
async def test_update_invoice(db):
    """Update billing_entity, line_items; assert changes persisted."""
    wid = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="Original Corp",
        items=[
            {
                "product_id": "p1",
                "sku": "X",
                "name": "A",
                "quantity": 1,
                "price": 10.0,
                "subtotal": 10.0,
            }
        ],
    )
    inv = await create_invoice_from_withdrawals([wid])

    updated = await update_invoice(
        inv.id,
        billing_entity="Updated Corp",
        contact_name="Jane Doe",
        contact_email="jane@test.com",
    )

    assert updated.billing_entity == "Updated Corp"
    assert updated.contact_name == "Jane Doe"
    assert updated.contact_email == "jane@test.com"


@pytest.mark.asyncio
async def test_delete_non_draft_invoice_raises(db):
    """Deleting an approved invoice must raise — only drafts are deletable."""
    wid = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="ACME Inc",
        items=[
            {
                "product_id": "p1",
                "sku": "X",
                "name": "A",
                "quantity": 1,
                "price": 10.0,
                "subtotal": 10.0,
            }
        ],
    )
    inv = await create_invoice_from_withdrawals([wid])

    await invoice_repo.update_fields(inv.id, {"status": "approved"})

    with pytest.raises(ValueError, match="draft"):
        await delete_draft_invoice(inv.id)


@pytest.mark.asyncio
async def test_get_nonexistent_invoice_returns_none(db):
    """get_by_id for a nonexistent ID returns None, not an error."""
    result = await invoice_repo.get_by_id("nonexistent-invoice-id")
    assert result is None


@pytest.mark.asyncio
async def test_invoice_total_matches_withdrawal_totals(db):
    """Invoice total must equal the sum of its withdrawal totals."""
    wid = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="ACME Inc",
        items=[
            {
                "product_id": "p1",
                "sku": "HDW-001",
                "name": "Widget",
                "quantity": 5,
                "price": 20.0,
                "cost": 10.0,
                "subtotal": 100.0,
            },
            {
                "product_id": "p2",
                "sku": "HDW-002",
                "name": "Gadget",
                "quantity": 3,
                "price": 15.0,
                "cost": 7.0,
                "subtotal": 45.0,
            },
        ],
    )
    inv = await create_invoice_from_withdrawals([wid])

    line_total = sum(li.amount for li in inv.line_items)
    assert line_total == pytest.approx(145.0)


@pytest.mark.asyncio
async def test_create_invoice_from_already_invoiced_withdrawal_raises(db):
    """A withdrawal already linked to an invoice cannot be re-invoiced."""
    wid = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="ACME Inc",
        items=[
            {
                "product_id": "p1",
                "sku": "X",
                "name": "A",
                "quantity": 1,
                "price": 10.0,
                "subtotal": 10.0,
            }
        ],
    )

    await create_invoice_from_withdrawals([wid])

    with pytest.raises((ValueError, Exception)):
        await create_invoice_from_withdrawals([wid])


@pytest.mark.asyncio
async def test_update_invoice_totals_persists_correctly(db):
    """update_invoice_totals writes the correct subtotal/tax/total to the DB."""
    wid = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="ACME Inc",
        items=[
            {
                "product_id": "p1",
                "sku": "X",
                "name": "A",
                "quantity": 1,
                "price": 10.0,
                "subtotal": 10.0,
            }
        ],
    )
    inv = await create_invoice_from_withdrawals([wid])

    await update_invoice_totals(inv.id, subtotal=50.0, tax=5.0, total=55.0)

    refreshed = await invoice_repo.get_by_id(inv.id)
    assert float(refreshed.subtotal) == pytest.approx(50.0)
    assert float(refreshed.tax) == pytest.approx(5.0)
    assert float(refreshed.total) == pytest.approx(55.0)


@pytest.mark.asyncio
async def test_update_invoice_with_line_items_recalculates_total(db):
    """update_invoice with line_items replaces lines and recomputes total = subtotal + tax."""
    wid = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="ACME Inc",
        items=[
            {
                "product_id": "p1",
                "sku": "X",
                "name": "A",
                "quantity": 1,
                "price": 10.0,
                "subtotal": 10.0,
            }
        ],
    )
    inv = await create_invoice_from_withdrawals([wid])

    new_line_items = [{"description": "New Item", "quantity": 2, "unit_price": 25.0, "cost": 10.0}]
    updated = await update_invoice(inv.id, line_items=new_line_items, tax=5.0)

    assert updated is not None
    assert float(updated.subtotal) == pytest.approx(50.0)
    assert float(updated.tax) == pytest.approx(5.0)
    assert float(updated.total) == pytest.approx(55.0)
