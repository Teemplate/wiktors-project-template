import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end config. The stack is brought up by `scripts/e2e.sh`, NOT by
 * Playwright's `webServer` option: the suite needs a migrated and seeded
 * database, which is several steps rather than one command, and the script
 * also has to tear the stack down again afterwards.
 */
export default defineConfig({
  testDir: "./e2e",
  // A hung page should fail the run, not the whole job's timeout budget.
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  // A test that only passes on a retry is flaky; make that visible locally.
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5273",
    // The trace is the only way to work out why a browser test failed on a
    // machine nobody can look at.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
