import { describe, expect, it } from "vitest";
import { DESIGNS, GOALS, PLAN_LEVELS, anatomySteps, chanceWords, defaultLabel, designInfo, exampleSegments, goalOf, isDefaultLabel, nice, snap, tech } from "../src/lib/words";
import { GLOSSARY } from "../src/lib/glossary";
import { detectableValue, powerAtValue } from "../src/plan/StepFind";
import { initialState, withCells, withTemplate, type Template } from "../src/plan/state";
import type { PowerCurve } from "../src/lib/plan";

const sentences = (text: string) => text.split(/(?<=[.?!])\s+/).filter(Boolean);
const words = (sentence: string) => sentence.split(/\s+/).filter(Boolean).length;
const TEMPLATES = DESIGNS.map((d) => d.id);

// docs/UX_FLOW.md, "Writing": one idea per sentence, at most 25 words.
describe("plain words of the Plan screens", () => {
  it("keeps every sentence short", () => {
    const texts = [
      ...GOALS.flatMap((g) => [g.title, g.text]),
      ...DESIGNS.flatMap((d) => [d.title, d.text, d.good]),
      ...Object.values(PLAN_LEVELS),
      ...TEMPLATES.flatMap((t) => (["short", "long"] as const).flatMap((l) => [1, 2].flatMap((n) => anatomySteps(t, n, l).flatMap((s) => [s.t, s.x, s.m])))),
      ...[0, 0.03, 0.2, 0.6, 0.9].map((p) => chanceWords(p).text),
    ];
    for (const text of texts) for (const s of sentences(text)) expect(words(s), s).toBeLessThanOrEqual(25);
  });

  it("uses no test-design terms in what a newcomer reads first", () => {
    const first = [...GOALS.flatMap((g) => [g.title, g.text]), ...DESIGNS.flatMap((d) => [d.title, d.text, d.good]),
      ...TEMPLATES.flatMap((t) => anatomySteps(t, 2).flatMap((s) => [s.t, s.x, s.m]))].join(" ");
    for (const term of [/\bcells?\b/i, /\bMDE\b/, /\biCPA\b/, /\biROAS\b/, /\bcontrol\b/i, /synthetic/i, /crossover/i, /\bholdout\b/i, /incremental/i, /\blift\b/i, /\bpower\b/i, /p-value/i, /permutation/i])
      expect(first).not.toMatch(term);
  });

  it("names the technical term only at Full", () => {
    expect(tech("brief", "plain", "technical")).toBe("plain");
    expect(tech("guided", "plain", "technical")).toBe("plain");
    expect(tech("full", "plain", "technical")).toBe("technical");
    for (const d of DESIGNS) expect(d.technical.length).toBeGreaterThan(0);
  });

  it("says the idea before the term in each ⓘ title", () => {
    for (const k of ["mde", "icpa", "iroas", "fit", "balance", "power", "control", "cell", "preperiod"] as const)
      expect(GLOSSARY[k].title, k).toMatch(/^[A-Z][^()]+ \(.+\)$/);
  });
});

describe("test types", () => {
  it("offers three test types for each question, and one recommendation", () => {
    for (const g of GOALS) {
      expect(DESIGNS.filter((d) => d.goal === g.id)).toHaveLength(3);
      expect(goalOf(g.first)).toBe(g.id);
    }
    expect(DESIGNS.filter((d) => d.recommended).map((d) => d.id)).toEqual(["two_vendor"]);
  });

  it("draws a picture whose parts make the whole country", () => {
    for (const t of TEMPLATES) {
      const segs = exampleSegments(t, []);
      expect(segs.reduce((a, s) => a + s.share, 0), t).toBeCloseTo(1, 6);
      expect(segs.filter((s) => s.role !== "none")).toHaveLength(t === "crossover" ? 2 : designInfo(t).cells);
    }
    expect(exampleSegments("two_vendor", ["Roku", "Hulu"]).map((s) => s.label)).toEqual(["Roku", "Hulu", "No test ads"]);
    expect(exampleSegments("custom", Array(6).fill("")).reduce((a, s) => a + s.share, 0)).toBeCloseTo(1, 6);
  });

  it("has five steps for every test type", () => {
    for (const t of TEMPLATES) expect(anatomySteps(t, designInfo(t).cells)).toHaveLength(5);
    expect(anatomySteps("crossover", 1, "long")[1].x).toContain("4 weeks");
    expect(anatomySteps("crossover", 1, "short")[2].x).toContain("3 days");
  });
});

