"""Tests for PO receive atomicity, UOM conversion, and WAC with pack_qty.

These tests target bugs that would silently corrupt stock, costs, or ledger
entries without producing any visible error at the API layer.
"""

from unittest.mock import AsyncMock, patch

import pytest

from catalog.application.queries import list_departments
from catalog.application.sku_lifecycle import create_product_with_sku
from catalog.infrastructure.sku_repo import sku_repo
from inventory.application.inventory_service import (
    process_import_stock_changes,
    process_receiving_stock_changes,
)
from purchasing.application.purchase_order_service import PurchasingDeps, receive_po_items
from purchasing.domain.purchase_order import (
    POItemStatus,
    POStatus,
    PurchaseOrder,
    PurchaseOrderItem,
    ReceiveItemUpdate,
)
from purchasing.infrastructure.po_repo import po_repo
from shared.kernel.types import CurrentUser


def _user():
    return CurrentUser(id="user-1", email="test@test.com", name="Test User", role="admin")


async def _create_test_product(
    name="Widget",
    quantity=100.0,
    cost=8.0,
    price=10.0,
    dept_id="dept-1",
    base_unit="each",
    purchase_uom="each",
    purchase_pack_qty=1,
):
    return await create_product_with_sku(
        category_id=dept_id,
        category_name="Hardware",
        name=name,
        quantity=quantity,
        price=price,
        cost=cost,
        user_id="user-1",
        user_name="Test",
        base_unit=base_unit,
        purchase_uom=purchase_uom,
        purchase_pack_qty=purchase_pack_qty,
        on_stock_import=process_import_stock_changes,
    )


async def _create_po_with_item(
    product_id=None,
    cost=None,
    unit_price=10.0,
    ordered_qty=50.0,
    name="Widget",
    status=POItemStatus.PENDING,
    purchase_uom="each",
    purchase_pack_qty=1,
):
    po = PurchaseOrder(
        vendor_id="v1",
        vendor_name="Acme Corp",
        status=POStatus.ORDERED,
        created_by_id="user-1",
        created_by_name="Test",
        organization_id="default",
    )
    await po_repo.insert_po(po)

    item = PurchaseOrderItem(
        po_id=po.id,
        name=name,
        ordered_qty=ordered_qty,
        delivered_qty=0,
        unit_price=unit_price,
        cost=cost or 0,
        base_unit="each",
        sell_uom="each",
        pack_qty=1,
        purchase_uom=purchase_uom,
        purchase_pack_qty=purchase_pack_qty,
        suggested_department="HDW",
        status=status,
        product_id=product_id,
        organization_id="default",
    )
    await po_repo.insert_items([item])
    return po, item


def _stub_deps(**overrides):
    from catalog.application.queries import (
        find_product_by_name_and_vendor,
        find_vendor_by_name,
        find_vendor_item_by_vendor_and_sku_code,
        get_department_by_code,
        get_sku_by_id,
        insert_vendor,
        update_sku,
    )
    from catalog.application.vendor_item_lifecycle import add_vendor_item
    from documents.application.import_parser import infer_uom, suggest_department

    async def _noop_enrich(items, *a, **kw):
        return items

    async def _noop_classify(items):
        return items

    async def _noop_create(**kw):
        return await create_product_with_sku(**kw, on_stock_import=process_receiving_stock_changes)

    defaults = {
        "list_departments": list_departments,
        "get_department_by_code": get_department_by_code,
        "find_vendor_by_name": find_vendor_by_name,
        "insert_vendor": insert_vendor,
        "get_sku_by_id": get_sku_by_id,
        "find_vendor_item_by_vendor_and_sku_code": find_vendor_item_by_vendor_and_sku_code,
        "find_sku_by_name_and_vendor": find_product_by_name_and_vendor,
        "update_sku": update_sku,
        "create_product_with_sku": _noop_create,
        "add_vendor_item": add_vendor_item,
        "process_receiving_stock_changes": process_receiving_stock_changes,
        "classify_uom_batch": _noop_classify,
        "infer_uom": infer_uom,
        "suggest_department": suggest_department,
        "enrich_for_import": _noop_enrich,
    }
    defaults.update(overrides)
    return PurchasingDeps(**defaults)


# ── Atomicity: stock + ledger + PO item stay consistent ──────────────────────


