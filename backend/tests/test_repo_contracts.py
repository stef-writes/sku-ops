"""
Repository contract tests — write → read → assert field names, types, values.

These tests enforce that:
  1. What the repo writes to the DB can be read back with the correct field names
  2. Numeric fields are the correct type (float, not int) after a round-trip
  3. Domain model field names match what the repo returns (e.g. unit_price vs price)
  4. JSON-serialized fields (items) survive round-trip correctly

These would have caught:
  - The price→unit_price column mapping bug in po_repo
  - Missing float coercion in credit_note_repo
  - Any schema drift between domain models and SQL columns
"""
import pytest

from catalog.application.product_lifecycle import create_product
from catalog.infrastructure.product_repo import product_repo
from finance.infrastructure.credit_note_repo import credit_note_repo
from finance.infrastructure.invoice_repo import invoice_repo
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

# ── Product repo ─────────────────────────────────────────────────────────────

class TestProductRepoContract:

    @pytest.mark.asyncio
    async def test_round_trip_preserves_float_quantity(self, db):
        """Insert a product with float quantity, read it back, assert float."""
        product = await create_product(
            department_id="dept-1", department_name="Hardware",
            name="Round Trip Widget", quantity=7.25,
            price=12.50, cost=6.75,
            base_unit="foot", sell_uom="inch",
            user_id="user-1", user_name="Test",
            on_stock_import=process_import_stock_changes,
        )
        row = await product_repo.get_by_id(product.id)
        assert row is not None

        assert isinstance(row["quantity"], float), f"quantity is {type(row['quantity'])}"
        assert row["quantity"] == pytest.approx(7.25)

        assert isinstance(row["price"], float), f"price is {type(row['price'])}"
        assert row["price"] == pytest.approx(12.50)

        assert isinstance(row["cost"], float), f"cost is {type(row['cost'])}"
        assert row["cost"] == pytest.approx(6.75)

        assert row["base_unit"] == "foot"
        assert row["sell_uom"] == "inch"

    @pytest.mark.asyncio
    async def test_list_products_returns_float_quantities(self, db):
        """Listing products must return float quantities, not int."""
        await create_product(
            department_id="dept-1", department_name="Hardware",
            name="List Test", quantity=3.5,
            user_id="user-1", user_name="Test",
            on_stock_import=process_import_stock_changes,
        )
        products = await product_repo.list_products(limit=10)
        assert len(products) >= 1
        for p in products:
            assert isinstance(p["quantity"], float), (
                f"product '{p['name']}' quantity is {type(p['quantity'])}"
            )


# ── Stock transaction repo ───────────────────────────────────────────────────

class TestStockRepoContract:

    @pytest.mark.asyncio
    async def test_transaction_round_trip_field_types(self, db):
        """Stock transaction read-back must have float quantity fields and unit."""
        product = await create_product(
            department_id="dept-1", department_name="Hardware",
            name="Stock Repo Test", quantity=15.75,
            base_unit="gallon",
            user_id="user-1", user_name="Test",
            on_stock_import=process_import_stock_changes,
        )
        txs = await stock_repo.list_by_product(product.id, limit=10)
        assert len(txs) >= 1
        tx = txs[0]

        required_fields = {
            "product_id", "sku", "quantity_delta", "quantity_before",
            "quantity_after", "transaction_type", "user_id", "unit",
        }
        missing = required_fields - set(tx.keys())
        assert not missing, f"Stock transaction missing fields: {missing}"

        for field in ("quantity_delta", "quantity_before", "quantity_after"):
            assert isinstance(tx[field], float), (
                f"stock_transaction.{field} is {type(tx[field]).__name__}, expected float"
            )

        assert isinstance(tx["unit"], str)


# ── Purchase order repo ──────────────────────────────────────────────────────

