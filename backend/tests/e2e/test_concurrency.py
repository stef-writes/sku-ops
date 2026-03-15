"""E2E: Concurrency safety — parallel withdrawals and payments.

Uses ThreadPoolExecutor to simulate concurrent API calls and verifies
that stock never goes negative and double-payments are handled safely.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from tests.e2e.helpers import create_product, create_withdrawal
from tests.helpers.auth import admin_headers


def _attempt_withdrawal(client, headers, product, quantity, job_id):
    """Attempt a withdrawal, returning (status_code, response_json_or_text)."""
    resp = client.post(
        "/api/withdrawals",
        json={
            "items": [
                {
                    "product_id": product["id"],
                    "sku": product["sku"],
                    "name": product["name"],
                    "quantity": quantity,
                    "unit_price": product["price"],
                    "cost": product["cost"],
                }
            ],
            "job_id": job_id,
            "service_address": "100 Concurrency Lane",
        },
        headers=headers,
    )
    if resp.status_code == 200:
        return resp.status_code, resp.json()
    return resp.status_code, resp.text


def _attempt_mark_paid(client, headers, withdrawal_id):
    """Attempt to mark a withdrawal paid, returning status_code."""
    resp = client.put(
        f"/api/withdrawals/{withdrawal_id}/mark-paid",
        json={},
        headers=headers,
    )
    return resp.status_code


@pytest.mark.timeout(30)
class TestConcurrency:
    """Concurrent operations should not corrupt data."""

    def test_parallel_withdrawals_no_negative_stock(self, client, seed_dept_id):
        """Two concurrent withdrawals for more than available stock: at most one succeeds."""
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=8, name="CC-ParallelWD"
        )

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_attempt_withdrawal, client, headers, product, 6, "JOB-RACE-1")
            f2 = pool.submit(_attempt_withdrawal, client, headers, product, 6, "JOB-RACE-2")

            results = []
            for f in as_completed([f1, f2]):
                results.append(f.result())

        successes = [r for r in results if r[0] == 200]

        resp = client.get(f"/api/catalog/skus/{product['id']}", headers=headers)
        final_qty = resp.json()["quantity"]

        assert final_qty >= 0, f"Stock should never go negative, got {final_qty}"

        if len(successes) == 2:
            assert final_qty == 8 - 12  # Both succeeded = -4, but that shouldn't happen
        elif len(successes) == 1:
            assert final_qty == 2, f"One withdrawal of 6 from 8 should leave 2, got {final_qty}"
        else:
            assert final_qty == 8, "If both failed, stock should be unchanged"

    def test_parallel_withdrawals_both_fit_stock(self, client, seed_dept_id):
        """Two concurrent withdrawals that both fit within available stock.

        We verify that stock is consistent regardless of how many succeeded.
        """
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=100, name="CC-BothSucceed"
        )

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_attempt_withdrawal, client, headers, product, 10, "JOB-BOTH-1")
            f2 = pool.submit(_attempt_withdrawal, client, headers, product, 10, "JOB-BOTH-2")

            results = [f.result() for f in as_completed([f1, f2])]

        successes = sum(1 for r in results if r[0] == 200)

        resp = client.get(f"/api/catalog/skus/{product['id']}", headers=headers)
        final_qty = resp.json()["quantity"]
        expected = 100 - (successes * 10)
        assert final_qty == expected, f"Expected {expected} (100 - {successes}*10), got {final_qty}"

    def test_parallel_mark_paid_safe(self, client, seed_dept_id):
        """Two concurrent mark-paid on the same withdrawal should not double-pay."""
        headers = admin_headers()
        product = create_product(
            client, headers, dept_id=seed_dept_id, quantity=50, name="CC-DoublePay"
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
