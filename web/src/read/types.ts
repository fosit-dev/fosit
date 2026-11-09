// Shapes returned by core/fosit/read.py::run_read (via api.run_read).

export type Interval = [number | null, number | null];

export type KpiResult = {
  kpi: "orders" | "revenue";
  att: number;
  p_value: number;
  pre_fit_nrmse: number;
  pre_fit_limit: number | null;
  pre_fit_period?: "day" | "week";
  pre_fit_ok: boolean;
  observed: number;
  counterfactual: number;
  incremental: number;
  lift: number;
  spend: number | null;
  per_1000?: number;
  icpa?: number | null;
  iroas?: number;
  intervals: Record<string, { incremental: Interval; lift: Interval; per_1000?: Interval; icpa?: Interval; iroas?: Interval }>;
  // role "holdout" (METHODOLOGY.md §13): observed = the held-out markets (no ads), counterfactual = their twin (with ads)
  series: { dates: string[]; observed: number[]; counterfactual: number[]; n_pre: number; test_days: number; role?: "cell" | "holdout" | "crossover" };
  // METHODOLOGY.md §5.6; null when the plan doesn't lock placebo calibration, n = 0 when no placebo could run
  placebo?: null | { n: number; quantiles?: Record<string, number>; p_value?: number; widened?: Record<string, boolean> };
  under_the_hood: {
    lambda: number | null;
    // crossover (§14): mean daily sales per half per block after the washout, and how many schedules were tested
    blocks?: { start: string; on: "A" | "B"; a_daily: number; b_daily: number }[];
    schedules_tested?: number;
    block_days?: number;
    washout_days?: number;
    top_weights: { geo_id: string; weight: number }[];
    negative_weight_sum: number;
    donors: number;
    dropped_donors: string[];
    tests_evaluated: number;
  };
};

export type Verdict = "positive" | "negative" | "no_detectable_lift" | "inconclusive";

export type CellResult = {
  id: string;
  label: string;
  budget: number;
  spend: number | null;
  n_geos: number;
  kpis: Record<string, KpiResult>;
  verdict: Verdict;
  verdict_reason: string;
  meaningful_effect: number | null;
  meaningful_basis: string;
  leakage: null | { impressions: number; leak_share: number; unverifiable_share: number; share: Record<string, number> };
};

export type H2HMetric = { estimate: number | null; null: number; intervals: Record<string, Interval | null>; distinguishable: boolean | null; note: string };
export type HeadToHead = { a: string; b: string; a_label: string; b_label: string; kpi: string; metrics: Record<string, H2HMetric> };

export type Check = { id: string; title: string; status: "pass" | "warn" | "fail"; blocking?: boolean; detail: string };

export type ReadResult = {
  ok: boolean;
  errors?: string[];
  design?: "geo_cells" | "national_holdout" | "crossover";
  interim: boolean;
  window: { pre_start: string; pre_end: string; start: string; end: string; planned_end: string; days: number; test_days: number };
  alpha: number;
  decision_level: number;
  levels: number[];
  permutations: { kind: string; n: number };
  primary_kpi: "orders" | "revenue";
  primary_metric: string;
  cells: CellResult[];
  head_to_head: HeadToHead[];
  checks: Check[];
  csv: string;
};
