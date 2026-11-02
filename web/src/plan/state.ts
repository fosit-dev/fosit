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

export type Template = "two_vendor" | "single" | "custom";

export type PlanState = {
  template: Template;
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

export const budgets = (s: PlanState) => s.split.map((p) => Math.round((s.totalBudget * p) / 100 * 100) / 100);

/** Planned pre-period in days: as requested, capped by the history available. */
export const preDays = (s: PlanState) => Math.min(s.preWeeks * 7, s.data?.summary.days ?? s.preWeeks * 7);

/** Anything that changes the market search makes old results stale. */
export const searchKey = (s: PlanState) =>
  JSON.stringify([s.data?.sha256, s.geoUnit, s.nCells, s.primaryKpi, s.excluded, s.shareMin, s.shareMax,
    s.durations, s.cooldown, preDays(s), s.permutations, s.seed]);

export const STEPS = ["Template", "Your test", "Sales data", "Markets", "Timing", "Find markets", "Lock & share"] as const;
