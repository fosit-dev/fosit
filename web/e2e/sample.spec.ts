// Realistic sample (250 metro areas, 26 weeks) on a phone-sized screen in dark mode:
// checks the mobile layout and how long the market search takes in the browser.
import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 }, colorScheme: "dark", hasTouch: true });

test("sample data flow works on mobile in dark mode", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Try it with sample data" }).click();
  await expect(page.getByText("Looks good")).toBeVisible({ timeout: 240_000 });
  await expect(page.getByText(/synthetic sample data/)).toBeVisible();
  await page.screenshot({ path: "test-results/m1-data.png", fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "no horizontal page scroll on mobile").toBeLessThanOrEqual(0);

  for (let i = 0; i < 3; i++) await page.getByRole("button", { name: "Continue →" }).click();
  const started = Date.now();
  await page.getByRole("button", { name: "Find fair market splits" }).click();
  await expect(page.getByRole("article", { name: "Design 1" })).toBeVisible({ timeout: 900_000 });
  console.log(`market search + power simulation took ${Math.round((Date.now() - started) / 1000)}s`);
  await page.getByRole("article", { name: "Design 1" }).getByRole("button", { name: /Show markets/ }).click();
  await page.getByRole("button", { name: /About Minimum detectable effect/ }).first().click();
  await page.screenshot({ path: "test-results/m2-designs.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});
