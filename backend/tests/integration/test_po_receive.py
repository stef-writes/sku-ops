"""Tests for PO receive flow: stock, WAC, ledger, status, cost fallback."""

import pytest

from catalog.application.product_lifecycle import create_product
from catalog.application.queries import list_departments
from catalog.infrastructure.product_repo import product_repo
from inventory.application.inventory_service import (
    process_import_stock_changes,
    process_receiving_stock_changes,
)
from inventory.infrastructure.stock_repo import stock_repo
from purchasing.application.purchase_order_service import (
    PurchasingDeps,
    _resolve_po_item_cost,
    receive_po_items,
)
from purchasing.domain.purchase_order import (
    POItemStatus,
    POStatus,
    PurchaseOrder,
    PurchaseOrderItem,
    ReceiveItemUpdate,
)
from purchasing.infrastructure.po_repo import po_repo
from shared.infrastructure.database import get_connection
from shared.kernel.types import CurrentUser


def _user():
    return CurrentUser(id="user-1", email="test@test.com", name="Test User", role="admin")


async def _create_test_product(
    name="Widget", quantity=100.0, cost=8.0, price=10.0, dept_id="dept-1"
):
    return await create_product(
        department_id=dept_id,
        department_name="Hardware",
        name=name,
        quantity=quantity,
        price=price,
        cost=cost,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )


async def _create_po_with_item(
    product_id=None,
    cost=None,
    unit_price=10.0,
    ordered_qty=50.0,
    name="Widget",
    status=POItemStatus.PENDING,
):
    po = PurchaseOrder(
        vendor_id="v1",
        vendor_name="Acme Corp",
        status=POStatus.ORDERED,
        created_by_id="user-1",
        created_by_name="Test",
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
        suggested_department="HDW",
        status=status,
        product_id=product_id,
    )
    await po_repo.insert_items([item])
    return po, item


def _stub_deps():
    """Build PurchasingDeps that wire through to real repos for integration tests."""
    from catalog.application.queries import (
        find_product_by_name_and_vendor,
        find_product_by_original_sku_and_vendor,
        find_vendor_by_name,
        get_department_by_code,
        get_product_by_id,
        insert_vendor,
        list_products_by_vendor,
        update_product,
    )
    from documents.application.import_parser import infer_uom, suggest_department

    async def _noop_enrich(items, *a, **kw):
        return items

    async def _noop_classify(items):
        return items

    async def _noop_create(**kw):
        return await create_product(**kw, on_stock_import=process_receiving_stock_changes)

    return PurchasingDeps(
        list_departments=list_departments,
        get_department_by_code=get_department_by_code,
        find_vendor_by_name=find_vendor_by_name,
        insert_vendor=insert_vendor,
        list_products_by_vendor=list_products_by_vendor,
        get_product_by_id=get_product_by_id,
        find_product_by_sku_and_vendor=find_product_by_original_sku_and_vendor,
        find_product_by_name_and_vendor=find_product_by_name_and_vendor,
        update_product=update_product,
        create_product=_noop_create,
        process_receiving_stock_changes=process_receiving_stock_changes,
        classify_uom_batch=_noop_classify,
        infer_uom=infer_uom,
        suggest_department=suggest_department,
        enrich_for_import=_noop_enrich,
    )


# ── Unit: cost resolution helper ─────────────────────────────────────────────


class TestResolvePOItemCost:
    def test_cost_present(self):
        assert _resolve_po_item_cost({"cost": 5.0}) == 5.0

    def test_fallback_to_unit_price(self):
        assert _resolve_po_item_cost({"unit_price": 10.0}) == pytest.approx(7.0)

    def test_fallback_to_price(self):
        assert _resolve_po_item_cost({"price": 20.0}) == pytest.approx(14.0)

    def test_cost_zero_falls_through(self):
        assert _resolve_po_item_cost({"cost": 0, "unit_price": 10.0}) == pytest.approx(7.0)

    def test_no_cost_no_price(self):
        assert _resolve_po_item_cost({}) == 0

    def test_cost_preferred_over_price(self):
        assert _resolve_po_item_cost({"cost": 6.0, "unit_price": 10.0}) == 6.0


