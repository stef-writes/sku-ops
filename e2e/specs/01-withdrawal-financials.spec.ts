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
 * Story 1 — Withdrawal creates correct financial entries
 *
 * Creates a product, issues a withdrawal via API, then verifies:
 * - Product stock decreased by the withdrawn quantity
 * - Dashboard revenue = withdrawal total
 * - Dashboard COGS = withdrawal cost_total
 * - Gross profit = revenue - COGS
 * - Unpaid balance = withdrawal total (not yet invoiced/paid)
 * - Stock history shows the decrement entry
 */

const PRODUCT = { name: "10AWG THHN Wire 500ft", price: 85.0, cost: 52.0, quantity: 50, min_stock: 5 };
const WITHDRAW_QTY = 3;

test.describe.serial("Story 1: Withdrawal financials", () => {
  let ctx: SeedContext;
  let productId: string;

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    ctx = await freshSeed(page.request);
    productId = (
      await apiPost(page.request, ctx.token, "/api/catalog/skus", {
        ...PRODUCT,
        category_id: ctx.categoryIds["ELE"],
      })
    ).id;
    await apiPost(page.request, ctx.token, "/api/jobs", { code: "JOB-E2E-001" });
    await page.close();
  });

  test("1a — product starts with correct stock", async ({ request }) => {
    const products = await apiGet(request, ctx.token, "/api/catalog/skus");
    const p = products.find((x: any) => x.id === productId);
    expect(p.quantity).toBe(PRODUCT.quantity);
    expect(p.price).toBe(PRODUCT.price);
    expect(p.cost).toBe(PRODUCT.cost);
  });

  test("1b — withdrawal decrements stock and records revenue", async ({ request }) => {
    const withdrawal = await apiPost(request, ctx.token, "/api/withdrawals/for-contractor", {
      contractor_id: ctx.contractorId,
      job_id: "JOB-E2E-001",
      service_address: "100 Test Lane",
      items: [{ product_id: productId, quantity: WITHDRAW_QTY }],
    });

    const item = withdrawal.items[0];
    expect(item.quantity).toBe(WITHDRAW_QTY);
    expect(item.unit_price).toBe(PRODUCT.price);
    expect(item.subtotal).toBeCloseTo(PRODUCT.price * WITHDRAW_QTY, 2);
    expect(withdrawal.cost_total).toBeCloseTo(PRODUCT.cost * WITHDRAW_QTY, 2);

    const products = await apiGet(request, ctx.token, "/api/catalog/skus");
    const p = products.find((x: any) => x.id === productId);
    expect(p.quantity).toBe(PRODUCT.quantity - WITHDRAW_QTY);

    const history = await apiGet(request, ctx.token, `/api/stock/${productId}/history`);
    const entry = history.history.find((h: any) => h.reference_type === "withdrawal");
    expect(entry).toBeTruthy();
    expect(entry.quantity_delta).toBe(-WITHDRAW_QTY);
    expect(entry.quantity_after).toBe(PRODUCT.quantity - WITHDRAW_QTY);
  });

  test("1c — dashboard revenue matches withdrawal", async ({ request, page }) => {
    const stats = await apiGet(request, ctx.token, "/api/dashboard/stats");
    const expectedRevenue = PRODUCT.price * WITHDRAW_QTY;
    const expectedCogs = PRODUCT.cost * WITHDRAW_QTY;

    expect(stats.range_revenue).toBeCloseTo(expectedRevenue, 2);
    expect(stats.range_cogs).toBeCloseTo(expectedCogs, 2);
    expect(stats.range_gross_profit).toBeCloseTo(expectedRevenue - expectedCogs, 2);
    expect(stats.unpaid_total).toBeCloseTo(expectedRevenue, 2);

    await loginAsAdmin(page);
    await navigateTo(page, "dashboard");
    await page.waitForTimeout(1000);
    await screenshot(page, "01-dashboard-after-withdrawal");
  });
});
