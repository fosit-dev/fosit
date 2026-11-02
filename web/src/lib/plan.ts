// The locked plan: types, construction, hashing and verification.
// Spec: schema/locked_plan.schema.json and docs/PREREGISTRATION.md.

import { canonicalize, type Json } from "./jcs";
import { sha256Hex } from "./hash";
import { addDays } from "./dates";

// ---- results coming back from the Python core (core/fosit/api.py::find_designs) ----

export type PowerCurve = {
  test_days: number;
  pre_days?: number;
  windows: number;
  points: { effect: number; power: number }[];
  mde: number | null;
  false_positive_rate?: number;
  calibration_flag?: boolean;
  baseline_daily?: number;
  baseline_test_total?: number;
  note: string;
  money?: { mde_units: number | null; detectable_icpa: number | null; detectable_iroas: number | null };
};

export type DesignResult = {
  cells: string[][];
  control: string[];
  shares: number[];
  control_share: number;
  balance: Record<string, number>;
  balance_score: number;
  fit_screen: number[];
  fit: number[];
  share_in_test: number;
  power: { cells: { cell_index: number; curves: PowerCurve[] }[] } | null;
};

export type FindResult = {
  designs: DesignResult[];
  funnel: Record<string, number>;
  best_failing: DesignResult[];
  settings: { selection: Record<string, unknown>; power: Record<string, unknown> };
};

// ---- the plan itself ----

export type Kpi = "orders" | "revenue";

export type Commitment = {
  tool: { name: "FOSIT"; version: string; core_sha256: string };
  created_at: string;
  test_name: string;
  advertiser_label?: string;
  currency: string;
  geo: { unit: "cbsa" | "state" | "custom"; mapping_name: string; mapping_sha256: string };
  kpi: { primary: Kpi; secondary: Kpi[]; aggregation: "daily" | "weekly" };
  dates: { pre_start: string; pre_end: string; test_start: string; test_end: string; cooldown_end: string };
  cells: { id: string; label: string; geo_ids: string[]; budget: number }[];
  control: { geo_ids: string[] };
  excluded: { geo_ids: string[]; reasons?: Record<string, string> };
  method: {
    estimator: "ridge_ascm";
    fixed_effects: boolean;
    lambda_selection: "cv_1se";
    inference: "conformal";
    permutations: { kind: "moving_block" | "iid"; n?: number; seed?: number };
    test_statistic: "abs_sum";
    alpha: number;
    report_levels: number[];
    head_to_head: "joint_conformal_projection";
    donor_min_nonzero_share: number;
    seed: number;
  };
  thresholds: {
    pre_fit_nrmse_max: Record<string, Record<string, number>>;
    leakage_warn_share: number;
    spend_share_tolerance_pp: number;
    min_budget_delivery: number;
    power_target: number;
  };
  decision: {
    primary_metric: "delta_icpa" | "delta_iroas" | "delta_incremental_per_1000" | "cell_lift";
    meaningful_effect_basis: "target_icpa" | "breakeven_iroas" | "planned_mde";
    target_icpa?: number;
    breakeven_iroas?: number;
    planned_mde_lift?: Record<string, number>;
  };
  assignment: {
    method: "stratified_random_search";
    candidates_searched: number;
    design_rank: number;
    label_assignment: "user" | "coin_flip";
    coin_flip_result?: Record<string, string>;
  };
  vendor_targeting_confirmed: { cell_id: string; confirmed: true }[];
  data_fingerprint: { kpi_history_sha256: string; rows: number; geos: number; first_date: string; last_date: string };
};

export type LockedPlan = {
  fosit_plan_version: "1.0";
  commitment: Commitment;
  hash: { algorithm: "SHA-256"; canonicalization: "RFC8785"; value: string };
  appendix?: Record<string, unknown>;
};

/** Round to a schema-safe decimal (see SCHEMA.md §6: numbers stay within [0.0001, 1e15)). */
export const round = (x: number, digits: number) => {
  const r = Math.round(x * 10 ** digits) / 10 ** digits;
  return Math.abs(r) < 1e-4 && r !== 0 ? 0.0001 * Math.sign(r) : r;
};

