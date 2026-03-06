"""
Domain invariant tests — pure logic, no database.

These enforce the mathematical and type-level properties that the domain
must satisfy regardless of infrastructure. A CMU professor would call
these "specification tests" — they encode the domain rules as executable
properties, not just happy-path spot checks.

Categories:
  1. UOM conversion correctness (round-trip, cross-family rejection)
  2. Unit family completeness (every ALLOWED_BASE_UNIT has a home)
  3. Quantity type contracts (domain models enforce float, never int)
  4. LineItem computed fields (subtotal, cost_total arithmetic)
  5. Stock decrement invariants (unit default, quantity positivity)
"""

import pytest

from catalog.domain.product import Product, ProductCreate, ProductUpdate
from catalog.domain.units import (
    ALLOWED_BASE_UNITS,
    UNIT_FAMILIES,
    are_compatible,
    convert_quantity,
    family_for_unit,
)
from inventory.domain.errors import InsufficientStockError, NegativeStockError
from inventory.domain.stock import StockDecrement, StockTransaction, StockTransactionType
from kernel.types import LineItem
from operations.domain.withdrawal import MaterialWithdrawal, WithdrawalItem

# ── 1. UOM conversion correctness ────────────────────────────────────────────

class TestUOMConversion:
    """Convert between units — verify mathematical correctness."""

    @pytest.mark.parametrize("from_u,to_u,qty,expected", [
        ("foot", "inch", 1.0, 12.0),
        ("inch", "foot", 12.0, 1.0),
        ("yard", "foot", 1.0, 3.0),
        ("foot", "yard", 3.0, 1.0),
        ("yard", "inch", 1.0, 36.0),
        ("inch", "yard", 36.0, 1.0),
        ("gallon", "quart", 1.0, 4.0),
        ("quart", "pint", 1.0, 2.0),
        ("gallon", "pint", 1.0, 8.0),
        ("pound", "ounce", 1.0, 16.0),
        ("ounce", "pound", 16.0, 1.0),
    ])
    def test_exact_conversions(self, from_u, to_u, qty, expected):
        result = convert_quantity(qty, from_u, to_u)
        assert result == pytest.approx(expected, rel=1e-4), (
            f"{qty} {from_u} → {to_u}: expected {expected}, got {result}"
        )

    @pytest.mark.parametrize("from_u,to_u,qty", [
        ("foot", "inch", 2.5),
        ("gallon", "pint", 0.25),
        ("pound", "ounce", 0.125),
        ("yard", "inch", 3.7),
        ("meter", "foot", 1.5),
    ])
    def test_round_trip_preserves_quantity(self, from_u, to_u, qty):
        """Converting A→B→A must return the original quantity (within fp tolerance)."""
        intermediate = convert_quantity(qty, from_u, to_u)
        back = convert_quantity(intermediate, to_u, from_u)
        assert back == pytest.approx(qty, rel=1e-4), (
            f"Round-trip failed: {qty} {from_u} → {intermediate} {to_u} → {back} {from_u}"
        )

    def test_identity_conversion(self):
        """Same unit → same quantity, no computation."""
        assert convert_quantity(42.5, "foot", "foot") == 42.5

    def test_case_insensitive(self):
        assert convert_quantity(1, "Foot", "INCH") == pytest.approx(12.0)

    @pytest.mark.parametrize("from_u,to_u", [
        ("foot", "gallon"),
        ("pound", "inch"),
        ("pint", "ounce"),
        ("sqft", "foot"),
    ])
    def test_cross_family_raises(self, from_u, to_u):
        """Converting between incompatible families must raise ValueError."""
        with pytest.raises(ValueError, match="Cannot convert"):
            convert_quantity(1.0, from_u, to_u)

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError, match="Unknown unit"):
            convert_quantity(1.0, "cubit", "foot")

    def test_fractional_inch_withdrawal(self):
        """The core use case: buy 100 ft, sell 18 inches = 1.5 ft deducted."""
        stock_ft = 100.0
        requested_inches = 18.0
        deducted_ft = convert_quantity(requested_inches, "inch", "foot")
        assert deducted_ft == pytest.approx(1.5)
        remaining = stock_ft - deducted_ft
        assert remaining == pytest.approx(98.5)

    def test_are_compatible(self):
        assert are_compatible("foot", "inch") is True
        assert are_compatible("gallon", "pint") is True
        assert are_compatible("foot", "gallon") is False
        assert are_compatible("each", "box") is True


# ── 2. Unit family completeness ──────────────────────────────────────────────

class TestUnitFamilyCompleteness:
    """Every allowed base unit must belong to exactly one family."""

    def test_every_allowed_unit_has_a_family(self):
        all_family_units = {u for fam in UNIT_FAMILIES.values() for u in fam}
        orphans = ALLOWED_BASE_UNITS - all_family_units
        assert not orphans, f"Units in ALLOWED_BASE_UNITS but no family: {orphans}"

    def test_no_unit_in_multiple_families(self):
        seen: dict[str, str] = {}
        for family, units in UNIT_FAMILIES.items():
            for unit in units:
                assert unit not in seen, (
                    f"'{unit}' in both '{seen[unit]}' and '{family}'"
                )
                seen[unit] = family

    def test_family_for_unit_returns_correct_family(self):
        for family, units in UNIT_FAMILIES.items():
            for unit in units:
                assert family_for_unit(unit) == family

    def test_conversion_factors_are_positive(self):
        for family, units in UNIT_FAMILIES.items():
            for unit, factor in units.items():
                assert factor > 0, f"{unit} in {family} has non-positive factor {factor}"


