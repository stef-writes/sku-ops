"""Tests for sell-unit cost normalization across the full stack.

Covers:
  1. cost_per_sell_unit() pure function
  2. Withdrawal service computes sell_cost and stores it on LineItem
  3. Ledger COGS/INVENTORY entries carry quantity, unit, unit_cost using sell_cost
  4. Invoice line items carry unit + sell_cost copied from withdrawal items
  5. Xero adapter builds per-line itemized COGS journal (not one aggregate entry)
  6. Xero adapter uses sell_cost over cost when available
"""
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from catalog.domain.units import cost_per_sell_unit
from finance.adapters.xero_adapter import XeroAdapter
from identity.domain.org_settings import OrgSettings

# ── 1. cost_per_sell_unit ─────────────────────────────────────────────────────

class TestCostPerSellUnit:
    def test_same_unit_same_pack(self):
        assert cost_per_sell_unit(5.0, "each", "each", 1) == 5.0

    def test_base_inch_sell_foot(self):
        # 1 foot = 12 inches; cost per inch = $1 → cost per foot = $12
        result = cost_per_sell_unit(1.0, "inch", "foot", 1)
        assert result == 12.0

    def test_base_foot_sell_yard(self):
        # 1 yard = 3 feet; cost per foot = $3 → cost per yard = $9
        result = cost_per_sell_unit(3.0, "foot", "yard", 1)
        assert result == 9.0

    def test_pack_qty_multiplier(self):
        # cost per each = $2, sell pack of 12 → cost per pack = $24
        result = cost_per_sell_unit(2.0, "each", "each", 12)
        assert result == 24.0

    def test_incompatible_units_returns_base(self):
        # foot vs gallon — incompatible; returns base cost × pack_qty unchanged
        result = cost_per_sell_unit(5.0, "foot", "gallon", 1)
        assert result == 5.0

    def test_zero_pack_qty_treated_as_one(self):
        assert cost_per_sell_unit(10.0, "each", "each", 0) == 10.0

    def test_base_pint_sell_gallon(self):
        # 1 gallon = 8 pints; cost per pint = $1 → cost per gallon = $8
        result = cost_per_sell_unit(1.0, "pint", "gallon", 1)
        assert result == 8.0

    def test_combined_unit_and_pack(self):
        # base=inch, sell=foot, pack=3 → 1 sell-unit = 3 feet = 36 inches
        # cost per inch = $0.10 → cost per (3 feet) = 0.10 × 36 = $3.60
        result = cost_per_sell_unit(0.10, "inch", "foot", 3)
        assert result == pytest.approx(3.6, abs=1e-4)


# ── 2. Withdrawal service computes sell_cost ──────────────────────────────────

@pytest.mark.asyncio
async def test_withdrawal_sell_cost_same_unit(db):
    """When base_unit == sell_uom and pack_qty == 1, sell_cost == cost."""
    from catalog.application.product_lifecycle import create_product
    from catalog.application.queries import list_products
    from inventory.application.inventory_service import (
        process_import_stock_changes,
        process_withdrawal_stock_changes,
    )
    from kernel.types import CurrentUser
    from operations.application.withdrawal_service import create_withdrawal
    from operations.domain.withdrawal import MaterialWithdrawalCreate, WithdrawalItem

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
        items=[WithdrawalItem(
            product_id=product.id, sku=product.sku, name=product.name,
            quantity=5, price=2.0, cost=1.0,
        )],
        job_id="JOB-001", service_address="123 Main",
    )
    user = CurrentUser(id="user-1", email="t@t.com", name="T", role="admin")
    contractor = {"id": "contractor-1", "name": "C"}

    result = await create_withdrawal(
        data, contractor, user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
    )

    items = result.get("items") or []
    assert len(items) == 1
    assert items[0].get("sell_cost") == pytest.approx(1.0)
    assert items[0].get("sell_uom") == "each"


@pytest.mark.asyncio
async def test_withdrawal_sell_cost_unit_conversion(db):
    """When base_unit=inch and sell_uom=foot, sell_cost is 12× base cost."""
    from catalog.application.product_lifecycle import create_product
    from catalog.application.queries import list_products
    from inventory.application.inventory_service import (
        process_import_stock_changes,
        process_withdrawal_stock_changes,
    )
    from kernel.types import CurrentUser
    from operations.application.withdrawal_service import create_withdrawal
    from operations.domain.withdrawal import MaterialWithdrawalCreate, WithdrawalItem

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
        items=[WithdrawalItem(
            product_id=product.id, sku=product.sku, name=product.name,
            quantity=10, price=0.12, unit="inch",
        )],
        job_id="JOB-002", service_address="456 Oak",
    )
    user = CurrentUser(id="user-1", email="t@t.com", name="T", role="admin")
    contractor = {"id": "contractor-1", "name": "C"}

    result = await create_withdrawal(
        data, contractor, user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
    )

    items = result.get("items") or []
    assert len(items) == 1
    # sell_uom=foot, base=inch: 1 foot = 12 inches, cost per foot = 0.05 * 12 = 0.60
    assert items[0].get("sell_uom") == "foot"
    assert items[0].get("sell_cost") == pytest.approx(0.60, abs=1e-4)


# ── 3. Ledger entries carry quantity, unit, unit_cost ─────────────────────────

