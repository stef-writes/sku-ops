"""
Adjustment ledger account routing tests.

Verifies that the reason field on a stock adjustment correctly routes the
financial impact to the right contra-inventory account:

  reason="damage"           → Account.DAMAGE
  reason="theft"            → Account.SHRINKAGE
  reason="correction"       → Account.SHRINKAGE
  reason="count"            → Account.SHRINKAGE
  reason=None               → Account.SHRINKAGE

Also verifies that positive deltas (found stock) reverse the correct account,
and that DAMAGE and SHRINKAGE entries never bleed into each other.
"""

from uuid import uuid4

import pytest

from finance.application.ledger_service import record_adjustment
from finance.domain.ledger import Account
from finance.infrastructure.ledger_repo import trial_balance
from shared.infrastructure.database import get_connection


async def _get_entries_for_ref(ref_id: str) -> list[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT account, amount FROM financial_ledger WHERE reference_id = ?",
        (ref_id,),
    )
    return [{"account": r[0], "amount": r[1]} for r in await cursor.fetchall()]


# ── Account routing by reason ─────────────────────────────────────────────────


class TestAdjustmentAccountRouting:
    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_damage_reason_hits_damage_account(self):
        """reason='damage' must produce an entry on Account.DAMAGE, not SHRINKAGE."""
        ref = str(uuid4())
        await record_adjustment(
            adjustment_ref_id=ref,
            product_id="p1",
            product_cost=10.0,
            quantity_delta=-3.0,
            department="Hardware",
            reason="damage",
        )
        entries = await _get_entries_for_ref(ref)
        accounts = {e["account"] for e in entries}
        assert Account.DAMAGE.value in accounts, "Expected DAMAGE account entry"
        assert Account.SHRINKAGE.value not in accounts, "Should NOT use SHRINKAGE for damage"

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    @pytest.mark.parametrize("reason", ["theft", "correction", "count", None])
    async def test_non_damage_reasons_hit_shrinkage(self, reason):
        """Any reason other than 'damage' must route to SHRINKAGE."""
        ref = str(uuid4())
        await record_adjustment(
            adjustment_ref_id=ref,
            product_id="p1",
            product_cost=10.0,
            quantity_delta=-2.0,
            department="Hardware",
            reason=reason,
        )
        entries = await _get_entries_for_ref(ref)
        accounts = {e["account"] for e in entries}
        assert Account.SHRINKAGE.value in accounts, f"Expected SHRINKAGE for reason={reason!r}"
        assert Account.DAMAGE.value not in accounts, f"Should NOT use DAMAGE for reason={reason!r}"

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_damage_account_appears_in_trial_balance(self):
        """After a damage adjustment, trial_balance must expose 'damage' as a key."""
        await record_adjustment(
            adjustment_ref_id=str(uuid4()),
            product_id="p1",
            product_cost=5.0,
            quantity_delta=-4.0,
            department="Hardware",
            reason="damage",
        )
        tb = await trial_balance()
        assert Account.DAMAGE.value in tb, "'damage' account must appear in trial balance"

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_shrinkage_account_appears_in_trial_balance(self):
        await record_adjustment(
            adjustment_ref_id=str(uuid4()),
            product_id="p1",
            product_cost=5.0,
            quantity_delta=-2.0,
            department="Hardware",
            reason="theft",
        )
        tb = await trial_balance()
        assert Account.SHRINKAGE.value in tb


# ── Double-entry correctness ──────────────────────────────────────────────────


class TestAdjustmentDoubleEntry:
    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_negative_delta_decreases_inventory_increases_contra(self):
        """Loss adjustment: INVENTORY goes down (negative), DAMAGE/SHRINKAGE goes up (positive)."""
        ref = str(uuid4())
        cost, qty = 10.0, 5.0
        await record_adjustment(
            adjustment_ref_id=ref,
            product_id="p1",
            product_cost=cost,
            quantity_delta=-qty,
            department="Hardware",
            reason="damage",
        )
        entries = await _get_entries_for_ref(ref)
        by_account = {e["account"]: e["amount"] for e in entries}
        expected = cost * qty
        assert by_account[Account.INVENTORY.value] == pytest.approx(-expected), (
            "INVENTORY should decrease on loss"
        )
        assert by_account[Account.DAMAGE.value] == pytest.approx(expected), (
            "DAMAGE should increase on loss"
        )

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_positive_delta_increases_inventory_decreases_contra(self):
        """Found-stock adjustment reverses the correct account."""
        ref = str(uuid4())
        cost, qty = 8.0, 3.0
        await record_adjustment(
            adjustment_ref_id=ref,
            product_id="p1",
            product_cost=cost,
            quantity_delta=qty,
            department="Hardware",
            reason="damage",
        )
        entries = await _get_entries_for_ref(ref)
        by_account = {e["account"]: e["amount"] for e in entries}
        expected = cost * qty
        assert by_account[Account.INVENTORY.value] == pytest.approx(expected)
        assert by_account[Account.DAMAGE.value] == pytest.approx(-expected)

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_damage_and_shrinkage_entries_independent(self):
        """Two adjustments with different reasons must not bleed into each other."""
        ref_damage = str(uuid4())
        ref_shrink = str(uuid4())

        await record_adjustment(
            adjustment_ref_id=ref_damage,
            product_id="p1",
            product_cost=10.0,
            quantity_delta=-1.0,
            department="Hardware",
            reason="damage",
        )
        await record_adjustment(
            adjustment_ref_id=ref_shrink,
            product_id="p1",
            product_cost=10.0,
            quantity_delta=-1.0,
            department="Hardware",
            reason="theft",
        )

        damage_entries = await _get_entries_for_ref(ref_damage)
        shrink_entries = await _get_entries_for_ref(ref_shrink)

        damage_accounts = {e["account"] for e in damage_entries}
        shrink_accounts = {e["account"] for e in shrink_entries}

        assert Account.DAMAGE.value in damage_accounts
        assert Account.SHRINKAGE.value not in damage_accounts
        assert Account.SHRINKAGE.value in shrink_accounts
        assert Account.DAMAGE.value not in shrink_accounts

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_zero_cost_product_skips_ledger_entry(self):
        """Products with cost=0 should produce no ledger entries (amount=0 guard)."""
        ref = str(uuid4())
        await record_adjustment(
            adjustment_ref_id=ref,
            product_id="p1",
            product_cost=0.0,
            quantity_delta=-5.0,
            department="Hardware",
            reason="damage",
        )
        entries = await _get_entries_for_ref(ref)
        assert len(entries) == 0, "Zero-cost product should not produce ledger entries"

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_idempotent_adjustment_recording(self):
        """Calling record_adjustment twice with the same ref_id must not duplicate entries."""
        ref = str(uuid4())
        kwargs = {
            "adjustment_ref_id": ref,
            "product_id": "p1",
            "product_cost": 10.0,
            "quantity_delta": -2.0,
            "department": "Hardware",
            "reason": "damage",
        }
        await record_adjustment(**kwargs)
        await record_adjustment(**kwargs)

        entries = await _get_entries_for_ref(ref)
        assert len(entries) == 2, "Idempotent: must produce exactly 2 entries total"