# ── Integration: receive updates stock ───────────────────────────────────────


@pytest.mark.asyncio
async def test_receive_updates_stock(db):
    """Receiving items increments product quantity."""
    product = await _create_test_product(quantity=100.0)
    po, item = await _create_po_with_item(product_id=product.id, cost=7.0, ordered_qty=50)

    result = await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=50)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    assert result["matched"] == 1
    assert result["errors"] == 0

    updated = await product_repo.get_by_id(product.id)
    assert updated.quantity == pytest.approx(150.0)


@pytest.mark.asyncio
async def test_receive_weighted_average_cost(db):
    """WAC: existing cost=$8 qty=100, receive cost=$12 qty=50 → WAC=$9.33."""
    product = await _create_test_product(quantity=100.0, cost=8.0)
    po, item = await _create_po_with_item(product_id=product.id, cost=12.0, ordered_qty=50)

    await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=50)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    updated = await product_repo.get_by_id(product.id)
    expected_wac = (100 * 8 + 50 * 12) / 150
    assert updated.cost == pytest.approx(expected_wac, abs=0.01)


@pytest.mark.asyncio
async def test_receive_cost_fallback_from_unit_price(db):
    """When item has unit_price but no cost, cost_total and ledger must still be non-zero."""
    product = await _create_test_product(quantity=100.0, cost=8.0)
    po, item = await _create_po_with_item(
        product_id=product.id,
        cost=None,
        unit_price=10.0,
        ordered_qty=50,
    )

    result = await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=50)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    assert result["cost_total"] > 0, "cost_total should use unit_price fallback"
    assert result["cost_total"] == pytest.approx(7.0 * 50)

    conn = get_connection()
    cursor = await conn.execute(
        "SELECT SUM(amount) FROM financial_ledger WHERE reference_id = ? AND account = 'inventory'",
        (po.id,),
    )
    row = await cursor.fetchone()
    assert row[0] is not None and row[0] > 0, "Ledger INVENTORY entry should be non-zero"


@pytest.mark.asyncio
async def test_receive_creates_stock_transaction(db):
    """Receiving should create a RECEIVING stock transaction."""
    product = await _create_test_product(quantity=100.0)
    po, item = await _create_po_with_item(product_id=product.id, cost=7.0, ordered_qty=25)

    await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=25)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    txs = await stock_repo.list_by_product(product.id, limit=50)
    receiving_txs = [t for t in txs if t.transaction_type == "receiving"]
    assert len(receiving_txs) >= 1
    assert receiving_txs[0].quantity_delta == pytest.approx(25.0)
    assert receiving_txs[0].reference_id == po.id


@pytest.mark.asyncio
async def test_receive_creates_ledger_entries(db):
    """Receiving should create INVENTORY + ACCOUNTS_PAYABLE entries in the financial ledger."""
    product = await _create_test_product(quantity=100.0)
    po, item = await _create_po_with_item(product_id=product.id, cost=6.0, ordered_qty=20)

    await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=20)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    conn = get_connection()
    cursor = await conn.execute(
        "SELECT account, ROUND(CAST(SUM(amount) AS NUMERIC), 2) FROM financial_ledger WHERE reference_id = ? GROUP BY account",
        (po.id,),
    )
    rows = {r[0]: r[1] for r in await cursor.fetchall()}

    expected = 6.0 * 20
    assert "inventory" in rows, "Should have INVENTORY ledger entry"
    assert "accounts_payable" in rows, "Should have AP ledger entry"
    assert rows["inventory"] == pytest.approx(expected)
    assert rows["accounts_payable"] == pytest.approx(expected)


@pytest.mark.asyncio
async def test_receive_po_status_becomes_received(db):
    """All items received → PO status = 'received'."""
    product = await _create_test_product(quantity=100.0)
    po, item = await _create_po_with_item(product_id=product.id, cost=5.0, ordered_qty=10)

    result = await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=10)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    assert result["status"] == "received"


