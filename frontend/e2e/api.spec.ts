import { expect, test } from "@playwright/test";

/**
 * Glue: web + api. nginx proxies /api to the backend, same-origin. This is the
 * test that catches a missing /api proxy: if nginx served index.html for
 * /api/*, the payload would parse as HTML and fail.
 */

const API = process.env.E2E_API_URL ?? "http://localhost:8273";

test("health reports ok without touching the database", async ({ request }) => {
  const response = await request.get(`${API}/api/health`);
  expect(response.ok()).toBeTruthy();
  expect((await response.json()).ok).toBe(true);
});

test("the backend is reachable from the browser origin", async ({ page }) => {
  await page.goto("/");
  const payload = await page.evaluate(async () => {
    const r = await fetch("/api/health");
    return { type: r.headers.get("content-type"), body: await r.json() };
  });
  expect(payload.type).toContain("application/json");
  expect(payload.body.ok).toBe(true);
});

test("the page shows the api's greeting", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("hello")).toContainText("hello from");
});
