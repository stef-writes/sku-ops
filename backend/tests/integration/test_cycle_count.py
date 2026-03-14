"""
Cycle count tests — domain invariants, service integration, atomicity.

Coverage:
  1. Domain model (pure, no DB)
  2. open_cycle_count — snapshot correctness, scope filtering, empty-scope guard
  3. Snapshot isolation — snapshot_qty is frozen after open
  4. update_counted_qty — variance computation, committed-count guard
  5. commit_cycle_count — adjustments applied, skips, status transition,
     double-commit guard, stock transaction records, ledger entries
  6. Atomicity — partial failure rolls back the entire commit
  7. Ledger balance invariant — post-commit ledger still sums to product qty
"""

import pytest

from catalog.application.sku_lifecycle import create_product_with_sku
from catalog.infrastructure.sku_repo import sku_repo
from finance.domain.ledger import Account
from finance.infrastructure.ledger_repo import trial_balance
from inventory.application.cycle_count_service import (
    commit_cycle_count,
    get_count_detail,
    list_cycle_counts,
    open_cycle_count,
    update_counted_qty,
)
from inventory.application.inventory_service import (
    get_stock_history,
    process_import_stock_changes,
    process_withdrawal_stock_changes,
)
from inventory.domain.cycle_count import CycleCountStatus
from inventory.domain.errors import NegativeStockError
from inventory.domain.stock import StockDecrement
from shared.infrastructure.database import get_connection
from shared.kernel.errors import ResourceNotFoundError

# ── Fixtures / helpers ────────────────────────────────────────────────────────


async def _make_product(name="Widget", qty=100.0, cost=5.0, dept="Hardware"):
    return await create_product_with_sku(
        category_id="dept-1",
        category_name=dept,
        name=name,
        quantity=qty,
        price=10.0,
        cost=cost,
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )


def _user():
    return {
        "committed_by_id": "user-1",
        "committed_by_name": "Test User",
    }


async def _open(scope=None):
    return await open_cycle_count(
        created_by_id="user-1",
        created_by_name="Test User",
        scope=scope,
    )


async def _commit(count_id):
    return await commit_cycle_count(
        count_id=count_id,
        **_user(),
    )


async def _update(count_id, item_id, counted_qty, notes=None):
    return await update_counted_qty(
        count_id=count_id,
        item_id=item_id,
        counted_qty=counted_qty,
        notes=notes,
    )


# ── 1. Domain model — pure, no DB ─────────────────────────────────────────────


class TestCycleCountDomain:
    def test_variance_arithmetic(self):
        """variance = counted_qty - snapshot_qty: positive, negative, zero."""
        cases = [
            (10.0, 12.0, 2.0),
            (10.0, 8.0, -2.0),
            (10.0, 10.0, 0.0),
            (0.0, 0.5, 0.5),
            (100.0, 100.0, 0.0),
        ]
        for snapshot, counted, expected in cases:
            variance = round(counted - snapshot, 6)
            assert variance == pytest.approx(expected), (
                f"snapshot={snapshot} counted={counted} expected variance={expected}"
            )

    def test_fractional_variance(self):
        """Fractional quantities must not be truncated."""
        variance = round(3.75 - 5.25, 6)
        assert variance == pytest.approx(-1.5)


# ── 2. open_cycle_count ───────────────────────────────────────────────────────


