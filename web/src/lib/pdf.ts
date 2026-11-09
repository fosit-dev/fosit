// Plan PDF, generated entirely in the browser with jsPDF (no upload, no fonts fetched).
// One document for the advertiser and every vendor: what was agreed, and how to check it later.

import { jsPDF } from "jspdf";
import { isCrossoverPlan, isHoldout, scheduleRows, type LockedPlan } from "./plan";
import { groupHash, shortCode } from "./hash";
import { pretty, daysBetween } from "./dates";
import { money, pct, weeks } from "./format";

type Names = Record<string, string>;

export const MARGIN = 54;
export const PAGE_W = 612; // US Letter, points
export const PAGE_H = 792;
export const WIDTH = PAGE_W - 2 * MARGIN;

export class Writer {
  doc = new jsPDF({ unit: "pt", format: "letter" });
  y = MARGIN;

  ensure(h: number) {
    if (this.y + h > PAGE_H - MARGIN) {
      this.doc.addPage();
      this.y = MARGIN;
    }
  }
  heading(text: string) {
    this.ensure(40);
    this.y += 10;
    this.doc.setFont("helvetica", "bold").setFontSize(13).setTextColor(20, 30, 60);
    this.doc.text(text, MARGIN, this.y);
    this.y += 8;
    this.doc.setDrawColor(200, 205, 220).line(MARGIN, this.y, PAGE_W - MARGIN, this.y);
    this.y += 14;
  }
  para(text: string, opts: { size?: number; bold?: boolean; mono?: boolean; color?: [number, number, number]; indent?: number } = {}) {
    const size = opts.size ?? 10;
    this.doc.setFont(opts.mono ? "courier" : "helvetica", opts.bold ? "bold" : "normal").setFontSize(size);
    this.doc.setTextColor(...(opts.color ?? [30, 30, 30]));
    const lines = this.doc.splitTextToSize(text, WIDTH - (opts.indent ?? 0)) as string[];
    for (const line of lines) {
      this.ensure(size * 1.35);
      this.doc.text(line, MARGIN + (opts.indent ?? 0), this.y);
      this.y += size * 1.35;
    }
    this.y += 3;
  }
  link(label: string, url: string) {
    this.ensure(14);
    this.doc.setFont("helvetica", "bold").setFontSize(10).setTextColor(30, 30, 30);
    this.doc.text(label, MARGIN, this.y);
    this.doc.setFont("helvetica", "normal").setTextColor(35, 72, 201);
    this.doc.textWithLink(url, MARGIN + this.doc.getTextWidth(label) + 6, this.y, { url });
    this.y += 16;
  }
  row(label: string, value: string) {
    this.doc.setFontSize(10);
    const lines = this.doc.splitTextToSize(value, WIDTH - 150) as string[];
    this.doc.setFont("helvetica", "bold");
    const labels = this.doc.splitTextToSize(label, 140) as string[];
    const n = Math.max(lines.length, labels.length);
    this.ensure(n * 13.5);
    this.doc.setTextColor(80, 85, 100);
    labels.forEach((l, i) => this.doc.text(l, MARGIN, this.y + i * 13.5));
    this.doc.setFont("helvetica", "normal").setTextColor(30, 30, 30);
    lines.forEach((l, i) => this.doc.text(l, MARGIN + 150, this.y + i * 13.5));
    this.y += n * 13.5 + 2;
  }
  footer(hash: string) {
    const pages = this.doc.getNumberOfPages();
    for (let i = 1; i <= pages; i++) {
      this.doc.setPage(i);
      this.doc.setFont("helvetica", "normal").setFontSize(8).setTextColor(110, 115, 130);
      this.doc.text(`FOSIT locked plan · fingerprint ${shortCode(hash)} · page ${i} of ${pages}`, MARGIN, PAGE_H - 28);
      this.doc.text("Free Open-Source Incrementality Tool · Apache 2.0", PAGE_W - MARGIN, PAGE_H - 28, { align: "right" });
    }
  }
}

const geoList = (ids: string[], names: Names) => ids.map((g) => (names[g] && names[g] !== g ? `${names[g]} (${g})` : g)).join("; ");