export type PlanInputs = {
  testName: string;
  advertiserLabel: string;
  currency: string;
  geoUnit: "cbsa" | "state" | "custom";
  mappingName: string;
  mappingSha256: string;
  primaryKpi: Kpi;
  secondaryKpis: Kpi[];
  labels: string[];                 // index = market-set index in the design
  budgets: number[];                // index = market-set index
  testStart: string;
  testDays: number;
  cooldownDays: number;
  preDays: number;
  design: DesignResult;
  designRank: number;
  candidatesSearched: number;
  excluded: Record<string, string>;
  permutations: "moving_block" | "iid";
  alpha: number;
  seed: number;
  decisionBasis: "target_icpa" | "breakeven_iroas" | "planned_mde";
  targetIcpa?: number;
  breakevenIroas?: number;
  coinFlip?: number[] | null;       // coinFlip[setIndex] = cell index the set was assigned to
  plannedMde?: (number | null)[];   // index = market-set index; locked so "no detectable lift" can't be redefined later
  dataFingerprint: Commitment["data_fingerprint"];
  toolVersion: string;
  coreSha256: string;
  createdAt: string;
};

const sorted = (xs: string[]) => [...xs].sort();

/** Turn wizard inputs plus the chosen design into the plan's hashed commitment. */
export function buildCommitment(p: PlanInputs): Commitment {
  const n = p.design.cells.length;
  const order = p.coinFlip ?? Array.from({ length: n }, (_, i) => i);
  // cell k receives market set s where order[s] = k
  const cells = Array.from({ length: n }, (_, k) => {
    const s = order.indexOf(k);
    return { id: `cell_${k + 1}`, label: p.labels[k], geo_ids: sorted(p.design.cells[s]), budget: round(p.budgets[k], 2) };
  });
  const kpis: Kpi[] = [p.primaryKpi, ...p.secondaryKpis.filter((k) => k !== p.primaryKpi)];
  const fitByCell: Record<string, Record<string, number>> = {};
  cells.forEach((c, k) => {
    const fit = p.design.fit[order.indexOf(k)];
    const limit = round(Math.max(Math.min(1.5 * fit, 0.15), 0.0001), 4);
    fitByCell[c.id] = Object.fromEntries(kpis.map((kpi) => [kpi, limit]));
  });
  const preEnd = addDays(p.testStart, -1);
  const testEnd = addDays(p.testStart, p.testDays - 1);
  const c: Commitment = {
    tool: { name: "FOSIT", version: p.toolVersion, core_sha256: p.coreSha256 },
    created_at: p.createdAt,
    test_name: p.testName.trim(),
    currency: p.currency,
    geo: { unit: p.geoUnit, mapping_name: p.mappingName, mapping_sha256: p.mappingSha256 },
    kpi: { primary: p.primaryKpi, secondary: kpis.slice(1), aggregation: "daily" },
    dates: {
      pre_start: addDays(preEnd, -(p.preDays - 1)),
      pre_end: preEnd,
      test_start: p.testStart,
      test_end: testEnd,
      cooldown_end: addDays(testEnd, p.cooldownDays),
    },
    cells,
    control: { geo_ids: sorted(p.design.control) },
    excluded: { geo_ids: sorted(Object.keys(p.excluded)), reasons: { ...p.excluded } },
    method: {
      estimator: "ridge_ascm",
      fixed_effects: true,
      lambda_selection: "cv_1se",
      inference: "conformal",
      permutations: p.permutations === "iid" ? { kind: "iid", n: 1000, seed: p.seed } : { kind: "moving_block" },
      test_statistic: "abs_sum",
      alpha: p.alpha,
      report_levels: [0.9, 0.95],
      head_to_head: "joint_conformal_projection",
      donor_min_nonzero_share: 0.5,
      seed: p.seed,
    },
    thresholds: {
      pre_fit_nrmse_max: fitByCell,
      leakage_warn_share: 0.05,
      spend_share_tolerance_pp: 5,
      min_budget_delivery: 0.9,
      power_target: 0.8,
    },
    decision: {
      primary_metric: n === 1 ? "cell_lift" : p.primaryKpi === "orders" ? "delta_icpa" : "delta_iroas",
      meaningful_effect_basis: p.decisionBasis,
      ...(p.decisionBasis === "target_icpa" && p.targetIcpa ? { target_icpa: round(p.targetIcpa, 2) } : {}),
      ...(p.decisionBasis === "breakeven_iroas" && p.breakevenIroas ? { breakeven_iroas: round(p.breakevenIroas, 4) } : {}),
      ...(p.plannedMde?.some((m) => m)
        ? { planned_mde_lift: Object.fromEntries(cells.flatMap((cell, k) => {
            const m = p.plannedMde![order.indexOf(k)];
            return m ? [[cell.id, round(m, 4)]] : [];
          })) }
        : {}),
    },
    assignment: {
      method: "stratified_random_search",
      candidates_searched: p.candidatesSearched,
      design_rank: p.designRank,
      label_assignment: p.coinFlip ? "coin_flip" : "user",
      ...(p.coinFlip ? { coin_flip_result: Object.fromEntries(p.coinFlip.map((k, s) => [`market_set_${s + 1}`, `cell_${k + 1}`])) } : {}),
    },
    vendor_targeting_confirmed: cells.map((cell) => ({ cell_id: cell.id, confirmed: true as const })),
    data_fingerprint: p.dataFingerprint,
  };
  if (p.advertiserLabel.trim()) c.advertiser_label = p.advertiserLabel.trim();
  if (!Object.keys(p.excluded).length) delete c.excluded.reasons;
  return c;
}

