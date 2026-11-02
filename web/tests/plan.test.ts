import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildCommitment, hashCommitment, lockPlan, validateCommitment, verifyPlan, type DesignResult, type LockedPlan, type PlanInputs } from "../src/lib/plan";

const fixture: LockedPlan = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "..", "tests", "fixtures", "plan_example.fosit-plan.json"), "utf8"));

const design: DesignResult = {
  cells: [["41740", "12060", "19100"], ["16980", "47900", "38060"]],
  control: ["35620", "31080", "14460"],
  shares: [0.08, 0.081], control_share: 0.8, balance: { share: 0.01 }, balance_score: 0.01,
  fit_screen: [0.05, 0.06], fit: [0.0541, 0.065], share_in_test: 0.161, power: null,
};

const inputs = (over: Partial<PlanInputs> = {}): PlanInputs => ({
  testName: "Test", advertiserLabel: "", currency: "USD", geoUnit: "cbsa", mappingName: "m", mappingSha256: "a".repeat(64),
  primaryKpi: "orders", secondaryKpis: ["revenue"], labels: ["Vendor A", "Vendor B"], budgets: [50000, 50000],
  testStart: "2026-11-30", testDays: 28, cooldownDays: 7, preDays: 175, design, designRank: 1, candidatesSearched: 2000,
  excluded: { "26420": "promo" }, permutations: "moving_block", alpha: 0.1, seed: 7, decisionBasis: "planned_mde",
  coinFlip: null, toolVersion: "0.1.0", coreSha256: "0".repeat(64), createdAt: "2026-11-02T12:00:00Z",
  dataFingerprint: { kpi_history_sha256: "b".repeat(64), rows: 10, geos: 7, first_date: "2026-05-04", last_date: "2026-11-01" },
  ...over,
});

describe("locked plan", () => {
  it("hashes the shared fixture exactly like the documented Python one-liner", async () => {
    expect(await hashCommitment(fixture.commitment)).toBe(fixture.hash.value);
    expect((await verifyPlan(fixture, fixture.hash.value.toUpperCase())).matchesAnchor).toBe(true);
  });

  it("builds a valid, sorted commitment with dates derived from the start date", () => {
    const c = buildCommitment(inputs());
    expect(validateCommitment(c)).toEqual([]);
    expect(c.dates).toEqual({ pre_start: "2026-06-08", pre_end: "2026-11-29", test_start: "2026-11-30", test_end: "2026-12-27", cooldown_end: "2027-01-03" });
    expect(c.cells[0].geo_ids).toEqual(["12060", "19100", "41740"]);
    expect(c.thresholds.pre_fit_nrmse_max.cell_1.orders).toBe(0.0812);
    expect(c.decision.primary_metric).toBe("delta_icpa");
  });

  it("coin flip swaps market sets but keeps labels and budgets with their cells", () => {
    const c = buildCommitment(inputs({ coinFlip: [1, 0], budgets: [60000, 40000] }));
    expect(c.cells[0]).toMatchObject({ label: "Vendor A", budget: 60000, geo_ids: ["16980", "38060", "47900"] });
    expect(c.assignment.coin_flip_result).toEqual({ market_set_1: "cell_2", market_set_2: "cell_1" });
  });

  it("detects tampering and overlapping markets", async () => {
    const plan = await lockPlan(buildCommitment(inputs()));
    const tampered = structuredClone(plan);
    tampered.commitment.cells[0].geo_ids.push("99999");
    const v = await verifyPlan(tampered, plan.hash.value);
    expect(v.selfConsistent).toBe(false);
    expect(v.matchesAnchor).toBe(false);
    const bad = buildCommitment(inputs({ design: { ...design, control: [...design.control, "41740"] } }));
    expect(validateCommitment(bad).join(" ")).toMatch(/41740/);
  });

  it("an attacker who also recomputes the internal hash is still caught by the anchor", async () => {
    const plan = await lockPlan(buildCommitment(inputs()));
    const forged = structuredClone(plan);
    forged.commitment.dates.test_end = "2027-01-10";
    forged.hash.value = await hashCommitment(forged.commitment);
    const v = await verifyPlan(forged, plan.hash.value);
    expect(v.selfConsistent).toBe(true);
    expect(v.matchesAnchor).toBe(false);
  });
});
