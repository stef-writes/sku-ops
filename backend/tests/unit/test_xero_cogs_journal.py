"""Pure unit tests for sell-unit cost normalization and COGS journal building.

Extracted from test_sell_cost_normalization.py — no DB, no network.
"""

import pytest

from finance.adapters.xero_adapter import XeroAdapter
from shared.kernel.units import cost_per_sell_unit
from tests.helpers.xero import make_settings

# ── cost_per_sell_unit ────────────────────────────────────────────────────────


class TestCostPerSellUnit:
    def test_same_unit_same_pack(self):
        assert cost_per_sell_unit(5.0, "each", "each", 1) == 5.0

    def test_base_inch_sell_foot(self):
        result = cost_per_sell_unit(1.0, "inch", "foot", 1)
        assert result == 12.0

    def test_base_foot_sell_yard(self):
        result = cost_per_sell_unit(3.0, "foot", "yard", 1)
        assert result == 9.0

    def test_pack_qty_multiplier(self):
        result = cost_per_sell_unit(2.0, "each", "each", 12)
        assert result == 24.0

    def test_incompatible_units_returns_base(self):
        result = cost_per_sell_unit(5.0, "foot", "gallon", 1)
        assert result == 5.0

    def test_zero_pack_qty_treated_as_one(self):
        assert cost_per_sell_unit(10.0, "each", "each", 0) == 10.0

    def test_base_pint_sell_gallon(self):
        result = cost_per_sell_unit(1.0, "pint", "gallon", 1)
        assert result == 8.0

    def test_combined_unit_and_pack(self):
        result = cost_per_sell_unit(0.10, "inch", "foot", 3)
        assert result == pytest.approx(3.6, abs=1e-4)


# ── COGS journal line building ────────────────────────────────────────────────


def _invoice_with_sell_cost() -> dict:
    return {
        "id": "inv-1",
        "invoice_number": "INV-00042",
        "xero_invoice_id": "xero-abc",
        "line_items": [
            {
                "description": "Wire",
                "quantity": 24,
                "unit_price": 0.20,
                "amount": 4.80,
                "cost": 0.08,
                "sell_cost": 0.96,
                "unit": "inch",
                "sell_uom": "foot",
                "product_id": "prod-1",
            },
            {
                "description": "Conduit",
                "quantity": 5,
                "unit_price": 10.0,
                "amount": 50.0,
                "cost": 4.0,
                "sell_cost": 4.0,
                "unit": "each",
                "sell_uom": "each",
                "product_id": "prod-2",
            },
        ],
    }


def _invoice_legacy_no_sell_cost() -> dict:
    """Older invoice with only cost (no sell_cost)."""
    return {
        "id": "inv-2",
        "invoice_number": "INV-00043",
        "xero_invoice_id": "xero-def",
        "line_items": [
            {
                "description": "Lumber",
                "quantity": 10,
                "unit_price": 10.0,
                "amount": 100.0,
                "cost": 6.0,
                "product_id": "prod-3",
            },
        ],
    }


class TestBuildCogsJournalLines:
    def setup_method(self):
        self.adapter = XeroAdapter()
        self.settings = make_settings()

    def test_returns_two_lines_per_item(self):
        invoice = _invoice_with_sell_cost()
        lines, _total = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-abc")
        assert len(lines) == 4

    def test_cost_total_uses_sell_cost(self):
        invoice = _invoice_with_sell_cost()
        _, total = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-abc")
        assert total == pytest.approx(43.04, abs=0.01)

    def test_cogs_lines_use_correct_account(self):
        invoice = _invoice_with_sell_cost()
        lines, _ = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-abc")
        cogs_lines = [l for l in lines if l["LineAmount"] > 0]
        assert all(l["AccountCode"] == "500" for l in cogs_lines)

    def test_inventory_lines_use_correct_account(self):
        invoice = _invoice_with_sell_cost()
        lines, _ = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-abc")
        inv_lines = [l for l in lines if l["LineAmount"] < 0]
        assert all(l["AccountCode"] == "630" for l in inv_lines)

    def test_journal_is_balanced(self):
        """Sum of all journal line amounts must be zero."""
        invoice = _invoice_with_sell_cost()
        lines, _ = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-abc")
        total = sum(l["LineAmount"] for l in lines)
        assert total == pytest.approx(0.0, abs=0.01)

    def test_per_line_descriptions_include_item_name(self):
        invoice = _invoice_with_sell_cost()
        lines, _ = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-abc")
        descriptions = [l["Description"] for l in lines]
        assert any("Wire" in d for d in descriptions)
        assert any("Conduit" in d for d in descriptions)

    def test_per_line_descriptions_include_invoice_number(self):
        invoice = _invoice_with_sell_cost()
        lines, _ = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-abc")
        assert all("INV-00042" in l["Description"] for l in lines)

    def test_falls_back_to_cost_when_sell_cost_missing(self):
        """Legacy invoices without sell_cost should still work using cost."""
        invoice = _invoice_legacy_no_sell_cost()
        lines, total = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-def")
        assert len(lines) == 2
        assert total == pytest.approx(60.0, abs=0.01)

    def test_tracking_applied_per_line_when_configured(self):
        settings = make_settings(xero_tracking_category_id="cat-123")
        invoice = _invoice_with_sell_cost()
        lines, _ = self.adapter._build_cogs_journal_lines(
            invoice, settings, "xero-abc", first_job_id="JOB-42"
        )
        assert all("Tracking" in l for l in lines)
        assert all(l["Tracking"][0]["TrackingCategoryID"] == "cat-123" for l in lines)

    def test_no_tracking_when_no_category_configured(self):
        invoice = _invoice_with_sell_cost()
        lines, _ = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-abc")
        assert all("Tracking" not in l for l in lines)

    def test_zero_cost_lines_excluded(self):
        """Line items with zero sell_cost (and zero cost) must not appear in the journal."""
        invoice = {
            "id": "inv-3",
            "invoice_number": "INV-00044",
            "xero_invoice_id": "xero-ghi",
            "line_items": [
                {
                    "description": "Free Sample",
                    "quantity": 1,
                    "unit_price": 0.0,
                    "amount": 0.0,
                    "cost": 0.0,
                    "sell_cost": 0.0,
                },
                {
                    "description": "Paid Item",
                    "quantity": 2,
                    "unit_price": 5.0,
                    "amount": 10.0,
                    "cost": 3.0,
                    "sell_cost": 3.0,
                },
            ],
        }
        lines, total = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-ghi")
        assert len(lines) == 2
        assert total == pytest.approx(6.0, abs=0.01)
