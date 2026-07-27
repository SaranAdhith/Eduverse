import { defineConfig, devices } from "@playwright/test";

// DOC_07 §7: E2E runs the built frontend against a docker-compose'd test DB with
// seed data + cached content chunks, so the LLM-dependent endpoints are offline.
const PORT = Number(process.env.E2E_PORT ?? 3000);
const BASE_URL = process.env.E2E_BASE_URL ?? `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  // Start the frontend for the tests. The backend is expected to already be
  // running at NEXT_PUBLIC_API_URL (spun up by the CI/dev harness with seed data).
  webServer: {
    command: process.env.E2E_BUILD
      ? "pnpm build && pnpm start"
      : "pnpm dev",
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
