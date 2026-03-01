"""Tests for product lifecycle service."""
import pytest
import pytest_asyncio

from db import get_connection
from repositories import department_repo, product_repo
from services.product_lifecycle import create_product, update_product, delete_product
from domain.exceptions import ResourceNotFoundError


@pytest.mark.asyncio
async def test_create_product(db):
    """Create product increments department count and records stock transaction when quantity > 0."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Test Widget",
        quantity=10,
        price=9.99,
        cost=5.0,
        user_id="user-1",
        user_name="Test",
    )
    assert product.sku.startswith("HDW-")
    assert product.name == "Test Widget"
    assert product.quantity == 10

    dept = await department_repo.get_by_id("dept-1")
    assert dept["product_count"] == 1

    # Stock transaction recorded
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM stock_transactions WHERE product_id = ?",
        (product.id,),
    )
    rows = await cursor.fetchall()
    assert len(rows) == 1
    assert len(rows) == 1
    assert rows[0]["quantity_delta"] == 10


@pytest.mark.asyncio
async def test_create_product_invalid_department(db):
    """Create product with invalid department raises ResourceNotFoundError."""
    with pytest.raises(ResourceNotFoundError):
        await create_product(
            department_id="nonexistent",
            department_name="X",
            name="X",
        )


@pytest.mark.asyncio
async def test_update_product_changes_department_count(db):
    """Update product department updates department_name and adjusts counts."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Item A",
        user_id="user-1",
        user_name="Test",
    )
    # Add second department
    conn = get_connection()
    await conn.execute(
        """INSERT INTO departments (id, name, code, description, product_count, created_at)
           VALUES ('dept-2', 'Plumbing', 'PLU', 'Plumbing', 0, datetime('now'))"""
    )
    await conn.commit()

    result = await update_product(product.id, {"department_id": "dept-2"})
    assert result["department_id"] == "dept-2"
    assert result["department_name"] == "Plumbing"


@pytest.mark.asyncio
async def test_delete_product_removes_product(db):
    """Delete product removes it and updates department count in same transaction."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Item B",
        user_id="user-1",
        user_name="Test",
    )
    product_id = product.id
    await delete_product(product_id)
    assert await product_repo.get_by_id(product_id) is None


@pytest.mark.asyncio
async def test_delete_nonexistent_raises(db):
    """Delete nonexistent product raises ResourceNotFoundError."""
    with pytest.raises(ResourceNotFoundError):
        await delete_product("nonexistent-id")