describe("names of the groups", () => {
  it("starts with neutral names that follow the test type", () => {
    const s = initialState();
    expect(s.labels).toEqual(["Vendor A", "Vendor B"]);
    expect(withTemplate(s, "national_holdout", 1).labels).toEqual(["Campaign"]);
    expect(withTemplate(s, "single", 1).labels).toEqual(["Campaign"]);
    expect(withTemplate(s, "vendor_split", 2).labels).toEqual(["Vendor A", "Vendor B"]);
    expect(withCells({ ...s, template: "custom" }, 4).labels).toEqual(["Vendor A", "Vendor B", "Vendor C", "Vendor D"]);
    for (const t of TEMPLATES) expect(isDefaultLabel(defaultLabel(t as Template, 0))).toBe(true);
  });

  it("keeps a name that the person typed", () => {
    const s = { ...initialState(), labels: ["Roku", "Vendor B"] };
    expect(withTemplate(s, "custom", 3).labels).toEqual(["Roku", "Vendor B", "Vendor C"]);
    expect(withTemplate(s, "single", 1).labels).toEqual(["Roku"]);
    expect(withTemplate({ ...s, template: "single", labels: ["Campaign"] }, "two_vendor", 2).labels).toEqual(["Vendor A", "Vendor B"]);
  });
});

describe("will the test see it?", () => {
  const curve: PowerCurve = { test_days: 28, windows: 20, mde: 0.05, baseline_test_total: 10_000, note: "",
    points: [{ effect: 0, power: 0.1 }, { effect: 0.05, power: 0.8 }, { effect: 0.1, power: 1 }] };

  it("turns the smallest visible effect into money", () => {
    expect(detectableValue(curve, 50_000, "orders")).toBeCloseTo(100, 6);      // 500 extra orders for 50,000
    expect(detectableValue({ ...curve, baseline_test_total: 1_000_000 }, 50_000, "revenue")).toBeCloseTo(1, 6);
    expect(detectableValue({ ...curve, mde: null }, 50_000, "orders")).toBeNull();
  });

  it("reads the chance from the simulation's curve", () => {
    expect(powerAtValue(curve, 50_000, 100, "orders")).toBeCloseTo(0.8, 6);    // exactly the smallest visible effect
    expect(powerAtValue(curve, 50_000, 50, "orders")).toBeCloseTo(1, 6);       // cheaper orders = a bigger effect
    expect(powerAtValue(curve, 50_000, 200, "orders")).toBeCloseTo(0.45, 6);   // dearer orders = a smaller effect
    expect(powerAtValue({ ...curve, baseline_test_total: 1_000_000 }, 50_000, 2, "revenue")).toBeCloseTo(1, 6);
    expect(powerAtValue(curve, 50_000, 0, "orders")).toBeNull();
  });

  it("says the chance in words, with the same thresholds as the reports", () => {
    expect(chanceWords(0.86)).toMatchObject({ tone: "ok" });
    expect(chanceWords(0.6)).toMatchObject({ tone: "warn" });
    expect(chanceWords(0.2)).toMatchObject({ tone: "err" });
    expect(chanceWords(0.01).text).toBe("The test will not see an effect this small.");
  });

  it("rounds slider values to numbers people say", () => {
    expect(nice(83.7)).toBe(100);
    expect(nice(27)).toBe(25);
    expect(snap(83.71)).toBe(84);
    expect(snap(1234)).toBe(1200);
  });
});
