"""Tests for inventory service and withdrawal stock changes."""
import pytest

from db import get_connection
from domain.exceptions import InsufficientStockError
from models.withdrawal import WithdrawalItem
from repositories import department_repo, product_repo
from services.inventory import process_withdrawal_stock_changes
from services.product_lifecycle import create_product


@pytest.mark.asyncio
async def test_insufficient_stock_raises(db):
    """Withdrawal with quantity exceeding available raises InsufficientStockError."""
    from db import init_db, close_db
    await init_db()
    conn = get_connection()
    await conn.execute(
        """INSERT OR REPLACE INTO departments (id, name, code, description, product_count, created_at)
           VALUES ('dept-1', 'Hardware', 'HDW', 'HW', 0, datetime('now'))"""
    )
    await conn.commit()

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
    await close_db()
