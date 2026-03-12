"""Integration tests for sell-unit cost normalization.

Covers the DB-backed portion of the sell_cost feature:
  1. Withdrawal service computes sell_cost and stores it on LineItem
  2. Ledger COGS/INVENTORY entries carry quantity, unit, unit_cost using sell_cost
  3. Ledger REVENUE entries carry quantity and unit_cost
  4. Invoice line items carry unit + sell_cost copied from withdrawal items

Pure unit tests (cost_per_sell_unit, _build_cogs_journal_lines) are in
tests/unit/test_xero_cogs_journal.py.
"""

import pytest

from catalog.application.product_lifecycle import create_product
from catalog.application.queries import list_products
from inventory.application.inventory_service import (
    process_import_stock_changes,
    process_withdrawal_stock_changes,
)
from operations.application.withdrawal_service import create_withdrawal
from operations.domain.withdrawal import ContractorContext, MaterialWithdrawalCreate, WithdrawalItem
from shared.kernel.types import CurrentUser


@pytest.mark.asyncio
async def test_withdrawal_sell_cost_same_unit(db):
    """When base_unit == sell_uom and pack_qty == 1, sell_cost == cost."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Bolt",
        quantity=50,
        price=2.0,
        cost=1.0,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
        base_unit="each",
        sell_uom="each",
        pack_qty=1,
    )

    data = MaterialWithdrawalCreate(
        items=[
            WithdrawalItem(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                quantity=5,
                price=2.0,
                cost=1.0,
            )
        ],
        job_id="JOB-001",
        service_address="123 Main",
    )
    user = CurrentUser(id="user-1", email="t@t.com", name="T", role="admin")
    contractor = ContractorContext(id="contractor-1", name="C")

    result = await create_withdrawal(
        data,
        contractor,
        user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
    )

    items = result.get("items") or []
    assert len(items) == 1
    assert items[0].get("sell_cost") == pytest.approx(1.0)
    assert items[0].get("sell_uom") == "each"


@pytest.mark.asyncio
async def test_withdrawal_sell_cost_unit_conversion(db):
    """When base_unit=inch and sell_uom=foot, sell_cost is 12x base cost."""
    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Wire",
        quantity=1000,
        price=0.12,
        cost=0.05,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
        base_unit="inch",
        sell_uom="foot",
        pack_qty=1,
    )

    data = MaterialWithdrawalCreate(
        items=[
            WithdrawalItem(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                quantity=10,
                price=0.12,
                unit="inch",
            )
        ],
        job_id="JOB-002",
        service_address="456 Oak",
    )
    user = CurrentUser(id="user-1", email="t@t.com", name="T", role="admin")
    contractor = ContractorContext(id="contractor-1", name="C")

    result = await create_withdrawal(
        data,
        contractor,
        user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
    )

    items = result.get("items") or []
    assert len(items) == 1
    assert items[0].get("sell_uom") == "foot"
    assert items[0].get("sell_cost") == pytest.approx(0.60, abs=1e-4)


@pytest.mark.asyncio
async def test_ledger_cogs_entry_has_quantity_and_unit_cost(db):
    """COGS ledger entry must carry qty, sell_uom unit, and sell_cost as unit_cost."""
    from shared.infrastructure.database import get_connection

    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Pipe",
        quantity=500,
        price=0.20,
        cost=0.08,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
        base_unit="inch",
        sell_uom="foot",
        pack_qty=1,
    )

    data = MaterialWithdrawalCreate(
        items=[
            WithdrawalItem(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                quantity=24,
                price=0.20,
                unit="inch",
            )
        ],
        job_id="JOB-003",
        service_address="789 Elm",
    )
    user = CurrentUser(id="user-1", email="t@t.com", name="T", role="admin")
    contractor = ContractorContext(id="contractor-1", name="C")

    result = await create_withdrawal(
        data,
        contractor,
        user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
    )

    conn = get_connection()
    cursor = await conn.execute(
        """SELECT quantity, unit, unit_cost, amount
           FROM financial_ledger
           WHERE reference_id = ? AND account = 'cogs'""",
        (result["id"],),
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    assert len(rows) == 1

    row = rows[0]
    assert row["quantity"] == pytest.approx(24.0)
    assert row["unit"] == "foot"
    assert row["unit_cost"] == pytest.approx(0.96, abs=1e-4)
    assert row["amount"] == pytest.approx(23.04, abs=0.01)


@pytest.mark.asyncio
async def test_ledger_revenue_entry_has_quantity_and_unit_cost(db):
    """REVENUE entry carries withdrawal qty/unit and unit_price as unit_cost."""
    from shared.infrastructure.database import get_connection

    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Conduit",
        quantity=100,
        price=5.0,
        cost=2.0,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )

    data = MaterialWithdrawalCreate(
        items=[
            WithdrawalItem(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                quantity=3,
                price=5.0,
            )
        ],
        job_id="JOB-004",
        service_address="1 A St",
    )
    user = CurrentUser(id="user-1", email="t@t.com", name="T", role="admin")
    contractor = ContractorContext(id="contractor-1", name="C")

    result = await create_withdrawal(
        data,
        contractor,
        user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
    )

    conn = get_connection()
    cursor = await conn.execute(
        """SELECT quantity, unit, unit_cost FROM financial_ledger
           WHERE reference_id = ? AND account = 'revenue'""",
        (result["id"],),
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    assert len(rows) == 1
    assert rows[0]["quantity"] == pytest.approx(3.0)
    assert rows[0]["unit_cost"] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_invoice_line_items_carry_sell_cost(db):
    """Invoice line items built from withdrawals must copy unit and sell_cost."""
    from finance.application.invoice_service import (
        create_invoice_from_withdrawals,
        get_invoice,
    )

    product = await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name="Tubing",
        quantity=200,
        price=0.15,
        cost=0.06,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
        base_unit="inch",
        sell_uom="foot",
        pack_qty=1,
    )

    data = MaterialWithdrawalCreate(
        items=[
            WithdrawalItem(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                quantity=36,
                price=0.15,
                unit="inch",
            )
        ],
        job_id="JOB-005",
        service_address="2 B St",
    )
    user = CurrentUser(id="user-1", email="t@t.com", name="T", role="admin")
    contractor = ContractorContext(id="contractor-1", name="C", billing_entity="ACME Inc")

    withdrawal = await create_withdrawal(
        data,
        contractor,
        user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
    )

    inv = await create_invoice_from_withdrawals([withdrawal["id"]])
    full_inv = await get_invoice(inv.id)

    line_items = full_inv.line_items
    assert len(line_items) == 1
    li = line_items[0]
    assert li.sell_cost == pytest.approx(0.72, abs=1e-4)
    assert li.unit == "inch"
