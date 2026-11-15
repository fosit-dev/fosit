import { InfoTip } from "../components/InfoTip";
import { useLevel } from "../lib/level";
import { ImpactChart } from "../components/Charts";
import { money, num, pct } from "../lib/format";
import { fadeHalfLife, fadeSentence, type LockedPlan } from "../lib/plan";
import type { CellResult, KpiResult, ReadResult, Summary } from "./types";
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

const DOT = ["var(--c1, #2a78d6)", "var(--c2, #eb6834)", "var(--c3, #1baf7a)", "var(--c4, #eda100)", "var(--c5, #e87ba4)", "var(--c6, #008300)"];

/** The answer first (core/fosit/explain.py): one headline, one detail and one action per cell, in plain words. */
function AnswerCard({ s, r }: { s: Summary; r: ReadResult }) {
  return (
    <section className="card" aria-labelledby="the-answer">
      <h2 id="the-answer">The answer</h2>
      {s.notes.map((n) => <div key={n} className="callout warn">{n}</div>)}
      {s.cells.map((a, i) => (
        <div key={a.id} className="answer-row">
          <span aria-hidden style={{ width: 12, height: 12, borderRadius: "50%", marginTop: 7, background: DOT[i % DOT.length] }} />
          <div>
            <VerdictBadge v={a.verdict} />
            <div className="head">{a.headline}</div>
            <p className="muted" style={{ margin: "4px 0" }}>{a.detail}</p>
            {a.action && <div className="todo"><strong>What to do:</strong> {a.action}</div>}
          </div>
        </div>
      ))}
      {s.head_to_head && (
        <div className="answer-row">
          <span aria-hidden style={{ width: 12, height: 12, borderRadius: "50%", marginTop: 7, background: "var(--text)" }} />
          <div><div className="head">{s.head_to_head.headline}</div><p className="muted" style={{ margin: "4px 0" }}>{s.head_to_head.detail}</p></div>
        </div>
      )}
      {r.cells.length > 0 && <p className="small muted" style={{ marginBottom: 0 }}>Download the interactive report below: it has a slider to test the value of an extra order, and charts to explore.</p>}
    </section>
  );
}