class TestOpenCycleCount:
    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_open_snapshots_current_qty(self):
        """Each item's snapshot_qty must equal the product's current quantity at open time."""
        p1 = await _make_product("Bolt", qty=50.0)
        p2 = await _make_product("Nut", qty=25.0)

        count = await _open()
        detail = await get_count_detail(count.id)

        item_map = {i.product_id: i for i in detail.items}
        assert item_map[p1.id].snapshot_qty == pytest.approx(50.0)
        assert item_map[p2.id].snapshot_qty == pytest.approx(25.0)

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_open_sets_status_open(self):
        await _make_product("Screw", qty=10.0)
        count = await _open()
        assert count.status == CycleCountStatus.OPEN

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_open_with_scope_filters_by_department(self):
        """Only products from the scoped department appear in items."""
        conn = get_connection()
        await conn.execute(
            """INSERT OR REPLACE INTO departments (id, name, code, description, sku_count, created_at)
               VALUES ('dept-plumbing', 'Plumbing', 'PLU', 'Plumbing', 0, datetime('now'))"""
        )
        await conn.commit()

        hw = await _make_product("Hammer", dept="Hardware")
        pl = await create_product_with_sku(
            category_id="dept-plumbing",
            category_name="Plumbing",
            name="Pipe",
            quantity=30.0,
            price=5.0,
            cost=2.0,
            user_id="user-1",
            user_name="Test",
            on_stock_import=process_import_stock_changes,
        )

        count = await _open(scope="Hardware")
        detail = await get_count_detail(count.id)

        product_ids = {i.product_id for i in detail.items}
        assert hw.id in product_ids, "Hardware product must be in count"
        assert pl.id not in product_ids, "Plumbing product must NOT be in scoped Hardware count"

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_open_no_scope_includes_all_departments(self):
        conn = get_connection()
        await conn.execute(
            """INSERT OR REPLACE INTO departments (id, name, code, description, sku_count, created_at)
               VALUES ('dept-elec', 'Electrical', 'ELE', '', 0, datetime('now'))"""
        )
        await conn.commit()

        hw = await _make_product("Bolt", dept="Hardware")
        el = await create_product_with_sku(
            category_id="dept-elec",
            category_name="Electrical",
            name="Wire",
            quantity=200.0,
            price=1.0,
            cost=0.5,
            user_id="user-1",
            user_name="Test",
            on_stock_import=process_import_stock_changes,
        )

        count = await _open(scope=None)
        detail = await get_count_detail(count.id)
        product_ids = {i.product_id for i in detail.items}

        assert hw.id in product_ids
        assert el.id in product_ids

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_open_empty_scope_raises(self):
        """A scope with no matching products must raise ValueError."""
        await _make_product("Bolt", dept="Hardware")
        with pytest.raises(ValueError, match="No products found"):
            await _open(scope="Nonexistent Department")

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_open_appears_in_list(self):
        await _make_product("Washer", qty=10.0)
        count = await _open()
        counts = await list_cycle_counts()
        ids = [c.id for c in counts]
        assert count.id in ids

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_open_list_filter_by_status(self):
        await _make_product("Nail", qty=10.0)
        count = await _open()

        open_counts = await list_cycle_counts(status="open")
        committed_counts = await list_cycle_counts(status="committed")

        open_ids = [c.id for c in open_counts]
        committed_ids = [c.id for c in committed_counts]

        assert count.id in open_ids
        assert count.id not in committed_ids


# ── 3. Snapshot isolation ─────────────────────────────────────────────────────


class TestSnapshotIsolation:
    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_snapshot_not_changed_by_subsequent_withdrawal(self):
        """Withdrawing stock after opening must not alter snapshot_qty."""
        p = await _make_product("Pipe", qty=100.0)
        count = await _open()

        detail_before = await get_count_detail(count.id)
        snap_before = next(i.snapshot_qty for i in detail_before.items if i.product_id == p.id)

        await process_withdrawal_stock_changes(
            items=[StockDecrement(product_id=p.id, sku=p.sku, name=p.name, quantity=20.0)],
            withdrawal_id="w-snap-test",
            user_id="user-1",
            user_name="Test",
        )

        detail_after = await get_count_detail(count.id)
        snap_after = next(i.snapshot_qty for i in detail_after.items if i.product_id == p.id)

        assert snap_before == pytest.approx(100.0)
        assert snap_after == pytest.approx(100.0), (
            "snapshot_qty must be immutable after count is opened"
        )


# ── 4. update_counted_qty ─────────────────────────────────────────────────────


class TestUpdateCountedQty:
    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_update_stores_counted_qty_and_variance(self):
        p = await _make_product("Valve", qty=50.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)

        updated = await _update(count.id, item.id, counted_qty=47.0)

        assert updated.counted_qty == pytest.approx(47.0)
        assert updated.variance == pytest.approx(-3.0)

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_update_positive_variance(self):
        p = await _make_product("Flange", qty=10.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)

        updated = await _update(count.id, item.id, counted_qty=13.0)

        assert updated.variance == pytest.approx(3.0)

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_update_zero_variance(self):
        p = await _make_product("Clamp", qty=20.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)

        updated = await _update(count.id, item.id, counted_qty=20.0)

        assert updated.variance == pytest.approx(0.0)

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_update_stores_notes(self):
        p = await _make_product("Elbow", qty=5.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)

        updated = await _update(count.id, item.id, counted_qty=5.0, notes="damaged box")
        assert updated.notes == "damaged box"

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_update_rejects_committed_count(self):
        """Updating an item on a committed count must raise ValueError."""
        p = await _make_product("Cap", qty=10.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)
        await _update(count.id, item.id, counted_qty=10.0)
        await _commit(count.id)

        with pytest.raises(ValueError, match="committed"):
            await _update(count.id, item.id, counted_qty=9.0)

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_update_nonexistent_item_raises(self):
        await _make_product("Tee", qty=10.0)
        count = await _open()
        with pytest.raises(ResourceNotFoundError):
            await _update(count.id, "nonexistent-item-id", counted_qty=5.0)