/** `readUrl`: where to come back to read the results (shown as a link under the fingerprint). */
export function planPdf(plan: LockedPlan, names: Names, includeAppendix: boolean, readUrl?: string): Blob {
  const c = plan.commitment;
  const w = new Writer();
  const d = c.dates;
  const testDays = daysBetween(d.test_start, d.test_end) + 1;
  const cooldownDays = daysBetween(d.test_end, d.cooldown_end);
  const holdout = isHoldout(c);
  const cross = isCrossoverPlan(c);

  w.doc.setFont("helvetica", "bold").setFontSize(20).setTextColor(20, 30, 60).text("Locked test plan", MARGIN, w.y + 6);
  w.y += 26;
  w.para(c.test_name + (c.advertiser_label ? ` · ${c.advertiser_label}` : ""), { size: 13 });
  w.para(`Locked ${new Date(c.created_at).toUTCString()} with FOSIT ${c.tool.version}.`, { size: 9, color: [90, 95, 110] });

  w.heading("Plan fingerprint (SHA-256)");
  w.para(groupHash(plan.hash.value), { mono: true, size: 11, bold: true });
  w.para(`Short code: ${shortCode(plan.hash.value)}`, { size: 10 });
  w.para(
    "Send this document, the plan JSON file and the fingerprint above to the advertiser and every vendor before the test " +
      "starts. When results are read, FOSIT recomputes the fingerprint from the JSON file. If anyone changed a market, a date, " +
      "the KPI or the method, it won't match, and the report is marked \"NOT THE PRE-REGISTERED ANALYSIS\".",
    { size: 9.5 },
  );
  if (readUrl) {
    w.para(`After the cooldown ends (${pretty(d.cooldown_end)}), load the plan JSON, your sales and each vendor's spend here:`, { size: 9.5 });
    w.link("Read the results:", readUrl);
  }

  w.heading("What we agreed");
  w.row("Measure", `${c.kpi.primary} (primary)${c.kpi.secondary.length ? `; ${c.kpi.secondary.join(", ")} (secondary)` : ""}, daily`);
  w.row("Test (ads on)", `${pretty(d.test_start)} – ${pretty(d.test_end)} (${weeks(testDays)})`);
  w.row("Cooldown (ads off)", `until ${pretty(d.cooldown_end)} (${cooldownDays} days, still measured)`);
  w.row("History used", `${pretty(d.pre_start)} – ${pretty(d.pre_end)} (${weeks(daysBetween(d.pre_start, d.pre_end) + 1)})`);
  w.row("Geography", `${c.geo.unit === "cbsa" ? "US metro and micro areas (Census CBSAs)" : c.geo.unit === "state" ? "US states" : "Custom markets"} — ${c.geo.mapping_name}`);
  w.row("Total budget", money(c.cells.reduce((s, x) => s + x.budget, 0), c.currency));

  if (cross) {
    w.heading("Schedule: which half has the ads (drawn at random before launch)");
    for (const r of scheduleRows(c)) w.row(`Block ${r.block}`, `${pretty(r.start)} – ${pretty(r.end)}: ads in half ${r.on} ONLY`);
    w.heading(`Half A — ${c.cells[0].geo_ids.length} markets (budget for the whole test ${money(c.cells[0].budget, c.currency)})`);
    w.para(geoList(c.cells[0].geo_ids, names), { size: 8.5 });
    w.heading(`Half B — ${c.control.geo_ids.length} markets`);
    w.para(geoList(c.control.geo_ids, names), { size: 8.5 });
  } else if (holdout) {
    w.heading(`Holdout — ${c.control.geo_ids.length} markets with NO ads from ${pretty(d.test_start)} to ${pretty(d.cooldown_end)}`);
    w.para(geoList(c.control.geo_ids, names), { size: 9 });
    for (const cell of c.cells) {
      if (c.cells.length === 1) {
        w.heading(`${cell.label} — runs everywhere else (${cell.geo_ids.length} markets), budget ${money(cell.budget, c.currency)}`);
        w.para(geoList(cell.geo_ids, names), { size: 8 });
      } else {
        w.heading(`${cell.label} — ${cell.geo_ids.length} markets, budget ${money(cell.budget, c.currency)}`);
        w.para(`Run ads ONLY in these markets (${cell.id}):`, { size: 9.5, bold: true });
        w.para(geoList(cell.geo_ids, names), { size: 9 });
      }
    }
  } else {
    for (const cell of c.cells) {
      w.heading(`${cell.label} — ${cell.geo_ids.length} markets, budget ${money(cell.budget, c.currency)}`);
      w.para(`Run ads ONLY in these markets (${cell.id}):`, { size: 9.5, bold: true });
      w.para(geoList(cell.geo_ids, names), { size: 9 });
    }
    w.heading(`Control — ${c.control.geo_ids.length} markets with NO test ads from any vendor`);
    w.para(geoList(c.control.geo_ids, names), { size: 8 });
  }
  if (c.excluded.geo_ids.length) {
    w.heading(`Excluded — ${c.excluded.geo_ids.length} markets left out of the analysis`);
    w.para(c.excluded.geo_ids.map((g) => `${names[g] ?? g}${c.excluded.reasons?.[g] ? ` (${c.excluded.reasons[g]})` : ""}`).join("; "), { size: 8.5 });
  }

  w.heading("How results will be read (fixed now)");
  const m = c.method;
  w.para(cross
    ? `Halves take turns (METHODOLOGY §14). For every half and block, mean daily sales after the first ${c.design?.type === "crossover" ? c.design.washout_days : 0} days ` +
      `(while the previous block's ads fade) are compared: the gap between a half with the ads and the same half without them, ` +
      `net of national swings that hit both halves at once, is the ads' lift. The result is tested against every other balanced ` +
      `schedule the coin could have produced (an exact randomization test), and the range is every lift that test doesn't rule out. ` +
      `Decisions use ${pct(1 - m.alpha, 0)} ranges (95% also reported).`
    : holdout
    ? `National holdout (METHODOLOGY §13). The held-out markets are compared with a statistical twin built from the markets with ads${c.cells.length > 1 ? " (one twin per vendor, from that vendor's markets only)" : ""}, ` +
      `each indexed to its own history (ridge-augmented synthetic control with market fixed effects, ridge penalty chosen by ` +
      `cross-validation). The gap is the share of sales the ads drove, applied to the markets with ads. Uncertainty comes from conformal ` +
      `inference with ${m.permutations.kind === "moving_block" ? "moving-block (circular time-shift)" : "random (iid)"} permutations. ` +
      `Decisions use ${pct(1 - m.alpha, 0)} intervals (95% also reported)${m.placebo_calibration ? `, each checked against ${m.placebo_calibration.n} placebo cells over the same dates` : ""}. The campaign was ${c.design?.type === "national_holdout" && c.design.ads_before_test === "always_on" ? "running everywhere" : "off everywhere"} during the history period.`
    :
    `Each cell is compared with a statistical twin built from the control markets (ridge-augmented synthetic control with ` +
      `market fixed effects, ridge penalty chosen by cross-validation). Uncertainty comes from conformal inference with ` +
      `${m.permutations.kind === "moving_block" ? "moving-block (circular time-shift)" : "random (iid)"} permutations. ` +
      `Decisions use ${pct(1 - m.alpha, 0)} intervals (95% also reported)${m.placebo_calibration ? `, each checked against ${m.placebo_calibration.n} placebo cells over the same dates and widened if they drift more` : ""}. Vendor-vs-vendor differences use a joint ` +
      `confidence region for both cells, which is deliberately cautious about declaring a winner.`,
    { size: 9.5 },
  );
  const dec = c.decision;
  w.row("Primary comparison", { delta_icpa: "Difference in incremental CPA between cells", delta_iroas: "Difference in incremental ROAS between cells", delta_incremental_per_1000: "Difference in incremental orders per 1,000 spent", cell_lift: holdout ? "Incremental lift in the markets with ads" : "Incremental lift in the test cell" }[dec.primary_metric]);
  w.row("Worth it if", dec.target_icpa ? `incremental CPA at most ${money(dec.target_icpa, c.currency, 2)}` : dec.breakeven_iroas ? `incremental ROAS at least ${dec.breakeven_iroas}` : "lift at least the planned minimum detectable effect");
  w.row("Honesty checks", `pre-period fit within plan limits; at most ${pct(c.thresholds.leakage_warn_share, 0)} of impressions ${holdout ? "in held-out markets" : "outside assigned markets"}; spend split within ±${c.thresholds.spend_share_tolerance_pp} points of plan; no read before ${pretty(d.cooldown_end)}; no other changes that differ across markets`);
  w.row("Random seed", String(m.seed));
  w.row("Code fingerprint", c.tool.core_sha256);
  w.row("Data fingerprint", `${c.data_fingerprint.kpi_history_sha256} (${c.data_fingerprint.rows.toLocaleString()} rows, ${c.data_fingerprint.first_date} – ${c.data_fingerprint.last_date})`);
  if (c.assignment.label_assignment === "coin_flip") w.row("Who got which markets", "Decided by a random coin flip after the market sets were chosen.");

  w.heading("Before launch, each vendor confirmed");
  for (const cell of c.cells)
    w.para(cross ? `[x] ${cell.label} can switch the ads between the two halves on exactly the dates above.` :
      holdout && c.cells.length === 1 ? `[x] ${cell.label} can keep every held-out market free of ads for the dates above.` :
      holdout ? `[x] ${cell.label} can target exactly its market list above, and nothing in the held-out markets.` : `[x] ${cell.label} can target exactly its market list above, and nothing in control.`, { size: 9.5 });

  if (includeAppendix && plan.appendix) {
    const a = plan.appendix as { design?: { fit: number[]; balance_score: number; share_in_test: number }; mde?: { label: string; mde: number | null; detectable_icpa: number | null }[] };
    w.heading("Appendix: design diagnostics (not part of the fingerprint)");
    if (a.design) {
      w.row("Share of sales in test", pct(a.design.share_in_test));
      w.row("Pre-period fit error", a.design.fit.map((f) => pct(f)).join(" / "));
      w.row("Balance gap", pct(a.design.balance_score));
    }
    for (const r of a.mde ?? []) w.row(`${r.label}: detectable lift`, `${pct(r.mde)}${r.detectable_icpa ? ` (true iCPA would need to be at most ${money(r.detectable_icpa, c.currency)})` : ""}`);
  }

  w.heading("How to verify this plan yourself");
  w.para(
    "1) Open the plan JSON in FOSIT's Read module and paste the fingerprint from the pre-launch email. " +
      "2) Or recompute it without FOSIT: SHA-256 of the RFC 8785 canonical JSON of the \"commitment\" object (see docs/PREREGISTRATION.md for a one-line Python command).",
    { size: 9.5 },
  );
  w.footer(plan.hash.value);
  return w.doc.output("blob");
}
