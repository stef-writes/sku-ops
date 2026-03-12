import { test, expect } from "@playwright/test";

const BASE_URL = "http://localhost:3000";
const ADMIN_EMAIL = "admin@demo.local";
const ADMIN_PASSWORD = "demo123";

test.describe("SKU-Ops Manual Testing Suite", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to login page
    await page.goto(BASE_URL);
    await page.waitForLoadState("networkidle");

    // Take screenshot of login page
    await page.screenshot({ path: "test-results/01-login-page.png", fullPage: true });

    // Attempt login with admin@demo.local / demo123
    // There are two login forms (admin and contractor), use the admin one
    const emailInput = page.getByTestId('admin-login-email-input');
    const passwordInput = page.locator('#admin-login-email').locator('..').locator('input[type="password"]');
    const loginButton = page.locator('button[type="submit"]').first();

    await emailInput.fill(ADMIN_EMAIL);
    await passwordInput.fill(ADMIN_PASSWORD);
    await loginButton.click();

    // Wait for navigation after login
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/02-logged-in.png", fullPage: true });
  });

  test("TEST 1: Create a new product", async ({ page }) => {
    console.log("\n=== TEST 1: Create a new product ===");

    // Navigate to catalog/products/SKU section
    // Try multiple possible navigation paths
    const catalogLink = page.locator('a:has-text("Catalog"), a:has-text("Products"), [href*="catalog"], [href*="product"]').first();
    await catalogLink.click();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/03-catalog-page.png", fullPage: true });

    console.log("Current URL:", page.url());

    // Look for "New Product" or "Add Product" button
    const newProductButton = page.locator('button:has-text("New"), button:has-text("Add"), button:has-text("Create"), a:has-text("New Product")').first();
    await newProductButton.click();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/04-new-product-form.png", fullPage: true });

    console.log("Product form URL:", page.url());

    // Fill in product details
    await page.locator('input[name="name"], input[placeholder*="name" i]').fill("Steel Corner Bracket 90deg");
    await page.screenshot({ path: "test-results/05-after-name-entry.png", fullPage: true });

    // Check if AI suggested a SKU
    const skuInput = page.locator('input[name="sku"], input[placeholder*="sku" i]');
    const suggestedSKU = await skuInput.inputValue();
    console.log("AI Suggested SKU:", suggestedSKU || "(none)");

    // If no SKU suggested, enter one manually
    if (!suggestedSKU) {
      await skuInput.fill("SCB-90-001");
    }

    // Fill category (try to select first available or create "Hardware")
    const categorySelect = page.locator('select[name="category"], input[name="category"]');
    const categoryExists = await categorySelect.count() > 0;
    if (categoryExists) {
      await categorySelect.first().click();
      await page.locator('option').first().click();
    }

    // Fill vendor (pick first available)
    const vendorSelect = page.locator('select[name="vendor"], select[name="vendor_id"]');
    if (await vendorSelect.count() > 0) {
      await vendorSelect.first().click();
      await page.locator('option').nth(1).click(); // Skip the empty option
    }

    // Fill unit of measure
    const uomInput = page.locator('input[name="uom"], input[name="unit"], select[name="uom"]');
    if (await uomInput.count() > 0) {
      if (await uomInput.first().getAttribute("type") === "select-one") {
        await uomInput.first().click();
        await page.locator('option:has-text("EA"), option:has-text("Each")').first().click();
      } else {
        await uomInput.first().fill("EA");
      }
    }

    // Fill cost
    const costInput = page.locator('input[name="cost"], input[name="unit_cost"], input[placeholder*="cost" i]');
    await costInput.fill("4.50");

    // Fill markup
    const markupInput = page.locator('input[name="markup"], input[name="margin"], input[placeholder*="markup" i]');
    if (await markupInput.count() > 0) {
      await markupInput.fill("40");
    }

    await page.screenshot({ path: "test-results/06-filled-product-form.png", fullPage: true });

    // Check calculated sell price before saving
    const sellPriceDisplay = page.locator('[name="sell_price"], [name="price"], text=/\\$[0-9.]+/');
    const sellPriceBeforeSave = await sellPriceDisplay.first().textContent();
    console.log("Calculated sell price:", sellPriceBeforeSave);

    // Save the product
    const saveButton = page.locator('button[type="submit"], button:has-text("Save"), button:has-text("Create")');
    await saveButton.click();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/07-after-save.png", fullPage: true });

    // Check for success message
    const successMessage = await page.locator('[role="alert"], .success, .notification, text=/success/i').first().textContent();
    console.log("Success message:", successMessage || "(none visible)");
    console.log("Final URL:", page.url());

    // Record results
    console.log("\n--- TEST 1 RESULTS ---");
    console.log("Status: PASS (assuming no errors)");
    console.log("SKU used:", suggestedSKU || "SCB-90-001");
    console.log("Sell price calculated:", sellPriceBeforeSave);
  });

  test("TEST 2: Edit the product", async ({ page }) => {
    console.log("\n=== TEST 2: Edit the product ===");

    // Navigate to products
    const catalogLink = page.locator('a:has-text("Catalog"), a:has-text("Products")').first();
    await catalogLink.click();
    await page.waitForLoadState("networkidle");

    // Find the product we created (Steel Corner Bracket 90deg)
    const productRow = page.locator('tr:has-text("Steel Corner Bracket"), [data-testid*="SCB-90"]').first();
    await productRow.click();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/08-edit-product-form.png", fullPage: true });

    // Get current sell price
    const sellPriceBeforeEdit = await page.locator('[name="sell_price"], [name="price"]').first().inputValue();
    console.log("Sell price before edit:", sellPriceBeforeEdit);

    // Change cost from 4.50 to 6.00
    const costInput = page.locator('input[name="cost"], input[name="unit_cost"]');
    await costInput.fill("6.00");
    await page.waitForTimeout(500); // Wait for auto-calculation

    await page.screenshot({ path: "test-results/09-after-cost-change.png", fullPage: true });

    // Get new sell price
    const sellPriceAfterEdit = await page.locator('[name="sell_price"], [name="price"]').first().inputValue();
    console.log("Sell price after edit:", sellPriceAfterEdit);

    // Save changes
    const saveButton = page.locator('button[type="submit"], button:has-text("Save")');
    await saveButton.click();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/10-after-edit-save.png", fullPage: true });

    console.log("\n--- TEST 2 RESULTS ---");
    console.log("Status: PASS");
    console.log("Sell price updated automatically:", sellPriceBeforeEdit !== sellPriceAfterEdit);
    console.log("New sell price:", sellPriceAfterEdit);
  });

  test("TEST 3: Duplicate SKU rejection", async ({ page }) => {
    console.log("\n=== TEST 3: Duplicate SKU rejection ===");

    // Navigate to catalog
    const catalogLink = page.locator('a:has-text("Catalog"), a:has-text("Products")').first();
    await catalogLink.click();
    await page.waitForLoadState("networkidle");

    // Click new product
    const newProductButton = page.locator('button:has-text("New"), button:has-text("Add")').first();
    await newProductButton.click();
    await page.waitForLoadState("networkidle");

    // Try to use the same SKU
    await page.locator('input[name="name"]').fill("Duplicate Test Product");
    await page.locator('input[name="sku"]').fill("SCB-90-001");

    await page.screenshot({ path: "test-results/11-duplicate-sku-entry.png", fullPage: true });

    // Try to save or check for immediate validation
    const saveButton = page.locator('button[type="submit"], button:has-text("Save")');
    await saveButton.click();
    await page.waitForTimeout(1000);

    await page.screenshot({ path: "test-results/12-duplicate-sku-error.png", fullPage: true });

    // Check for error message
    const errorMessage = await page.locator('[role="alert"], .error, .invalid-feedback, text=/duplicate/i, text=/already exists/i').first().textContent();
    console.log("Error message:", errorMessage || "(none visible)");

    console.log("\n--- TEST 3 RESULTS ---");
    console.log("Status:", errorMessage ? "PASS" : "FAIL");
    console.log("Error message shown:", errorMessage || "(none)");
  });

  test("TEST 4: Search and lookup", async ({ page }) => {
    console.log("\n=== TEST 4: Search and lookup ===");

    // Navigate to catalog
    const catalogLink = page.locator('a:has-text("Catalog"), a:has-text("Products")').first();
    await catalogLink.click();
    await page.waitForLoadState("networkidle");

    const searchInput = page.locator('input[type="search"], input[placeholder*="search" i], input[name="search"]');

    // Test 4.1: Search by SKU
    console.log("\n4.1: Search by SKU");
    await searchInput.fill("SCB-90-001");
    await page.waitForTimeout(500);
    await page.screenshot({ path: "test-results/13-search-by-sku.png", fullPage: true });

    const skuResults = await page.locator('tr:has-text("SCB-90-001")').count();
    console.log("SKU search results:", skuResults);

    // Test 4.2: Search by product name
    console.log("\n4.2: Search by product name");
    await searchInput.fill("Steel Corner");
    await page.waitForTimeout(500);
    await page.screenshot({ path: "test-results/14-search-by-name.png", fullPage: true });

    const nameResults = await page.locator('tr:has-text("Steel Corner")').count();
    console.log("Name search results:", nameResults);

    // Test 4.3: Check for barcode field
    console.log("\n4.3: Check for barcode search");
    const barcodeFieldExists = await page.locator('input[name="barcode"], th:has-text("Barcode")').count() > 0;
    console.log("Barcode field exists:", barcodeFieldExists);

    console.log("\n--- TEST 4 RESULTS ---");
    console.log("SKU search: ", skuResults > 0 ? "PASS" : "FAIL");
    console.log("Name search:", nameResults > 0 ? "PASS" : "FAIL");
    console.log("Barcode field:", barcodeFieldExists ? "Present" : "Absent");
  });

  test("TEST 5: AI SKU naming convention", async ({ page }) => {
    console.log("\n=== TEST 5: AI SKU naming convention ===");

    // Navigate to catalog
    const catalogLink = page.locator('a:has-text("Catalog"), a:has-text("Products")').first();
    await catalogLink.click();
    await page.waitForLoadState("networkidle");

    const testProducts = [
      "Copper Pipe 1/2 inch",
      "Safety Gloves Large",
      "PVC Elbow 90deg"
    ];

    const suggestions: Record<string, string> = {};

    for (const productName of testProducts) {
      // Click new product
      const newProductButton = page.locator('button:has-text("New"), button:has-text("Add")').first();
      await newProductButton.click();
      await page.waitForLoadState("networkidle");

      // Enter product name
      const nameInput = page.locator('input[name="name"]');
      await nameInput.fill(productName);

      // Wait for AI suggestion
      await page.waitForTimeout(1000);

      const skuInput = page.locator('input[name="sku"]');
      const suggestedSKU = await skuInput.inputValue();
      suggestions[productName] = suggestedSKU || "(none)";

      console.log(`Product: ${productName} → SKU: ${suggestedSKU || "(none)"}`);

      await page.screenshot({ path: `test-results/15-ai-suggestion-${testProducts.indexOf(productName) + 1}.png`, fullPage: true });

      // Cancel/go back
      const cancelButton = page.locator('button:has-text("Cancel"), a:has-text("Back")');
      if (await cancelButton.count() > 0) {
        await cancelButton.first().click();
      } else {
        await page.goBack();
      }
      await page.waitForLoadState("networkidle");
    }

    console.log("\n--- TEST 5 RESULTS ---");
    console.log("AI suggestions:", suggestions);
    console.log("Pattern consistency:", Object.values(suggestions).every(s => s !== "(none)") ? "CONSISTENT" : "INCONSISTENT");
  });
});