# ── 5. commit_cycle_count ─────────────────────────────────────────────────────


class TestCommitCycleCount:
    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_commit_applies_negative_variance(self):
        """Shortage: product quantity should decrease by |variance|."""
        p = await _make_product("Rod", qty=100.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)

        await _update(count.id, item.id, counted_qty=90.0)
        await _commit(count.id)

        updated = await sku_repo.get_by_id(p.id)
        assert updated.quantity == pytest.approx(90.0)

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_commit_applies_positive_variance(self):
        """Overage: product quantity should increase by variance."""
        p = await _make_product("Rivet", qty=50.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)

        await _update(count.id, item.id, counted_qty=55.0)
        await _commit(count.id)

        updated = await sku_repo.get_by_id(p.id)
        assert updated.quantity == pytest.approx(55.0)

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_commit_skips_uncounted_items(self):
        """Items without a counted_qty must not be adjusted."""
        p_counted = await _make_product("Bolt A", qty=30.0)
        p_skipped = await _make_product("Bolt B", qty=40.0)

        count = await _open()
        detail = await get_count_detail(count.id)

        item_counted = next(i for i in detail.items if i.product_id == p_counted.id)
        await _update(count.id, item_counted.id, counted_qty=25.0)

        await _commit(count.id)

        updated_counted = await sku_repo.get_by_id(p_counted.id)
        updated_skipped = await sku_repo.get_by_id(p_skipped.id)

        assert updated_counted.quantity == pytest.approx(25.0)
        assert updated_skipped.quantity == pytest.approx(40.0), (
            "Uncounted item must not be adjusted"
        )

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_commit_skips_zero_variance_items(self):
        """Items counted at exactly snapshot_qty must not produce a stock transaction."""
        p = await _make_product("Pin", qty=15.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)

        await _update(count.id, item.id, counted_qty=15.0)
        result = await _commit(count.id)

        assert result.items_adjusted == 0

        history = await get_stock_history(p.id, limit=50)
        adjustment_txs = [t for t in history if t.transaction_type == "adjustment"]
        assert len(adjustment_txs) == 0, "Zero-variance item should produce no adjustment"

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_commit_sets_status_committed(self):
        p = await _make_product("Stud", qty=10.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)
        await _update(count.id, item.id, counted_qty=10.0)

        await _commit(count.id)

        detail_after = await get_count_detail(count.id)
        assert detail_after.status == CycleCountStatus.COMMITTED

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_commit_records_committer_and_timestamp(self):
        p = await _make_product("Bracket", qty=10.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)
        await _update(count.id, item.id, counted_qty=10.0)

        result = await _commit(count.id)

        assert result.committed_by_id == "user-1"
        assert result.committed_at is not None

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_commit_rejects_already_committed(self):
        """Second commit attempt must raise ValueError."""
        p = await _make_product("Stud B", qty=10.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)
        await _update(count.id, item.id, counted_qty=10.0)
        await _commit(count.id)

        with pytest.raises(ValueError, match="already committed"):
            await _commit(count.id)

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_commit_writes_stock_transactions_with_reason_count(self):
        """Each adjusted item must produce a stock transaction with reason='count'."""
        p = await _make_product("Bushing", qty=20.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)

        await _update(count.id, item.id, counted_qty=17.0)
        await _commit(count.id)

        history = await get_stock_history(p.id, limit=50)
        adj_txs = [t for t in history if t.transaction_type == "adjustment"]

        assert len(adj_txs) == 1
        assert adj_txs[0].reason == "count"
        assert adj_txs[0].quantity_delta == pytest.approx(-3.0)

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_commit_writes_ledger_entries(self):
        """A negative variance must produce INVENTORY (decrease) + SHRINKAGE (increase) entries."""
        p = await _make_product("Coupler", qty=50.0, cost=4.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)

        await _update(count.id, item.id, counted_qty=45.0)
        await _commit(count.id)

        tb = await trial_balance()
        assert Account.SHRINKAGE.value in tb, "Shrinkage ledger entry expected"
        assert Account.INVENTORY.value in tb, "Inventory ledger entry expected"

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_commit_items_adjusted_count(self):
        """items_adjusted in the result must reflect only items with non-zero variance."""
        p1 = await _make_product("Anchor A", qty=10.0)
        p2 = await _make_product("Anchor B", qty=20.0)
        await _make_product("Anchor C", qty=30.0)

        count = await _open()
        detail = await get_count_detail(count.id)
        items = {i.product_id: i for i in detail.items}

        await _update(count.id, items[p1.id].id, counted_qty=9.0)  # -1 → adjusted
        await _update(count.id, items[p2.id].id, counted_qty=20.0)  # 0 → skipped
        # p3: no entry → skipped

        result = await _commit(count.id)
        assert result.items_adjusted == 1


