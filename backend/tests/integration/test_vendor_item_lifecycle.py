"""Tests for vendor item lifecycle: add, update, remove, set preferred."""

import pytest

from catalog.application.sku_lifecycle import create_product_with_sku
from catalog.application.vendor_item_lifecycle import (
    add_vendor_item,
    get_vendor_items_for_sku,
    remove_vendor_item,
    set_preferred_vendor,
    update_vendor_item,
)
from shared.infrastructure.database import get_connection
from shared.kernel.errors import ResourceNotFoundError


async def _seed_vendor(vendor_id="vendor-1", name="Acme Supply"):
    conn = get_connection()
    await conn.execute(
        """INSERT INTO vendors (id, name, organization_id, created_at)
           VALUES ($1, $2, 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name""",
        (vendor_id, name),
    )
    await conn.commit()


async def _make_sku(name="Test SKU"):
    return await create_product_with_sku(
        category_id="dept-1",
        category_name="Hardware",
        name=name,
        user_id="user-1",
        user_name="Test",
    )


@pytest.mark.asyncio
async def test_add_vendor_item(db):
    """Adding a vendor item links vendor to SKU with correct fields."""
    await _seed_vendor()
    sku = await _make_sku()

    vi = await add_vendor_item(
        sku_id=sku.id,
        vendor_id="vendor-1",
        vendor_sku="ACME-001",
        purchase_uom="case",
        purchase_pack_qty=12,
        cost=45.99,
        lead_time_days=5,
    )
    assert vi.vendor_id == "vendor-1"
    assert vi.sku_id == sku.id
    assert vi.vendor_sku == "ACME-001"
    assert vi.purchase_uom == "case"
    assert vi.purchase_pack_qty == 12
    assert vi.cost == pytest.approx(45.99)
    assert vi.lead_time_days == 5
    assert vi.vendor_name == "Acme Supply"


@pytest.mark.asyncio
async def test_list_vendor_items_for_sku(db):
    """Listing vendor items returns all linked vendors for a SKU."""
    await _seed_vendor("vendor-1", "Acme")
    await _seed_vendor("vendor-2", "BuildCo")
    sku = await _make_sku()

    await add_vendor_item(sku_id=sku.id, vendor_id="vendor-1", cost=10.0)
    await add_vendor_item(sku_id=sku.id, vendor_id="vendor-2", cost=12.0)

    items = await get_vendor_items_for_sku(sku.id)
    assert len(items) == 2
    vendor_ids = {vi.vendor_id for vi in items}
    assert vendor_ids == {"vendor-1", "vendor-2"}


@pytest.mark.asyncio
async def test_set_preferred_vendor(db):
    """Setting preferred clears other preferred flags for the same SKU."""
    await _seed_vendor("vendor-1", "Acme")
    await _seed_vendor("vendor-2", "BuildCo")
    sku = await _make_sku()

    vi1 = await add_vendor_item(sku_id=sku.id, vendor_id="vendor-1", is_preferred=True)
    vi2 = await add_vendor_item(sku_id=sku.id, vendor_id="vendor-2")

    items = await get_vendor_items_for_sku(sku.id)
    preferred = [vi for vi in items if vi.is_preferred]
    assert len(preferred) == 1
    assert preferred[0].id == vi1.id

    await set_preferred_vendor(sku.id, vi2.id)

    items = await get_vendor_items_for_sku(sku.id)
    preferred = [vi for vi in items if vi.is_preferred]
    assert len(preferred) == 1
    assert preferred[0].id == vi2.id


@pytest.mark.asyncio
async def test_remove_vendor_item(db):
    """Removing a vendor item soft-deletes it."""
    await _seed_vendor()
    sku = await _make_sku()

    vi = await add_vendor_item(sku_id=sku.id, vendor_id="vendor-1")
    await remove_vendor_item(vi.id)

    items = await get_vendor_items_for_sku(sku.id)
    assert len(items) == 0


@pytest.mark.asyncio
async def test_remove_nonexistent_raises(db):
    """Removing a nonexistent vendor item raises ResourceNotFoundError."""
    with pytest.raises(ResourceNotFoundError):
        await remove_vendor_item("nonexistent-id")


@pytest.mark.asyncio
async def test_update_vendor_item(db):
    """Updating a vendor item changes the specified fields."""
    await _seed_vendor()
    sku = await _make_sku()

    vi = await add_vendor_item(sku_id=sku.id, vendor_id="vendor-1", cost=10.0)

    updated = await update_vendor_item(vi.id, {"cost": 15.0, "lead_time_days": 7})
    assert updated.cost == pytest.approx(15.0)
    assert updated.lead_time_days == 7


@pytest.mark.asyncio
async def test_set_preferred_wrong_sku_raises(db):
    """Setting preferred with wrong SKU raises ResourceNotFoundError."""
    await _seed_vendor()
    sku1 = await _make_sku("SKU A")
    sku2 = await _make_sku("SKU B")

    vi = await add_vendor_item(sku_id=sku1.id, vendor_id="vendor-1")

    with pytest.raises(ResourceNotFoundError):
        await set_preferred_vendor(sku2.id, vi.id)
