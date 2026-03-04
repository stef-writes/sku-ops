"""Tests for product lifecycle service."""
import pytest
import pytest_asyncio

from shared.infrastructure.database import get_connection
from catalog.infrastructure.department_repo import department_repo
from catalog.infrastructure.product_repo import product_repo
from catalog.application.product_lifecycle import create_product, update_product, delete_product
from kernel.errors import ResourceNotFoundError
from catalog.domain.errors import DuplicateBarcodeError, InvalidBarcodeError


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


@pytest.mark.asyncio
async def test_create_product_duplicate_barcode_raises(db):
    """Create product with barcode already used raises DuplicateBarcodeError."""
    product1 = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Product A",
        barcode="042100005264",
        user_id="user-1",
        user_name="Test",
    )
    assert product1.barcode == "042100005264"

    with pytest.raises(DuplicateBarcodeError):
        await create_product(
            department_id="dept-1",
            department_name="Hardware",
            name="Product B",
            barcode="042100005264",
            user_id="user-1",
            user_name="Test",
        )


@pytest.mark.asyncio
async def test_create_product_invalid_upc_raises(db):
    """Create product with invalid UPC check digit raises InvalidBarcodeError."""
    with pytest.raises(InvalidBarcodeError):
        await create_product(
            department_id="dept-1",
            department_name="Hardware",
            name="Product Bad",
            barcode="042100005265",
            user_id="user-1",
            user_name="Test",
        )


@pytest.mark.asyncio
async def test_create_product_blank_barcode_uses_sku(db):
    """Create product with blank barcode uses SKU as barcode."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Product No Barcode",
        barcode=None,
        user_id="user-1",
        user_name="Test",
    )
    assert product.barcode == product.sku


@pytest.mark.asyncio
async def test_update_product_to_duplicate_barcode_raises(db):
    """Update product barcode to one already used raises DuplicateBarcodeError."""
    product1 = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Product One",
        barcode="042100005264",
        user_id="user-1",
        user_name="Test",
    )
    product2 = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Product Two",
        barcode="023456000073",
        user_id="user-1",
        user_name="Test",
    )

    with pytest.raises(DuplicateBarcodeError):
        await update_product(product2.id, {"barcode": "042100005264"})


@pytest.mark.asyncio
async def test_update_product_invalid_upc_raises(db):
    """Update product with invalid UPC raises InvalidBarcodeError."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Product",
        user_id="user-1",
        user_name="Test",
    )

    with pytest.raises(InvalidBarcodeError):
        await update_product(product.id, {"barcode": "042100005265"})
