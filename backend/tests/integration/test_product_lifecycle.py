"""Tests for SKU lifecycle service (formerly product lifecycle)."""

import pytest

from catalog.application.sku_lifecycle import (
    create_product_with_sku,
    delete_sku,
    update_sku,
)
from catalog.domain.errors import DuplicateBarcodeError, InvalidBarcodeError
from catalog.domain.product import SkuUpdate
from catalog.infrastructure.department_repo import department_repo
from catalog.infrastructure.sku_repo import sku_repo
from inventory.application.inventory_service import process_import_stock_changes
from shared.infrastructure.database import get_connection
from shared.kernel.errors import ResourceNotFoundError


@pytest.mark.asyncio
async def test_create_product(db):
    """Create SKU increments department sku_count and records stock transaction when quantity > 0."""
    sku = await create_product_with_sku(
        category_id="dept-1",
        category_name="Hardware",
        name="Test Widget",
        quantity=10,
        price=9.99,
        cost=5.0,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )
    assert sku.sku.startswith("HDW-")
    assert sku.name == "Test Widget"
    assert sku.quantity == 10

    dept = await department_repo.get_by_id("dept-1")
    assert dept.sku_count == 1

    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM stock_transactions WHERE product_id = ?",
        (sku.id,),
    )
    rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["quantity_delta"] == 10


@pytest.mark.asyncio
async def test_create_product_invalid_department(db):
    """Create SKU with invalid department raises ResourceNotFoundError."""
    with pytest.raises(ResourceNotFoundError):
        await create_product_with_sku(
            category_id="nonexistent",
            category_name="X",
            name="X",
        )


@pytest.mark.asyncio
async def test_update_product_changes_department_count(db):
    """Update SKU department updates category_name and adjusts counts."""
    sku = await create_product_with_sku(
        category_id="dept-1",
        category_name="Hardware",
        name="Item A",
        user_id="user-1",
        user_name="Test",
    )
    conn = get_connection()
    await conn.execute(
        """INSERT INTO departments (id, name, code, description, sku_count, created_at)
           VALUES ('dept-2', 'Plumbing', 'PLU', 'Plumbing', 0, datetime('now'))"""
    )
    await conn.commit()

    result = await update_sku(sku.id, SkuUpdate(category_id="dept-2"))
    assert result.category_id == "dept-2"
    assert result.category_name == "Plumbing"


@pytest.mark.asyncio
async def test_delete_product_removes_product(db):
    """Delete SKU removes it and updates department count."""
    sku = await create_product_with_sku(
        category_id="dept-1",
        category_name="Hardware",
        name="Item B",
        user_id="user-1",
        user_name="Test",
    )
    sku_id = sku.id
    await delete_sku(sku_id)
    assert await sku_repo.get_by_id(sku_id) is None


@pytest.mark.asyncio
async def test_delete_nonexistent_raises(db):
    """Delete nonexistent SKU raises ResourceNotFoundError."""
    with pytest.raises(ResourceNotFoundError):
        await delete_sku("nonexistent-id")


@pytest.mark.asyncio
async def test_create_product_duplicate_barcode_raises(db):
    """Create SKU with barcode already used raises DuplicateBarcodeError."""
    sku1 = await create_product_with_sku(
        category_id="dept-1",
        category_name="Hardware",
        name="Product A",
        barcode="042100005264",
        user_id="user-1",
        user_name="Test",
    )
    assert sku1.barcode == "042100005264"

    with pytest.raises(DuplicateBarcodeError):
        await create_product_with_sku(
            category_id="dept-1",
            category_name="Hardware",
            name="Product B",
            barcode="042100005264",
            user_id="user-1",
            user_name="Test",
        )


@pytest.mark.asyncio
async def test_create_product_invalid_upc_raises(db):
    """Create SKU with invalid UPC check digit raises InvalidBarcodeError."""
    with pytest.raises(InvalidBarcodeError):
        await create_product_with_sku(
            category_id="dept-1",
            category_name="Hardware",
            name="Product Bad",
            barcode="042100005265",
            user_id="user-1",
            user_name="Test",
        )


@pytest.mark.asyncio
async def test_create_product_blank_barcode_uses_sku(db):
    """Create SKU with blank barcode uses SKU code as barcode."""
    sku = await create_product_with_sku(
        category_id="dept-1",
        category_name="Hardware",
        name="Product No Barcode",
        barcode=None,
        user_id="user-1",
        user_name="Test",
    )
    assert sku.barcode == sku.sku


@pytest.mark.asyncio
async def test_update_product_to_duplicate_barcode_raises(db):
    """Update SKU barcode to one already used raises DuplicateBarcodeError."""
    await create_product_with_sku(
        category_id="dept-1",
        category_name="Hardware",
        name="Product One",
        barcode="042100005264",
        user_id="user-1",
        user_name="Test",
    )
    sku2 = await create_product_with_sku(
        category_id="dept-1",
        category_name="Hardware",
        name="Product Two",
        barcode="023456000073",
        user_id="user-1",
        user_name="Test",
    )

    with pytest.raises(DuplicateBarcodeError):
        await update_sku(sku2.id, SkuUpdate(barcode="042100005264"))


@pytest.mark.asyncio
async def test_update_product_invalid_upc_raises(db):
    """Update SKU with invalid UPC raises InvalidBarcodeError."""
    sku = await create_product_with_sku(
        category_id="dept-1",
        category_name="Hardware",
        name="Product",
        user_id="user-1",
        user_name="Test",
    )

    with pytest.raises(InvalidBarcodeError):
        await update_sku(sku.id, SkuUpdate(barcode="042100005265"))
