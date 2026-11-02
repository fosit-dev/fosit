// The privacy guarantee, tested from the outside: run the whole Plan flow on a file full of
// canary values and fail if ANY request leaves the app's origin or carries user data.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Request } from "@playwright/test";
import { canonicalize } from "../src/lib/jcs";

const FIXTURE = join(dirname(fileURLToPath(import.meta.url)), "fixtures", "canary_history.csv");
const CANARY = "CANARY7Q";

test("Plan flow keeps user data in the browser and produces a verifiable locked plan", async ({ page, baseURL }) => {
  const origin = new URL(baseURL!).origin;
  const requests: Request[] = [];
  page.on("request", (r) => requests.push(r));

  await page.goto("/");
  await expect(page.getByText("Your data never leaves this browser.")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Why this exists/ })).toBeVisible();
  await page.screenshot({ path: "test-results/01-why.png", fullPage: true });

  await page.getByRole("button", { name: "Plan a test" }).first().click();
  await page.getByRole("button", { name: "Continue →" }).click();
  await page.getByLabel("Test name").fill("E2E canary test");
  await page.getByRole("button", { name: "Continue →" }).click();

  await page.getByLabel(/My own market IDs/).check();
  await page.getByTestId("kpi-file").setInputFiles(FIXTURE);
  await expect(page.getByText("Looks good")).toBeVisible({ timeout: 240_000 });
  await page.screenshot({ path: "test-results/02-data.png", fullPage: true });
  await page.getByRole("button", { name: "Continue →" }).click();
  await page.getByRole("button", { name: "Continue →" }).click();

  for (const w of ["3 weeks", "6 weeks", "8 weeks"]) await page.getByRole("checkbox", { name: w }).uncheck();
  await page.getByRole("button", { name: "Continue →" }).click();

  await page.getByRole("button", { name: "Find fair market splits" }).click();
  await expect(page.getByRole("article", { name: "Design 1" })).toBeVisible({ timeout: 600_000 });
  await page.getByRole("article", { name: "Design 1" }).getByRole("button", { name: /Show markets/ }).click();
  await page.screenshot({ path: "test-results/03-designs.png", fullPage: true });
  await page.getByRole("button", { name: "Continue →" }).click();

  for (const box of await page.getByRole("checkbox").all()) await box.check();
  await page.getByRole("button", { name: "Lock plan" }).click();
  const shown = (await page.getByTestId("plan-hash").innerText()).replace(/\s+/g, "");
  expect(shown).toMatch(/^[0-9a-f]{64}$/);
  await page.screenshot({ path: "test-results/04-locked.png", fullPage: true });

  const [jsonDl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download plan JSON" }).click()]);
  const plan = JSON.parse(readFileSync((await jsonDl.path())!, "utf8"));
  const recomputed = createHash("sha256").update(canonicalize(plan.commitment)).digest("hex");
  expect(recomputed).toBe(shown);
  expect(plan.hash.value).toBe(shown);
  expect(plan.commitment.cells).toHaveLength(2);
  expect(plan.commitment.cells[0].geo_ids.every((g: string) => g.startsWith(CANARY))).toBe(true);

  const [pdfDl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download plan PDF" }).click()]);
  expect(readFileSync((await pdfDl.path())!).subarray(0, 5).toString()).toBe("%PDF-");
  await pdfDl.saveAs("test-results/plan.pdf");

  // --- the privacy assertions ---
  const offOrigin = requests.filter((r) => !r.url().startsWith("data:") && !r.url().startsWith("blob:") && new URL(r.url()).origin !== origin);
  expect(offOrigin.map((r) => r.url()), "requests to another origin").toEqual([]);
  const leaking = requests.filter((r) => r.url().includes(CANARY) || (r.postData() ?? "").includes(CANARY));
  expect(leaking.map((r) => r.url()), "requests carrying user data").toEqual([]);
  const writes = requests.filter((r) => !["GET", "HEAD"].includes(r.method()));
  expect(writes.map((r) => `${r.method()} ${r.url()}`), "non-GET requests").toEqual([]);

  // and the Content-Security-Policy would stop a cross-origin request even if code tried one
  const blocked = await page.evaluate(() => fetch("https://example.com/").then(() => false, () => true));
  expect(blocked).toBe(true);
});
