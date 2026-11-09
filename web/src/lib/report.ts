// "CFO-ready" results report, generated in the browser with jsPDF. Verdicts first, then the
// evidence: honesty checks, per-cell numbers with ranges, head-to-head, and how it was computed.
import type { LockedPlan } from "./plan";
import { MARGIN, PAGE_H, PAGE_W, WIDTH, Writer } from "./pdf";
import { pretty } from "./dates";
import { money, num, pct } from "./format";
import { groupHash, shortCode } from "./hash";
import type { Check, ReadResult } from "../read/types";
import { VERDICT, impactLabels, h2hLabel, cellSentence, h2hSentence, h2hValue, icpaText, levelKey, primaryH2H, rangeText } from "../read/text";

type Args = {
  plan: LockedPlan; result: ReadResult; checks: Check[]; mismatch: boolean; recomputed: string;
  shocks: { answer: string; note: string }; names: Record<string, string>;
};

// jsPDF's built-in fonts only cover Latin-1: replace the few symbols our copy uses.
const latin = (s: string) => s.replace(/[≤]/g, "<=").replace(/[≥]/g, ">=").replace(/[−]/g, "-").replace(/[→]/g, "->").replace(/[✓]/g, "OK").replace(/[…]/g, "...");

function chart(w: Writer, dates: string[], observed: number[], cf: number[], nPre: number, testDays: number, holdout: boolean, crossover = false) {
  const from = Math.max(0, nPre - 56);
  const o = observed.slice(from), c = cf.slice(from), pre = nPre - from;
  const h = 130, top = w.y, left = MARGIN + 34, width = WIDTH - 34;
  w.ensure(h + 30);
  const y0 = w.y;
  const max = Math.max(...o, ...c), min = Math.min(0, ...o, ...c);
  const X = (i: number) => left + (i / Math.max(o.length - 1, 1)) * width;
  const Y = (v: number) => y0 + (1 - (v - min) / (max - min || 1)) * h;
  const doc = w.doc;
  doc.setFillColor(232, 237, 252);
  doc.rect(X(pre), y0, X(Math.min(pre + testDays - 1, o.length - 1)) - X(pre), h, "F");
  doc.setFontSize(7).setTextColor(110, 115, 130).setFont("helvetica", "normal");
  doc.text(Math.round(max).toLocaleString("en-US"), MARGIN, Y(max) + 3);
  doc.text(Math.round(min).toLocaleString("en-US"), MARGIN, Y(min));
  doc.text(dates[from], left, y0 + h + 10);
  doc.text(dates[dates.length - 1], left + width, y0 + h + 10, { align: "right" });
  doc.text("ads on", X(pre) + 3, y0 + 9);
  const line = (vs: number[], rgb: [number, number, number], dash: boolean) => {
    doc.setDrawColor(...rgb).setLineWidth(1.1);
    if (dash) doc.setLineDashPattern([3, 2], 0);
    for (let i = 1; i < vs.length; i++) doc.line(X(i - 1), Y(vs[i - 1]), X(i), Y(vs[i]));
    doc.setLineDashPattern([], 0);
  };
  line(c, [194, 65, 12], true);
  line(o, [35, 72, 201], false);
  const lab = impactLabels(holdout, crossover);
  doc.setFontSize(8).setTextColor(35, 72, 201).text(lab.real, left, y0 + h + 22);
  doc.setTextColor(194, 65, 12).text(`- - ${lab.twin}`, left + (holdout ? 110 : 80), y0 + h + 22);
  w.y = Math.max(top, y0) + h + 44;
}

