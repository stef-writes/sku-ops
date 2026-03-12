"""Tests for withdrawal service."""

import pytest

from catalog.application.product_lifecycle import create_product
from catalog.application.queries import list_products
from catalog.infrastructure.product_repo import product_repo
from finance.application.invoice_service import create_invoice_from_withdrawals
from inventory.application.inventory_service import (
    process_import_stock_changes,
    process_withdrawal_stock_changes,
)
from inventory.domain.errors import InsufficientStockError
from inventory.infrastructure.stock_repo import stock_repo
from operations.application.withdrawal_service import create_withdrawal as _create_withdrawal
from operations.domain.withdrawal import MaterialWithdrawalCreate, WithdrawalItem
from operations.infrastructure.withdrawal_repo import withdrawal_repo
from shared.kernel.types import CurrentUser


def _test_user(user_id="user-1", name="Test User"):
    return CurrentUser(id=user_id, email="test@test.com", name=name, role="admin")


async def create_withdrawal(data, contractor, current_user):
    if isinstance(current_user, dict):
        current_user = CurrentUser(**{"email": "test@test.com", "role": "admin", **current_user})
    return await _create_withdrawal(
        data,
        contractor,
        current_user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
        create_invoice=create_invoice_from_withdrawals,
    )


@pytest.mark.asyncio
async def test_create_withdrawal_success(db):
    """Create withdrawal with valid items; assert withdrawal and invoice created, stock decremented."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Widget",
        quantity=10,
        price=10.0,
        cost=5.0,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )

    items = [
        WithdrawalItem(
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            quantity=3,
            price=10.0,
            cost=5.0,
            subtotal=30.0,
        )
    ]
    data = MaterialWithdrawalCreate(
        items=items,
        job_id="JOB-001",
        service_address="123 Main St",
        notes="Test",
    )
    contractor = {
        "id": "contractor-1",
        "name": "Contractor User",
        "company": "ACME",
        "billing_entity": "ACME Inc",
    }
    current_user = {"id": "user-1", "name": "Test User"}

    result = await create_withdrawal(data, contractor, current_user)

    assert "id" in result
    assert result["payment_status"] == "unpaid"
    assert result["subtotal"] == 30.0
    assert result["contractor_id"] == "contractor-1"
    assert "invoice_id" in result

    # Stock decremented
    updated = await product_repo.get_by_id(product.id)
    assert updated.quantity == 7

    # Withdrawal persisted
    withdrawal = await withdrawal_repo.get_by_id(result["id"])
    assert withdrawal is not None


@pytest.mark.asyncio
async def test_create_withdrawal_insufficient_stock_raises(db):
    """Items exceed available quantity; assert HTTPException 400."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Low Stock",
        quantity=2,
        price=10.0,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )

    items = [
        WithdrawalItem(
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            quantity=5,
            price=10.0,
            cost=5.0,
            subtotal=50.0,
        )
    ]
    data = MaterialWithdrawalCreate(
        items=items,
        job_id="JOB-002",
        service_address="456 Oak Ave",
    )
    contractor = {"id": "contractor-1", "name": "Contractor User"}
    current_user = {"id": "user-1", "name": "Test"}

    with pytest.raises(InsufficientStockError) as exc_info:
        await create_withdrawal(data, contractor, current_user)

    assert exc_info.value.requested == 5
    assert exc_info.value.available == 2

    # Stock unchanged
    updated = await product_repo.get_by_id(product.id)
    assert updated.quantity == 2