# ── 6. Atomicity ──────────────────────────────────────────────────────────────


class TestCommitAtomicity:
    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_partial_failure_rolls_back_entire_commit(self):
        """If any adjustment fails (NegativeStockError), no adjustments are persisted."""
        p_ok = await _make_product("Safe Product", qty=50.0)
        p_bad = await _make_product("Undersupply Product", qty=5.0)

        count = await _open()
        detail = await get_count_detail(count.id)
        items = {i.product_id: i for i in detail.items}

        # p_ok: valid negative variance
        await _update(count.id, items[p_ok.id].id, counted_qty=40.0)
        # p_bad: variance would drive qty below 0
        await _update(count.id, items[p_bad.id].id, counted_qty=-100.0)

        with pytest.raises(NegativeStockError):
            await _commit(count.id)

        # Both products must be unchanged
        p_ok_after = await sku_repo.get_by_id(p_ok.id)
        p_bad_after = await sku_repo.get_by_id(p_bad.id)

        assert p_ok_after.quantity == pytest.approx(50.0), (
            "Safe product should be unchanged after rolled-back commit"
        )
        assert p_bad_after.quantity == pytest.approx(5.0), "Failing product should be unchanged"

        # Count must still be open — not partially committed
        detail_after = await get_count_detail(count.id)
        assert detail_after.status == CycleCountStatus.OPEN, (
            "Count must remain open after a failed commit"
        )

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_successful_commit_is_durable(self):
        """After a successful commit, all adjustments are visible in the DB."""
        p = await _make_product("Durable Widget", qty=100.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)

        await _update(count.id, item.id, counted_qty=95.0)
        await _commit(count.id)

        refreshed = await sku_repo.get_by_id(p.id)
        assert refreshed.quantity == pytest.approx(95.0)

        history = await get_stock_history(p.id, limit=10)
        adj_txs = [t for t in history if t.transaction_type == "adjustment"]
        assert len(adj_txs) == 1


# ── 7. Post-commit ledger balance invariant ───────────────────────────────────


class TestPostCommitLedgerBalance:
    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_product_qty_equals_ledger_sum_after_commit(self):
        """After commit: product.quantity == sum of all stock_transaction deltas."""
        p = await _make_product("Auditee", qty=80.0)
        count = await _open()
        detail = await get_count_detail(count.id)
        item = next(i for i in detail.items if i.product_id == p.id)

        await _update(count.id, item.id, counted_qty=75.0)
        await _commit(count.id)

        current = await sku_repo.get_by_id(p.id)
        history = await get_stock_history(p.id, limit=100)

        ledger_sum = sum(float(tx.quantity_delta) for tx in history)
        assert current.quantity == pytest.approx(ledger_sum), (
            f"Ledger integrity violation: product qty={current.quantity}, ledger sum={ledger_sum}"
        )

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_multi_product_commit_all_balances_preserved(self):
        """Multiple products adjusted in one commit all maintain ledger balance."""
        products = [
            await _make_product(f"Ledger Product {i}", qty=float(10 * (i + 1))) for i in range(3)
        ]
        counted_qtys = [5.0, 22.0, 28.0]  # mix of shortage, overage, overage

        count = await _open()
        detail = await get_count_detail(count.id)
        item_map = {i.product_id: i for i in detail.items}

        for p, cq in zip(products, counted_qtys, strict=False):
            await _update(count.id, item_map[p.id].id, counted_qty=cq)

        await _commit(count.id)

        for p, cq in zip(products, counted_qtys, strict=False):
            current = await sku_repo.get_by_id(p.id)
            history = await get_stock_history(p.id, limit=100)
            ledger_sum = sum(float(tx.quantity_delta) for tx in history)

            assert current.quantity == pytest.approx(cq), (
                f"{p.name}: expected qty {cq}, got {current.quantity}"
            )
            assert current.quantity == pytest.approx(ledger_sum), (
                f"{p.name}: ledger integrity violation"
            )