/** Cross-field rules from SCHEMA.md §6. Returns human-readable problems (empty = valid). */
export function validateCommitment(c: Commitment): string[] {
  const problems: string[] = [];
  const d = c.dates;
  if (!(d.pre_start < d.pre_end && d.pre_end < d.test_start && d.test_start <= d.test_end && d.test_end <= d.cooldown_end))
    problems.push("Dates must run pre-period → test → cooldown, in order.");
  const seen = new Map<string, string>();
  const lists: [string, string[]][] = [
    ...c.cells.map((cell) => [cell.label, cell.geo_ids] as [string, string[]]),
    ["control", c.control.geo_ids],
    ["excluded", c.excluded.geo_ids],
  ];
  for (const [name, ids] of lists) {
    if (ids.join("\n") !== sorted(ids).join("\n")) problems.push(`${name}: geo list must be sorted.`);
    for (const g of ids) {
      if (seen.has(g)) problems.push(`Market ${g} is in both ${seen.get(g)} and ${name}.`);
      seen.set(g, name);
    }
  }
  const labels = c.cells.map((x) => x.label.trim());
  if (new Set(labels).size !== labels.length || labels.some((l) => !l)) problems.push("Cell labels must be unique and non-empty.");
  if (c.vendor_targeting_confirmed.length !== c.cells.length) problems.push("Every cell's targeting must be confirmed.");
  const walk = (v: unknown, path: string) => {
    if (typeof v === "number" && v !== 0 && !Number.isInteger(v) && (Math.abs(v) < 1e-4 || Math.abs(v) >= 1e15))
      problems.push(`${path}: number out of the hash-safe range.`);
    else if (v && typeof v === "object") Object.entries(v).forEach(([k, x]) => walk(x, `${path}.${k}`));
  };
  walk(c, "commitment");
  return problems;
}

export async function hashCommitment(c: Commitment): Promise<string> {
  return sha256Hex(canonicalize(c as unknown as Json));
}

export async function lockPlan(c: Commitment, appendix?: Record<string, unknown>): Promise<LockedPlan> {
  const problems = validateCommitment(c);
  if (problems.length) throw new Error(problems.join(" "));
  const plan: LockedPlan = {
    fosit_plan_version: "1.0",
    commitment: c,
    hash: { algorithm: "SHA-256", canonicalization: "RFC8785", value: await hashCommitment(c) },
  };
  if (appendix) plan.appendix = appendix;
  return plan;
}

/** Self-consistency check used at read time (PREREGISTRATION.md, "The ritual" step 4). */
export async function verifyPlan(plan: LockedPlan, anchorHash?: string) {
  const recomputed = await hashCommitment(plan.commitment);
  return {
    recomputed,
    selfConsistent: recomputed === plan.hash.value,
    matchesAnchor: anchorHash ? recomputed === anchorHash.replace(/\s+/g, "").toLowerCase() : null,
  };
}
