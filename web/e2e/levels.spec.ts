// The Plan screens adapt to the reader: plain words and pictures by default, the fewest questions at Brief,
// and the technical names only at Full (docs/UX_FLOW.md, "Plan module"). No sales data is needed for these steps.
import { expect, test } from "@playwright/test";

const JARGON = /\b(iCPA|iROAS|MDE|cells?|control markets|synthetic|crossover|permutation|pre-period)\b/i;

test("planning starts in plain words, with a picture of each test type", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Plan a test" }).first().click();
  await expect(page.getByRole("heading", { name: "How much detail do you want?" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Guided/ })).toHaveAttribute("aria-pressed", "true");

  // The question first, then three test types that answer it, each with a picture.
  await expect(page.getByRole("button", { name: /Which vendor brings more extra sales/ })).toHaveAttribute("aria-pressed", "true");
  const types = page.getByRole("group", { name: "Test type" });
  await expect(types.getByRole("button")).toHaveCount(3);
  await expect(types.getByRole("button", { name: /Each vendor in a few markets/ })).toHaveAttribute("aria-pressed", "true");
  await expect(types.getByRole("img").first()).toHaveAttribute("aria-label", /Vendor A: about 10% of sales; Vendor B: about 10% of sales; No test ads: about 80% of sales/);

  // The anatomy: five numbered steps; a step opens to say more.
  await expect(page.getByRole("heading", { name: "How this test works" })).toBeVisible();
  const step = page.getByRole("button", { name: /Step 3: Build a twin/ });
  await step.click();
  await expect(step).toHaveAttribute("aria-expanded", "true");
  await expect(step).toContainText("FOSIT fixes the mix before the test starts.");
  expect(await page.locator("main").innerText()).not.toMatch(JARGON);

  // The other question offers the other three test types, and the picture follows the choice.
  await page.getByRole("button", { name: /Do my ads bring extra sales/ }).click();
  await expect(types.getByRole("button", { name: /Ads in a few markets/ })).toHaveAttribute("aria-pressed", "true");
  await types.getByRole("button", { name: /Two halves take turns/ }).click();
  await expect(page.getByRole("button", { name: /Step 2: Take turns/ })).toContainText("Every 2 weeks");
  expect(await page.locator("main").innerText()).not.toMatch(JARGON);

  // Full names each test type the way an analyst does. Brief folds the explanation away.
  await page.getByRole("radio", { name: "Full", exact: true }).click();
  await expect(types.getByText("Geo crossover")).toBeVisible();
  await page.getByRole("radio", { name: "Brief", exact: true }).click();
  await expect(types.getByText("Geo crossover")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "How this test works" })).toHaveCount(0);
  await expect(page.locator("summary", { hasText: "How this test works" })).toBeVisible();
});

test("the questions use the reader's words, and the technical names appear only at Full", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Plan a test" }).first().click();
  await page.getByRole("button", { name: "Continue →" }).click();

  await expect(page.getByLabel("Vendor 1 name")).toHaveValue("Vendor A");
  await page.getByRole("combobox", { name: /What would make this worth it/ }).selectOption({ label: "I know the most I can pay for one extra order" });
  await expect(page.getByLabel(/The most you can pay for one extra order \(USD\)/)).toBeVisible();
  expect(await page.locator("main").innerText()).not.toMatch(JARGON);
  await expect(page.getByText(/Enter the most you can pay for one extra order/)).toBeVisible();

  await page.getByRole("radio", { name: "Full", exact: true }).click();
  await expect(page.getByLabel("Cell 1 name")).toHaveValue("Vendor A");
  await expect(page.getByLabel(/Target iCPA \(USD\)/)).toBeVisible();

  // Brief asks less: no optional advertiser field.
  await page.getByRole("radio", { name: "Brief", exact: true }).click();
  await expect(page.getByLabel(/Advertiser/)).toHaveCount(0);
  await expect(page.getByLabel("Vendor 1 name")).toBeVisible();
});

test("the intro shows how each kind of test works", async ({ page }) => {
  await page.goto("/");
  const demo = page.locator("div.card", { has: page.getByRole("heading", { name: "See how a test works" }) });
  await expect(demo.getByRole("button", { name: /Step 1: Split the markets/ })).toBeVisible();
  await demo.getByRole("button", { name: "A small business" }).click();
  await expect(demo.getByRole("button", { name: /Step 1: Two halves/ })).toBeVisible();
  await expect(demo.getByRole("img").first()).toHaveAttribute("aria-label", /Half A: about 50% of sales; Half B: about 50% of sales/);
});

test("the Python engine loads only when the person first uses the tool", async ({ page }) => {
  const engine: string[] = [];
  page.on("request", (r) => { if (/pyodide|fosit-core\.zip/.test(r.url())) engine.push(r.url()); });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Why this exists/ })).toBeVisible();
  await page.waitForTimeout(1500);
  expect(engine, "a visitor who only reads the page downloads no engine").toEqual([]);
  await page.getByRole("button", { name: "Plan a test" }).first().click();
  await expect.poll(() => engine.length, { timeout: 15_000 }).toBeGreaterThan(0);
});
