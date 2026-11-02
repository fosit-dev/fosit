// Read module end to end on the shipped two-vendor example, plus a tampered-plan check.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Request } from "@playwright/test";

const EXAMPLE = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "examples", "two_vendor");

test("reads the two-vendor example: verdicts, checks, exports, and no data leaves the browser", async ({ page, baseURL }) => {
  const origin = new URL(baseURL!).origin;
  const requests: Request[] = [];
  page.on("request", (r) => requests.push(r));
  await page.goto("/");
  await page.getByRole("button", { name: "Read", exact: true }).click();
  await page.getByRole("button", { name: /Try it with the example/ }).click();
  await expect(page.getByRole("button", { name: "Run the analysis" })).toBeEnabled({ timeout: 240_000 });
  await page.getByRole("button", { name: "Run the analysis" }).click();
  await expect(page.getByRole("heading", { name: "3 · Honesty checks" })).toBeVisible({ timeout: 300_000 });
  await expect(page.getByText("The plan is exactly the one fingerprinted before launch.")).toBeVisible();
  await expect(page.getByText("Answer the question above to see the results.")).toBeVisible();
  await page.getByLabel("No, nothing else changed differently").check();
  await expect(page.getByRole("heading", { name: /Bottom line/ })).toBeVisible();
  const bottom = page.locator("section", { has: page.getByRole("heading", { name: /Bottom line/ }) });
  await expect(bottom.getByText(/Vendor A drove/)).toBeVisible();
  await expect(bottom.locator(".verdict").first()).toHaveText(/Positive lift/);
  await expect(bottom.getByText(/Head-to-head:/)).toBeVisible();
  await page.screenshot({ path: "test-results/r1-results.png", fullPage: true });

  const [pdf] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download report (PDF)" }).click()]);
  await pdf.saveAs("test-results/report.pdf");
  expect(readFileSync("test-results/report.pdf").subarray(0, 5).toString()).toBe("%PDF-");
  const [csv] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Results (CSV)" }).click()]);
  const plan = JSON.parse(readFileSync(join(EXAMPLE, "plan.fosit-plan.json"), "utf8"));
  expect(readFileSync((await csv.path())!, "utf8")).toContain(plan.hash.value);
  const [cfg] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Analysis config/ }).click()]);
  const config = JSON.parse(readFileSync((await cfg.path())!, "utf8"));
  expect(config.plan_check.matches_anchor).toBe(true);
  expect(config.inputs.kpi_history.sha256).toMatch(/^[0-9a-f]{64}$/);

  expect(requests.filter((r) => !/^(data|blob):/.test(r.url()) && new URL(r.url()).origin !== origin).map((r) => r.url())).toEqual([]);
  expect(requests.filter((r) => !["GET", "HEAD"].includes(r.method())).map((r) => r.url())).toEqual([]);
});

test("a plan changed after launch is caught and the report is watermarked", async ({ page }) => {
  const plan = JSON.parse(readFileSync(join(EXAMPLE, "plan.fosit-plan.json"), "utf8"));
  const original = plan.hash.value;
  const tampered = structuredClone(plan);
  tampered.commitment.dates.test_end = "2026-09-27";       // someone shortened the test after the fact
  await page.goto("/");
  await page.getByRole("button", { name: "Read", exact: true }).click();
  await page.getByTestId("plan-file").setInputFiles({ name: "plan.fosit-plan.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(tampered)) });
  await page.getByLabel(/Paste the fingerprint/).fill(original);
  await expect(page.getByText("This isn't the plan that was locked before launch.")).toBeVisible();
  await page.locator('input[type="file"][accept=".json"]').last().setInputFiles({ name: "original.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(plan)) });
  await expect(page.getByText("commitment.dates.test_end")).toBeVisible();
  await page.getByTestId("read-kpi-file").setInputFiles(join(EXAMPLE, "kpi_history.csv"));
  await expect(page.getByRole("button", { name: "Run the analysis" })).toBeEnabled({ timeout: 240_000 });
  await page.getByRole("button", { name: "Run the analysis" }).click();
  await expect(page.getByText("NOT THE PRE-REGISTERED ANALYSIS")).toBeVisible({ timeout: 300_000 });
  await expect(page.locator(".check-tile.fail")).toContainText("Plan match");
});

test.describe("on a phone in dark mode", () => {
  test.use({ viewport: { width: 390, height: 844 }, colorScheme: "dark", hasTouch: true });
  test("Read results fit the screen", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Read", exact: true }).click();
    await page.getByRole("button", { name: /Try it with the example/ }).click();
    await expect(page.getByRole("button", { name: "Run the analysis" })).toBeEnabled({ timeout: 240_000 });
    await page.getByRole("button", { name: "Run the analysis" }).click();
    await page.getByLabel("No, nothing else changed differently").check({ timeout: 300_000 });
    await expect(page.getByRole("heading", { name: /Bottom line/ })).toBeVisible();
    await page.getByRole("heading", { name: "Vendor A", exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: "test-results/r2-mobile.png" });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
