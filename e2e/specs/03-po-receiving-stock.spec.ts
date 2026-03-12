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
 * Story 3 — PO receiving increases stock and inventory cost
 *
 * Creates a low-stock product, creates a PO, receives it.
 * Verifies:
 * - Stock increases by received quantity
 * - Inventory cost on dashboard reflects new stock
 * - Stock history shows the receiving event
 * - Low stock resolves after receiving
 */

const PRODUCT = { name: "Deck Screws #8 3in Box/1000", price: 35.0, cost: 18.0, quantity: 5, min_stock: 20 };
const PO_QTY = 50;

test.describe.serial("Story 3: PO receiving and stock", () => {
  let ctx: SeedContext;
  let productId: string;
  let vendorName: string;

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    ctx = await freshSeed(page.request);
    const req = page.request;
    const t = ctx.token;

    const vendors = await apiGet(req, t, "/api/vendors");
    vendorName = vendors[0].name;

    const product = await apiPost(req, t, "/api/products", {
      ...PRODUCT,
      department_id: ctx.deptIds["HDW"],
      vendor_id: vendors[0].id,
    });
    productId = product.id;
    await page.close();
  });

  test("3a — product starts as low stock", async ({ request }) => {
    const stats = await apiGet(request, ctx.token, "/api/dashboard/stats");
    expect(stats.low_stock_count).toBeGreaterThanOrEqual(1);
  });

  test("3b — create PO and receive items increases stock", async ({ request }) => {
    const products = await apiGet(request, ctx.token, "/api/products");
    const p = products.find((x: any) => x.id === productId);
    const stockBefore = p.quantity;

    const statsBefore = await apiGet(request, ctx.token, "/api/dashboard/stats");
    const invCostBefore = statsBefore.inventory_cost;

    const po = await apiPost(request, ctx.token, "/api/purchase-orders", {
      vendor_name: vendorName,
      items: [{ product_id: productId, sku: p.sku, name: p.name, quantity: PO_QTY, cost: PRODUCT.cost }],
    });
    expect(po.status).toBe("ordered");

    await apiPost(request, ctx.token, `/api/purchase-orders/${po.id}/delivery`, {
      item_ids: po.items.map((i: any) => i.id),
    });

    await apiPost(request, ctx.token, `/api/purchase-orders/${po.id}/receive`, {
      items: po.items.map((i: any) => ({ id: i.id, received_qty: PO_QTY })),
    });

    const productsAfter = await apiGet(request, ctx.token, "/api/products");
    const pAfter = productsAfter.find((x: any) => x.id === productId);
    expect(pAfter.quantity).toBe(stockBefore + PO_QTY);

    const statsAfter = await apiGet(request, ctx.token, "/api/dashboard/stats");
    expect(statsAfter.inventory_cost).toBeCloseTo(invCostBefore + PRODUCT.cost * PO_QTY, 2);

    const history = await apiGet(request, ctx.token, `/api/stock/${productId}/history`);
    const receiving = history.history.find((h: any) => h.transaction_type === "receiving");
    expect(receiving).toBeTruthy();
    expect(receiving.quantity_delta).toBe(PO_QTY);
  });

  test("3c — low stock resolved after receiving", async ({ request, page }) => {
    const products = await apiGet(request, ctx.token, "/api/products");
    const p = products.find((x: any) => x.id === productId);
    expect(p.quantity).toBeGreaterThan(p.min_stock);

    await loginAsAdmin(page);
    await navigateTo(page, "purchase-orders");
    await page.waitForTimeout(1000);
    await screenshot(page, "03-purchase-orders");
    await navigateTo(page, "products");
    await page.waitForTimeout(1000);
    await screenshot(page, "03-products-after-receiving");
  });
});
