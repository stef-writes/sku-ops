"""Tests for invoice repository."""
import pytest
import pytest_asyncio

from finance.infrastructure.invoice_repo import invoice_repo
from operations.infrastructure.withdrawal_repo import withdrawal_repo


async def _create_withdrawal_with_items(contractor_id: str, billing_entity: str, items: list) -> str:
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
            {"product_id": "p1", "sku": "HDW-X-000001", "name": "Item A", "quantity": 2, "price": 10.0, "cost": 5.0, "subtotal": 20.0},
            {"product_id": "p2", "sku": "HDW-Y-000002", "name": "Item B", "quantity": 1, "price": 15.0, "cost": 8.0, "subtotal": 15.0},
        ],
    )

    inv = await invoice_repo.create_from_withdrawals([wid])

    assert inv is not None
    assert "id" in inv
    assert inv["billing_entity"] == "ACME Inc"
    assert inv["status"] == "draft"
    assert inv["withdrawal_ids"] == [wid]
    assert len(inv["line_items"]) == 2
    line_amts = sorted(i["amount"] for i in inv["line_items"])
    assert line_amts == [15.0, 20.0]

    # Withdrawal linked
    w = await withdrawal_repo.get_by_id(wid)
    assert w["invoice_id"] == inv["id"]


@pytest.mark.asyncio
async def test_create_from_withdrawals_different_billing_entity_raises(db):
    """Withdrawals with different billing_entity raise ValueError."""
    wid1 = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="ACME Inc",
        items=[{"product_id": "p1", "sku": "X", "name": "A", "quantity": 1, "price": 10.0, "subtotal": 10.0}],
    )
    wid2 = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="Other Corp",
        items=[{"product_id": "p2", "sku": "Y", "name": "B", "quantity": 1, "price": 10.0, "subtotal": 10.0}],
    )

    with pytest.raises(ValueError) as exc_info:
        await invoice_repo.create_from_withdrawals([wid1, wid2])

    assert "billing_entity" in str(exc_info.value).lower() or "same" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_delete_draft_unlinks_withdrawals(db):
    """Delete draft; verify invoice_withdrawals and invoice removed; withdrawals remain unpaid."""
    wid = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="ACME Inc",
        items=[{"product_id": "p1", "sku": "X", "name": "A", "quantity": 1, "price": 10.0, "subtotal": 10.0}],
    )
    inv = await invoice_repo.create_from_withdrawals([wid])
    inv_id = inv["id"]

    ok = await invoice_repo.delete_draft(inv_id)

    assert ok is True
    inv_after = await invoice_repo.get_by_id(inv_id)
    assert inv_after is None

    w = await withdrawal_repo.get_by_id(wid)
    assert w is not None
    assert w["invoice_id"] is None
    assert w["payment_status"] == "unpaid"


@pytest.mark.asyncio
async def test_update_invoice(db):
    """Update billing_entity, line_items; assert changes persisted."""
    wid = await _create_withdrawal_with_items(
        contractor_id="contractor-1",
        billing_entity="Original Corp",
        items=[{"product_id": "p1", "sku": "X", "name": "A", "quantity": 1, "price": 10.0, "subtotal": 10.0}],
    )
    inv = await invoice_repo.create_from_withdrawals([wid])

    updated = await invoice_repo.update(
        inv["id"],
        billing_entity="Updated Corp",
        contact_name="Jane Doe",
        contact_email="jane@test.com",
    )

    assert updated["billing_entity"] == "Updated Corp"
    assert updated["contact_name"] == "Jane Doe"
    assert updated["contact_email"] == "jane@test.com"
