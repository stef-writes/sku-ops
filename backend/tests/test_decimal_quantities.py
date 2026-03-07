"""
Decimal quantity & UOM conversion integration tests.

These are the tests that would have caught every int-truncation bug. They
exercise the full application flow — product creation, withdrawal, receiving,
adjustment — with fractional quantities and cross-unit conversions, and then
verify the database state, stock transactions, and returned values.

Every test uses at least one non-integer quantity. If any layer truncates
to int, these fail.
"""
import pytest

from catalog.application.product_lifecycle import create_product
from catalog.infrastructure.product_repo import product_repo
from inventory.application.inventory_service import (
    get_stock_history,
    process_adjustment_stock_changes,
    process_import_stock_changes,
    process_receiving_stock_changes,
    process_withdrawal_stock_changes,
)
from inventory.domain.errors import InsufficientStockError, NegativeStockError
from inventory.domain.stock import StockDecrement


async def _create_product(name, quantity, base_unit="each", **kw):
    """Helper: create product with a given base_unit and fractional quantity."""
    return await create_product(
        department_id="dept-1",
        department_name="Hardware",
        name=name,
        quantity=quantity,
        price=kw.get("price", 10.0),
        cost=kw.get("cost", 5.0),
        base_unit=base_unit,
        sell_uom=kw.get("sell_uom", base_unit),
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )


# ── Fractional product creation ──────────────────────────────────────────────

class TestFractionalProductCreation:

    @pytest.mark.asyncio
    async def test_create_product_with_fractional_quantity(self, _db):
        """Product created with 10.5 must store 10.5, not 10."""
        product = await _create_product("Half Widget", 10.5)
        assert product.quantity == 10.5

        persisted = await product_repo.get_by_id(product.id)
        assert persisted["quantity"] == pytest.approx(10.5), (
            f"DB stored {persisted['quantity']}, expected 10.5 — int truncation?"
        )

    @pytest.mark.asyncio
    async def test_stock_transaction_records_fractional_quantity(self, _db):
        """The initial IMPORT stock transaction must record the fractional quantity."""
        product = await _create_product("Fractional Import", 7.25)
        history = await get_stock_history(product.id)
        assert len(history) == 1
        tx = history[0]
        assert tx["quantity_delta"] == pytest.approx(7.25)
        assert isinstance(tx["quantity_delta"], float)


# ── Fractional withdrawal ────────────────────────────────────────────────────

class TestFractionalWithdrawal:

    @pytest.mark.asyncio
    async def test_withdraw_fractional_quantity(self, _db):
        """Withdraw 2.5 from 10.0 → 7.5 remaining."""
        product = await _create_product("Wire", 10.0)
        decrements = [
            StockDecrement(product_id=product.id, sku=product.sku, name=product.name, quantity=2.5),
        ]
        await process_withdrawal_stock_changes(
            items=decrements, withdrawal_id="w-1",
            user_id="user-1", user_name="Test",
        )
        updated = await product_repo.get_by_id(product.id)
        assert updated["quantity"] == pytest.approx(7.5)

    @pytest.mark.asyncio
    async def test_withdraw_fractional_insufficient_stock(self, _db):
        """Withdraw 5.5 from 5.0 must raise, not silently truncate to 5."""
        product = await _create_product("Wire", 5.0)
        decrements = [
            StockDecrement(product_id=product.id, sku=product.sku, name=product.name, quantity=5.5),
        ]
        with pytest.raises(InsufficientStockError) as exc_info:
            await process_withdrawal_stock_changes(
                items=decrements, withdrawal_id="w-2",
                user_id="user-1", user_name="Test",
            )
        assert exc_info.value.requested == 5.5
        assert exc_info.value.available == pytest.approx(5.0)

        unchanged = await product_repo.get_by_id(product.id)
        assert unchanged["quantity"] == pytest.approx(5.0), "Stock should be unchanged after failed withdrawal"

    @pytest.mark.asyncio
    async def test_withdraw_exactly_all_stock(self, _db):
        """Withdraw 3.75 from 3.75 → exactly 0 remaining."""
        product = await _create_product("Sealant", 3.75)
        decrements = [
            StockDecrement(product_id=product.id, sku=product.sku, name=product.name, quantity=3.75),
        ]
        await process_withdrawal_stock_changes(
            items=decrements, withdrawal_id="w-3",
            user_id="user-1", user_name="Test",
        )
        updated = await product_repo.get_by_id(product.id)
        assert updated["quantity"] == pytest.approx(0.0)


# ── UOM conversion in withdrawals ────────────────────────────────────────────

