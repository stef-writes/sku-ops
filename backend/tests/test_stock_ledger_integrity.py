"""
Stock ledger integrity tests.

The stock ledger is an append-only log of every quantity change. These tests
enforce the fundamental invariant:

    current_quantity == initial_import + sum(all transaction deltas after import)

If any code path changes quantity without recording a transaction (or records
a transaction with the wrong delta), these tests catch it.

Also tests organization isolation — org A's data must never leak into org B's views.
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
from inventory.domain.stock import StockDecrement


async def _create_product(name, quantity, base_unit="each", org_id="default", dept_id="dept-1", **kw):
    return await create_product(
        department_id=dept_id,
        department_name="Hardware",
        name=name,
        quantity=quantity,
        price=kw.get("price", 10.0),
        cost=kw.get("cost", 5.0),
        base_unit=base_unit,
        user_id="user-1",
        user_name="Test",
        organization_id=org_id,
        on_stock_import=process_import_stock_changes,
    )


# ── Ledger balance invariant ─────────────────────────────────────────────────

class TestLedgerBalanceInvariant:
    """For any product, current quantity must equal the sum of all ledger deltas."""

    @pytest.mark.asyncio
    async def test_balance_after_mixed_operations(self, db):
        """Create → withdraw → receive → adjust → verify balance."""
        product = await _create_product("Copper Fitting", 20.0, base_unit="foot")

        # Withdraw 3.5 ft
        await process_withdrawal_stock_changes(
            items=[StockDecrement(
                product_id=product.id, sku=product.sku,
                name=product.name, quantity=3.5,
            )],
            withdrawal_id="w-ledger-1",
            user_id="user-1", user_name="Test",
        )

        # Receive 12 inches = 1 foot
        await process_receiving_stock_changes(
            product_id=product.id, sku=product.sku,
            product_name=product.name, quantity=12.0, unit="inch",
            user_id="user-1", user_name="Test",
        )

        # Adjust -2.25
        await process_adjustment_stock_changes(
            product_id=product.id, quantity_delta=-2.25,
            reason="damaged", user_id="user-1", user_name="Test",
        )

        # Verify: 20.0 - 3.5 + 1.0 - 2.25 = 15.25
        current = await product_repo.get_by_id(product.id)
        assert current["quantity"] == pytest.approx(15.25)

        # Verify ledger sums to same value
        history = await get_stock_history(product.id, limit=100)
        ledger_sum = sum(tx["quantity_delta"] for tx in history)
        assert current["quantity"] == pytest.approx(ledger_sum), (
            f"Ledger integrity violation: product qty={current['quantity']}, "
            f"ledger sum={ledger_sum}"
        )

    @pytest.mark.asyncio
    async def test_failed_withdrawal_preserves_ledger_balance(self, db):
        """A failed withdrawal must not leave orphan transactions."""
        product = await _create_product("Valve", 5.0)

        with pytest.raises(Exception):
            await process_withdrawal_stock_changes(
                items=[StockDecrement(
                    product_id=product.id, sku=product.sku,
                    name=product.name, quantity=10.0,
                )],
                withdrawal_id="w-fail",
                user_id="user-1", user_name="Test",
            )

        current = await product_repo.get_by_id(product.id)
        history = await get_stock_history(product.id, limit=100)

        withdrawal_txs = [t for t in history if t.get("transaction_type") == "withdrawal"]
        assert len(withdrawal_txs) == 0, "Failed withdrawal should leave no ledger entries"

        ledger_sum = sum(tx["quantity_delta"] for tx in history)
        assert current["quantity"] == pytest.approx(ledger_sum)

    @pytest.mark.asyncio
    async def test_multiple_withdrawals_ledger_consistency(self, db):
        """Three successive fractional withdrawals — ledger must stay balanced."""
        product = await _create_product("Wire Spool", 100.0)

        for i, qty in enumerate([12.5, 7.75, 0.25]):
            await process_withdrawal_stock_changes(
                items=[StockDecrement(
                    product_id=product.id, sku=product.sku,
                    name=product.name, quantity=qty,
                )],
                withdrawal_id=f"w-multi-{i}",
                user_id="user-1", user_name="Test",
            )

        current = await product_repo.get_by_id(product.id)
        expected = 100.0 - 12.5 - 7.75 - 0.25  # 79.5
        assert current["quantity"] == pytest.approx(expected)

        history = await get_stock_history(product.id, limit=100)
        ledger_sum = sum(tx["quantity_delta"] for tx in history)
        assert current["quantity"] == pytest.approx(ledger_sum)


# ── Transaction field completeness ───────────────────────────────────────────

class TestTransactionFieldCompleteness:
    """Every stock transaction must have complete, correctly-typed fields."""

    @pytest.mark.asyncio
    async def test_transaction_fields_are_float(self, db):
        """quantity_delta, quantity_before, quantity_after must be float, not int."""
        product = await _create_product("Test Float Fields", 10.5)
        history = await get_stock_history(product.id)
        assert len(history) >= 1
        tx = history[0]

        for field in ("quantity_delta", "quantity_before", "quantity_after"):
            assert isinstance(tx[field], float), (
                f"stock_transaction.{field} is {type(tx[field]).__name__}, expected float"
            )

    @pytest.mark.asyncio
    async def test_transaction_has_unit_field(self, db):
        """Every stock transaction must record the unit."""
        product = await _create_product("Piping", 50.0, base_unit="foot")
        await process_withdrawal_stock_changes(
            items=[StockDecrement(
                product_id=product.id, sku=product.sku,
                name=product.name, quantity=6.0, unit="inch",
            )],
            withdrawal_id="w-unit-check",
            user_id="user-1", user_name="Test",
        )
        history = await get_stock_history(product.id)
        withdrawal_txs = [t for t in history if t.get("transaction_type") == "withdrawal"]
        assert len(withdrawal_txs) == 1
        assert "unit" in withdrawal_txs[0], "Stock transaction missing 'unit' field"
        assert withdrawal_txs[0]["unit"] == "foot", "Unit should be the product's base_unit"

    @pytest.mark.asyncio
    async def test_transaction_before_after_arithmetic(self, db):
        """For every transaction: quantity_after == quantity_before + quantity_delta."""
        product = await _create_product("Audit Product", 25.0)

        await process_withdrawal_stock_changes(
            items=[StockDecrement(
                product_id=product.id, sku=product.sku,
                name=product.name, quantity=3.5,
            )],
            withdrawal_id="w-arith",
            user_id="user-1", user_name="Test",
        )
        await process_adjustment_stock_changes(
            product_id=product.id, quantity_delta=1.25,
            reason="found", user_id="user-1", user_name="Test",
        )

        history = await get_stock_history(product.id, limit=100)
        for tx in history:
            computed_after = tx["quantity_before"] + tx["quantity_delta"]
            assert tx["quantity_after"] == pytest.approx(computed_after), (
                f"Arithmetic violation in {tx['transaction_type']}: "
                f"{tx['quantity_before']} + {tx['quantity_delta']} != {tx['quantity_after']}"
            )


# ── Organization isolation ───────────────────────────────────────────────────

class TestOrganizationIsolation:

    @pytest.mark.asyncio
    async def test_product_isolated_by_org(self, db):
        """Products from org-A must not appear in org-B queries."""
        from shared.infrastructure.database import get_connection
        conn = get_connection()
        for org in ("org-a", "org-b"):
            await conn.execute(
                "INSERT OR IGNORE INTO departments (id, name, code, description, product_count, organization_id, created_at) "
                "VALUES (?, 'Hardware', 'HDW', 'Hardware dept', 0, ?, datetime('now'))",
                (f"dept-1-{org}", org),
            )
        await conn.commit()

        p1 = await _create_product("Org A Widget", 10.0, org_id="org-a", dept_id="dept-1-org-a")
        await _create_product("Org B Widget", 20.0, org_id="org-b", dept_id="dept-1-org-b")

        from_a = await product_repo.get_by_id(p1.id, organization_id="org-a")
        from_b = await product_repo.get_by_id(p1.id, organization_id="org-b")

        assert from_a is not None, "Org A should see its own product"
        assert from_b is None, "Org B should NOT see Org A's product"
