"""E2E: Stress scenarios — worst-case user behavior and precise edge cases.

Two test classes:

TestStressScenarios
  N-way concurrency on the same resource, exact numerical invariants on stock
  and ledger. Encodes the bugs found in the architecture audit.

TestAdversarialBehavior
  Models the worst things a real user (or flaky frontend) can do:
  rapid retries, contradictory concurrent actions on the same resource,
  interleaved lifecycle steps, out-of-order operations.

All tests run against Postgres (the only supported backend).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from starlette.testclient import TestClient

from tests.e2e.helpers import (
    create_po,
    create_product,
    create_withdrawal,
    open_cycle_count,
    update_cycle_count_item,
)
from tests.helpers.auth import admin_headers

_N_WORKERS = 5  # concurrency fan-out for high-load tests


# ── DB query helpers ──────────────────────────────────────────────────────────


def _count_ledger(client: TestClient, reference_id: str, reference_type: str) -> int:
    """Count all ledger rows for a given reference."""

    async def _q() -> int:
        from shared.infrastructure.database import get_connection

        conn = get_connection()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM financial_ledger WHERE reference_id = $1 AND reference_type = $2",
            (reference_id, reference_type),
        )
        row = await cursor.fetchone()
        return int(row[0])

    return client.portal.call(_q)


def _count_ledger_by_account(
    client: TestClient, reference_id: str, reference_type: str, account: str
) -> int:
    """Count ledger rows for a specific account within a reference."""

    async def _q() -> int:
        from shared.infrastructure.database import get_connection

        conn = get_connection()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM financial_ledger "
            "WHERE reference_id = $1 AND reference_type = $2 AND account = $3",
            (reference_id, reference_type, account),
        )
        row = await cursor.fetchone()
        return int(row[0])

    return client.portal.call(_q)


def _sum_ledger_amount(
    client: TestClient, reference_id: str, reference_type: str, account: str
) -> float:
    """Sum amounts for a specific account within a reference."""

    async def _q() -> float:
        from shared.infrastructure.database import get_connection

        conn = get_connection()
        cursor = await conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM financial_ledger "
            "WHERE reference_id = $1 AND reference_type = $2 AND account = $3",
            (reference_id, reference_type, account),
        )
        row = await cursor.fetchone()
        return float(row[0])

    return client.portal.call(_q)


def _get_stock_qty(client: TestClient, product_id: str, headers: dict) -> float:
    resp = client.get(f"/api/catalog/skus/{product_id}", headers=headers)
    assert resp.status_code == 200
    return float(resp.json()["quantity"])


def _get_withdrawal(client: TestClient, withdrawal_id: str, headers: dict) -> dict[str, Any]:
    resp = client.get(f"/api/withdrawals/{withdrawal_id}", headers=headers)
    assert resp.status_code == 200
    return resp.json()


# ── Attempt helpers ───────────────────────────────────────────────────────────


def _attempt_commit(client: TestClient, headers: dict, count_id: str) -> int:
    resp = client.post(f"/api/cycle-counts/{count_id}/commit", json={}, headers=headers)
    return resp.status_code


def _attempt_mark_paid(client: TestClient, headers: dict, withdrawal_id: str) -> int:
    resp = client.put(f"/api/withdrawals/{withdrawal_id}/mark-paid", json={}, headers=headers)
    return resp.status_code


def _attempt_bulk_mark_paid(
    client: TestClient, headers: dict, withdrawal_ids: list[str]
) -> tuple[int, Any]:
    resp = client.put(
        "/api/withdrawals/bulk-mark-paid",
        json={"withdrawal_ids": withdrawal_ids},
        headers=headers,
    )
    return resp.status_code, resp.json() if resp.status_code == 200 else resp.text


def _attempt_create_invoice(
    client: TestClient, headers: dict, withdrawal_ids: list[str]
) -> tuple[int, Any]:
    resp = client.post(
        "/api/invoices",
        json={"withdrawal_ids": withdrawal_ids},
        headers=headers,
    )
    return resp.status_code, resp.json() if resp.status_code == 200 else resp.text


def _attempt_receive(
    client: TestClient, headers: dict, po_id: str, items: list[dict[str, Any]]
) -> tuple[int, Any]:
    pending = [
        {"id": i["id"], "delivered_qty": i.get("ordered_qty", 10)}
        for i in items
        if i.get("status") == "pending"
    ]
    resp = client.post(
        f"/api/purchase-orders/{po_id}/receive",
        json={"items": pending},
        headers=headers,
    )
    return resp.status_code, resp.json() if resp.status_code == 200 else resp.text


def _setup_po_pending(
    client: TestClient, headers: dict, product: dict[str, Any], *, quantity: int = 50
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Create a PO, mark delivery, return (po, pending_items)."""
    po = create_po(client, headers, product, quantity=quantity, vendor_name="Stress Vendor")
    po_resp = client.get(f"/api/purchase-orders/{po['id']}", headers=headers)
    items = po_resp.json().get("items", [])
    ordered_ids = [i["id"] for i in items if i.get("status") == "ordered"]
    if ordered_ids:
        client.post(
            f"/api/purchase-orders/{po['id']}/delivery",
            json={"item_ids": ordered_ids},
            headers=headers,
        )
    po_resp = client.get(f"/api/purchase-orders/{po['id']}", headers=headers)
    items = po_resp.json().get("items", [])
    return po, items