@pytest.mark.asyncio
async def test_po_receive_rolls_back_stock_on_ledger_failure(db):
    """If ledger recording raises, stock must NOT have increased."""
    product = await _create_test_product(quantity=100.0)
    po, item = await _create_po_with_item(product_id=product.id, cost=7.0, ordered_qty=50)

    with patch(
        "purchasing.application.po_receiving_service._record_po_receipt_ledger",
        side_effect=RuntimeError("Simulated ledger failure"),
    ):
        with pytest.raises(RuntimeError, match="Simulated ledger failure"):
            await receive_po_items(
                po_id=po.id,
                item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=50)],
                deps=_stub_deps(),
                current_user=_user(),
            )

    updated = await sku_repo.get_by_id(product.id)
    assert updated.quantity == pytest.approx(100.0), "Stock should NOT have increased"

    po_items = await po_repo.get_po_items(po.id)
    assert po_items[0].status == POItemStatus.PENDING.value, "PO item should still be PENDING"


@pytest.mark.asyncio
async def test_po_receive_vendor_item_failure_reports_error_item_stays_pending(db):
    """If add_vendor_item raises, the item error is reported and the PO item stays pending.

    The original_sku must be set on the PO item (not via ReceiveItemUpdate which
    doesn't carry that field) so that the vendor_item branch is reached.
    """
    po = PurchaseOrder(
        vendor_id="v1",
        vendor_name="Acme Corp",
        status=POStatus.ORDERED,
        created_by_id="user-1",
        created_by_name="Test",
        organization_id="default",
    )
    await po_repo.insert_po(po)
    item = PurchaseOrderItem(
        po_id=po.id,
        name="Atomicity Widget",
        original_sku="VENDOR-SKU-123",
        ordered_qty=10,
        delivered_qty=0,
        unit_price=10.0,
        cost=5.0,
        base_unit="each",
        sell_uom="each",
        pack_qty=1,
        suggested_department="HDW",
        status=POItemStatus.PENDING,
        product_id=None,
        organization_id="default",
    )
    await po_repo.insert_items([item])

    failing_add = AsyncMock(side_effect=RuntimeError("Simulated vendor item failure"))
    deps = _stub_deps(add_vendor_item=failing_add)

    result = await receive_po_items(
        po_id=po.id,
        item_updates=[
            ReceiveItemUpdate(
                id=item.id,
                delivered_qty=10,
                suggested_department="HDW",
            )
        ],
        deps=deps,
        current_user=_user(),
    )

    assert result.errors == 1, "Error should be reported for the failed item"

    po_items = await po_repo.get_po_items(po.id)
    assert po_items[0].status != POItemStatus.ARRIVED.value, (
        "PO item should NOT be ARRIVED when add_vendor_item failed"
    )


# ── UOM conversion: case/each with purchase_pack_qty ─────────────────────────


@pytest.mark.asyncio
async def test_po_receive_case_uom_converts_to_base_units(db):
    """Receiving 5 cases with purchase_pack_qty=12 should add 60 each to stock."""
    product = await _create_test_product(
        quantity=100.0,
        cost=1.0,
        purchase_uom="case",
        purchase_pack_qty=12,
    )
    po, item = await _create_po_with_item(
        product_id=product.id,
        cost=24.0,
        ordered_qty=5,
        purchase_uom="case",
        purchase_pack_qty=12,
    )

    result = await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=5)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    assert result.errors == 0
    updated = await sku_repo.get_by_id(product.id)
    assert updated.quantity == pytest.approx(160.0), f"Expected 100 + 60, got {updated.quantity}"


@pytest.mark.asyncio
async def test_po_receive_wac_correct_with_uom_conversion(db):
    """WAC must use per-base-unit cost, not per-case cost.

    Existing: qty=100, cost=$1/each
    Receive: 5 cases @ $24/case (12 per case) = 60 each @ $2/each
    Expected WAC: (100*1 + 60*2) / 160 = 220/160 = 1.375
    """
    product = await _create_test_product(
        quantity=100.0,
        cost=1.0,
        purchase_uom="case",
        purchase_pack_qty=12,
    )
    po, item = await _create_po_with_item(
        product_id=product.id,
        cost=24.0,
        ordered_qty=5,
        purchase_uom="case",
        purchase_pack_qty=12,
    )

    await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=5)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    updated = await sku_repo.get_by_id(product.id)
    expected_wac = round((100 * 1 + 60 * 2) / 160, 4)
    assert updated.cost == pytest.approx(expected_wac, abs=0.01), (
        f"Expected WAC {expected_wac}, got {updated.cost}"
    )


@pytest.mark.asyncio
async def test_po_receive_same_uom_no_multiplication(db):
    """When purchase_uom == base_unit, no pack_qty multiplication should happen."""
    product = await _create_test_product(quantity=50.0, cost=5.0)
    po, item = await _create_po_with_item(product_id=product.id, cost=6.0, ordered_qty=20)

    await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=20)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    updated = await sku_repo.get_by_id(product.id)
    assert updated.quantity == pytest.approx(70.0), "Stock should be 50 + 20"
