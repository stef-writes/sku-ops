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
 * Story 5 — Margin and P&L accuracy across products/jobs
 *
 * Creates products with different margins across departments, issues withdrawals
 * to different jobs, then verifies:
 * - Dashboard revenue/COGS/profit match exact withdrawal sums
 * - Margin percentage is mathematically correct
 * - P&L report matches dashboard
 * - Inventory report shows correct remaining stock value
 */

const ITEMS = [
  { name: "2x4x8 SPF Stud", price: 6.5, cost: 3.8, qty: 100, wQty: 20, dept: "LUM" },
  { name: "Romex 12/2 250ft", price: 125.0, cost: 78.0, qty: 30, wQty: 4, dept: "ELE" },
  { name: "PVC Cement 8oz", price: 8.0, cost: 3.5, qty: 60, wQty: 10, dept: "PLU" },
];

test.describe.serial("Story 5: Margin and P&L accuracy", () => {
  let ctx: SeedContext;
  let totalRevenue = 0;
  let totalCost = 0;

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    ctx = await freshSeed(page.request);
    const req = page.request;
    const t = ctx.token;

    await apiPost(req, t, "/api/jobs", { code: "JOB-MARGIN-1" });
    await apiPost(req, t, "/api/jobs", { code: "JOB-MARGIN-2" });

    const pIds: string[] = [];
    for (const item of ITEMS) {
      const p = await apiPost(req, t, "/api/catalog/skus", {
        name: item.name,
        price: item.price,
        cost: item.cost,
        quantity: item.qty,
        min_stock: 5,
        category_id: ctx.categoryIds[item.dept],
      });
      pIds.push(p.id);
    }

    const w1 = await apiPost(req, t, "/api/withdrawals/for-contractor", {
      contractor_id: ctx.contractorId,
      job_id: "JOB-MARGIN-1",
      service_address: "300 Margin St",
      items: [
        { product_id: pIds[0], quantity: ITEMS[0].wQty },
        { product_id: pIds[1], quantity: ITEMS[1].wQty },
      ],
    });
    const w2 = await apiPost(req, t, "/api/withdrawals/for-contractor", {
      contractor_id: ctx.contractorId,
      job_id: "JOB-MARGIN-2",
      service_address: "400 Profit Blvd",
      items: [{ product_id: pIds[2], quantity: ITEMS[2].wQty }],
    });
    totalRevenue = w1.total + w2.total;
    totalCost = w1.cost_total + w2.cost_total;
    await page.close();
  });

  test("5a — dashboard financials match withdrawal sums", async ({ request }) => {
    const stats = await apiGet(request, ctx.token, "/api/dashboard/stats");

    expect(stats.range_revenue).toBeCloseTo(totalRevenue, 2);
    expect(stats.range_cogs).toBeCloseTo(totalCost, 2);
    expect(stats.range_gross_profit).toBeCloseTo(totalRevenue - totalCost, 2);

    const expectedMargin = ((totalRevenue - totalCost) / totalRevenue) * 100;
    expect(stats.range_margin_pct).toBeCloseTo(expectedMargin, 1);
  });

  test("5b — P&L report totals match", async ({ request }) => {
    const pl = await apiGet(request, ctx.token, "/api/reports/pl");
    expect(pl.summary.revenue).toBeCloseTo(totalRevenue, 2);
    expect(pl.summary.cogs).toBeCloseTo(totalCost, 2);
    expect(pl.summary.gross_profit).toBeCloseTo(totalRevenue - totalCost, 2);
  });

  test("5c — inventory report reflects remaining stock value", async ({ request }) => {
    const inv = await apiGet(request, ctx.token, "/api/reports/inventory");

    let expectedRetail = 0;
    let expectedCostValue = 0;
    for (const item of ITEMS) {
      const remaining = item.qty - item.wQty;
      expectedRetail += item.price * remaining;
      expectedCostValue += item.cost * remaining;
    }

    expect(inv.total_retail_value).toBeCloseTo(expectedRetail, 2);
    expect(inv.total_cost_value).toBeCloseTo(expectedCostValue, 2);
    expect(inv.unrealized_margin).toBeCloseTo(expectedRetail - expectedCostValue, 2);
  });

  test("5d — reports UI shows data", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/reports?tab=pl");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    await screenshot(page, "05-pl-report");
    await page.goto("/reports?tab=inventory");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    await screenshot(page, "05-inventory-report");
    await navigateTo(page, "dashboard");
    await page.waitForTimeout(1000);
    await screenshot(page, "05-dashboard-margins");
  });
});
