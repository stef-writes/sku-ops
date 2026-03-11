import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./specs",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: "http://localhost:8000",
    trace: "on-first-retry",
  },
  webServer: {
    command: "cd ../.. && ./bin/dev server",
    port: 8000,
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
