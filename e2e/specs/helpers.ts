import { type Page, type APIRequestContext, expect } from "@playwright/test";

const API = "http://localhost:8000";

// ── Auth ───────────────────────────────────────────────────────────────────────

export async function getAdminToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${API}/api/auth/login`, {
    data: { email: "admin@demo.local", password: "demo123" },
  });
  expect(resp.ok(), `Login failed: ${resp.status()}`).toBeTruthy();
  return (await resp.json()).token;
}

export function authHeader(token: string) {
  return { Authorization: `Bearer ${token}` };
}

// ── Seed ───────────────────────────────────────────────────────────────────────

export async function seedResetEmpty(request: APIRequestContext) {
  const resp = await request.post(`${API}/api/seed/reset-empty`);
  expect(resp.ok(), `Seed reset-empty failed: ${resp.status()}`).toBeTruthy();
}

// ── API helpers ────────────────────────────────────────────────────────────────

export async function apiGet(request: APIRequestContext, token: string, path: string) {
  const resp = await request.get(`${API}${path}`, { headers: authHeader(token) });
  expect(resp.ok(), `GET ${path} → ${resp.status()}`).toBeTruthy();
  return resp.json();
}

export async function apiPost(request: APIRequestContext, token: string, path: string, data: any) {
  const resp = await request.post(`${API}${path}`, {
    headers: { ...authHeader(token), "Content-Type": "application/json" },
    data,
  });
  expect(resp.ok(), `POST ${path} → ${resp.status()} — ${await resp.text()}`).toBeTruthy();
  return resp.json();
}

export async function apiPut(request: APIRequestContext, token: string, path: string, data?: any) {
  const resp = await request.put(`${API}${path}`, {
    headers: { ...authHeader(token), "Content-Type": "application/json" },
    data: data ?? {},
  });
  expect(resp.ok(), `PUT ${path} → ${resp.status()}`).toBeTruthy();
  return resp.json();
}

// ── UI helpers ─────────────────────────────────────────────────────────────────

export async function loginAsAdmin(page: Page) {
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByTestId("admin-login-email-input").fill("admin@demo.local");
  await page.getByTestId("admin-login-password-input").fill("demo123");
  await page.getByTestId("admin-login-submit-btn").click();
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("app-layout")).toBeVisible();
}

export async function screenshot(page: Page, name: string) {
  await page.screenshot({
    path: `test-results/screenshots/${name}.png`,
    fullPage: true,
  });
}

export async function navigateTo(page: Page, navLabel: string) {
  const sidebar = page.getByTestId("sidebar");
  const collapsed = await sidebar.evaluate((el) => el.getBoundingClientRect().width < 100);
  if (collapsed) {
    await page.getByTestId("sidebar-toggle").click();
    await page.waitForTimeout(300);
  }
  await page.getByTestId(`nav-${navLabel}`).click();
  await page.waitForLoadState("networkidle");
}

// ── Fixture: seed empty + get token + lookup IDs ───────────────────────────────

export interface SeedContext {
  token: string;
  deptIds: Record<string, string>; // code → id
  contractorId: string;
}

export async function freshSeed(request: APIRequestContext): Promise<SeedContext> {
  await seedResetEmpty(request);
  const token = await getAdminToken(request);
  const depts = await apiGet(request, token, "/api/departments");
  const deptIds: Record<string, string> = {};
  for (const d of depts) deptIds[d.code] = d.id;
  const contractors = await apiGet(request, token, "/api/contractors");
  return { token, deptIds, contractorId: contractors[0].id };
}
