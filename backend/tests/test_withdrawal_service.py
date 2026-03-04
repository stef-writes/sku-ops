"""Tests for withdrawal service."""
import pytest
import pytest_asyncio

from shared.infrastructure.database import get_connection
from fastapi import HTTPException
from operations.domain.withdrawal import MaterialWithdrawalCreate, WithdrawalItem
from catalog.infrastructure.product_repo import product_repo
from inventory.infrastructure.stock_repo import stock_repo
from operations.infrastructure.withdrawal_repo import withdrawal_repo
from catalog.application.product_lifecycle import create_product
from operations.application.withdrawal_service import create_withdrawal


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
    contractor = {"id": "contractor-1", "name": "Contractor User", "company": "ACME", "billing_entity": "ACME Inc"}
    current_user = {"id": "user-1", "name": "Test User"}

    result = await create_withdrawal(data, contractor, current_user)

    assert "id" in result
    assert result["payment_status"] == "unpaid"
    assert result["subtotal"] == 30.0
    assert result["contractor_id"] == "contractor-1"
    assert "invoice_id" in result

    # Stock decremented
    updated = await product_repo.get_by_id(product.id)
    assert updated["quantity"] == 7

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

    with pytest.raises(HTTPException) as exc_info:
        await create_withdrawal(data, contractor, current_user)

    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in str(exc_info.value.detail)
    assert "5" in str(exc_info.value.detail)
    assert "2" in str(exc_info.value.detail)

    # Stock unchanged
    updated = await product_repo.get_by_id(product.id)
    assert updated["quantity"] == 2


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
    withdrawal_txs = [tx for tx in history if tx.get("transaction_type") == "withdrawal"]
    assert len(withdrawal_txs) >= 1
    assert withdrawal_txs[0]["quantity_delta"] == -2
    assert withdrawal_txs[0]["reference_id"] == result["id"]
