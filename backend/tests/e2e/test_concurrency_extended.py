"""E2E: Extended concurrency tests targeting race conditions that corrupt data.

Each test fires two concurrent requests that target the same resource and
verifies that database-level guards prevent double-counting, double-ledger
entries, or duplicate invoices.

NOTE: These tests require proper transaction isolation (Postgres).
SQLite's single-connection architecture cannot properly isolate concurrent
transactions, making these tests unreliable on SQLite.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.e2e.helpers import (
    create_po,
    create_product,
    create_withdrawal,
    open_cycle_count,
    update_cycle_count_item,
)
from tests.helpers.auth import admin_headers

_is_sqlite = "sqlite" in os.environ.get("DATABASE_URL", "sqlite")
pytestmark = pytest.mark.skipif(_is_sqlite, reason="Requires Postgres for transaction isolation")


def _create_po_pending(client, headers, product, *, quantity=10):
    """Create a PO and mark delivery so items are PENDING (ready for receive)."""
    po = create_po(client, headers, product, quantity=quantity, vendor_name="Race Vendor")

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


def _attempt_receive(client, headers, po_id, items):
    """Attempt to receive pending PO items."""
    pending_items = [
        {"id": i["id"], "delivered_qty": i.get("ordered_qty", 10)}
        for i in items
        if i.get("status") == "pending"
    ]
    resp = client.post(
        f"/api/purchase-orders/{po_id}/receive",
        json={"items": pending_items},
        headers=headers,
    )
    return resp.status_code, resp.json() if resp.status_code == 200 else resp.text


def _attempt_commit(client, headers, count_id):
    """Attempt to commit a cycle count."""
    resp = client.post(
        f"/api/cycle-counts/{count_id}/commit",
        json={},
        headers=headers,
    )
    return resp.status_code


def _attempt_create_invoice(client, headers, withdrawal_ids):
    """Attempt to create an invoice from withdrawals."""
    resp = client.post(
        "/api/invoices",
        json={"withdrawal_ids": withdrawal_ids},
        headers=headers,
    )
    return resp.status_code, resp.json() if resp.status_code == 200 else resp.text


def _attempt_mark_paid(client, headers, withdrawal_id):
    """Attempt to mark a withdrawal paid."""
    resp = client.put(
        f"/api/withdrawals/{withdrawal_id}/mark-paid",
        json={},
        headers=headers,
    )
    return resp.status_code


def _query_ledger_entries(client, reference_id, account, reference_type=None):
    """Query financial_ledger via the app portal."""

    async def _query():
        from shared.infrastructure.database import get_connection

        conn = get_connection()
        if reference_type:
            cursor = await conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM financial_ledger "
                "WHERE reference_id = ? AND account = ? AND reference_type = ?",
                (reference_id, account, reference_type),
            )
        else:
            cursor = await conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM financial_ledger "
                "WHERE reference_id = ? AND account = ?",
                (reference_id, account),
            )
        row = await cursor.fetchone()
        return row[0], float(row[1])

    return client.portal.call(_query)


@pytest.mark.timeout(30)
class TestConcurrencyExtended:
    """Race condition tests that verify data integrity under concurrent access."""

    def test_concurrent_po_receive_no_double_stock(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """Two concurrent receives of the same PO item must not double-count stock."""
        headers = admin_headers()
        product: dict[str, Any] = create_product(
            client, headers, dept_id=seed_dept_id, quantity=100, name="CC-PO-Race"
        )

        po, items = _create_po_pending(client, headers, product, quantity=50)

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_attempt_receive, client, headers, po["id"], items)
            f2 = pool.submit(_attempt_receive, client, headers, po["id"], items)

            [f.result() for f in as_completed([f1, f2])]

        resp = client.get(f"/api/catalog/skus/{product['id']}", headers=headers)
        final_qty: float = resp.json()["quantity"]

        assert final_qty == pytest.approx(150.0), (
            f"Stock should be 100 + 50 = 150 (not 200). Got {final_qty}"
        )

    def test_concurrent_cycle_count_commit_no_double_adjust(
        self, client: TestClient, seed_dept_id: str
    ) -> None:
        """Two concurrent commits of the same cycle count must not double-apply variances."""
        headers = admin_headers()
        product: dict[str, Any] = create_product(
            client, headers, dept_id=seed_dept_id, quantity=100, name="CC-CycleRace"
        )

        count = open_cycle_count(client, headers)
        count_id: str = count["id"]

        detail_resp = client.get(f"/api/cycle-counts/{count_id}", headers=headers)
        items: list[dict[str, Any]] = detail_resp.json().get("items", [])
        target_item: dict[str, Any] | None = next(
            (i for i in items if i["product_id"] == product["id"]), None
        )
        assert target_item is not None, "Product should be in cycle count"

        update_cycle_count_item(client, headers, count_id, target_item["id"], counted_qty=90)

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_attempt_commit, client, headers, count_id)
            f2 = pool.submit(_attempt_commit, client, headers, count_id)

            statuses = [f.result() for f in as_completed([f1, f2])]

        successes = sum(1 for s in statuses if s == 200)
        assert successes <= 1, f"At most one commit should succeed, got {successes}"

        resp = client.get(f"/api/catalog/skus/{product['id']}", headers=headers)
        final_qty: float = resp.json()["quantity"]
        assert final_qty == pytest.approx(90.0), (
            f"Stock should be 90 (adjusted once by -10), got {final_qty}"
        )

    def test_concurrent_mark_paid_single_ledger_entry(self, client, seed_dept_id):
        """Two concurrent mark-paid calls must produce exactly one AR ledger entry."""
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=50, name="CC-LedgerRace"
        )
        wd = create_withdrawal(client, headers, product, quantity=5)

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_attempt_mark_paid, client, headers, wd["id"])
            f2 = pool.submit(_attempt_mark_paid, client, headers, wd["id"])

            statuses = [f.result() for f in as_completed([f1, f2])]

        successes = [s for s in statuses if s == 200]
        assert len(successes) >= 1, "At least one mark-paid should succeed"

        resp = client.get(f"/api/withdrawals/{wd['id']}", headers=headers)
        assert resp.json()["payment_status"] == "paid"

        count, _total = _query_ledger_entries(
            client, wd["id"], "accounts_receivable", reference_type="payment"
        )
        assert count == 1, f"Expected exactly 1 AR ledger entry for payment, got {count}"

    def test_concurrent_invoice_creation_same_withdrawal(self, client, seed_dept_id):
        """Two concurrent invoice creations from the same withdrawal: exactly one succeeds."""
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=50, name="CC-InvRace"
        )
        wd = create_withdrawal(client, headers, product, quantity=5)

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_attempt_create_invoice, client, headers, [wd["id"]])
            f2 = pool.submit(_attempt_create_invoice, client, headers, [wd["id"]])

            results = [f.result() for f in as_completed([f1, f2])]

        successes = [r for r in results if r[0] == 200]
        assert len(successes) == 1, (
            f"Exactly one invoice creation should succeed, got {len(successes)}"
        )

        resp = client.get("/api/invoices", headers=headers)
        invoices = [inv for inv in resp.json() if wd["id"] in inv.get("withdrawal_ids", [])]
        assert len(invoices) <= 1, (
            f"Withdrawal should be on at most 1 invoice, found {len(invoices)}"
        )