export function ReadResults({ r, plan, names }: Props) {
  const { level } = useLevel();
  const c = plan.commitment;
  const currency = c.currency;
  const holdout = r.design === "national_holdout";
  const cross = r.design === "crossover";
  return (
    <>
      {r.summary && <AnswerCard s={r.summary} r={r} />}
      {(!r.summary || level === "full") && <section className="card" aria-labelledby="bottom-line">
        <h2 id="bottom-line">{r.summary ? "In numbers" : "Bottom line"}<InfoTip term="verdict" /></h2>
        {r.interim && !r.summary && <div className="callout warn"><strong>Early read.</strong> The test ends on {r.window.planned_end}. The numbers can change.</div>}
        {r.cells.map((cell) => (
          <p key={cell.id}><VerdictBadge v={cell.verdict} /> {cellSentence(cell, r, currency)}</p>
        ))}
        {r.head_to_head.filter((h) => h.kpi === r.primary_kpi).map((h) => {
          const p = primaryH2H(h, r);
          return p ? <p key={h.a + h.b}><strong>Head-to-head:</strong> {h2hSentence(h, p[0], p[1], r, currency)}</p> : null;
        })}
      </section>}

      {r.cells.map((cell) => {
        const m = cell.kpis[r.primary_kpi];
        return (
          <section className="card" key={cell.id} aria-labelledby={`cell-${cell.id}`}>
            <div className="row"><h2 id={`cell-${cell.id}`} style={{ margin: 0 }}>{cell.label}</h2><VerdictBadge v={cell.verdict} /></div>
            <p className="small muted">{cell.n_geos} markets{holdout ? ` with ads, ${c.control.geo_ids.length} held out` : ""} · spend {money(cell.spend, currency)} of {money(cell.budget, currency)} planned · {cell.verdict_reason}</p>
            {cell.meaningful_effect != null && <p className="small muted">Worthwhile effect: {num(cell.meaningful_effect)} ({cell.meaningful_basis}).</p>}
            {holdout && <p className="small">The chart shows the held-out markets: what they sold without the ads, and what their twin (built from the markets
              with ads) says they'd have sold with them. The gap is the share of sales the ads drove, applied to the {num(cell.n_geos)} markets {r.cells.length > 1 ? `with ${cell.label}'s ads` : "with ads"}.<InfoTip term="holdout" /></p>}
            {cross && <p className="small">The chart shows both halves together, and what they'd have sold without the ads (the estimated
              extra sales taken out of whichever half had the ads). {fadeSentence(fadeHalfLife(c) ?? 3)}<InfoTip term="crossover" /></p>}
            <ImpactChart crossover={m.series.role === "crossover"} title={holdout ? "Held-out markets" : cell.label} unit={r.primary_kpi} dates={m.series.dates} observed={m.series.observed}
              counterfactual={m.series.counterfactual} nPre={m.series.n_pre} testDays={m.series.test_days} holdout={m.series.role === "holdout"} />
            {level !== "brief" && <StatsTable cell={cell} r={r} currency={currency} />}
          </section>
        );
      })}

      {r.head_to_head.length > 0 && level !== "brief" && (
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

      {level !== "brief" && <section className="card">
        <details open={level === "full"}>
          <summary>Under the hood</summary>
          {cross
            ? <p className="small">Method (locked in the plan): two halves took turns having the ads on a random schedule; a two-way comparison (half and block) of log sales after each block's washout; a randomization test against every balanced schedule ({r.permutations.n}), exact only for "no effect at all"; decisions at {pct(r.decision_level, 0)}. Test {r.window.start} to {r.window.end} ({r.window.days} days). The ranges assume that the ads' effect is gone after the washout (half-life about {fadeHalfLife(c) ?? 3} days); a longer effect moves them down (METHODOLOGY §14.5).</p>
            : <p className="small">Method (locked in the plan): ridge-augmented synthetic control with market fixed effects; conformal inference with {r.permutations.kind === "moving_block" ? `moving-block permutations (${r.permutations.n} time shifts)` : `${r.permutations.n} random permutations`}; decisions at {pct(r.decision_level, 0)}. Measurement window {r.window.start} to {r.window.end} ({r.window.days} days, {r.window.test_days} with ads).</p>}
          {r.cells.map((cell) => {
            const u = cell.kpis[r.primary_kpi].under_the_hood;
            if (cross && u.blocks) return (
              <div key={cell.id}>
                <h4>Block by block</h4>
                <p className="small">Mean daily {r.primary_kpi} per half, leaving out the first {u.washout_days} days of each {u.block_days}-day block.
                  The result was tested against all {u.schedules_tested} balanced schedules the coin could have drawn.
                  Before the test the halves' ratio moved {pct(cell.kpis[r.primary_kpi].pre_fit_nrmse)} from block to block.</p>
                <div className="table-wrap"><table>
                  <thead><tr><th>Block from</th><th>Ads in</th><th>Half A / day</th><th>Half B / day</th></tr></thead>
                  <tbody>{u.blocks.map((b) => <tr key={b.start}><td>{b.start}</td><td>Half {b.on}</td><td>{num(b.a_daily)}</td><td>{num(b.b_daily)}</td></tr>)}</tbody>
                </table></div>
              </div>
            );
            return (
              <div key={cell.id}>
                <h4>{holdout ? (r.cells.length > 1 ? `The holdout's twin from ${cell.label}'s markets` : "The holdout's twin") : `${cell.label}'s twin`}</h4>
                <p className="small">Built from {u.donors} {holdout ? `markets with ${r.cells.length > 1 ? `${cell.label}'s ` : ""}ads, each indexed to its own history (METHODOLOGY §13.3)` : "control markets"}{u.dropped_donors.length ? ` (${u.dropped_donors.length} too sparse to use)` : ""}. Ridge penalty λ = {u.lambda?.toExponential(2)}. Sum of negative weights {u.negative_weight_sum.toFixed(3)}. {u.tests_evaluated} hypotheses tested to build the ranges. Pre-period fit error {pct(cell.kpis[r.primary_kpi].pre_fit_nrmse)}{cell.kpis[r.primary_kpi].pre_fit_period === "week" ? " (on weekly totals)" : ""}.</p>
                <div className="chips">{u.top_weights.map((w) => <span key={w.geo_id} className="chip">{names[w.geo_id] ?? w.geo_id}: {w.weight.toFixed(3)}</span>)}</div>
                <PlaceboNote pl={cell.kpis[r.primary_kpi].placebo} level={levelKey(r)} />
              </div>
            );
          })}
        </details>
      </section>}
    </>
  );
}