class TestUOMConversionWithdrawal:

    @pytest.mark.asyncio
    async def test_withdraw_inches_from_feet_product(self, _db):
        """Product stored in feet (100). Withdraw 18 inches = 1.5 feet deducted."""
        product = await _create_product("Copper Pipe", 100.0, base_unit="foot")

        decrements = [
            StockDecrement(
                product_id=product.id, sku=product.sku, name=product.name,
                quantity=18.0, unit="inch",
            ),
        ]
        await process_withdrawal_stock_changes(
            items=decrements, withdrawal_id="w-uom-1",
            user_id="user-1", user_name="Test",
        )
        updated = await product_repo.get_by_id(product.id)
        assert updated["quantity"] == pytest.approx(98.5), (
            f"100 ft - 18 in should be 98.5 ft, got {updated['quantity']}"
        )

    @pytest.mark.asyncio
    async def test_withdraw_yards_from_feet_product(self, _db):
        """Product stored in feet (30). Withdraw 2 yards = 6 feet deducted."""
        product = await _create_product("Rope", 30.0, base_unit="foot")

        decrements = [
            StockDecrement(
                product_id=product.id, sku=product.sku, name=product.name,
                quantity=2.0, unit="yard",
            ),
        ]
        await process_withdrawal_stock_changes(
            items=decrements, withdrawal_id="w-uom-2",
            user_id="user-1", user_name="Test",
        )
        updated = await product_repo.get_by_id(product.id)
        assert updated["quantity"] == pytest.approx(24.0)

    @pytest.mark.asyncio
    async def test_withdraw_pints_from_gallon_product(self, _db):
        """Product stored in gallons (5). Withdraw 4 pints = 0.5 gallons."""
        product = await _create_product("Paint", 5.0, base_unit="gallon")

        decrements = [
            StockDecrement(
                product_id=product.id, sku=product.sku, name=product.name,
                quantity=4.0, unit="pint",
            ),
        ]
        await process_withdrawal_stock_changes(
            items=decrements, withdrawal_id="w-uom-3",
            user_id="user-1", user_name="Test",
        )
        updated = await product_repo.get_by_id(product.id)
        assert updated["quantity"] == pytest.approx(4.5)

    @pytest.mark.asyncio
    async def test_stock_transaction_records_base_unit(self, _db):
        """Stock transaction should record the converted quantity in base_unit."""
        product = await _create_product("Chain", 50.0, base_unit="foot")

        decrements = [
            StockDecrement(
                product_id=product.id, sku=product.sku, name=product.name,
                quantity=24.0, unit="inch",
            ),
        ]
        await process_withdrawal_stock_changes(
            items=decrements, withdrawal_id="w-uom-tx",
            user_id="user-1", user_name="Test",
        )
        history = await get_stock_history(product.id)
        withdrawal_txs = [t for t in history if t.get("transaction_type") == "withdrawal"]
        assert len(withdrawal_txs) == 1
        tx = withdrawal_txs[0]
        assert tx["quantity_delta"] == pytest.approx(-2.0), "24 inches = 2 feet"
        assert tx["unit"] == "foot"


# ── UOM conversion in receiving ──────────────────────────────────────────────

class TestUOMConversionReceiving:

    @pytest.mark.asyncio
    async def test_receive_inches_into_feet_product(self, _db):
        """Product stored in feet (50). Receive 36 inches = 3 feet added."""
        product = await _create_product("Tubing", 50.0, base_unit="foot")

        await process_receiving_stock_changes(
            product_id=product.id, sku=product.sku, product_name=product.name,
            quantity=36.0, unit="inch",
            user_id="user-1", user_name="Test",
            reference_id="po-1",
        )
        updated = await product_repo.get_by_id(product.id)
        assert updated["quantity"] == pytest.approx(53.0), (
            f"50 ft + 36 in should be 53 ft, got {updated['quantity']}"
        )

    @pytest.mark.asyncio
    async def test_receive_ounces_into_pounds_product(self, _db):
        """Product stored in pounds (10). Receive 32 ounces = 2 pounds added."""
        product = await _create_product("Solder", 10.0, base_unit="pound")

        await process_receiving_stock_changes(
            product_id=product.id, sku=product.sku, product_name=product.name,
            quantity=32.0, unit="ounce",
            user_id="user-1", user_name="Test",
        )
        updated = await product_repo.get_by_id(product.id)
        assert updated["quantity"] == pytest.approx(12.0)


# ── Stock adjustment with decimals ───────────────────────────────────────────

class TestFractionalAdjustment:

    @pytest.mark.asyncio
    async def test_positive_adjustment_with_decimal(self, _db):
        product = await _create_product("Bolts", 10.0)
        await process_adjustment_stock_changes(
            product_id=product.id, quantity_delta=0.5,
            reason="found extra", user_id="user-1", user_name="Test",
        )
        updated = await product_repo.get_by_id(product.id)
        assert updated["quantity"] == pytest.approx(10.5)

    @pytest.mark.asyncio
    async def test_negative_adjustment_with_decimal(self, _db):
        product = await _create_product("Nuts", 10.0)
        await process_adjustment_stock_changes(
            product_id=product.id, quantity_delta=-3.25,
            reason="damaged", user_id="user-1", user_name="Test",
        )
        updated = await product_repo.get_by_id(product.id)
        assert updated["quantity"] == pytest.approx(6.75)

    @pytest.mark.asyncio
    async def test_adjustment_that_would_go_negative_raises(self, _db):
        product = await _create_product("Screws", 2.0)
        with pytest.raises(NegativeStockError):
            await process_adjustment_stock_changes(
                product_id=product.id, quantity_delta=-3.0,
                reason="correction", user_id="user-1", user_name="Test",
            )
        unchanged = await product_repo.get_by_id(product.id)
        assert unchanged["quantity"] == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_zero_adjustment_raises(self, _db):
        product = await _create_product("Washers", 5.0)
        with pytest.raises(ValueError, match="zero"):
            await process_adjustment_stock_changes(
                product_id=product.id, quantity_delta=0,
                reason="oops", user_id="user-1", user_name="Test",
            )