# ── Test class ────────────────────────────────────────────────────────────────


@pytest.mark.timeout(60)
class TestStressScenarios:
    """High-load edge cases for financial and inventory mutations."""

    # ── Bulk mark-paid: the fixed race condition ──────────────────────────────

    def test_bulk_mark_paid_concurrent_overlapping_exact_one_ledger_entry(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """Two concurrent bulk mark-paid calls on the same IDs produce exactly 1 payment
        ledger entry per withdrawal.

        This is the exact race fixed in withdrawal_service.bulk_mark_withdrawals_paid:
        the old code iterated all pre-fetched withdrawals regardless of which were
        actually changed by the UPDATE. Under concurrent calls both could write ledger.
        """
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=200, name="STRESS-BulkRace"
        )
        wds = [
            create_withdrawal(client, headers, product, quantity=2, job_id=f"JOB-BR-{i}")
            for i in range(4)
        ]
        wd_ids = [w["id"] for w in wds]

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_attempt_bulk_mark_paid, client, headers, wd_ids)
            f2 = pool.submit(_attempt_bulk_mark_paid, client, headers, wd_ids)
            results = [f.result() for f in as_completed([f1, f2])]

        successes = [r for r in results if r[0] == 200]
        assert len(successes) >= 1, "At least one bulk operation should succeed"

        for wd_id in wd_ids:
            payment_entries = _count_ledger_by_account(
                client, wd_id, "payment", "accounts_receivable"
            )
            assert payment_entries == 1, (
                f"Withdrawal {wd_id}: expected exactly 1 payment AR entry, got {payment_entries}"
            )
            wd = _get_withdrawal(client, wd_id, headers)
            assert wd["payment_status"] == "paid", f"Withdrawal {wd_id} should be paid"

    def test_bulk_mark_paid_with_already_paid_no_duplicate_ledger(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """Bulk mark-paid that includes already-paid withdrawals must not add duplicate
        ledger entries for the pre-paid ones.

        Edge case: the bulk call succeeds for the new ones, silently skips the paid ones.
        """
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=200, name="STRESS-BulkMixed"
        )
        already_paid = create_withdrawal(
            client, headers, product, quantity=2, job_id="JOB-PRE-PAID"
        )
        new_wd = create_withdrawal(client, headers, product, quantity=2, job_id="JOB-NEW-WD")

        # Pre-pay one withdrawal
        resp = client.put(
            f"/api/withdrawals/{already_paid['id']}/mark-paid", json={}, headers=headers
        )
        assert resp.status_code == 200

        # Verify initial state: 1 payment entry for the pre-paid one
        pre_count = _count_ledger_by_account(
            client, already_paid["id"], "payment", "accounts_receivable"
        )
        assert pre_count == 1, "Pre-paid withdrawal should already have 1 payment entry"

        # Bulk that includes the already-paid one
        resp = client.put(
            "/api/withdrawals/bulk-mark-paid",
            json={"withdrawal_ids": [already_paid["id"], new_wd["id"]]},
            headers=headers,
        )
        assert resp.status_code == 200

        # Already-paid must still have exactly 1 entry — not 2
        post_count = _count_ledger_by_account(
            client, already_paid["id"], "payment", "accounts_receivable"
        )
        assert post_count == 1, (
            f"Already-paid withdrawal must have exactly 1 payment AR entry after bulk, got {post_count}"
        )

        # New one should now have exactly 1 entry
        new_count = _count_ledger_by_account(client, new_wd["id"], "payment", "accounts_receivable")
        assert new_count == 1, (
            f"New withdrawal should have exactly 1 payment entry, got {new_count}"
        )

    def test_n_way_concurrent_bulk_mark_paid_single_ledger_per_withdrawal(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """N concurrent bulk mark-paid calls on the same withdrawal set: each withdrawal
        ends up paid with exactly 1 payment ledger entry, regardless of fan-out.
        """
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=500, name="STRESS-NFan"
        )
        wds = [
            create_withdrawal(client, headers, product, quantity=1, job_id=f"JOB-NFAN-{i}")
            for i in range(3)
        ]
        wd_ids = [w["id"] for w in wds]

        with ThreadPoolExecutor(max_workers=_N_WORKERS) as pool:
            futures = [
                pool.submit(_attempt_bulk_mark_paid, client, headers, wd_ids)
                for _ in range(_N_WORKERS)
            ]
            [f.result() for f in as_completed(futures)]

        for wd_id in wd_ids:
            payment_entries = _count_ledger_by_account(
                client, wd_id, "payment", "accounts_receivable"
            )
            assert payment_entries == 1, (
                f"Withdrawal {wd_id}: expected exactly 1 payment AR entry across {_N_WORKERS} "
                f"concurrent bulk calls, got {payment_entries}"
            )

    # ── Cycle count: status-flip-first ordering ───────────────────────────────

    def test_cycle_count_n_way_concurrent_commit_exact_stock(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """N concurrent commits of the same cycle count apply the variance exactly once.

        Tests the fix: status flips first inside the transaction, so any concurrent
        commit that loses the conditional UPDATE never touches stock at all.
        """
        headers = admin_headers()
        initial_qty = 100.0
        counted_qty = 75.0
        expected_qty = 75.0  # variance = -25, applied exactly once

        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=int(initial_qty), name="STRESS-CCNway"
        )
        count = open_cycle_count(client, headers)
        count_id: str = count["id"]

        detail = client.get(f"/api/cycle-counts/{count_id}", headers=headers).json()
        target = next(
            (i for i in detail.get("items", []) if i["product_id"] == product["id"]), None
        )
        assert target is not None, "Product must appear in the cycle count"

        update_cycle_count_item(client, headers, count_id, target["id"], counted_qty=counted_qty)

        with ThreadPoolExecutor(max_workers=_N_WORKERS) as pool:
            futures = [
                pool.submit(_attempt_commit, client, headers, count_id) for _ in range(_N_WORKERS)
            ]
            statuses = [f.result() for f in as_completed(futures)]

        successes = sum(1 for s in statuses if s == 200)
        assert successes == 1, (
            f"Exactly 1 commit should succeed across {_N_WORKERS} workers, got {successes}"
        )

        final_qty = _get_stock_qty(client, product["id"], headers)
        assert final_qty == pytest.approx(expected_qty), (
            f"Stock should be {expected_qty} (variance applied once). "
            f"Got {final_qty} — variance may have been applied {successes} times or rolled back incorrectly."
        )

    def test_cycle_count_positive_variance_applied_once(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """Positive variance (found stock) applied under concurrent commits: exactly once."""
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=50, name="STRESS-CCPos"
        )
        count = open_cycle_count(client, headers)
        count_id: str = count["id"]

        detail = client.get(f"/api/cycle-counts/{count_id}", headers=headers).json()
        target = next(
            (i for i in detail.get("items", []) if i["product_id"] == product["id"]), None
        )
        assert target is not None

        update_cycle_count_item(client, headers, count_id, target["id"], counted_qty=70.0)

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(_attempt_commit, client, headers, count_id) for _ in range(3)]
            statuses = [f.result() for f in as_completed(futures)]

        successes = sum(1 for s in statuses if s == 200)
        assert successes == 1, f"Exactly 1 commit should succeed, got {successes}"

        final_qty = _get_stock_qty(client, product["id"], headers)
        assert final_qty == pytest.approx(70.0), (
            f"Stock should be 70.0 (snapshot=50, variance=+20, applied once). Got {final_qty}"
        )

    def test_cycle_count_commit_ledger_entries_written_once(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """Concurrent cycle count commits produce exactly one set of adjustment ledger entries."""
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=100, name="STRESS-CCLedger"
        )
        count = open_cycle_count(client, headers)
        count_id: str = count["id"]

        detail = client.get(f"/api/cycle-counts/{count_id}", headers=headers).json()
        target = next(
            (i for i in detail.get("items", []) if i["product_id"] == product["id"]), None
        )
        assert target is not None

        update_cycle_count_item(client, headers, count_id, target["id"], counted_qty=80.0)

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(_attempt_commit, client, headers, count_id) for _ in range(3)]
            [f.result() for f in as_completed(futures)]

        # There is one adjustment reference per product per commit. All concurrent
        # losers must produce zero ledger rows. Only the winner writes entries.
        #
        # Query the inventory account entries for this product via the adjustment
        # reference — cycle counts write adjustment-type ledger entries.
        async def _count_adjustment_entries() -> int:
            from shared.infrastructure.database import get_connection

            conn = get_connection()
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM financial_ledger "
                "WHERE reference_type = 'adjustment' AND product_id = $1",
                (product["id"],),
            )
            row = await cursor.fetchone()
            return int(row[0])

        total_adjustment_entries = client.portal.call(_count_adjustment_entries)
        # Each variance produces 2 ledger rows (INVENTORY + SHRINKAGE/ADJUSTMENT offset).
        # Exactly one commit succeeded, so exactly 2 entries.
        assert total_adjustment_entries == 2, (
            f"Cycle count variance should produce exactly 2 ledger entries (inventory + offset), "
            f"got {total_adjustment_entries}. Concurrent commits may have double-written."
        )

    # ── PO receive: stock + ledger both checked ───────────────────────────────

    def test_po_receive_n_way_concurrent_stock_and_ledger(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """N concurrent receives on the same PO increment stock exactly once and write
        exactly one set of PO receipt ledger entries.
        """
        headers = admin_headers()
        initial_qty = 100.0
        order_qty = 40

        product = create_product(
            client,
            headers,
            dept_id=seed_dept_id,
            quantity=int(initial_qty),
            name="STRESS-POReceive",
        )
        po, items = _setup_po_pending(client, headers, product, quantity=order_qty)

        with ThreadPoolExecutor(max_workers=_N_WORKERS) as pool:
            futures = [
                pool.submit(_attempt_receive, client, headers, po["id"], items)
                for _ in range(_N_WORKERS)
            ]
            results = [f.result() for f in as_completed(futures)]

        successes = [r for r in results if r[0] == 200]
        assert len(successes) >= 1, "At least one receive must succeed"

        # Stock must be exactly initial + order_qty (receive applied once regardless of fan-out)
        final_qty = _get_stock_qty(client, product["id"], headers)
        assert final_qty == pytest.approx(initial_qty + order_qty), (
            f"Stock should be {initial_qty + order_qty} (received once). Got {final_qty}. "
            f"{len(successes)} of {_N_WORKERS} concurrent receives reported success."
        )

        # Ledger: exactly one set of INVENTORY + AP entries for this PO receipt.
        # Each item that has cost > 0 writes 2 entries. With one item at cost=5.0 and
        # qty=40, that's 2 rows. Any double-write would produce 4 or more.
        inventory_entries = _count_ledger_by_account(client, po["id"], "po_receipt", "inventory")
        assert inventory_entries == 1, (
            f"PO {po['id']}: expected exactly 1 inventory ledger entry for po_receipt, "
            f"got {inventory_entries}"
        )
        ap_entries = _count_ledger_by_account(client, po["id"], "po_receipt", "accounts_payable")
        assert ap_entries == 1, (
            f"PO {po['id']}: expected exactly 1 AP ledger entry for po_receipt, got {ap_entries}"
        )

    # ── Invoice creation: exactly one invoice per withdrawal set ─────────────

    def test_n_way_concurrent_invoice_creation_exactly_one(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """N concurrent invoice creation attempts for the same withdrawal set: exactly 1 invoice."""
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=100, name="STRESS-InvNway"
        )
        wd = create_withdrawal(client, headers, product, quantity=5)

        with ThreadPoolExecutor(max_workers=_N_WORKERS) as pool:
            futures = [
                pool.submit(_attempt_create_invoice, client, headers, [wd["id"]])
                for _ in range(_N_WORKERS)
            ]
            results = [f.result() for f in as_completed(futures)]

        successes = [r for r in results if r[0] == 200]
        assert len(successes) == 1, (
            f"Exactly 1 of {_N_WORKERS} concurrent invoice creations should succeed, "
            f"got {len(successes)}"
        )

        # Withdrawal must be linked to exactly one invoice
        resp = client.get("/api/invoices", headers=headers)
        invoices = [inv for inv in resp.json() if wd["id"] in inv.get("withdrawal_ids", [])]
        assert len(invoices) == 1, (
            f"Withdrawal should be on exactly 1 invoice, found {len(invoices)}"
        )

        # Withdrawal status should be invoiced
        wd_state = _get_withdrawal(client, wd["id"], headers)
        assert wd_state["payment_status"] == "invoiced", (
            f"Withdrawal should be 'invoiced', got {wd_state['payment_status']}"
        )

    # ── Mark-paid: exact ledger count under N-way concurrency ────────────────

    def test_n_way_concurrent_mark_paid_exactly_one_ledger_entry(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """N concurrent mark-paid calls on the same withdrawal: exactly 1 payment AR entry."""
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=100, name="STRESS-MarkPaidN"
        )
        wd = create_withdrawal(client, headers, product, quantity=4)

        with ThreadPoolExecutor(max_workers=_N_WORKERS) as pool:
            futures = [
                pool.submit(_attempt_mark_paid, client, headers, wd["id"])
                for _ in range(_N_WORKERS)
            ]
            statuses = [f.result() for f in as_completed(futures)]

        successes = sum(1 for s in statuses if s == 200)
        assert successes >= 1, "At least one mark-paid must succeed"

        wd_state = _get_withdrawal(client, wd["id"], headers)
        assert wd_state["payment_status"] == "paid"

        payment_entries = _count_ledger_by_account(
            client, wd["id"], "payment", "accounts_receivable"
        )
        assert payment_entries == 1, (
            f"Exactly 1 payment AR entry expected across {_N_WORKERS} concurrent mark-paid calls. "
            f"Got {payment_entries}. {successes} calls reported success."
        )

    # ── Withdrawal ledger: entries written once, balanced ────────────────────

    def test_withdrawal_ledger_entries_written_exactly_once(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """A withdrawal writes its full ledger journal exactly once.

        Verifies the entries_exist guard in record_withdrawal prevents double-write
        even if the event handler were called more than once (belt-and-suspenders).
        """
        headers = admin_headers()
        product = create_product(
            client,
            headers,
            dept_id=seed_dept_id,
            quantity=100,
            price=20.0,
            cost=8.0,
            name="STRESS-WDLedger",
        )
        wd = create_withdrawal(client, headers, product, quantity=5)

        # One withdrawal = one journal: REVENUE + COGS + INVENTORY per item + TAX + AR
        # With 1 item: 3 item entries + TAX + AR = 5 total
        total_entries = _count_ledger(client, wd["id"], "withdrawal")
        assert total_entries == 5, (
            f"1-item withdrawal should produce exactly 5 ledger rows "
            f"(REVENUE, COGS, INVENTORY, TAX, AR). Got {total_entries}."
        )

        # AR entry should equal withdrawal total (positive)
        ar_amount = _sum_ledger_amount(client, wd["id"], "withdrawal", "accounts_receivable")
        assert ar_amount == pytest.approx(wd["total"], abs=0.01), (
            f"AR ledger entry should equal withdrawal total {wd['total']}. Got {ar_amount}."
        )

        # REVENUE + COGS net to gross profit
        revenue = _sum_ledger_amount(client, wd["id"], "withdrawal", "revenue")
        cogs = _sum_ledger_amount(client, wd["id"], "withdrawal", "cogs")
        assert revenue > 0, "Revenue entry must be positive"
        assert cogs > 0, "COGS entry must be positive"
        assert revenue - cogs == pytest.approx(
            (product["price"] - product["cost"]) * 5, abs=0.02
        ), "Gross profit per item should match price - cost"

    # ── Concurrent withdrawals draining stock: no negative ──────────────────

    def test_n_way_withdrawal_stock_never_negative(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """N concurrent withdrawals that collectively exceed available stock:
        stock never goes negative. Some succeed, some fail — but the math is exact.
        """
        headers = admin_headers()
        initial_qty = 30
        per_request = 10  # 5 requests × 10 = 50, exceeds 30

        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=initial_qty, name="STRESS-StockFloor"
        )

        def _attempt_withdrawal_floor(job_id: str) -> int:
            return client.post(
                "/api/withdrawals",
                json={
                    "items": [
                        {
                            "product_id": product["id"],
                            "sku": product["sku"],
                            "name": product["name"],
                            "quantity": per_request,
                            "unit_price": product["price"],
                            "cost": product["cost"],
                        }
                    ],
                    "job_id": job_id,
                    "service_address": "1 Race St",
                },
                headers=headers,
            ).status_code

        with ThreadPoolExecutor(max_workers=_N_WORKERS) as pool:
            futures = [
                pool.submit(_attempt_withdrawal_floor, f"JOB-FLOOR-{i}") for i in range(_N_WORKERS)
            ]
            statuses = [f.result() for f in as_completed(futures)]

        successes = sum(1 for s in statuses if s == 200)
        final_qty = _get_stock_qty(client, product["id"], headers)

        assert final_qty >= 0, f"Stock must never go negative. Got {final_qty}"
        assert final_qty == pytest.approx(initial_qty - (successes * per_request), abs=0.01), (
            f"Stock mismatch: initial={initial_qty}, successes={successes}, "
            f"per_request={per_request}, expected={initial_qty - successes * per_request}, "
            f"got={final_qty}"
        )


# ── Adversarial behavior tests ───────────────────────────────────────────────


def _attempt_return(
    client: TestClient, headers: dict, withdrawal_id: str, product: dict[str, Any], qty: int
) -> tuple[int, Any]:
    resp = client.post(
        "/api/returns",
        json={
            "withdrawal_id": withdrawal_id,
            "items": [
                {
                    "product_id": product["id"],
                    "sku": product["sku"],
                    "name": product["name"],
                    "quantity": qty,
                }
            ],
        },
        headers=headers,
    )
    return resp.status_code, resp.json() if resp.status_code == 200 else resp.text


def _attempt_delete_invoice(client: TestClient, headers: dict, invoice_id: str) -> int:
    resp = client.delete(f"/api/invoices/{invoice_id}", headers=headers)
    return resp.status_code


@pytest.mark.timeout(90)
class TestAdversarialBehavior:
    """Models the worst user behavior: rapid retries, contradictory actions,
    interleaved lifecycle steps, out-of-order operations."""

    # ── Pay-while-invoicing: user clicks "pay" while admin creates invoice ───

    def test_mark_paid_while_invoicing_same_withdrawal(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """Concurrent mark-paid and invoice-creation on the same unpaid withdrawal.

        Only one lifecycle path should win. The withdrawal should end up either:
          - invoiced (invoice won) — 0 payment ledger entries, 1 invoice link
          - paid (mark-paid won) — 1 payment ledger entry, no invoice link

        It must NOT end up both invoiced AND paid with a stale invoice link.
        """
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=100, name="ADV-PayInvoiceRace"
        )
        wd = create_withdrawal(client, headers, product, quantity=5)

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_pay = pool.submit(_attempt_mark_paid, client, headers, wd["id"])
            f_inv = pool.submit(_attempt_create_invoice, client, headers, [wd["id"]])
            f_pay.result()
            f_inv.result()

        wd_state = _get_withdrawal(client, wd["id"], headers)
        status = wd_state["payment_status"]
        invoice_id = wd_state.get("invoice_id")

        # At most one path should succeed cleanly
        if status == "paid":
            payment_entries = _count_ledger_by_account(
                client, wd["id"], "payment", "accounts_receivable"
            )
            assert payment_entries == 1, (
                f"Paid withdrawal should have exactly 1 payment AR entry, got {payment_entries}"
            )
        elif status == "invoiced":
            assert invoice_id is not None, "Invoiced withdrawal must have an invoice_id"
            payment_entries = _count_ledger_by_account(
                client, wd["id"], "payment", "accounts_receivable"
            )
            assert payment_entries == 0, (
                f"Invoiced (not paid) withdrawal should have 0 payment entries, got {payment_entries}"
            )
        else:
            # 'unpaid' is acceptable if both failed due to contention
            assert status == "unpaid", f"Unexpected payment_status: {status}"

    # ── Rapid mark-paid retries: user mashes the Pay button ──────────────────

    def test_rapid_mark_paid_retries_idempotent(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """User clicks Pay 10 times rapidly. Final state: paid, exactly 1 payment entry."""
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=100, name="ADV-MashPay"
        )
        wd = create_withdrawal(client, headers, product, quantity=3)

        n_retries = 10
        with ThreadPoolExecutor(max_workers=n_retries) as pool:
            futures = [
                pool.submit(_attempt_mark_paid, client, headers, wd["id"]) for _ in range(n_retries)
            ]
            statuses = [f.result() for f in as_completed(futures)]

        successes = sum(1 for s in statuses if s == 200)
        assert successes >= 1, "At least one attempt should succeed"

        wd_state = _get_withdrawal(client, wd["id"], headers)
        assert wd_state["payment_status"] == "paid"

        payment_entries = _count_ledger_by_account(
            client, wd["id"], "payment", "accounts_receivable"
        )
        assert payment_entries == 1, (
            f"10 rapid retries must produce exactly 1 payment AR entry. Got {payment_entries}"
        )

    # ── Return-after-pay: user pays then immediately tries to return ─────────

    def test_return_on_paid_withdrawal_restocks_correctly(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """User pays a withdrawal, then returns some items.
        Stock must reflect both the withdrawal decrement and the return increment.
        Payment status remains paid (payment was already settled).
        """
        headers = admin_headers()
        initial_qty = 100
        withdraw_qty = 10
        return_qty = 4

        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=initial_qty, name="ADV-ReturnAfterPay"
        )
        wd = create_withdrawal(client, headers, product, quantity=withdraw_qty)

        # Pay first
        resp = client.put(f"/api/withdrawals/{wd['id']}/mark-paid", json={}, headers=headers)
        assert resp.status_code == 200

        # Return some items
        ret_status, ret_body = _attempt_return(client, headers, wd["id"], product, return_qty)
        assert ret_status == 200, f"Return should succeed on paid withdrawal: {ret_body}"

        final_qty = _get_stock_qty(client, product["id"], headers)
        expected = initial_qty - withdraw_qty + return_qty
        assert final_qty == pytest.approx(expected), (
            f"Stock should be {expected} ({initial_qty} - {withdraw_qty} + {return_qty}). Got {final_qty}"
        )

    # ── Concurrent return + mark-paid on same withdrawal ─────────────────────

    def test_concurrent_return_and_mark_paid(self, client: TestClient, seed_dept_id: str) -> None:
        """User processes a return while someone else marks the withdrawal paid.
        Both can succeed (return creates credit note, mark-paid records payment).
        Stock and ledger must be consistent regardless of ordering.
        """
        headers = admin_headers()
        initial_qty = 100
        withdraw_qty = 10
        return_qty = 3

        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=initial_qty, name="ADV-ReturnPayRace"
        )
        wd = create_withdrawal(client, headers, product, quantity=withdraw_qty)

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_ret = pool.submit(_attempt_return, client, headers, wd["id"], product, return_qty)
            f_pay = pool.submit(_attempt_mark_paid, client, headers, wd["id"])
            ret_status, _ = f_ret.result()
            pay_status = f_pay.result()

        # Stock: withdrawal took `withdraw_qty`; if return succeeded, `return_qty` restored
        final_qty = _get_stock_qty(client, product["id"], headers)
        returned = return_qty if ret_status == 200 else 0
        expected = initial_qty - withdraw_qty + returned
        assert final_qty == pytest.approx(expected, abs=0.01), (
            f"Stock should be {expected}. Got {final_qty}. "
            f"Return status={ret_status}, pay status={pay_status}"
        )

        # Ledger: at most 1 payment AR entry
        payment_entries = _count_ledger_by_account(
            client, wd["id"], "payment", "accounts_receivable"
        )
        assert payment_entries <= 1, f"At most 1 payment AR entry. Got {payment_entries}"

    # ── Invoice-then-immediately-delete: user creates and nukes invoice ──────

    def test_invoice_create_then_concurrent_delete(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """User creates an invoice, then immediately fires delete while another
        request tries to create a second invoice for the same withdrawals.
        After the dust settles: each withdrawal is on 0 or 1 invoice, never orphaned.
        """
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=100, name="ADV-InvDeleteRace"
        )
        wd = create_withdrawal(client, headers, product, quantity=5)

        # Create the first invoice
        inv_status, inv_body = _attempt_create_invoice(client, headers, [wd["id"]])
        assert inv_status == 200, f"First invoice creation should succeed: {inv_body}"
        invoice_id = inv_body["id"]

        # Fire delete + re-create concurrently
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_del = pool.submit(_attempt_delete_invoice, client, headers, invoice_id)
            f_create = pool.submit(_attempt_create_invoice, client, headers, [wd["id"]])
            f_del.result()
            f_create.result()

        wd_state = _get_withdrawal(client, wd["id"], headers)
        status = wd_state["payment_status"]
        inv_link = wd_state.get("invoice_id")

        # Withdrawal must be in a consistent state
        if status == "invoiced":
            assert inv_link is not None, "Invoiced withdrawal must have an invoice_id"
            # Verify the linked invoice actually exists
            inv_resp = client.get(f"/api/invoices/{inv_link}", headers=headers)
            assert inv_resp.status_code == 200, (
                f"Withdrawal links to invoice {inv_link} but that invoice doesn't exist (orphan)"
            )
        elif status == "unpaid":
            # Delete won, re-create either didn't run or also lost
            pass
        else:
            # 'paid' shouldn't happen here since we never called mark-paid
            pytest.fail(f"Unexpected status {status} — no mark-paid was called")

    # ── Bulk mark-paid interleaved with single mark-paid ─────────────────────

    def test_bulk_and_single_mark_paid_interleaved(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """Admin clicks bulk-pay on a list while also clicking single-pay on one of them.
        All end up paid, each with exactly 1 payment ledger entry.
        """
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=200, name="ADV-BulkSingleMix"
        )
        wds = [
            create_withdrawal(client, headers, product, quantity=2, job_id=f"JOB-MIX-{i}")
            for i in range(3)
        ]
        wd_ids = [w["id"] for w in wds]
        target_id = wd_ids[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_bulk = pool.submit(_attempt_bulk_mark_paid, client, headers, wd_ids)
            f_single = pool.submit(_attempt_mark_paid, client, headers, target_id)
            f_bulk.result()
            f_single.result()

        for wd_id in wd_ids:
            wd_state = _get_withdrawal(client, wd_id, headers)
            assert wd_state["payment_status"] == "paid", f"Withdrawal {wd_id} should be paid"

            payment_entries = _count_ledger_by_account(
                client, wd_id, "payment", "accounts_receivable"
            )
            assert payment_entries == 1, (
                f"Withdrawal {wd_id}: interleaved bulk+single must produce exactly 1 payment AR entry. "
                f"Got {payment_entries}"
            )

    # ── Withdraw → invoice → pay → return: full lifecycle with ledger check ──

    def test_full_lifecycle_ledger_balance(self, client: TestClient, seed_dept_id: str) -> None:
        """Walk through the complete lifecycle of a withdrawal and verify that
        ledger entries are balanced at each step and cumulative totals are exact.

        Steps: create withdrawal → invoice → mark-paid → partial return
        """
        headers = admin_headers()
        product = create_product(
            client,
            headers,
            dept_id=seed_dept_id,
            quantity=200,
            price=25.0,
            cost=10.0,
            name="ADV-FullLifecycle",
        )
        wd = create_withdrawal(client, headers, product, quantity=8)
        wd_total = wd["total"]

        # Step 1: Verify withdrawal ledger
        wd_ledger_count = _count_ledger(client, wd["id"], "withdrawal")
        assert wd_ledger_count == 5, (
            f"Withdrawal should have 5 ledger entries. Got {wd_ledger_count}"
        )

        wd_ar = _sum_ledger_amount(client, wd["id"], "withdrawal", "accounts_receivable")
        assert wd_ar == pytest.approx(wd_total, abs=0.01), (
            f"Withdrawal AR should equal total {wd_total}. Got {wd_ar}"
        )

        # Step 2: Invoice
        inv_status, inv_body = _attempt_create_invoice(client, headers, [wd["id"]])
        assert inv_status == 200, f"Invoice creation should succeed: {inv_body}"
        wd_state = _get_withdrawal(client, wd["id"], headers)
        assert wd_state["payment_status"] == "invoiced"

        # Step 3: Pay
        pay_status = _attempt_mark_paid(client, headers, wd["id"])
        assert pay_status == 200
        wd_state = _get_withdrawal(client, wd["id"], headers)
        assert wd_state["payment_status"] == "paid"

        payment_ar = _sum_ledger_amount(client, wd["id"], "payment", "accounts_receivable")
        assert payment_ar == pytest.approx(-wd_total, abs=0.01), (
            f"Payment AR should be -{wd_total} (reducing receivable). Got {payment_ar}"
        )

        # Step 4: Partial return (3 of 8)
        ret_status, _ = _attempt_return(client, headers, wd["id"], product, 3)
        assert ret_status == 200

        # Stock check: 200 - 8 + 3 = 195
        final_qty = _get_stock_qty(client, product["id"], headers)
        assert final_qty == pytest.approx(195.0), f"Stock should be 195. Got {final_qty}"

        # Net AR across all entries for this withdrawal should be:
        #   +wd_total (withdrawal) -wd_total (payment) = 0 from those two
        # The return writes its own reference_id (the return's ID), so
        # withdrawal-scoped AR entries are exactly 0 net after payment.
        net_ar = wd_ar + payment_ar
        assert net_ar == pytest.approx(0.0, abs=0.01), (
            f"Net AR for withdrawal after payment should be 0. Got {net_ar}"
        )

    # ── Simultaneous withdrawals on same product, different jobs ─────────────

    def test_concurrent_withdrawals_different_jobs_stock_exact(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """Multiple users withdraw the same product for different jobs simultaneously.
        Total stock decrement must equal the sum of all successful withdrawals.
        Each successful withdrawal must have exactly 5 ledger entries.
        """
        headers = admin_headers()
        initial_qty = 100
        per_wd = 15

        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=initial_qty, name="ADV-MultiJob"
        )

        def _do_withdrawal(job_suffix: int) -> tuple[int, Any]:
            resp = client.post(
                "/api/withdrawals",
                json={
                    "items": [
                        {
                            "product_id": product["id"],
                            "sku": product["sku"],
                            "name": product["name"],
                            "quantity": per_wd,
                            "unit_price": product["price"],
                            "cost": product["cost"],
                        }
                    ],
                    "job_id": f"JOB-MULTI-{job_suffix}",
                    "service_address": "123 Multi St",
                },
                headers=headers,
            )
            if resp.status_code == 200:
                return resp.status_code, resp.json()
            return resp.status_code, resp.text

        with ThreadPoolExecutor(max_workers=_N_WORKERS) as pool:
            futures = [pool.submit(_do_withdrawal, i) for i in range(_N_WORKERS)]
            results = [f.result() for f in as_completed(futures)]

        successes = [(s, b) for s, b in results if s == 200]
        final_qty = _get_stock_qty(client, product["id"], headers)

        assert final_qty >= 0, f"Stock must never go negative. Got {final_qty}"
        assert final_qty == pytest.approx(initial_qty - (len(successes) * per_wd), abs=0.01), (
            f"Stock mismatch: {len(successes)} withdrawals of {per_wd} from {initial_qty}. "
            f"Expected {initial_qty - len(successes) * per_wd}, got {final_qty}"
        )

        for _status, body in successes:
            wd_id = body["id"]
            ledger_count = _count_ledger(client, wd_id, "withdrawal")
            assert ledger_count == 5, (
                f"Withdrawal {wd_id}: expected 5 ledger entries. Got {ledger_count}"
            )

    # ── Double-return on same withdrawal: return more than was withdrawn ─────

    def test_double_return_cannot_exceed_withdrawal_quantity(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """User returns items, then tries to return the same items again.
        The second return should fail or return fewer items — total returned
        must never exceed total withdrawn.
        """
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=100, name="ADV-DoubleReturn"
        )
        wd = create_withdrawal(client, headers, product, quantity=10)

        # First return: 6 items
        ret1_status, _ = _attempt_return(client, headers, wd["id"], product, 6)
        assert ret1_status == 200, "First return of 6 should succeed"

        # Second return: try 6 more (only 4 remain)
        _attempt_return(client, headers, wd["id"], product, 6)

        # Either the second return is rejected or it returns at most 4
        final_qty = _get_stock_qty(client, product["id"], headers)
        # Worst valid case: 100 - 10 + 6 + 4 = 100 (if second succeeded partially)
        # Best case: 100 - 10 + 6 = 96 (second rejected)
        assert final_qty <= 100, (
            f"Stock {final_qty} exceeds initial 100 — returned more than was withdrawn"
        )
        assert final_qty >= 90, f"Stock {final_qty} below 90 — something was double-decremented"

    # ── Concurrent returns on same withdrawal ────────────────────────────────

    def test_concurrent_returns_same_withdrawal_stock_bounded(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """Two concurrent returns for the same items on the same withdrawal.
        Total stock restored must not exceed what was withdrawn.
        """
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=100, name="ADV-ConcurrentReturn"
        )
        wd = create_withdrawal(client, headers, product, quantity=10)

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_attempt_return, client, headers, wd["id"], product, 10)
            f2 = pool.submit(_attempt_return, client, headers, wd["id"], product, 10)
            r1_status, _ = f1.result()
            r2_status, _ = f2.result()

        final_qty = _get_stock_qty(client, product["id"], headers)

        # Stock can be at most 100 (all 10 returned). It must never exceed 100.
        assert final_qty <= 100, (
            f"Stock {final_qty} exceeds initial 100 — concurrent returns double-restored. "
            f"Return 1: {r1_status}, Return 2: {r2_status}"
        )
        # At least one return should succeed, restoring to at least 100 - 10 + 10 = 100
        # or 100 - 10 = 90 if both fail (unlikely but acceptable)
        assert final_qty >= 90, f"Stock unexpectedly low at {final_qty}"