class TestPORepoContract:

    @pytest.mark.asyncio
    async def test_po_item_round_trip_has_unit_price_not_price(self, db):
        """PO items read from DB must use 'unit_price', not the raw column name 'price'."""
        po = PurchaseOrder(
            vendor_id="v1", vendor_name="Acme", status=POStatus.ORDERED,
            created_by_id="user-1", created_by_name="Test",
        )
        await po_repo.insert_po(po)

        item = PurchaseOrderItem(
            po_id=po.id, name="Pipe", ordered_qty=5.5, delivered_qty=0,
            unit_price=12.99, cost=8.50,
            base_unit="foot", sell_uom="inch", pack_qty=1,
            suggested_department="PLU", status=POItemStatus.ORDERED,
        )
        await po_repo.insert_items([item])

        items = await po_repo.get_po_items(po.id)
        assert len(items) == 1
        read_item = items[0]

        assert "unit_price" in read_item, (
            f"PO item missing 'unit_price' — got keys: {list(read_item.keys())}"
        )
        assert read_item["unit_price"] == pytest.approx(12.99)
        assert read_item["ordered_qty"] == pytest.approx(5.5)
        assert read_item["base_unit"] == "foot"

    @pytest.mark.asyncio
    async def test_po_item_float_quantities(self, db):
        """PO item quantities must be float after read-back."""
        po = PurchaseOrder(
            vendor_id="v1", vendor_name="Acme", status=POStatus.ORDERED,
            created_by_id="user-1", created_by_name="Test",
        )
        await po_repo.insert_po(po)

        item = PurchaseOrderItem(
            po_id=po.id, name="Fitting", ordered_qty=3.25, delivered_qty=1.5,
            unit_price=7.0, cost=4.0,
            base_unit="each", sell_uom="each", pack_qty=1,
            suggested_department="HDW", status=POItemStatus.PENDING,
        )
        await po_repo.insert_items([item])

        items = await po_repo.get_po_items(po.id)
        read_item = items[0]

        for field in ("ordered_qty", "delivered_qty", "unit_price", "cost"):
            val = read_item[field]
            assert isinstance(val, (int, float)), f"{field} is {type(val)}"
            assert float(val) == float(getattr(item, field))


# ── Credit note repo ─────────────────────────────────────────────────────────

class TestCreditNoteRepoContract:

    @pytest.mark.asyncio
    async def test_credit_note_line_items_have_float_amounts(self, db):
        """Credit note line items must have float quantity, unit_price, amount, cost."""
        cn = await credit_note_repo.insert_credit_note(
            return_id="ret-1",
            invoice_id=None,
            items=[
                {"description": "Widget return", "quantity": 2.5, "unit_price": 10.0, "cost": 5.0, "product_id": None},
            ],
            subtotal=25.0,
            tax=2.50,
            total=27.50,
            organization_id="default",
        )
        assert cn is not None

        cn_read = await credit_note_repo.get_by_id(cn["id"])
        assert cn_read is not None
        assert len(cn_read["line_items"]) == 1

        li = cn_read["line_items"][0]
        for field in ("quantity", "unit_price", "amount", "cost"):
            assert isinstance(li[field], float), (
                f"credit_note line_item.{field} is {type(li[field]).__name__}, expected float"
            )
        assert li["quantity"] == pytest.approx(2.5)
        assert li["unit_price"] == pytest.approx(10.0)


# ── Invoice repo ─────────────────────────────────────────────────────────────

class TestInvoiceRepoContract:

    @pytest.mark.asyncio
    async def test_invoice_line_items_have_float_amounts(self, db):
        """Invoice line items must have float quantity and amounts."""
        conn = get_connection()
        await conn.execute(
            """INSERT INTO withdrawals
               (id, items, job_id, service_address, subtotal, tax, total, cost_total,
                contractor_id, contractor_name, contractor_company, billing_entity,
                payment_status, processed_by_id, processed_by_name,
                organization_id, created_at, invoice_id, paid_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), NULL, NULL)""",
            (
                "w-inv-test",
                '[{"product_id":"p1","sku":"S","name":"X","quantity":2.5,"unit_price":10.0,"cost":5.0,"subtotal":25.0,"cost_total":12.5,"unit":"each"}]',
                "JOB-1", "123 Main St",
                25.0, 2.50, 27.50, 12.50,
                "contractor-1", "Contractor", "ACME", "ACME Inc",
                "unpaid", "user-1", "Test", "default",
            ),
        )
        await conn.commit()

        inv = await invoice_repo.create_from_withdrawals(["w-inv-test"], "default")
        assert inv is not None
        assert len(inv["line_items"]) >= 1

        li = inv["line_items"][0]
        for field in ("quantity", "unit_price", "amount"):
            assert isinstance(li[field], float), (
                f"invoice line_item.{field} is {type(li[field]).__name__}, expected float"
            )


# ── Material request repo ────────────────────────────────────────────────────

class TestMaterialRequestRepoContract:

    @pytest.mark.asyncio
    async def test_round_trip_preserves_items_json(self, db):
        """Material request items (JSON blob) must survive round-trip."""
        from operations.domain.material_request import MaterialRequest
        from operations.domain.withdrawal import WithdrawalItem

        mr = MaterialRequest(
            contractor_id="contractor-1",
            contractor_name="Contractor User",
            items=[
                WithdrawalItem(
                    product_id="p1", sku="HDW-001", name="Widget",
                    quantity=2.5, unit_price=10.0, cost=5.0, unit="foot",
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
        assert len(read["items"]) == 1
        item = read["items"][0]
        assert item["quantity"] == 2.5
        assert item["unit"] == "foot"