export function reportPdf({ plan, result: r, checks, mismatch, recomputed, shocks, names }: Args): Blob {
  const c = plan.commitment;
  const cur = c.currency;
  const w = new Writer();
  const doc = w.doc;

  doc.setFont("helvetica", "bold").setFontSize(20).setTextColor(20, 30, 60).text("Incrementality report", MARGIN, w.y + 6);
  w.y += 26;
  w.para(latin(c.test_name + (c.advertiser_label ? ` - ${c.advertiser_label}` : "")), { size: 13 });
  w.para(`Ads ${pretty(c.dates.test_start)} - ${pretty(c.dates.test_end)}, measured through ${pretty(r.window.end)}. Read ${pretty(new Date().toISOString().slice(0, 10))} with FOSIT.`, { size: 9, color: [90, 95, 110] });
  if (r.interim) w.para(`INTERIM: read before the planned end (${pretty(r.window.planned_end)}). Results can still move.`, { bold: true, color: [138, 83, 0] });

  w.heading("Bottom line");
  for (const cell of r.cells) w.para(latin(`[${VERDICT[cell.verdict].label}] ${cellSentence(cell, r, cur)}`), { size: 10.5 });
  for (const h of r.head_to_head.filter((x) => x.kpi === r.primary_kpi)) {
    const p = primaryH2H(h, r);
    if (p) w.para(latin(`Head-to-head: ${h2hSentence(h, p[0], p[1], r, cur)}`), { size: 10.5 });
  }
  w.para("Ranges are " + pct(r.decision_level, 0) + " confidence intervals. \"Inconclusive\" means the test can't tell; \"no detectable lift\" means any effect is too small to be worthwhile.", { size: 8.5, color: [90, 95, 110] });

  w.heading("Honesty checks");
  for (const ch of checks) w.row(`${ch.status === "pass" ? "PASS" : ch.status === "warn" ? "WARN" : "FAIL"}  ${ch.title}`, latin(ch.detail));
  if (shocks.answer === "changed") w.para(latin(`Reported change during the test: ${shocks.note}`), { size: 9.5 });

  for (const cell of r.cells) {
    w.heading(latin(`${cell.label}: ${VERDICT[cell.verdict].label}`));
    w.para(latin(`${cell.n_geos} markets. Spend ${money(cell.spend, cur)} of ${money(cell.budget, cur)} planned. ${cell.verdict_reason}`), { size: 9.5 });
    const m = cell.kpis[r.primary_kpi];
    chart(w, m.series.dates, m.series.observed, m.series.counterfactual, m.series.n_pre, m.series.test_days, m.series.role === "holdout", m.series.role === "crossover");
    for (const [kpi, km] of Object.entries(cell.kpis)) {
      const unit = (x: number | null) => (kpi === "revenue" ? money(x, cur) : num(x));
      const ranges = (key: "incremental" | "lift" | "icpa" | "iroas", f: (x: number | null) => string) =>
        r.levels.map((l) => `${pct(l, 0)}: ${rangeText(km.intervals[String(l)][key], f)}`).join("; ");
      w.row(`Incremental ${kpi}`, latin(`${unit(km.incremental)} (${ranges("incremental", unit)})`));
      w.row(`Lift (${kpi})`, latin(`${pct(km.lift)} (${ranges("lift", (x) => pct(x))})`));
      if (kpi === "orders" && km.spend) {
        const t = icpaText(km, levelKey(r), cur);
        w.row("iCPA", latin(`${t.value} (${ranges("icpa", (x) => money(x, cur))})`));
      }
      if (kpi === "revenue" && km.spend) w.row("iROAS", latin(`${km.iroas?.toFixed(2) ?? "-"} (${ranges("iroas", (x) => (x == null ? "-" : x.toFixed(2)))})`));
      w.row(`p-value (${kpi})`, `${km.p_value.toFixed(3)}; pre-period fit error ${pct(km.pre_fit_nrmse)}${km.pre_fit_limit ? ` (limit ${pct(km.pre_fit_limit)})` : ""}`);
    }
  }

  if (r.head_to_head.length) {
    w.heading("Head-to-head");
    for (const h of r.head_to_head) {
      w.para(latin(`${h.a_label} vs ${h.b_label} (${h.kpi})`), { bold: true, size: 10 });
      for (const [name, m] of Object.entries(h.metrics)) {
        const iv = m.intervals[levelKey(r)];
        w.row(latin(h2hLabel(name, h.kpi)), latin(iv ? `${h2hValue(name, m.estimate, cur, h.kpi)} (${pct(r.decision_level, 0)} range ${rangeText(iv, (x) => h2hValue(name, x, cur, h.kpi))}): ${m.distinguishable ? "distinguishable" : "not distinguishable"}` : m.note));
      }
    }
    w.para("The cells ran in different markets, so differences reflect vendor + markets. Markets were balanced at planning time; these ranges are deliberately cautious.", { size: 8.5, color: [90, 95, 110] });
  }

  w.heading("How this was computed");
  w.para(latin(r.design === "crossover"
    ? `Halves take turns (METHODOLOGY §14): two balanced halves of the country had the ads in alternate blocks, in a random order fixed in the plan. Per half and block, mean daily sales after a washout were compared; the lift is the gap between a half with and without the ads, net of national swings that hit both halves at once. Ranges and p-values come from an exact randomization test against every other balanced schedule. Every setting was fixed in the locked plan before launch. Full method: docs/METHODOLOGY.md in the FOSIT repository.`
    : r.design === "national_holdout"
    ? `National holdout: the ${c.control.geo_ids.length} held-out markets are compared with a statistical twin built from the markets with ads, each indexed to its own history (ridge-augmented synthetic control with market fixed effects, Ben-Michael, Feller & Rothstein 2021). The gap is the share of sales the ads drove, applied to the markets with ads (METHODOLOGY §13). Ranges and p-values come from conformal inference (Chernozhukov, Wuthrich & Zhu 2021) with ${r.permutations.kind === "moving_block" ? "moving-block permutations" : "random permutations"}. ${c.method.placebo_calibration ? `Ranges were checked against ${c.method.placebo_calibration.n} placebo cells over the same dates and widened where those drifted more (METHODOLOGY §5.6). ` : ""}Every setting was fixed in the locked plan before launch. Full method: docs/METHODOLOGY.md in the FOSIT repository.`
    : `Each cell is compared with a statistical twin built from ${c.control.geo_ids.length} control markets (ridge-augmented synthetic control with market fixed effects, Ben-Michael, Feller & Rothstein 2021). Ranges and p-values come from conformal inference (Chernozhukov, Wuthrich & Zhu 2021) with ${r.permutations.kind === "moving_block" ? "moving-block permutations" : "random permutations"}. ${c.method.placebo_calibration ? `Ranges were checked against ${c.method.placebo_calibration.n} placebo cells over the same dates and widened where those drifted more (METHODOLOGY §5.6). ` : ""}Every setting was fixed in the locked plan before launch. Full method: docs/METHODOLOGY.md in the FOSIT repository.`), { size: 9.5 });
  w.row("Plan fingerprint", groupHash(recomputed));
  w.row("Locked fingerprint", plan.hash.value === recomputed ? "matches" : `does NOT match (${shortCode(plan.hash.value)})`);
  w.row("History used", `${pretty(c.dates.pre_start)} - ${pretty(c.dates.pre_end)}`);
  w.row("Code fingerprint", c.tool.core_sha256);
  const topNames = r.cells.map((cell) => `${cell.label}: ${cell.kpis[r.primary_kpi].under_the_hood.top_weights.slice(0, 5).map((t) => `${names[t.geo_id] ?? t.geo_id} ${t.weight.toFixed(2)}`).join(", ")}`);
  w.row("Largest twin weights", latin(topNames.join(" | ")));

  // footer + watermark on every page
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    if (mismatch) {
      doc.setFont("helvetica", "bold").setFontSize(30).setTextColor(200, 40, 30);
      doc.text("NOT THE PRE-REGISTERED ANALYSIS", PAGE_W / 2, PAGE_H / 2, { align: "center", angle: 30 });
    }
    doc.setFont("helvetica", "normal").setFontSize(8).setTextColor(110, 115, 130);
    doc.text(`FOSIT report - plan ${shortCode(recomputed)}${r.interim ? " - INTERIM" : ""}${mismatch ? " - PLAN CHANGED" : ""} - page ${i} of ${pages}`, MARGIN, PAGE_H - 28);
    doc.text("Free Open-Source Incrementality Tool - Apache 2.0", PAGE_W - MARGIN, PAGE_H - 28, { align: "right" });
  }
  return doc.output("blob");
}
