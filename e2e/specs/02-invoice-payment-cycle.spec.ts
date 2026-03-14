import { test, expect } from "@playwright/test";
import {
  freshSeed,
  apiGet,
  apiPost,
  loginAsAdmin,
  screenshot,
  navigateTo,
  type SeedContext,
} from "./helpers";

/**
 * Story 2 — Invoice & payment cycle
 *
 * Creates two withdrawals, invoices them together, records payment.
 * Verifies:
 * - Invoice total = sum of linked withdrawal totals
 * - After payment, unpaid balance drops to zero
 * - Withdrawal payment_status changes to "paid"
 */

const PRODUCTS = [
  { name: "PEX Pipe 1/2in 100ft", price: 42.0, cost: 25.0, quantity: 200, min_stock: 20 },
  { name: "Copper Fitting 1/2in Tee", price: 3.5, cost: 1.8, quantity: 500, min_stock: 50 },
];

test.describe.serial("Story 2: Invoice & payment cycle", () => {
  let ctx: SeedContext;
  let withdrawalIds: string[] = [];
  let expectedTotal = 0;
  let invoiceId: string;

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    ctx = await freshSeed(page.request);
    const req = page.request;
    const t = ctx.token;
    const deptId = ctx.categoryIds["PLU"];

    const pIds: string[] = [];
    for (const p of PRODUCTS) {
      const created = await apiPost(req, t, "/api/catalog/skus", { ...p, category_id: deptId });
      pIds.push(created.id);
    }
    await apiPost(req, t, "/api/jobs", { code: "JOB-INV-001" });

    const w1 = await apiPost(req, t, "/api/withdrawals/for-contractor", {
      contractor_id: ctx.contractorId,
      job_id: "JOB-INV-001",
      service_address: "200 Invoice Ave",
      items: [
        { product_id: pIds[0], quantity: 5 },
        { product_id: pIds[1], quantity: 20 },
      ],
    });
    const w2 = await apiPost(req, t, "/api/withdrawals/for-contractor", {
      contractor_id: ctx.contractorId,
      job_id: "JOB-INV-001",
      service_address: "200 Invoice Ave",
      items: [{ product_id: pIds[0], quantity: 3 }],
    });
    withdrawalIds = [w1.id, w2.id];
    expectedTotal = w1.total + w2.total;
    await page.close();
  });

  test("2a — invoice total matches sum of withdrawals", async ({ request }) => {
    const invoice = await apiPost(request, ctx.token, "/api/invoices", {
      withdrawal_ids: withdrawalIds,
    });
    invoiceId = invoice.id;

    expect(invoice.total).toBeCloseTo(expectedTotal, 2);
    expect(invoice.withdrawal_count).toBe(2);
    expect(invoice.status).toBe("draft");

    for (const wId of withdrawalIds) {
      const w = await apiGet(request, ctx.token, `/api/withdrawals/${wId}`);
      expect(w.invoice_id).toBe(invoiceId);
    }
  });

  test("2b — payment zeroes unpaid balance", async ({ request }) => {
    const statsBefore = await apiGet(request, ctx.token, "/api/dashboard/stats");
    expect(statsBefore.unpaid_total).toBeGreaterThan(0);

    await apiPost(request, ctx.token, "/api/payments", {
      invoice_id: invoiceId,
      amount: expectedTotal,
      method: "bank_transfer",
      reference: "TRF-E2E-001",
      payment_date: new Date().toISOString().split("T")[0],
    });

    for (const wId of withdrawalIds) {
      const w = await apiGet(request, ctx.token, `/api/withdrawals/${wId}`);
      expect(w.payment_status).toBe("paid");
    }

    const statsAfter = await apiGet(request, ctx.token, "/api/dashboard/stats");
    expect(statsAfter.unpaid_total).toBe(0);
  });

  test("2c — UI shows invoice and payment", async ({ page }) => {
    await loginAsAdmin(page);
    await navigateTo(page, "invoices");
    await page.waitForTimeout(1000);
    await screenshot(page, "02-invoices-page");
    await navigateTo(page, "payments");
    await page.waitForTimeout(1000);
    await screenshot(page, "02-payments-page");
    await navigateTo(page, "dashboard");
    await page.waitForTimeout(1000);
    await screenshot(page, "02-dashboard-after-payment");
  });
});
