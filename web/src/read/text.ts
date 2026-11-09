// Plain-English rendering of results. Shared by the screen and the PDF report so they always agree.
import { money, num, pct } from "../lib/format";
import type { CellResult, H2HMetric, HeadToHead, Interval, KpiResult, ReadResult, Verdict } from "./types";

export const VERDICT: Record<Verdict, { icon: string; label: string; tone: "ok" | "neutral" | "warn" }> = {
  positive: { icon: "✓", label: "Positive lift", tone: "ok" },
  no_detectable_lift: { icon: "–", label: "No detectable lift", tone: "neutral" },
  inconclusive: { icon: "?", label: "Inconclusive", tone: "neutral" },
  negative: { icon: "!", label: "Negative lift: investigate", tone: "warn" },
};

/** Chart wording. In a national holdout the real line is the held-out markets and the twin shows them *with* the ads (§13.4). */
export const impactLabels = (holdout: boolean, crossover = false) => crossover
  ? { real: "Sales, both halves", twin: "Without the ads (estimated)", aria: "daily", twinAria: "the estimate without the ads" }
  : holdout
  ? { real: "Held-out markets (no ads)", twin: "Twin: what they'd have sold with the ads", aria: "the held-out markets' daily", twinAria: "their twin's estimate with ads" }
  : { real: "What happened", twin: "Twin: what would have happened without ads", aria: "daily", twinAria: "the twin's estimate without ads" };

export const levelKey = (r: ReadResult) => String(r.decision_level);
export const levelPct = (r: ReadResult) => pct(r.decision_level, 0);

const fmtUnit = (kpi: string, x: number | null | undefined, currency: string) =>
  kpi === "revenue" ? money(x, currency) : num(x);

export function rangeText(iv: Interval | undefined, f: (x: number | null) => string): string {
  if (!iv) return "–";
  const [lo, hi] = iv;
  if (lo == null && hi == null) return "not defined";
  if (hi == null) return `at least ${f(lo)}, no upper limit`;
  if (lo == null) return `up to ${f(hi)}`;
  return `${f(lo)} to ${f(hi)}`;
}

/** iCPA wording that stays honest when the incremental range includes zero (§6). */
export function icpaText(m: KpiResult, key: string, currency: string): { value: string; range: string } {
  const iv = m.intervals[key];
  const incLo = iv?.incremental[0];
  const range = iv?.icpa ? rangeText(iv.icpa, (x) => money(x, currency)) : "–";
  if (m.icpa == null || incLo == null || incLo <= 0) {
    const lo = iv?.icpa?.[0];
    return { value: lo != null ? `at least ${money(lo, currency)}` : "not defined", range: lo != null ? "no upper limit: we can't rule out zero extra orders" : "no extra orders detected" };
  }
  return { value: money(m.icpa, currency), range };
}

export function cellSentence(cell: CellResult, r: ReadResult, currency: string): string {
  const k = levelKey(r);
  const lp = levelPct(r);
  const m = cell.kpis[r.primary_kpi];
  const unit = r.primary_kpi === "orders" ? "incremental orders" : "incremental revenue";
  const inc = fmtUnit(r.primary_kpi, m.incremental, currency);
  const range = rangeText(m.intervals[k].incremental, (x) => fmtUnit(r.primary_kpi, x, currency));
  const where = r.design === "national_holdout" ? ` in its ${num(cell.n_geos)} markets`
    : r.design === "crossover" ? " while each half had the ads" : "";
  let s = `${cell.label} drove ${inc} ${unit}${where} (${lp} range: ${range})`;
  if (r.primary_kpi === "orders" && m.spend) {
    const t = icpaText(m, k, currency);
    s += t.value.startsWith("at least") || t.value === "not defined" ? `; iCPA ${t.value} (${t.range})` : ` at an iCPA of ${t.value} (range ${t.range})`;
  }
  if (r.primary_kpi === "revenue" && m.spend && m.iroas != null) {
    s += ` for an iROAS of ${m.iroas.toFixed(2)} (range ${rangeText(m.intervals[k].iroas, (x) => (x == null ? "–" : x.toFixed(2)))})`;
  }
  return s + ".";
}

export const H2H_LABEL: Record<string, string> = {
  delta_icpa: "Difference in iCPA",
  ratio_icpa: "iCPA ratio",
  delta_iroas: "Difference in iROAS",
  delta_incremental_per_1000: "Difference in incremental orders per 1,000 spent",
  delta_incremental: "Difference in incremental total",
};

export const h2hLabel = (name: string, kpi: string) =>
  name === "delta_incremental_per_1000" && kpi === "revenue" ? "Difference in incremental revenue per 1,000 spent" : H2H_LABEL[name] ?? name;

export function h2hValue(name: string, x: number | null, currency: string, kpi: string): string {
  if (x == null) return "–";
  if (name === "delta_icpa") return money(x, currency, 2);
  if (name === "ratio_icpa" || name === "delta_iroas") return x.toFixed(2);
  if (name === "delta_incremental_per_1000") return kpi === "revenue" ? money(x, currency) : num(x, 1);
  return kpi === "revenue" ? money(x, currency) : num(x);
}

export function h2hSentence(h: HeadToHead, name: string, m: H2HMetric, r: ReadResult, currency: string): string {
  const k = levelKey(r);
  const iv = m.intervals[k];
  const what = `${h2hLabel(name, h.kpi)} (${h.a_label} minus ${h.b_label})`;
  if (!iv) return `${what}: ${m.note}`;
  const range = rangeText(iv, (x) => h2hValue(name, x, currency, h.kpi));
  const verdict = m.distinguishable ? "Distinguishable from zero" : "Not distinguishable on this evidence";
  return `${what}: ${h2hValue(name, m.estimate, currency, h.kpi)} (${levelPct(r)} range: ${range}). ${verdict}.`;
}

/** The primary head-to-head metric for this plan, falling back to orders-per-1,000 when iCPA isn't defined. */
export function primaryH2H(h: HeadToHead, r: ReadResult): [string, H2HMetric] | null {
  const want = r.primary_metric in h.metrics ? r.primary_metric : "delta_incremental_per_1000";
  const m = h.metrics[want];
  if (m && m.intervals[levelKey(r)]) return [want, m];
  const fb = h.metrics.delta_incremental_per_1000;
  return fb ? ["delta_incremental_per_1000", fb] : null;
}
