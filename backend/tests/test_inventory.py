"""Tests for inventory service and withdrawal stock changes."""
import pytest

from inventory.domain.errors import InsufficientStockError
from operations.domain.withdrawal import WithdrawalItem
from inventory.application.inventory_service import process_withdrawal_stock_changes
from catalog.application.product_lifecycle import create_product


@pytest.mark.asyncio
async def test_insufficient_stock_raises(db):
    """Withdrawal with quantity exceeding available raises InsufficientStockError."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Low Stock Item",
        quantity=2,
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

    with pytest.raises(InsufficientStockError) as exc_info:
        await process_withdrawal_stock_changes(
            items=items,
            withdrawal_id="w-1",
            user_id="user-1",
            user_name="Test",
        )

    assert exc_info.value.requested == 5
    assert exc_info.value.available == 2
