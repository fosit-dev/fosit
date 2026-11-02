import { useState } from "react";
import { InfoTip } from "../components/InfoTip";
import { FitChart, PowerChart } from "../components/Charts";
import type { DesignResult, FindResult, PowerCurve } from "../lib/plan";
import { money, num, pct, weeks } from "../lib/format";
import { callPython } from "../worker/client";
import type { Progress } from "../worker/protocol";
import { budgets, isHoldout, preDays, searchKey, type PlanState } from "./state";

type Props = {
  s: PlanState;
  set: (p: Partial<PlanState>) => void;
  run: () => Promise<void>;
  cancel: () => void;
  running: boolean;
  progress: Progress | null;
  error: string | null;
};

export const curveFor = (d: DesignResult, cell: number, days: number): PowerCurve | undefined =>
  d.power?.cells[cell]?.curves.find((c) => c.test_days === days);

/** iCPA at which a vendor's effect would just be detectable (§10.2), using this cell's budget. */
export const detectableIcpa = (c: PowerCurve | undefined, budget: number) =>
  c?.mde && c.baseline_test_total ? budget / (c.mde * c.baseline_test_total) : null;

export function powerAtIcpa(c: PowerCurve | undefined, budget: number, icpa: number): number | null {
  if (!c?.points.length || !c.baseline_test_total || icpa <= 0) return null;
  const e = budget / icpa / c.baseline_test_total;
  const pts = c.points;
  if (e <= pts[0].effect) return pts[0].power;
  for (let i = 1; i < pts.length; i++) {
    if (e <= pts[i].effect) {
      const t = (e - pts[i - 1].effect) / (pts[i].effect - pts[i - 1].effect);
      return pts[i - 1].power + t * (pts[i].power - pts[i - 1].power);
    }
  }
  return pts[pts.length - 1].power;
}

const worstMde = (d: DesignResult, days: number) => {
  const m = d.cells.map((_, i) => curveFor(d, i, days)?.mde ?? null);
  return m.some((x) => x == null) ? null : Math.max(...(m as number[]));
};
const flagged = (d: DesignResult) => d.power?.cells.some((c) => c.curves.some((cv) => cv.calibration_flag)) ?? false;

function stageText(p: Progress | null) {
  if (!p) return "Starting…";
  if (p.stage === "screen") return `Checking fit of fair candidates: ${p.done} of ${p.total}`;
  if (p.stage === "fit") return `Scoring the best candidates in detail: ${p.done} of ${p.total}`;
  if (p.stage === "power") return `Replaying your history to measure sensitivity: design ${p.design} of ${p.designs} (${p.done}/${p.total})`;
  return p.stage;
}

function Funnel({ r, days, plannedPre, holdout }: { r: FindResult; days: number; plannedPre: number; holdout: boolean }) {
  const f = r.funnel;
  const simPre = r.designs[0]?.power?.cells[0]?.curves.find((c) => c.test_days === days)?.pre_days;
  return (
    <p className="small muted">
      Searched {num(f.generated)} random {holdout ? "holdouts" : "splits"} → {num(f.passed_share_and_balance)} were fair (size and balance) →
      {" "}{num(f.scored_full_fit)} scored in detail → {num(f.passed_fit)} fit well.
      {simPre != null && <> For a {weeks(days)} test, sensitivity was simulated with {Math.round(simPre / 7)} weeks of history
        {simPre < plannedPre ? ` (your plan uses ${Math.round(plannedPre / 7)}; the simulation needs spare history to replay past windows, so the real test should be at least this sensitive)` : ""}.</>}
    </p>
  );
}

