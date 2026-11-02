// National holdout (METHODOLOGY.md §13): plan one on the sample data, and read the shipped example.
import { readFileSync } from "node:fs";
import { expect, test, type Request } from "@playwright/test";

test("plans a national holdout on the sample data", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Plan a test" }).first().click();
  await page.getByRole("button", { name: /National campaign with a holdout/ }).click();
  const next = page.getByRole("button", { name: "Continue →" });
  await expect(next).toBeDisabled();
  await page.getByLabel("Yes, but only in some markets").check();
  await expect(page.getByText(/can't measure this cleanly/)).toBeVisible();
  await expect(next).toBeDisabled();
  await page.getByLabel(/No, it's off/).check();
  await next.click();

  await expect(page.getByLabel("Campaign name")).toHaveValue("Campaign");
  await page.getByLabel("Test name").fill("Holdout e2e");
  await next.click();
  await page.getByRole("button", { name: "Use sample data" }).click();
  await expect(page.getByText("Looks good")).toBeVisible({ timeout: 240_000 });
  await next.click();
  await expect(page.getByText(/keep every held-out market completely dark/)).toBeVisible();
  await next.click();
  await next.click();

  await page.getByRole("button", { name: "Find a fair holdout" }).click();
  const design = page.getByRole("article", { name: "Design 1" });
  await expect(design).toBeVisible({ timeout: 900_000 });
  await expect(design.getByText(/of sales held out/)).toBeVisible();
  await expect(design.getByText(/in the campaign's markets/)).toBeVisible();
  await design.getByRole("button", { name: /Show markets/ }).click();
  await expect(design.getByText(/Holdout markets vs their twin/)).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: "test-results/h1-designs.png", fullPage: true });
  await next.click();

  await page.getByLabel(/confirmed they can keep all \d+ held-out markets free of ads/).check();
  await page.getByLabel("Dates and budgets are final.").check();
  await page.getByRole("button", { name: "Lock plan" }).click();
  await expect(page.getByTestId("plan-hash")).toBeVisible();
  const [json] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download plan JSON" }).click()]);
  const plan = JSON.parse(readFileSync((await json.path())!, "utf8"));
  expect(plan.commitment.design).toEqual({ type: "national_holdout", ads_before_test: "off" });
  expect(plan.commitment.cells).toHaveLength(1);
  expect(plan.commitment.control.geo_ids.length).toBeGreaterThanOrEqual(10);
  const [pdf] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download plan PDF" }).click()]);
  expect(readFileSync((await pdf.path())!).subarray(0, 5).toString()).toBe("%PDF-");
});

test("reads the national-holdout example", async ({ page, baseURL }) => {
  const origin = new URL(baseURL!).origin;
  const requests: Request[] = [];
  page.on("request", (r) => requests.push(r));
  await page.goto("/");
  await page.getByRole("button", { name: "Read", exact: true }).click();
  await page.getByRole("button", { name: /Try the national-holdout example/ }).click();
  await expect(page.getByText(/National holdout · CTV campaign/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Run the analysis" })).toBeEnabled({ timeout: 240_000 });
  await page.getByRole("button", { name: "Run the analysis" }).click();
  await expect(page.getByRole("heading", { name: "3 · Honesty checks" })).toBeVisible({ timeout: 300_000 });
  await page.getByLabel("No, nothing else changed differently").check();
  const bottom = page.locator("section", { has: page.getByRole("heading", { name: /Bottom line/ }) });
  await expect(bottom.getByText(/CTV campaign drove .* incremental orders in its \d+ markets/)).toBeVisible();
  await expect(bottom.locator(".verdict").first()).toHaveText(/Positive lift/);
  await expect(page.getByText("Held-out markets (no ads)")).toBeVisible();
  await expect(page.getByText("Twin: what they'd have sold with the ads")).toBeVisible();
  await page.screenshot({ path: "test-results/h2-results.png", fullPage: true });
  const [pdf] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download report (PDF)" }).click()]);
  expect(readFileSync((await pdf.path())!).subarray(0, 5).toString()).toBe("%PDF-");
  expect(requests.filter((r) => !/^(data|blob):/.test(r.url()) && new URL(r.url()).origin !== origin).map((r) => r.url())).toEqual([]);
});