@pytest.mark.asyncio
async def test_create_withdrawal_stock_transaction_recorded(db):
    """Verify stock_transactions has WITHDRAWAL record."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Transaction Test",
        quantity=5,
        price=8.0,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )

    items = [
        WithdrawalItem(
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            quantity=2,
            price=8.0,
            cost=4.0,
            subtotal=16.0,
        )
    ]
    data = MaterialWithdrawalCreate(
        items=items,
        job_id="JOB-003",
        service_address="789 Elm St",
    )
    contractor = {"id": "contractor-1", "name": "Contractor"}
    current_user = {"id": "user-1", "name": "Test"}

    result = await create_withdrawal(data, contractor, current_user)

    history = await stock_repo.list_by_product(product.id, limit=10)
    withdrawal_txs = [tx for tx in history if tx.transaction_type == "withdrawal"]
    assert len(withdrawal_txs) >= 1
    assert withdrawal_txs[0].quantity_delta == -2
    assert withdrawal_txs[0].reference_id == result["id"]


@pytest.mark.asyncio
async def test_create_withdrawal_multi_item(db):
    """Withdrawal with two different products decrements both correctly."""
    product_a = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Multi-A",
        quantity=20,
        price=10.0,
        cost=5.0,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )
    product_b = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Multi-B",
        quantity=15,
        price=8.0,
        cost=3.0,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )

    items = [
        WithdrawalItem(
            product_id=product_a.id,
            sku=product_a.sku,
            name=product_a.name,
            quantity=4,
            price=10.0,
            cost=5.0,
            subtotal=40.0,
        ),
        WithdrawalItem(
            product_id=product_b.id,
            sku=product_b.sku,
            name=product_b.name,
            quantity=7,
            price=8.0,
            cost=3.0,
            subtotal=56.0,
        ),
    ]
    data = MaterialWithdrawalCreate(
        items=items, job_id="JOB-MULTI", service_address="Multi St"
    )
    contractor = {
        "id": "contractor-1",
        "name": "Contractor",
        "billing_entity": "ACME Inc",
    }
    current_user = {"id": "user-1", "name": "Test"}

    result = await create_withdrawal(data, contractor, current_user)

    assert result["subtotal"] == pytest.approx(96.0)
    assert result["tax"] > 0

    updated_a = await product_repo.get_by_id(product_a.id)
    updated_b = await product_repo.get_by_id(product_b.id)
    assert updated_a.quantity == 16
    assert updated_b.quantity == 8


@pytest.mark.asyncio
async def test_create_withdrawal_tax_computation(db):
    """Verify tax is computed correctly as subtotal * tax_rate."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Tax Test",
        quantity=50,
        price=25.0,
        cost=10.0,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )

    items = [
        WithdrawalItem(
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            quantity=4,
            price=25.0,
            cost=10.0,
            subtotal=100.0,
        )
    ]
    data = MaterialWithdrawalCreate(
        items=items, job_id="JOB-TAX", service_address="Tax St"
    )
    contractor = {"id": "contractor-1", "name": "Contractor"}
    current_user = {"id": "user-1", "name": "Test"}

    result = await create_withdrawal(data, contractor, current_user)

    assert result["subtotal"] == pytest.approx(100.0)
    assert result["tax"] == pytest.approx(10.0)
    assert result["total"] == pytest.approx(110.0)


@pytest.mark.asyncio
async def test_create_withdrawal_auto_invoice_failure_still_creates_withdrawal(db):
    """If auto-invoice fails, the withdrawal must still be created and returned."""

    async def failing_create_invoice(**kwargs):
        raise ValueError("Invoice creation failed")

    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Invoice Fail Test",
        quantity=10,
        price=10.0,
        cost=5.0,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )

    items = [
        WithdrawalItem(
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            quantity=2,
            price=10.0,
            cost=5.0,
            subtotal=20.0,
        )
    ]
    data = MaterialWithdrawalCreate(
        items=items, job_id="JOB-FAIL", service_address="Fail St"
    )
    contractor = {"id": "contractor-1", "name": "Contractor"}
    user = _test_user()

    result = await _create_withdrawal(
        data,
        contractor,
        user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
        create_invoice=failing_create_invoice,
    )

    assert "id" in result
    assert "invoice_id" not in result

    updated = await product_repo.get_by_id(product.id)
    assert updated.quantity == 8
