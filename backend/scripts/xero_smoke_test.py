"""
Xero sandbox smoke test — run manually before going live.

Fires real API calls against Xero. Always run against the SANDBOX organisation,
never production. Each test creates a document in DRAFT status and immediately
voids/deletes it, leaving Xero clean.

Usage:
    cd backend
    python -m scripts.xero_smoke_test --org-id <your_org_id>

Prerequisites:
  1. The org must be connected to Xero via OAuth (xero_access_token set).
  2. The Xero org must be a DEMO COMPANY / sandbox — not your live books.
  3. Account codes in org_settings must match actual account codes in that Xero org.

Exit codes:
  0 — all checks passed
  1 — one or more checks failed

The script is deliberately sequential and verbose so every failure is obvious.
"""
import argparse
import asyncio
import logging
import os
import sys

# Bootstrap Django-style: must happen before any app imports
os.environ.setdefault("ENV", "development")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("xero_smoke_test")

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
SKIP = "\033[33m–\033[0m"


class SmokeTestRunner:
    def __init__(self, org_id: str):
        self.org_id = org_id
        self.passed = 0
        self.failed = 0
        self.created_invoice_id: str | None = None
        self.created_bill_id: str | None = None
        self.created_cn_id: str | None = None

    def _ok(self, name: str, detail: str = "") -> None:
        self.passed += 1
        logger.info("%s  %s  %s", PASS, name, detail)

    def _fail(self, name: str, error: str) -> None:
        self.failed += 1
        logger.error("%s  %s  ERROR: %s", FAIL, name, error)

    def _skip(self, name: str, reason: str) -> None:
        logger.info("%s  %s  (skipped: %s)", SKIP, name, reason)

    # ── Setup ─────────────────────────────────────────────────────────────────

    async def _load(self):
        from shared.infrastructure.database import init_db
        await init_db()
        from identity.application.org_service import get_org_settings
        self.settings = await get_org_settings(self.org_id)
        from finance.adapters.xero_adapter import XeroAdapter
        self.adapter = XeroAdapter()

    # ── Check 1 — Token valid / refresh works ─────────────────────────────────

    async def check_token(self):
        name = "Token refresh"
        try:
            if not self.settings.xero_access_token:
                self._fail(name, "No access token — connect Xero first at /settings")
                return False
            if self.adapter._is_token_expired(self.settings):
                logger.info("  Token expired, attempting refresh...")
                self.settings = await self.adapter.refresh_token(self.settings)
                logger.info("  Refreshed. New expiry: %s", self.settings.xero_token_expiry)
            self._ok(name, f"tenant={self.settings.xero_tenant_id}")
            return True
        except Exception as e:
            self._fail(name, str(e))
            return False

    # ── Check 2 — Read-only ping: list tracking categories ───────────────────

    async def check_read_ping(self):
        name = "Read-only API ping (TrackingCategories)"
        try:
            categories = await self.adapter.list_tracking_categories(self.settings)
            self._ok(name, f"{len(categories)} categories found")
            return True
        except Exception as e:
            self._fail(name, str(e))
            return False

    # ── Check 3 — Create a DRAFT invoice ─────────────────────────────────────

    async def check_create_invoice(self):
        name = "Create DRAFT invoice (ACCREC)"
        test_invoice = {
            "id": "smoke-test-invoice",
            "invoice_number": "SMOKE-TEST-001",
            "billing_entity": "Smoke Test Customer",
            "status": "draft",
            "invoice_date": "2025-01-01T00:00:00Z",
            "due_date": "2025-01-31T00:00:00Z",
            "subtotal": 100.0,
            "tax": 15.0,
            "total": 115.0,
            "currency": "USD",
            "xero_invoice_id": None,
            "line_items": [
                {
                    "description": "SMOKE TEST LINE — safe to delete",
                    "quantity": 1,
                    "unit_price": 100.0,
                    "amount": 100.0,
                    "cost": 60.0,
                    "product_id": None,
                    "job_id": None,
                }
            ],
        }
        try:
            result = await self.adapter.sync_invoice(test_invoice, self.settings)
            if result.success and result.xero_invoice_id:
                self.created_invoice_id = result.xero_invoice_id
                self._ok(name, f"xero_invoice_id={result.xero_invoice_id}")
                return True
            self._fail(name, result.error or "No InvoiceID returned")
            return False
        except Exception as e:
            self._fail(name, str(e))
            return False

    # ── Check 4 — Fetch invoice back and verify total ─────────────────────────

    async def check_fetch_invoice(self):
        name = "Fetch invoice back from Xero"
        if not self.created_invoice_id:
            self._skip(name, "invoice creation failed")
            return False
        try:
            data = await self.adapter.fetch_invoice(self.created_invoice_id, self.settings)
            if not data:
                self._fail(name, "Empty response from Xero")
                return False
            # Xero may add tax rounding, allow small drift
            if abs(data["total"] - 115.0) > 0.05:
                self._fail(name, f"Total mismatch: expected 115.0, got {data['total']}")
                return False
            self._ok(name, f"total={data['total']}, lines={data['line_count']}, status={data['status']}")
            return True
        except Exception as e:
            self._fail(name, str(e))
            return False

    # ── Check 5 — Void the test invoice (cleanup) ─────────────────────────────

    async def check_void_invoice(self):
        name = "Void test invoice (cleanup)"
        if not self.created_invoice_id:
            self._skip(name, "no invoice to void")
            return True
        try:
            import httpx
            void_payload = {
                "Invoices": [{
                    "InvoiceID": self.created_invoice_id,
                    "Status": "VOIDED",
                }]
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.xero.com/api.xro/2.0/Invoices",
                    headers=self.adapter._auth_headers(self.settings),
                    json=void_payload,
                    timeout=20,
                )
            resp.raise_for_status()
            self._ok(name, f"voided {self.created_invoice_id}")
            self.created_invoice_id = None
            return True
        except Exception as e:
            self._fail(name, f"{e} — manually void invoice {self.created_invoice_id} in Xero")
            return False

    # ── Check 6 — Create a DRAFT Bill (ACCPAY) ───────────────────────────────

    async def check_create_bill(self):
        name = "Create DRAFT Bill (ACCPAY)"
        test_po = {
            "id": "smoke-test-po",
            "vendor_name": "Smoke Test Vendor",
            "document_date": "2025-01-01",
            "xero_bill_id": None,
            "items": [
                {"name": "SMOKE TEST ITEM — safe to delete", "delivered_qty": 5, "cost": 10.0},
            ],
        }
        try:
            result = await self.adapter.sync_po_receipt(test_po, 50.0, self.settings)
            if result.success and result.xero_invoice_id:
                self.created_bill_id = result.xero_invoice_id
                self._ok(name, f"xero_bill_id={result.xero_invoice_id}")
                return True
            self._fail(name, result.error or "No InvoiceID returned for bill")
            return False
        except Exception as e:
            self._fail(name, str(e))
            return False

    # ── Check 7 — Verify Bill is ACCPAY type ─────────────────────────────────

    async def check_bill_type(self):
        name = "Verify Bill is ACCPAY type in Xero"
        if not self.created_bill_id:
            self._skip(name, "bill creation failed")
            return False
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.xero.com/api.xro/2.0/Invoices/{self.created_bill_id}",
                    headers=self.adapter._auth_headers(self.settings),
                    timeout=15,
                )
            resp.raise_for_status()
            invoices = resp.json().get("Invoices", [])
            if not invoices:
                self._fail(name, "Bill not found in Xero")
                return False
            bill_type = invoices[0].get("Type")
            if bill_type != "ACCPAY":
                self._fail(name, f"Expected ACCPAY, got {bill_type!r}. This is NOT a Bill — it's not creating AP liability.")
                return False
            contact_name = invoices[0].get("Contact", {}).get("Name", "")
            self._ok(name, f"type={bill_type}, contact={contact_name!r}")
            return True
        except Exception as e:
            self._fail(name, str(e))
            return False

    # ── Check 8 — Void the test Bill (cleanup) ────────────────────────────────

    async def check_void_bill(self):
        name = "Void test Bill (cleanup)"
        if not self.created_bill_id:
            self._skip(name, "no bill to void")
            return True
        try:
            import httpx
            void_payload = {"Invoices": [{"InvoiceID": self.created_bill_id, "Status": "VOIDED"}]}
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.xero.com/api.xro/2.0/Invoices",
                    headers=self.adapter._auth_headers(self.settings),
                    json=void_payload,
                    timeout=20,
                )
            resp.raise_for_status()
            self._ok(name, f"voided {self.created_bill_id}")
            self.created_bill_id = None
            return True
        except Exception as e:
            self._fail(name, f"{e} — manually void bill {self.created_bill_id} in Xero")
            return False

    # ── Check 9 — Create a credit note ───────────────────────────────────────

    async def check_create_credit_note(self):
        name = "Create AUTHORISED credit note (ACCREC)"
        test_cn = {
            "id": "smoke-test-cn",
            "credit_note_number": "SMOKE-CN-001",
            "billing_entity": "Smoke Test Customer",
            "status": "applied",
            "created_at": "2025-01-01T00:00:00Z",
            "xero_credit_note_id": None,
            "line_items": [
                {
                    "description": "SMOKE TEST CREDIT — safe to delete",
                    "quantity": 1,
                    "unit_price": 50.0,
                    "amount": 50.0,
                    "cost": 30.0,
                }
            ],
        }
        try:
            result = await self.adapter.sync_credit_note(test_cn, self.settings)
            if result.success and result.xero_invoice_id:
                self.created_cn_id = result.xero_invoice_id
                self._ok(name, f"xero_credit_note_id={result.xero_invoice_id}")
                return True
            self._fail(name, result.error or "No CreditNoteID returned")
            return False
        except Exception as e:
            self._fail(name, str(e))
            return False

    # ── Check 10 — Void the credit note (cleanup) ─────────────────────────────

    async def check_void_credit_note(self):
        name = "Void test credit note (cleanup)"
        if not self.created_cn_id:
            self._skip(name, "no credit note to void")
            return True
        try:
            import httpx
            void_payload = {"CreditNotes": [{"CreditNoteID": self.created_cn_id, "Status": "VOIDED"}]}
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.xero.com/api.xro/2.0/CreditNotes",
                    headers=self.adapter._auth_headers(self.settings),
                    json=void_payload,
                    timeout=20,
                )
            resp.raise_for_status()
            self._ok(name, f"voided {self.created_cn_id}")
            self.created_cn_id = None
            return True
        except Exception as e:
            self._fail(name, f"{e} — manually void credit note {self.created_cn_id} in Xero")
            return False

    # ── Runner ────────────────────────────────────────────────────────────────

    async def run(self):
        logger.info("=" * 60)
        logger.info("Xero Smoke Test — org: %s", self.org_id)
        logger.info("=" * 60)

        await self._load()

        # Abort early if no token
        if not await self.check_token():
            logger.error("Aborting — cannot proceed without a valid Xero token.")
            return 1

        await self.check_read_ping()
        await self.check_create_invoice()
        await self.check_fetch_invoice()
        await self.check_void_invoice()
        await self.check_create_bill()
        await self.check_bill_type()
        await self.check_void_bill()
        await self.check_create_credit_note()
        await self.check_void_credit_note()

        logger.info("=" * 60)
        if self.failed == 0:
            logger.info(
                "%s  All %d checks passed. Xero integration is ready.",
                PASS, self.passed
            )
            return 0
        logger.error(
            "%d passed  %d FAILED — fix failures before enabling live sync.",
            self.passed, self.failed,
        )
        # Emergency: if we failed to clean up, remind the operator
        if self.created_invoice_id:
            logger.warning("ACTION REQUIRED: Manually void invoice %s in Xero", self.created_invoice_id)
        if self.created_bill_id:
            logger.warning("ACTION REQUIRED: Manually void bill %s in Xero", self.created_bill_id)
        if self.created_cn_id:
            logger.warning("ACTION REQUIRED: Manually void credit note %s in Xero", self.created_cn_id)
        return 1


async def _main(org_id: str) -> int:
    from shared.infrastructure.database import close_db
    runner = SmokeTestRunner(org_id)
    exit_code = await runner.run()
    await close_db()
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Xero sandbox smoke test")
    parser.add_argument(
        "--org-id", default="default",
        help="Organization ID to test against (default: 'default')",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args.org_id)))