function DesignCard({ d, rank, s, set, chosen }: { d: DesignResult; rank: number; s: PlanState; set: Props["set"]; chosen: boolean }) {
  const [open, setOpen] = useState(false);
  const [chart, setChart] = useState<{ dates: string[]; fit_end: number; cells: { observed: number[]; twin: number[] }[] } | null>(null);
  const [icpa, setIcpa] = useState<number>(s.targetIcpa ?? 0);
  const names = Object.fromEntries((s.data?.geos ?? []).map((g) => [g.geo_id, g.name]));
  const b = budgets(s);
  const mde = worstMde(d, s.duration);
  const det = d.cells.map((_, i) => detectableIcpa(curveFor(d, i, s.duration), b[i]));
  const known = det.filter((x): x is number => x != null);
  const defaultIcpa = icpa || (known.length ? Math.max(1, Math.round(Math.min(...known))) : 50);
  const holdout = isHoldout(s);
  const who = holdout ? "the campaign" : "a vendor";

  const expand = async () => {
    setOpen((o) => !o);
    if (!chart && d.power) {
      const c = await callPython<typeof chart>("design_chart", {
        cells: d.cells, control: d.control, kpi: s.primaryKpi, pre_days: preDays(s), holdout_days: Math.min(...s.durations),
        design: holdout ? "national_holdout" : "geo_cells",
      }).catch(() => null);
      setChart(c);
    }
  };

  return (
    <article className={`design ${chosen ? "chosen" : ""}`} aria-label={`Design ${rank}`}>
      <div className="row">
        <span className="muted small">Design {rank}{rank === 1 ? " · best" : ""}</span>
        <span className="spacer" />
        <button className={chosen ? "btn-primary" : ""} onClick={() => set({ chosen: rank - 1, coinFlip: null, locked: null })} aria-pressed={chosen}>
          {chosen ? "✓ Chosen" : "Choose this design"}
        </button>
      </div>
      {d.power ? (
        <>
          <p className="big" style={{ margin: "6px 0" }}>
            {mde != null ? <>Can detect a lift of <span style={{ color: "var(--accent)" }}>{pct(mde)}</span> or more {holdout ? "in the campaign's markets" : "in each cell"}</> : "Can't reliably detect lifts under 50% with this design"}
            {" "}({weeks(s.duration)} test)<InfoTip term="mde" />
          </p>
          {mde != null && (
            <p style={{ margin: 0 }}>
              If {who}'s true iCPA is worse than{" "}
              <strong>{det.map((x, i) => `${money(x, s.currency)}${d.cells.length > 1 ? ` (${s.labels[i]})` : ""}`).join(" / ")}</strong>,
              this test probably won't see it.<InfoTip term="detectableIcpa" />
            </p>
          )}
          {mde != null && s.decisionBasis === "target_icpa" && s.targetIcpa && det.some((x) => x != null && x < s.targetIcpa!) && (
            <p className="callout warn small">
              Even {holdout ? "a campaign" : "a vendor"} that hits your target iCPA of {money(s.targetIcpa, s.currency)} would probably go undetected here. The test budget is
              small relative to your sales. A bigger budget or a longer test would help{holdout ? "" : ", as would bigger cells"}; otherwise expect an "inconclusive" answer.
            </p>
          )}
        </>
      ) : (
        <p className="muted">Sensitivity not simulated for this design (only the top 5 are, to save time).</p>
      )}
      <div className="chips">
        <span className={`chip ${Math.max(...d.fit) <= 0.1 ? "ok" : "warn"}`}>Fit error {d.fit.map((f) => pct(f)).join(" / ")}<InfoTip term="fit" /></span>
        <span className={`chip ${d.balance_score <= 0.1 ? "ok" : "warn"}`}>Balance gap {pct(d.balance_score)}<InfoTip term="balance" /></span>
        {holdout ? (
          <>
            <span className="chip">{pct(d.control_share)} of sales held out<InfoTip term="holdout" /></span>
            <span className="chip">{d.control.length} markets held out · {d.cells[0].length} with ads</span>
          </>
        ) : (
          <>
            <span className="chip">{pct(d.share_in_test)} of sales in test<InfoTip term="shareInTest" /></span>
            <span className="chip">{d.cells.map((c) => c.length).join(" + ")} test markets · {d.control.length} control<InfoTip term="control" /></span>
          </>
        )}
        {flagged(d) && <span className="chip warn">⚠ Found fake lifts in past data<InfoTip term="falsePositive" /></span>}
      </div>
      <button type="button" className="link-btn small" aria-expanded={open} onClick={expand}>{open ? "Hide details" : "Show markets, fit and sensitivity"}</button>
      {open && (
        <div style={{ marginTop: 12 }}>
          <div className="table-wrap">
            <table>
              <thead><tr><th>{holdout ? "Campaign" : "Cell"}</th><th>Markets</th><th>Share of sales</th><th>Fit error</th><th>Detectable lift</th><th>Detectable iCPA</th><th>Fake-lift rate<InfoTip term="falsePositive" /></th></tr></thead>
              <tbody>
                {d.cells.map((c, i) => {
                  const cv = curveFor(d, i, s.duration);
                  return (
                    <tr key={i}>
                      <td>{s.labels[i]}</td><td>{c.length}</td><td>{pct(d.shares[i])}</td><td>{pct(d.fit[i])}</td>
                      <td>{pct(cv?.mde)}</td><td>{money(det[i], s.currency)}</td>
                      <td>{cv ? `${pct(cv.false_positive_rate, 0)} of ${cv.windows} windows` : "–"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <h4>{holdout ? "Balance: holdout vs. markets with ads" : "Balance between cells"}<InfoTip term="balance" /></h4>
          <div className="chips">{Object.entries(d.balance).map(([k, v]) => <span key={k} className={`chip ${v <= 0.1 ? "ok" : "warn"}`}>{k}: {pct(v)} gap</span>)}</div>
          {d.power && (
            <>
              <div className="field" style={{ maxWidth: 420 }}>
                <label htmlFor={`icpa-${rank}`}>If {who}'s true iCPA were {money(defaultIcpa, s.currency)}…</label>
                <input id={`icpa-${rank}`} type="range" min={1} max={Math.max(500, defaultIcpa * 3)} step={1} value={defaultIcpa} onChange={(e) => setIcpa(Number(e.target.value))} />
                <p className="small" style={{ margin: 0 }}>
                  Chance this test detects it: {d.cells.map((_, i) => `${s.labels[i]} ${pct(powerAtIcpa(curveFor(d, i, s.duration), b[i], defaultIcpa), 0)}`).join(" · ")}
                  <span className="muted"> (assumes extra orders grow in line with spend)</span>
                </p>
              </div>
              <div className="grid-2">
                {d.cells.map((_, i) => (
                  <div key={i}>
                    <h4 style={{ margin: "8px 0 0" }}>{s.labels[i]}: sensitivity<InfoTip term="power" /></h4>
                    <PowerChart title={s.labels[i]} curves={d.power!.cells[i].curves} />
                  </div>
                ))}
              </div>
            </>
          )}
          {chart && (
            <div className="grid-2">
              {chart.cells.map((c, i) => (
                <div key={i}>
                  <h4 style={{ margin: "8px 0 0" }}>{holdout ? "Holdout markets vs their twin (sales index, 1 = average)" : `${s.labels[i]} vs its twin`}<InfoTip term="twin" /></h4>
                  <FitChart title={holdout ? "Holdout" : s.labels[i]} dates={chart.dates} observed={c.observed} twin={c.twin} fitEnd={chart.fit_end} index={holdout} />
                </div>
              ))}
            </div>
          )}
          {holdout && <details><summary>Held-out markets, no ads ({d.control.length})</summary><p className="small">{d.control.map((g) => names[g] ?? g).join(" · ")}</p></details>}
          {d.cells.map((c, i) => (
            <details key={i}><summary>{holdout ? "Markets with ads" : `${s.labels[i]} markets`} ({c.length})</summary><p className="small">{c.map((g) => names[g] ?? g).join(" · ")}</p></details>
          ))}
        </div>
      )}
    </article>
  );
}

export function StepFind({ s, set, run, cancel, running, progress, error }: Props) {
  const r = s.result;
  const stale = r && s.resultKey !== searchKey(s);
  const share = progress ? Math.min(1, progress.done / Math.max(progress.total, 1)) : 0;
  const [showAll, setShowAll] = useState(false);
  const holdout = isHoldout(s);
  return (
    <section className="card">
      <h2>{holdout ? "Find a fair holdout" : "Find fair market splits"}</h2>
      <p className="muted">
        {holdout
          ? "We search thousands of random sets of markets to hold out, keep the ones that move like the rest of the country, then replay your history to see how small a lift each could detect."
          : "We search thousands of random ways to split your markets, keep the fair ones, then replay your history to see how small a lift each could detect."}
        {" "}This runs on your computer and can take a few minutes.
      </p>
      <div className="row">
        <button className="btn-primary" onClick={run} disabled={running}>{r && !stale ? "Search again" : holdout ? "Find a fair holdout" : "Find fair market splits"}</button>
        {running && <button onClick={cancel}>Cancel</button>}
      </div>
      {running && (
        <div style={{ marginTop: 16 }} aria-live="polite">
          <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(share * 100)}><div style={{ width: `${share * 100}%` }} /></div>
          <p className="small muted">{stageText(progress)}</p>
        </div>
      )}
      {error && <div className="callout err">{error}</div>}
      {stale && !running && <div className="callout warn">You changed a setting since this search. Run it again to update the designs.</div>}
      {r && !running && (
        <div style={{ marginTop: 16 }}>
          <Funnel r={r} days={s.duration} plannedPre={preDays(s)} holdout={holdout} />
          {r.designs.length === 0 ? (
            <div className="callout err">
              <strong>No design passed all the checks.</strong> Try allowing {holdout ? "a bigger holdout" : "bigger cells"} (Markets → Advanced), using more history, or excluding fewer markets.
              {r.best_failing.length > 0 && <> The closest had a fit error of {pct(Math.max(...r.best_failing[0].fit))} (limit 10%).</>}
            </div>
          ) : (
            <>
              <div className="row" role="group" aria-label="Test length">
                <span className="small muted">Show results for a</span>
                {s.durations.map((d) => (
                  <button key={d} className={s.duration === d ? "btn-primary small" : "small"} aria-pressed={s.duration === d} onClick={() => set({ duration: d, locked: null })}>{weeks(d)}</button>
                ))}
                <span className="small muted">test</span>
              </div>
              <div style={{ marginTop: 12 }}>
                {(showAll ? r.designs : r.designs.slice(0, 5)).map((d, i) => (
                  <DesignCard key={i} d={d} rank={i + 1} s={s} set={set} chosen={s.chosen === i} />
                ))}
              </div>
              {r.designs.length > 5 && <button className="link-btn" onClick={() => setShowAll((x) => !x)}>{showAll ? "Show fewer" : `Show ${r.designs.length - 5} more designs`}</button>}
            </>
          )}
        </div>
      )}
    </section>
  );
}