@pytest.mark.asyncio
async def test_ledger_cogs_entry_has_quantity_and_unit_cost(db):
    """COGS ledger entry must carry qty, sell_uom unit, and sell_cost as unit_cost."""
    from catalog.application.product_lifecycle import create_product
    from catalog.application.queries import list_products
    from inventory.application.inventory_service import (
        process_import_stock_changes,
        process_withdrawal_stock_changes,
    )
    from kernel.types import CurrentUser
    from operations.application.withdrawal_service import create_withdrawal
    from operations.domain.withdrawal import MaterialWithdrawalCreate, WithdrawalItem
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
        items=[WithdrawalItem(
            product_id=product.id, sku=product.sku, name=product.name,
            quantity=24, price=0.20, unit="inch",
        )],
        job_id="JOB-003", service_address="789 Elm",
    )
    user = CurrentUser(id="user-1", email="t@t.com", name="T", role="admin")
    contractor = {"id": "contractor-1", "name": "C"}

    result = await create_withdrawal(
        data, contractor, user,
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
    # qty=24 inches, sell_uom=foot → sell_cost per foot = 0.08 * 12 = 0.96
    # amount = sell_cost * qty = 0.96 * 24 = 23.04
    assert row["quantity"] == pytest.approx(24.0)
    assert row["unit"] == "foot"
    assert row["unit_cost"] == pytest.approx(0.96, abs=1e-4)
    assert row["amount"] == pytest.approx(23.04, abs=0.01)


@pytest.mark.asyncio
async def test_ledger_revenue_entry_has_quantity_and_unit_cost(db):
    """REVENUE entry carries withdrawal qty/unit and unit_price as unit_cost."""
    from catalog.application.product_lifecycle import create_product
    from catalog.application.queries import list_products
    from inventory.application.inventory_service import (
        process_import_stock_changes,
        process_withdrawal_stock_changes,
    )
    from kernel.types import CurrentUser
    from operations.application.withdrawal_service import create_withdrawal
    from operations.domain.withdrawal import MaterialWithdrawalCreate, WithdrawalItem
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
        items=[WithdrawalItem(
            product_id=product.id, sku=product.sku, name=product.name,
            quantity=3, price=5.0,
        )],
        job_id="JOB-004", service_address="1 A St",
    )
    user = CurrentUser(id="user-1", email="t@t.com", name="T", role="admin")
    contractor = {"id": "contractor-1", "name": "C"}

    result = await create_withdrawal(
        data, contractor, user,
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


# ── 4. Invoice line items carry unit + sell_cost ──────────────────────────────

@pytest.mark.asyncio
async def test_invoice_line_items_carry_sell_cost(db):
    """Invoice line items built from withdrawals must copy unit and sell_cost."""
    from catalog.application.product_lifecycle import create_product
    from catalog.application.queries import list_products
    from finance.application.invoice_service import (
        create_invoice_from_withdrawals,
        get_invoice,
    )
    from inventory.application.inventory_service import (
        process_import_stock_changes,
        process_withdrawal_stock_changes,
    )
    from kernel.types import CurrentUser
    from operations.application.withdrawal_service import create_withdrawal
    from operations.domain.withdrawal import MaterialWithdrawalCreate, WithdrawalItem

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
        items=[WithdrawalItem(
            product_id=product.id, sku=product.sku, name=product.name,
            quantity=36, price=0.15, unit="inch",
        )],
        job_id="JOB-005", service_address="2 B St",
    )
    user = CurrentUser(id="user-1", email="t@t.com", name="T", role="admin")
    contractor = {"id": "contractor-1", "name": "C", "billing_entity": "ACME Inc"}

    withdrawal = await create_withdrawal(
        data, contractor, user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
    )

    inv = await create_invoice_from_withdrawals(
        [withdrawal["id"]], organization_id="default"
    )
    full_inv = await get_invoice(inv["id"], "default")

    line_items = full_inv.get("line_items", [])
    assert len(line_items) == 1
    li = line_items[0]
    # sell_cost per foot = 0.06 * 12 = 0.72
    assert li.get("sell_cost") == pytest.approx(0.72, abs=1e-4)
    assert li.get("unit") == "inch"  # unit is the withdrawal unit


# ── 5 & 6. Xero adapter: per-line COGS journal ────────────────────────────────

def _settings(**overrides) -> OrgSettings:
    base = dict(
        organization_id="org-1",
        xero_access_token="tok-valid",
        xero_refresh_token="refresh-valid",
        xero_tenant_id="tenant-abc",
        xero_token_expiry=(
            datetime.now(UTC) + timedelta(hours=1)
        ).isoformat(),
        xero_sales_account_code="200",
        xero_cogs_account_code="500",
        xero_inventory_account_code="630",
        xero_ap_account_code="800",
    )
    base.update(overrides)
    return OrgSettings(**base)


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
        self.settings = _settings()

    def test_returns_two_lines_per_item(self):
        invoice = _invoice_with_sell_cost()
        lines, total = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-abc")
        # 2 items × 2 lines (cogs + inventory) = 4 lines
        assert len(lines) == 4

    def test_cost_total_uses_sell_cost(self):
        invoice = _invoice_with_sell_cost()
        _, total = self.adapter._build_cogs_journal_lines(invoice, self.settings, "xero-abc")
        # Wire: 24 × 0.96 = 23.04; Conduit: 5 × 4.0 = 20.0 → total = 43.04
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
        # 10 × 6.0 = 60.0
        assert total == pytest.approx(60.0, abs=0.01)

    def test_tracking_applied_per_line_when_configured(self):
        settings = _settings(
            xero_tracking_category_id="cat-123",
        )
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
        assert len(lines) == 2  # only the paid item (cogs + inv), free sample excluded
        assert total == pytest.approx(6.0, abs=0.01)
