import { expect, test } from "@playwright/test";

/**
 * Glue: web + api + postgres. The whole path, once: nginx serves the SPA,
 * proxies /api to the backend, the backend reaches a migrated Postgres, and the
 * seeded rows come back and render.
 *
 * Kept deliberately small. Its value is not coverage -- the unit tests cover
 * states -- it is that every layer is real. This is the test that catches a
 * missing /api proxy, an unapplied migration, or a container that starts and
 * then dies.
 */

const API = process.env.E2E_API_URL ?? "http://localhost:8273";

test("the api serves the seeded items", async ({ request }) => {
  const response = await request.get(`${API}/api/items`);
  expect(response.ok()).toBeTruthy();
  const items = await response.json();
  // scripts/e2e.sh already asserts this, but assert it here too so a failure
  // reads as "the seed did not take" rather than an inscrutable UI mismatch.
  expect(items.length).toBeGreaterThanOrEqual(3);
});

test("the page renders those items, through the nginx /api proxy", async ({ page }) => {
  await page.goto("/");

  // Not just "the list exists": an empty list would satisfy that while proving
  // nothing. Assert on seeded content.
  const list = page.getByTestId("items-list");
  await expect(list).toBeVisible();
  await expect(list.getByRole("listitem")).toHaveCount(3);
  await expect(page.getByText("First item")).toBeVisible();
});