@pytest.mark.asyncio
async def test_receive_rejects_ordered_items(db):
    """Items still in 'ordered' status (not yet at dock) should be rejected."""
    product = await _create_test_product(quantity=100.0)
    po, item = await _create_po_with_item(
        product_id=product.id,
        cost=5.0,
        ordered_qty=10,
        status=POItemStatus.ORDERED,
    )

    result = await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=10)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    assert result["errors"] == 1
    assert result["matched"] == 0
    assert "not yet marked" in result["error_details"][0]["error"]


# ── Override fields from review modal ──────────────────────────────────────


@pytest.mark.asyncio
async def test_receive_cost_override_affects_wac(db):
    """When the review modal overrides cost, the WAC should use the overridden value."""
    product = await _create_test_product(quantity=100.0, cost=8.0)
    po, item = await _create_po_with_item(product_id=product.id, cost=6.0, ordered_qty=50)

    result = await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=50, cost=20.0)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    assert result["matched"] == 1
    updated = await product_repo.get_by_id(product.id)
    expected_wac = (100 * 8 + 50 * 20) / 150
    assert updated.cost == pytest.approx(expected_wac, abs=0.01)


@pytest.mark.asyncio
async def test_receive_creates_product_with_overridden_name(db):
    """When no product match, overrides (name, department) apply to the new product."""
    po, item = await _create_po_with_item(
        product_id=None,
        cost=5.0,
        ordered_qty=10,
        name="Generic Widget",
    )

    result = await receive_po_items(
        po_id=po.id,
        item_updates=[
            ReceiveItemUpdate(
                id=item.id,
                delivered_qty=10,
                name="Corrected Widget Name",
                suggested_department="HDW",
            )
        ],
        deps=_stub_deps(),
        current_user=_user(),
    )

    assert result["received"] == 1
    assert result["errors"] == 0

    conn = get_connection()
    cursor = await conn.execute(
        "SELECT name FROM products WHERE id = (SELECT product_id FROM purchase_order_items WHERE id = ?)",
        (item.id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "Corrected Widget Name"


@pytest.mark.asyncio
async def test_receive_product_id_override_matches_explicit(db):
    """When the review modal sets product_id, it should be used instead of auto-match."""
    product_a = await _create_test_product(name="Widget A", quantity=50.0, cost=10.0)
    product_b = await _create_test_product(name="Widget B", quantity=30.0, cost=12.0)
    po, item = await _create_po_with_item(
        product_id=product_a.id,
        cost=8.0,
        ordered_qty=20,
    )

    result = await receive_po_items(
        po_id=po.id,
        item_updates=[ReceiveItemUpdate(id=item.id, delivered_qty=20, product_id=product_b.id)],
        deps=_stub_deps(),
        current_user=_user(),
    )

    assert result["matched"] == 1
    updated_b = await product_repo.get_by_id(product_b.id)
    assert updated_b.quantity == pytest.approx(50.0)

    updated_a = await product_repo.get_by_id(product_a.id)
    assert updated_a.quantity == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_receive_items_with_typed_input(db):
    """receive_po_items accepts ReceiveItemUpdate objects and correctly updates stock."""
    product = await _create_test_product(name="Typed Input Product", quantity=20.0, cost=5.0)
    po, item = await _create_po_with_item(product_id=product.id, cost=6.0, ordered_qty=15)

    update = ReceiveItemUpdate(
        id=item.id,
        delivered_qty=15,
        cost=6.0,
    )

    result = await receive_po_items(
        po_id=po.id,
        item_updates=[update],
        deps=_stub_deps(),
        current_user=_user(),
    )

    assert result["matched"] == 1
    assert result["errors"] == 0
    assert result["cost_total"] == pytest.approx(6.0 * 15)

    updated = await product_repo.get_by_id(product.id)
    assert updated.quantity == pytest.approx(35.0)
