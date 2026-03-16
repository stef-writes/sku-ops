"""
Repository contract tests — write -> read -> assert field names, types, values.

These tests enforce that:
  1. What the repo writes to the DB can be read back with the correct field names
  2. Numeric fields are the correct type (float, not int) after a round-trip
  3. Domain model field names match what the repo returns (e.g. unit_price vs price)
  4. JSON-serialized fields (items) survive round-trip correctly

These would have caught:
  - The price->unit_price column mapping bug in po_repo
  - Missing float coercion in credit_note_repo
  - Any schema drift between domain models and SQL columns
"""

import pytest

from catalog.application.sku_lifecycle import create_product_with_sku
from catalog.infrastructure.sku_repo import sku_repo
from finance.application.invoice_service import create_invoice_from_withdrawals
from finance.infrastructure.credit_note_repo import credit_note_repo
from inventory.application.inventory_service import process_import_stock_changes
from inventory.infrastructure.stock_repo import stock_repo
from operations.infrastructure.material_request_repo import material_request_repo
from purchasing.domain.purchase_order import (
    POItemStatus,
    POStatus,
    PurchaseOrder,
    PurchaseOrderItem,
)
from purchasing.infrastructure.po_repo import po_repo
from shared.infrastructure.database import get_connection

# -- Product repo -------------------------------------------------------------


class TestProductRepoContract:
    def test_round_trip_preserves_float_quantity(self, call):
        """Insert a SKU with float quantity, read it back, assert float."""

        async def _body():
            sku = await create_product_with_sku(
                category_id="dept-1",
                category_name="Hardware",
                name="Round Trip Widget",
                quantity=7.25,
                price=12.50,
                cost=6.75,
                base_unit="foot",
                sell_uom="inch",
                user_id="user-1",
                user_name="Test",
                on_stock_import=process_import_stock_changes,
            )
            row = await sku_repo.get_by_id(sku.id)
            assert row is not None

            assert isinstance(row.quantity, float), f"quantity is {type(row.quantity)}"
            assert row.quantity == pytest.approx(7.25)

            assert isinstance(row.price, float), f"price is {type(row.price)}"
            assert row.price == pytest.approx(12.50)

            assert isinstance(row.cost, float), f"cost is {type(row.cost)}"
            assert row.cost == pytest.approx(6.75)

            assert row.base_unit == "foot"
            assert row.sell_uom == "inch"

        call(_body)

    def test_list_skus_returns_float_quantities(self, call):
        """Listing SKUs must return float quantities, not int."""

        async def _body():
            await create_product_with_sku(
                category_id="dept-1",
                category_name="Hardware",
                name="List Test",
                quantity=3.5,
                user_id="user-1",
                user_name="Test",
                on_stock_import=process_import_stock_changes,
            )
            skus = await sku_repo.list_skus(limit=10)
            assert len(skus) >= 1
            for s in skus:
                assert isinstance(s.quantity, float), (
                    f"sku '{s.name}' quantity is {type(s.quantity)}"
                )

        call(_body)


# -- Stock transaction repo ---------------------------------------------------


class TestStockRepoContract:
    def test_transaction_round_trip_field_types(self, call):
        """Stock transaction read-back must have float quantity fields and unit."""

        async def _body():
            product = await create_product_with_sku(
                category_id="dept-1",
                category_name="Hardware",
                name="Stock Repo Test",
                quantity=15.75,
                base_unit="gallon",
                user_id="user-1",
                user_name="Test",
                on_stock_import=process_import_stock_changes,
            )
            txs = await stock_repo.list_by_product(product.id, limit=10)
            assert len(txs) >= 1
            tx = txs[0]

            assert tx.product_id is not None
            assert tx.sku is not None
            assert tx.user_id is not None
            assert tx.unit is not None

            for field in ("quantity_delta", "quantity_before", "quantity_after"):
                assert isinstance(getattr(tx, field), float), (
                    f"stock_transaction.{field} is {type(getattr(tx, field)).__name__}, expected float"
                )

            assert isinstance(tx.unit, str)

        call(_body)


# -- Purchase order repo ------------------------------------------------------


