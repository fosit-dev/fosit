import { InfoTip } from "../components/InfoTip";
import { ImpactChart } from "../components/Charts";
import { money, num, pct } from "../lib/format";
import type { LockedPlan } from "../lib/plan";
import type { CellResult, KpiResult, ReadResult } from "./types";
import { VERDICT, h2hLabel, cellSentence, h2hSentence, h2hValue, icpaText, levelKey, primaryH2H, rangeText } from "./text";

type Props = { r: ReadResult; plan: LockedPlan; names: Record<string, string> };

function VerdictBadge({ v }: { v: CellResult["verdict"] }) {
  const meta = VERDICT[v];
  return <span className={`verdict verdict-${meta.tone}`}><span aria-hidden>{meta.icon}</span> {meta.label}</span>;
}

function StatsTable({ cell, r, currency }: { cell: CellResult; r: ReadResult; currency: string }) {
  const rows: { label: string; term?: Parameters<typeof InfoTip>[0]["term"]; values: string[] }[] = [];
  const keys = r.levels.map(String);
  for (const kpi of Object.keys(cell.kpis)) {
    const m = cell.kpis[kpi];
    const unit = (x: number | null) => (kpi === "revenue" ? money(x, currency) : num(x));
    const title = kpi === "orders" ? "orders" : "revenue";
    rows.push({ label: `Incremental ${title}`, term: "incrementality", values: [unit(m.incremental), ...keys.map((k) => rangeText(m.intervals[k].incremental, unit))] });
    rows.push({ label: `Lift in ${title}`, values: [pct(m.lift), ...keys.map((k) => rangeText(m.intervals[k].lift, (x) => pct(x)))] });
    if (kpi === "orders" && m.spend) {
      const t = icpaText(m, levelKey(r), currency);
      rows.push({ label: "iCPA", term: "icpa", values: [t.value, ...keys.map((k) => rangeText(m.intervals[k].icpa, (x) => money(x, currency)))] });
      rows.push({ label: "Incremental orders per 1,000 spent", term: "perThousand", values: [num(m.per_1000, 1), ...keys.map((k) => rangeText(m.intervals[k].per_1000, (x) => num(x, 1)))] });
    }
    if (kpi === "revenue" && m.spend) {
      rows.push({ label: "iROAS", term: "iroas", values: [m.iroas?.toFixed(2) ?? "–", ...keys.map((k) => rangeText(m.intervals[k].iroas, (x) => (x == null ? "–" : x.toFixed(2))))] });
    }
    rows.push({ label: `p-value (${title})`, term: "pValue", values: [m.p_value.toFixed(3), ...keys.map(() => "")] });
  }
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Measure</th><th>Estimate</th>{keys.map((k) => <th key={k}>{pct(Number(k), 0)} range<InfoTip term="range" /></th>)}</tr></thead>
        <tbody>{rows.map((row) => (
          <tr key={row.label}><td>{row.label}{row.term && <InfoTip term={row.term} />}</td>{row.values.map((v, i) => <td key={i}>{v}</td>)}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function PlaceboNote({ pl, level }: { pl: KpiResult["placebo"]; level: string }) {
  if (pl == null) return <p className="small muted">This plan was locked without the placebo check, so the ranges are plain conformal ranges.</p>;
  if (!pl.n) return <p className="small muted">Placebo check skipped: too few markets to build fake cells from.</p>;
  return (
    <p className="small">Placebo check<InfoTip term="placebo" />: {pl.n} fake cells over the same dates.{" "}
      {pl.widened?.[level] ? "They drifted more than the conformal range allows, so the range was widened to match them." : "The conformal range already covered how far they drifted."}{" "}
      Placebo p-value {pl.p_value?.toFixed(3)}.</p>
  );
}

export function ReadResults({ r, plan, names }: Props) {
  const c = plan.commitment;
  const currency = c.currency;
  const holdout = r.design === "national_holdout";
  return (
    <>
      <section className="card" aria-labelledby="bottom-line">
        <h2 id="bottom-line">Bottom line<InfoTip term="verdict" /></h2>
        {r.interim && <div className="callout warn"><strong>INTERIM.</strong> Read before the planned end ({r.window.planned_end}). Results can still move.</div>}
        {r.cells.map((cell) => (
          <p key={cell.id}><VerdictBadge v={cell.verdict} /> {cellSentence(cell, r, currency)}</p>
        ))}
        {r.head_to_head.filter((h) => h.kpi === r.primary_kpi).map((h) => {
          const p = primaryH2H(h, r);
          return p ? <p key={h.a + h.b}><strong>Head-to-head:</strong> {h2hSentence(h, p[0], p[1], r, currency)}</p> : null;
        })}
      </section>

      {r.cells.map((cell) => {
        const m = cell.kpis[r.primary_kpi];
        return (
          <section className="card" key={cell.id} aria-labelledby={`cell-${cell.id}`}>
            <div className="row"><h2 id={`cell-${cell.id}`} style={{ margin: 0 }}>{cell.label}</h2><VerdictBadge v={cell.verdict} /></div>
            <p className="small muted">{cell.n_geos} markets{holdout ? ` with ads, ${c.control.geo_ids.length} held out` : ""} · spend {money(cell.spend, currency)} of {money(cell.budget, currency)} planned · {cell.verdict_reason}</p>
            {cell.meaningful_effect != null && <p className="small muted">Worthwhile effect: {num(cell.meaningful_effect)} ({cell.meaningful_basis}).</p>}
            {holdout && <p className="small">The chart shows the held-out markets: what they sold without the ads, and what their twin (built from the markets
              with ads) says they'd have sold with them. The gap is the share of sales the ads drove, applied to the {num(cell.n_geos)} markets {r.cells.length > 1 ? `with ${cell.label}'s ads` : "with ads"}.<InfoTip term="holdout" /></p>}
            <ImpactChart title={holdout ? "Held-out markets" : cell.label} unit={r.primary_kpi} dates={m.series.dates} observed={m.series.observed}
              counterfactual={m.series.counterfactual} nPre={m.series.n_pre} testDays={m.series.test_days} holdout={m.series.role === "holdout"} />
            <StatsTable cell={cell} r={r} currency={currency} />
          </section>
        );
      })}

      {r.head_to_head.length > 0 && (
        <section className="card" aria-labelledby="h2h">
          <h2 id="h2h">Head-to-head<InfoTip term="headToHead" /></h2>
          {r.head_to_head.map((h) => (
            <div key={h.a + h.b + h.kpi}>
              <h3>{h.a_label} vs {h.b_label} · {h.kpi}</h3>
              <div className="table-wrap"><table>
                <thead><tr><th>Comparison</th><th>Estimate</th>{r.levels.map((l) => <th key={l}>{pct(l, 0)} range</th>)}<th>Tell them apart?</th></tr></thead>
                <tbody>{Object.entries(h.metrics).map(([name, m]) => (
                  <tr key={name}>
                    <td>{h2hLabel(name, h.kpi)}{name === "delta_incremental_per_1000" && <InfoTip term="perThousand" />}</td>
                    <td>{h2hValue(name, m.estimate, currency, h.kpi)}</td>
                    {r.levels.map((l) => <td key={l}>{m.intervals[String(l)] ? rangeText(m.intervals[String(l)]!, (x) => h2hValue(name, x, currency, h.kpi)) : "not defined"}</td>)}
                    <td>{m.distinguishable == null ? <span className="small muted">{m.note ? "not defined" : "–"}</span> : m.distinguishable ? "Yes" : "No"}</td>
                  </tr>
                ))}</tbody>
              </table></div>
            </div>
          ))}
          <p className="small muted">The cells ran in different markets, so this compares vendor + markets. FOSIT balanced the markets to keep it fair, and its head-to-head ranges are deliberately cautious about naming a winner.</p>
        </section>
      )}

      <section className="card">
        <details>
          <summary>Under the hood</summary>
          <p className="small">Method (locked in the plan): ridge-augmented synthetic control with market fixed effects; conformal inference with {r.permutations.kind === "moving_block" ? `moving-block permutations (${r.permutations.n} time shifts)` : `${r.permutations.n} random permutations`}; decisions at {pct(r.decision_level, 0)}. Measurement window {r.window.start} to {r.window.end} ({r.window.days} days, {r.window.test_days} with ads).</p>
          {r.cells.map((cell) => {
            const u = cell.kpis[r.primary_kpi].under_the_hood;
            return (
              <div key={cell.id}>
                <h4>{holdout ? (r.cells.length > 1 ? `The holdout's twin from ${cell.label}'s markets` : "The holdout's twin") : `${cell.label}'s twin`}</h4>
                <p className="small">Built from {u.donors} {holdout ? `markets with ${r.cells.length > 1 ? `${cell.label}'s ` : ""}ads, each indexed to its own history (METHODOLOGY §13.3)` : "control markets"}{u.dropped_donors.length ? ` (${u.dropped_donors.length} too sparse to use)` : ""}. Ridge penalty λ = {u.lambda.toExponential(2)}. Sum of negative weights {u.negative_weight_sum.toFixed(3)}. {u.tests_evaluated} hypotheses tested to build the ranges. Pre-period fit error {pct(cell.kpis[r.primary_kpi].pre_fit_nrmse)}.</p>
                <div className="chips">{u.top_weights.map((w) => <span key={w.geo_id} className="chip">{names[w.geo_id] ?? w.geo_id}: {w.weight.toFixed(3)}</span>)}</div>
                <PlaceboNote pl={cell.kpis[r.primary_kpi].placebo} level={levelKey(r)} />
              </div>
            );
          })}
        </details>
      </section>
    </>
  );
}
