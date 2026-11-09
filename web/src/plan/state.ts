import type { Issue } from "../components/Issues";
import type { FindResult, Kpi, LockedPlan } from "../lib/plan";
import { nextMonday, todayUtc } from "../lib/dates";

export type GeoRow = { geo_id: string; name: string; share: number };
export type Summary = {
  first_date: string; last_date: string; days: number; weeks: number; geos: number;
  kpis: Kpi[]; totals: Record<string, number>; daily_totals: number[]; chart_kpi: Kpi;
};

export type LoadedData = {
  source: "upload" | "sample" | "orders";
  fileName: string;
  sha256: string;
  rows: number;
  summary: Summary;
  geos: GeoRow[];
  issues: Issue[];
  mappingName?: string;
  mappingSha256?: string;
};

export type Template = "two_vendor" | "single" | "custom" | "national_holdout" | "vendor_split";

export type PlanState = {
  template: Template;
  adsBeforeTest: "off" | "always_on" | "some" | null;   // national holdout only (METHODOLOGY.md §13.1)
  nCells: number;
  labels: string[];
  totalBudget: number;
  split: number[];              // percent per cell
  currency: string;
  testName: string;
  advertiserLabel: string;
  primaryKpi: Kpi;
  decisionBasis: "target_icpa" | "breakeven_iroas" | "planned_mde";
  targetIcpa: number | null;
  breakevenIroas: number | null;
  geoUnit: "cbsa" | "state" | "custom";
  data: LoadedData | null;
  excluded: Record<string, string>;
  shareMin: number;
  shareMax: number;
  durations: number[];          // test lengths (days) to compare
  cooldown: number;
  testStart: string;
  preWeeks: number;
  permutations: "moving_block" | "iid";
  fitPeriod: "auto" | "day" | "week";   // how the search judges twin fit (METHODOLOGY.md §9.3)
  seed: number;
  result: FindResult | null;
  resultKey: string;            // inputs the result was computed from; stale if they change
  chosen: number | null;
  duration: number;             // the test length the user picked
  coinFlip: number[] | null;
  confirmed: boolean[];
  datesFinal: boolean;
  includeDiagnostics: boolean;
  locked: LockedPlan | null;
};

export const DURATION_OPTIONS = [21, 28, 42, 56];

const randomSeed = () => crypto.getRandomValues(new Uint32Array(1))[0] % 2_000_000_000;

export function initialState(): PlanState {
  return {
    template: "two_vendor",
    adsBeforeTest: null,
    nCells: 2,
    labels: ["Cell 1", "Cell 2"],
    totalBudget: 100000,
    split: [50, 50],
    currency: "USD",
    testName: "",
    advertiserLabel: "",
    primaryKpi: "orders",
    decisionBasis: "planned_mde",
    targetIcpa: null,
    breakevenIroas: null,
    geoUnit: "cbsa",
    data: null,
    excluded: {},
    shareMin: 0.03,
    shareMax: 0.15,
    durations: [21, 28, 42, 56],
    cooldown: 7,
    testStart: nextMonday(todayUtc(), 14),
    preWeeks: 26,
    permutations: "moving_block",
    fitPeriod: "auto",
    seed: randomSeed(),
    result: null,
    resultKey: "",
    chosen: null,
    duration: 28,
    coinFlip: null,
    confirmed: [false, false],
    datesFinal: false,
    includeDiagnostics: true,
    locked: null,
  };
}

export function withCells(s: PlanState, n: number): Partial<PlanState> {
  const labels = Array.from({ length: n }, (_, i) => s.labels[i] ?? `Cell ${i + 1}`);
  const even = Math.floor(100 / n);
  const split = Array.from({ length: n }, (_, i) => (i === n - 1 ? 100 - even * (n - 1) : even));
  return { nCells: n, labels, split, confirmed: Array(n).fill(false), coinFlip: null };
}

/** METHODOLOGY.md §13: one campaign everywhere except a holdout, or (§13.7) vendors splitting every market that isn't held out. */
export const isHoldout = (s: Pick<PlanState, "template">) => s.template === "national_holdout" || s.template === "vendor_split";
export const isOneCampaign = (s: Pick<PlanState, "template">) => s.template === "national_holdout";

type Kind = "cells" | "campaign" | "split";
const kindOf = (t: Template): Kind => (t === "national_holdout" ? "campaign" : t === "vendor_split" ? "split" : "cells");
const SHARES: Record<Kind, { shareMin: number; shareMax: number }> = {
  cells: { shareMin: 0.03, shareMax: 0.15 },       // each cell's share
  campaign: { shareMin: 0.10, shareMax: 0.20 },    // the holdout's share
  split: { shareMin: 0.15, shareMax: 0.25 },       // the holdout's share
};

/** Switching design kind changes what the share sliders bound (each cell vs. the holdout) and resets the names. */
export function withTemplate(s: PlanState, template: Template, cells: number): Partial<PlanState> {
  const kind = kindOf(template);
  const changed = kind !== kindOf(s.template);
  return {
    template,
    ...withCells(s, cells),
    ...(changed ? { labels: kind === "campaign" ? ["Campaign"] : Array.from({ length: cells }, (_, i) => `Cell ${i + 1}`), ...SHARES[kind] } : {}),
    ...(changed && kind === "cells" ? { adsBeforeTest: null } : {}),
  };
}

export const budgets = (s: PlanState) => s.split.map((p) => Math.round((s.totalBudget * p) / 100 * 100) / 100);

/** Planned pre-period in days: as requested, capped by the history available. */
export const preDays = (s: PlanState) => Math.min(s.preWeeks * 7, s.data?.summary.days ?? s.preWeeks * 7);

/** Anything that changes the market search makes old results stale. */
export const searchKey = (s: PlanState) =>
  JSON.stringify([s.data?.sha256, s.geoUnit, isHoldout(s), s.nCells, s.primaryKpi, s.excluded, s.shareMin, s.shareMax,
    s.durations, s.cooldown, preDays(s), s.permutations, s.fitPeriod, s.seed]);

export const STEPS = ["Template", "Your test", "Sales data", "Markets", "Timing", "Find markets", "Lock & share"] as const;
