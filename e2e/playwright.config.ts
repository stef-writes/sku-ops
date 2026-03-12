import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./specs",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: 0,
  fullyParallel: false,
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "on",
    video: "retain-on-failure",
    actionTimeout: 15_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "cd .. && ./bin/dev server",
      port: 8000,
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: "cd .. && ./bin/dev ui",
      port: 3000,
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
