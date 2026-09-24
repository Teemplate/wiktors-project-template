import { expect, test } from "@playwright/test";

/**
 * Block: web. The production nginx image serves the built SPA. Every project
 * with a web block runs this; the api and items specs sit alongside it and
 * leave with their blocks.
 */

test("the page renders", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("an unknown path falls back to the SPA, not a 404", async ({ page }) => {
  const response = await page.goto("/some/client/route");
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