# ── 3. Quantity type contracts ────────────────────────────────────────────────

class TestQuantityTypeContracts:
    """Domain models must accept and preserve float quantities — never truncate to int."""

    def test_product_create_accepts_float_quantity(self):
        p = ProductCreate(name="Wire", quantity=2.5, price=10.0, department_id="d1")
        assert isinstance(p.quantity, float)
        assert p.quantity == 2.5

    def test_product_update_accepts_float_quantity(self):
        p = ProductUpdate(quantity=3.75)
        assert isinstance(p.quantity, float)
        assert p.quantity == 3.75

    def test_product_accepts_float_quantity(self):
        p = Product(
            name="Wire", quantity=10.5, price=1.0,
            department_id="d1", department_name="HW", sku="HW-001",
        )
        assert isinstance(p.quantity, float)
        assert p.quantity == 10.5

    def test_line_item_quantity_is_float(self):
        li = LineItem(product_id="p1", sku="S", name="X", quantity=3.5)
        assert isinstance(li.quantity, float)
        assert li.quantity == 3.5

    def test_line_item_int_quantity_coerced_to_float(self):
        li = LineItem(product_id="p1", sku="S", name="X", quantity=3)
        assert isinstance(li.quantity, float)

    def test_stock_decrement_quantity_is_float(self):
        sd = StockDecrement(product_id="p1", sku="S", name="X", quantity=1.75)
        assert isinstance(sd.quantity, float)
        assert sd.quantity == 1.75

    def test_stock_transaction_quantities_are_float(self):
        tx = StockTransaction(
            product_id="p1", sku="S", product_name="X",
            quantity_delta=-2.5, quantity_before=10.0, quantity_after=7.5,
            transaction_type=StockTransactionType.WITHDRAWAL,
            user_id="u1",
        )
        assert isinstance(tx.quantity_delta, float)
        assert isinstance(tx.quantity_before, float)
        assert isinstance(tx.quantity_after, float)

    def test_stock_transaction_arithmetic_consistency(self):
        """quantity_after must equal quantity_before + quantity_delta."""
        tx = StockTransaction(
            product_id="p1", sku="S", product_name="X",
            quantity_delta=-2.5, quantity_before=10.0, quantity_after=7.5,
            transaction_type=StockTransactionType.WITHDRAWAL,
            user_id="u1",
        )
        assert tx.quantity_after == pytest.approx(tx.quantity_before + tx.quantity_delta)


# ── 4. LineItem computed fields ───────────────────────────────────────────────

class TestLineItemArithmetic:

    def test_subtotal_with_fractional_quantity(self):
        li = LineItem(product_id="p1", sku="S", name="Pipe", quantity=2.5, unit_price=4.0)
        assert li.subtotal == 10.0

    def test_cost_total_with_fractional_quantity(self):
        li = LineItem(product_id="p1", sku="S", name="Pipe", quantity=2.5, cost=3.0)
        assert li.cost_total == 7.5

    def test_unit_defaults_to_each(self):
        li = LineItem(product_id="p1", sku="S", name="X", quantity=1)
        assert li.unit == "each"

    def test_unit_preserved(self):
        li = LineItem(product_id="p1", sku="S", name="X", quantity=1, unit="foot")
        assert li.unit == "foot"

    def test_price_alias(self):
        """LineItem accepts 'price' as alias for 'unit_price'."""
        li = LineItem(product_id="p1", sku="S", name="X", quantity=1, price=5.0)
        assert li.unit_price == 5.0


# ── 5. Stock decrement invariants ─────────────────────────────────────────────

class TestStockDecrementInvariants:

    def test_default_unit_is_each(self):
        sd = StockDecrement(product_id="p1", sku="S", name="X", quantity=1)
        assert sd.unit == "each"

    def test_custom_unit_preserved(self):
        sd = StockDecrement(product_id="p1", sku="S", name="X", quantity=5, unit="inch")
        assert sd.unit == "inch"


# ── 6. Error model contracts ─────────────────────────────────────────────────

class TestErrorContracts:

    def test_insufficient_stock_stores_float_quantities(self):
        err = InsufficientStockError(sku="W-001", requested=2.5, available=1.0)
        assert isinstance(err.requested, float)
        assert isinstance(err.available, float)
        assert "2.5" in str(err)

    def test_negative_stock_stores_float_quantities(self):
        err = NegativeStockError(product_id="p1", current=3.0, delta=-5.0)
        assert isinstance(err.current, float)
        assert isinstance(err.delta, float)


# ── 7. Withdrawal model invariants ───────────────────────────────────────────

class TestWithdrawalInvariants:

    def test_compute_totals_with_fractional_items(self):
        items = [
            WithdrawalItem(product_id="p1", sku="S1", name="A", quantity=2.5, unit_price=4.0, cost=2.0),
            WithdrawalItem(product_id="p2", sku="S2", name="B", quantity=0.75, unit_price=10.0, cost=6.0),
        ]
        w = MaterialWithdrawal(
            items=items, job_id="J", service_address="X",
            subtotal=0, tax=0, total=0, cost_total=0,
            contractor_id="c1", processed_by_id="u1",
        )
        w.compute_totals(tax_rate=0.10)
        expected_subtotal = 2.5 * 4.0 + 0.75 * 10.0  # 10.0 + 7.5 = 17.5
        assert w.subtotal == pytest.approx(expected_subtotal)
        assert w.tax == pytest.approx(1.75)
        assert w.total == pytest.approx(19.25)
        assert w.cost_total == pytest.approx(2.5 * 2.0 + 0.75 * 6.0)
