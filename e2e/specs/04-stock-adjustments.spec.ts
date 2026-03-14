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
 * Story 4 — Stock adjustments track correctly
 *
 * Creates a product, adjusts stock up and down via API.
 * Verifies:
 * - Quantity changes match the delta
 * - Stock history records each adjustment with correct reason
 * - Inventory cost on dashboard reflects adjusted quantity
 */

const PRODUCT = { name: "Interior Latex Paint 1gal White", price: 32.0, cost: 18.0, quantity: 25, min_stock: 5 };

test.describe.serial("Story 4: Stock adjustments", () => {
  let ctx: SeedContext;
  let productId: string;

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    ctx = await freshSeed(page.request);
    const product = await apiPost(page.request, ctx.token, "/api/catalog/skus", {
      ...PRODUCT,
      category_id: ctx.categoryIds["PNT"],
    });
    productId = product.id;
    await page.close();
  });

  test("4a — positive adjustment increases stock", async ({ request }) => {
    await apiPost(request, ctx.token, `/api/stock/${productId}/adjust`, {
      quantity_delta: 10,
      reason: "Correction",
    });

    const products = await apiGet(request, ctx.token, "/api/catalog/skus");
    const p = products.find((x: any) => x.id === productId);
    expect(p.quantity).toBe(PRODUCT.quantity + 10);

    const history = await apiGet(request, ctx.token, `/api/stock/${productId}/history`);
    const adj = history.history.find(
      (h: any) => h.transaction_type === "adjustment" && h.quantity_delta === 10
    );
    expect(adj).toBeTruthy();
    expect(adj.quantity_after).toBe(PRODUCT.quantity + 10);
  });

  test("4b — negative adjustment decreases stock", async ({ request }) => {
    await apiPost(request, ctx.token, `/api/stock/${productId}/adjust`, {
      quantity_delta: -3,
      reason: "Damage",
    });

    const products = await apiGet(request, ctx.token, "/api/catalog/skus");
    const p = products.find((x: any) => x.id === productId);
    expect(p.quantity).toBe(PRODUCT.quantity + 10 - 3);

    const history = await apiGet(request, ctx.token, `/api/stock/${productId}/history`);
    const adj = history.history.find(
      (h: any) => h.transaction_type === "adjustment" && h.quantity_delta === -3
    );
    expect(adj).toBeTruthy();
    expect(adj.reason).toBe("Damage");
  });

  test("4c — inventory cost reflects adjusted quantities", async ({ request, page }) => {
    const stats = await apiGet(request, ctx.token, "/api/dashboard/stats");
    const expectedCost = PRODUCT.cost * (PRODUCT.quantity + 10 - 3);
    expect(stats.inventory_cost).toBeCloseTo(expectedCost, 2);

    await loginAsAdmin(page);
    await navigateTo(page, "dashboard");
    await page.waitForTimeout(1000);
    await screenshot(page, "04-dashboard-after-adjustments");
  });
});