class TestPORepoContract:
    def test_po_item_round_trip_has_unit_price_not_price(self, call):
        """PO items read from DB must use 'unit_price', not the raw column name 'price'."""

        async def _body():
            po = PurchaseOrder(
                vendor_id="v1",
                vendor_name="Acme",
                status=POStatus.ORDERED,
                created_by_id="user-1",
                created_by_name="Test",
                organization_id="default",
            )
            await po_repo.insert_po(po)

            item = PurchaseOrderItem(
                po_id=po.id,
                name="Pipe",
                ordered_qty=5.5,
                delivered_qty=0,
                unit_price=12.99,
                cost=8.50,
                base_unit="foot",
                sell_uom="inch",
                pack_qty=1,
                suggested_department="PLU",
                status=POItemStatus.ORDERED,
                organization_id="default",
            )
            await po_repo.insert_items([item])

            items = await po_repo.get_po_items(po.id)
            assert len(items) == 1
            read_item = items[0]

            assert hasattr(read_item, "unit_price"), (
                f"PO item missing 'unit_price' — got fields: {list(read_item.model_fields)}"
            )
            assert read_item.unit_price == pytest.approx(12.99)
            assert read_item.ordered_qty == pytest.approx(5.5)
            assert read_item.base_unit == "foot"

        call(_body)

    def test_po_item_float_quantities(self, call):
        """PO item quantities must be float after read-back."""

        async def _body():
            po = PurchaseOrder(
                vendor_id="v1",
                vendor_name="Acme",
                status=POStatus.ORDERED,
                created_by_id="user-1",
                created_by_name="Test",
                organization_id="default",
            )
            await po_repo.insert_po(po)

            item = PurchaseOrderItem(
                po_id=po.id,
                name="Fitting",
                ordered_qty=3.25,
                delivered_qty=1.5,
                unit_price=7.0,
                cost=4.0,
                base_unit="each",
                sell_uom="each",
                pack_qty=1,
                suggested_department="HDW",
                status=POItemStatus.PENDING,
                organization_id="default",
            )
            await po_repo.insert_items([item])

            items = await po_repo.get_po_items(po.id)
            read_item = items[0]

            for field in ("ordered_qty", "delivered_qty", "unit_price", "cost"):
                val = getattr(read_item, field)
                assert isinstance(val, (int, float)), f"{field} is {type(val)}"
                assert float(val) == float(getattr(item, field))

        call(_body)


# -- Credit note repo ---------------------------------------------------------


class TestCreditNoteRepoContract:
    def test_credit_note_line_items_have_float_amounts(self, call):
        """Credit note line items must have float quantity, unit_price, amount, cost."""

        async def _body():
            cn = await credit_note_repo.insert_credit_note(
                return_id="ret-1",
                invoice_id=None,
                items=[
                    {
                        "description": "Widget return",
                        "quantity": 2.5,
                        "unit_price": 10.0,
                        "cost": 5.0,
                        "product_id": None,
                    },
                ],
                subtotal=25.0,
                tax=2.50,
                total=27.50,
            )
            assert cn is not None

            cn_read = await credit_note_repo.get_by_id(cn.id)
            assert cn_read is not None
            assert len(cn_read.line_items) == 1

            li = cn_read.line_items[0]
            for field in ("quantity", "unit_price", "amount", "cost"):
                assert isinstance(getattr(li, field), float), (
                    f"credit_note line_item.{field} is {type(getattr(li, field)).__name__}, expected float"
                )
            assert li.quantity == pytest.approx(2.5)
            assert li.unit_price == pytest.approx(10.0)

        call(_body)


# -- Invoice repo -------------------------------------------------------------


class TestInvoiceRepoContract:
    def test_invoice_line_items_have_float_amounts(self, call):
        """Invoice line items must have float quantity and amounts."""

        async def _body():
            conn = get_connection()
            await conn.execute(
                """INSERT INTO withdrawals
                   (id, items, job_id, service_address, subtotal, tax, total, cost_total,
                    contractor_id, contractor_name, contractor_company, billing_entity,
                    payment_status, processed_by_id, processed_by_name,
                    organization_id, created_at, invoice_id, paid_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, NOW(), NULL, NULL)""",
                (
                    "w-inv-test",
                    '[{"product_id":"p1","sku":"S","name":"X","quantity":2.5,"unit_price":10.0,"cost":5.0,"subtotal":25.0,"cost_total":12.5,"unit":"each"}]',
                    "JOB-1",
                    "123 Main St",
                    25.0,
                    2.50,
                    27.50,
                    12.50,
                    "contractor-1",
                    "Contractor",
                    "ACME",
                    "ACME Inc",
                    "unpaid",
                    "user-1",
                    "Test",
                    "default",
                ),
            )
            await conn.commit()

            inv = await create_invoice_from_withdrawals(["w-inv-test"])
            assert inv is not None
            assert len(inv.line_items) >= 1

            li = inv.line_items[0]
            for field in ("quantity", "unit_price", "amount"):
                assert isinstance(getattr(li, field), float), (
                    f"invoice line_item.{field} is {type(getattr(li, field)).__name__}, expected float"
                )

        call(_body)


# -- Material request repo ----------------------------------------------------


class TestMaterialRequestRepoContract:
    def test_round_trip_preserves_items_json(self, call):
        """Material request items (JSON blob) must survive round-trip."""

        async def _body():
            from operations.domain.material_request import MaterialRequest
            from operations.domain.withdrawal import WithdrawalItem

            mr = MaterialRequest(
                contractor_id="contractor-1",
                contractor_name="Contractor User",
                items=[
                    WithdrawalItem(
                        product_id="p1",
                        sku="HDW-001",
                        name="Widget",
                        quantity=2.5,
                        unit_price=10.0,
                        cost=5.0,
                        unit="foot",
                    ),
                ],
                status="pending",
                job_id="JOB-TEST",
                service_address="456 Oak",
                organization_id="default",
            )
            await material_request_repo.insert(mr)

            read = await material_request_repo.get_by_id(mr.id)
            assert read is not None
            assert len(read.items) == 1
            item = read.items[0]
            assert item.quantity == 2.5
            assert item.unit == "foot"

        call(_body)
