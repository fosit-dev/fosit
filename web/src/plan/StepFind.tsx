import { useState } from "react";
import { InfoTip } from "../components/InfoTip";
import { FitChart, PowerChart } from "../components/Charts";
import { Meter, ShareBar, segmentColors } from "../components/Visuals";
import type { DesignResult, FindResult, Kpi, PowerCurve } from "../lib/plan";
import { money, num, pct, weeks } from "../lib/format";
import { useLevel } from "../lib/level";
import { chanceWords, designInfo, snap, tech, type Segment } from "../lib/words";
import { callPython } from "../worker/client";
import type { Progress } from "../worker/protocol";
import { SMALL_BUSINESS_ORDERS_PER_DAY, ordersPerDay } from "./StepData";
import { budgets, isCampaign, isCrossover, isHoldout, isOneCampaign, preDays, searchKey, type PlanState } from "./state";

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

/** What a vendor must deliver for its effect to be just detectable (§10.2), using this cell's budget:
 * a cost per extra order (orders: lower is better) or extra revenue per 1 of ads (revenue: higher is better). */
export function detectableValue(c: PowerCurve | undefined, budget: number, kpi: Kpi): number | null {
  if (!c?.mde || !c.baseline_test_total || budget <= 0) return null;
  return kpi === "revenue" ? (c.mde * c.baseline_test_total) / budget : budget / (c.mde * c.baseline_test_total);
}

/** Chance that the test sees a vendor whose ads are worth `value`: a cost per extra order, or extra revenue per 1 of ads.
 * Reads the planning simulation's power curve at the lift that this value means for this cell's budget. */
export function powerAtValue(c: PowerCurve | undefined, budget: number, value: number, kpi: Kpi): number | null {
  if (!c?.points.length || !c.baseline_test_total || value <= 0) return null;
  const e = (kpi === "revenue" ? budget * value : budget / value) / c.baseline_test_total;
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

/** A cost per extra order: cents only when the number is small. */
const cost = (x: number | null | undefined, currency: string) => money(x, currency, x != null && Math.abs(x) < 20 ? 2 : 0);

const worstMde = (d: DesignResult, days: number) => {
  const m = d.cells.map((_, i) => curveFor(d, i, days)?.mde ?? null);
  return m.some((x) => x == null) ? null : Math.max(...(m as number[]));
};
const flagged = (d: DesignResult) => d.power?.cells.some((c) => c.curves.some((cv) => cv.calibration_flag)) ?? false;

function stageText(p: Progress | null) {
  if (!p) return "Starting…";
  if (p.stage === "screen") return `Checking which splits are fair: ${p.done} of ${p.total}`;
  if (p.stage === "fit") return `Looking closely at the best ones: ${p.done} of ${p.total}`;
  if (p.stage === "power") return `Replaying your past sales: design ${p.design} of ${p.designs} (${p.done}/${p.total})`;
  return p.stage;
}

function Funnel({ r, days, plannedPre, holdout, full }: { r: FindResult; days: number; plannedPre: number; holdout: boolean; full: boolean }) {
  const f = r.funnel;
  const simPre = r.designs[0]?.power?.cells[0]?.curves.find((c) => c.test_days === days)?.pre_days;
  return (
    <p className="small muted">
      FOSIT tried {num(f.generated)} random {holdout ? "sets of held-out markets" : "splits"}. {num(f.passed_share_and_balance)} were fair in size and balance.
      {" "}It looked closely at {num(f.scored_full_fit)} of them, and {num(f.passed_fit)} passed.
      {r.fit_period === "week" && <> Your daily sales are small, so FOSIT judged each twin on weekly totals.</>}
      {full && simPre != null && <> For a {weeks(days)} test, sensitivity was simulated with {Math.round(simPre / 7)} weeks of history
        {simPre < plannedPre ? ` (your plan uses ${Math.round(plannedPre / 7)}; the simulation needs spare history to replay past windows, so the real test should be at least this sensitive)` : ""}.</>}
    </p>
  );
}

/** The country as this design cuts it: who has the ads where, with real market counts and shares of sales. */
function designSegments(d: DesignResult, s: PlanState): Segment[] {
  const rest = Number.isFinite(d.control_share) ? d.control_share : Math.max(0, 1 - d.shares.reduce((a, x) => a + x, 0));
  if (isCrossover(s)) return [{ label: "Half A", share: d.shares[0], n: d.cells[0].length, role: "half" }, { label: "Half B", share: rest, n: d.control.length, role: "half" }];
  const ads = d.cells.map((c, i): Segment => ({ label: s.labels[i], share: d.shares[i], n: c.length, role: "ads" }));
  return [...ads, { label: isOneCampaign(s) ? "No ads" : isHoldout(s) ? "No CTV" : "No test ads", share: rest, n: d.control.length, role: "none" }];
}

/** "Will the test see it?": the person sets the cost of one extra order they expect, and reads the chance per vendor.
 * The chance comes from the planning simulation's power curve (METHODOLOGY §10.2). */
function SeeTool({ d, s, rank }: { d: DesignResult; s: PlanState; rank: number }) {
  const { level } = useLevel();
  const [picked, setPicked] = useState<number | null>(null);
  const orders = s.primaryKpi === "orders";
  const b = budgets(s);
  const curves = d.cells.map((_, i) => curveFor(d, i, s.duration));
  const live = curves.map((c, i) => ({ c, i })).filter(({ c }) => c?.points.length && c.baseline_test_total);
  if (!live.length) return null;
  const refs = live.map(({ c, i }) => detectableValue(c, b[i], s.primaryKpi)).filter((x): x is number => x != null && Number.isFinite(x) && x > 0);
  const target = orders ? (s.decisionBasis === "target_icpa" ? s.targetIcpa : null) : s.decisionBasis === "breakeven_iroas" ? s.breakevenIroas : null;
  // Start at the person's own limit, or where the first vendor is just visible (so the meter starts near 80%).
  const base = target && target > 0 ? target : refs.length ? snap(refs[0]) : orders ? 50 : 2;
  const lo = Math.min(base, ...refs) / 4, hi = Math.max(base, ...refs) * 4;
  const value = Math.max(lo, Math.min(hi, picked ?? base));
  const toV = (t: number) => snap(lo * (hi / lo) ** (t / 1000));
  const toT = (v: number) => Math.round((1000 * Math.log(v / lo)) / Math.log(hi / lo));
  const colors = segmentColors(designSegments(d, s));
  const cross = isCrossover(s);
  const who = isCampaign(s) || d.cells.length === 1 ? "the campaign" : "a vendor";
  const say = orders ? `${cost(value, s.currency)} per extra order` : `${value.toFixed(2)} ${s.currency} back for each 1 ${s.currency} of ads`;
  return (
    <div className="callout" style={{ background: "var(--surface)" }}>
      <h4 style={{ margin: "0 0 4px" }}>Will the test see it?<InfoTip term="power" /></h4>
      <p className="small muted" style={{ margin: 0 }}>
        {orders ? `Move the slider to the cost of one extra order that you expect from ${who}.` : `Move the slider to the extra revenue that you expect for each 1 ${s.currency} of ads.`}
        {target ? " It starts at the number that you gave." : ""}
      </p>
      <div className="tool">
        <label htmlFor={`see-${rank}`}>{orders ? "Expected cost of one extra order" : `Expected extra revenue for each 1 ${s.currency} of ads`}</label>
        <div className="val" aria-live="polite">{say}</div>
        <input id={`see-${rank}`} type="range" min={0} max={1000} value={toT(value)} aria-valuetext={say} onChange={(e) => setPicked(toV(Number(e.target.value)))} />
      </div>
      {live.map(({ c, i }) => {
        const effect = (orders ? b[i] / value : b[i] * value) / c!.baseline_test_total!;
        const p = powerAtValue(c, b[i], value, s.primaryKpi) ?? 0;
        const w = chanceWords(p);
        return (
          <div className="rangerow" key={i}>
            <div className="lab"><i className="swatch" style={{ background: colors[i] }} />{s.labels[i]}</div>
            <Meter p={p} tone={w.tone} label={`${s.labels[i]}: ${pct(p, 0)} chance that the test sees it`} />
            <div className="say">That is {pct(effect)} more sales {cross ? "while a half has the ads" : "in these markets"}. {w.text}</div>
          </div>
        );
      })}
      {level !== "brief" && <p className="tiny">FOSIT replayed this test many times on your past sales to find this chance. Aim for 80% or more.
        {level === "full" && " The slider assumes that extra orders grow in line with spend."}</p>}
    </div>
  );
}

function DesignCard({ d, rank, s, set, chosen }: { d: DesignResult; rank: number; s: PlanState; set: Props["set"]; chosen: boolean }) {
  const { level } = useLevel();
  const full = level === "full";
  const [open, setOpen] = useState(false);
  const [chart, setChart] = useState<{ dates: string[]; fit_end: number; cells: { observed: number[]; twin: number[] }[] } | null>(null);
  const names = Object.fromEntries((s.data?.geos ?? []).map((g) => [g.geo_id, g.name]));
  const b = budgets(s);
  const orders = s.primaryKpi === "orders";
  const mde = worstMde(d, s.duration);
  const det = d.cells.map((_, i) => detectableValue(curveFor(d, i, s.duration), b[i], s.primaryKpi));
  const holdout = isHoldout(s);
  const cross = isCrossover(s);
  const one = isOneCampaign(s) || cross;
  const where = cross ? "while a half has the ads" : one ? "in the campaign's markets" : d.cells.length === 1 ? "in the test markets" : tech(level, "in each vendor's markets", "in each cell");
  const detText = det.map((x, i) => `${orders ? cost(x, s.currency) : x == null ? "–" : x.toFixed(2)}${d.cells.length > 1 ? ` (${s.labels[i]})` : ""}`).join(" / ");
  // A vendor that only just meets the person's own limit has a smaller effect than this test can see.
  const limit = orders ? (s.decisionBasis === "target_icpa" ? s.targetIcpa : null) : s.decisionBasis === "breakeven_iroas" ? s.breakevenIroas : null;
  const limitTooFine = mde != null && limit != null && det.some((x) => x != null && (orders ? x < limit : x > limit));
  const fitOk = Math.max(...d.fit) <= 0.1, balOk = d.balance_score <= 0.1;
  const fitText = d.fit.map((f) => pct(f)).join(" / ");

  const expand = async () => {
    setOpen((o) => !o);
    if (!chart && d.power) {
      const c = await callPython<typeof chart>("design_chart", {
        cells: d.cells, control: d.control, kpi: s.primaryKpi, pre_days: preDays(s), holdout_days: Math.min(...s.durations),
        design: cross ? "crossover" : holdout ? "national_holdout" : "geo_cells",
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
      <ShareBar segments={designSegments(d, s)} />
      {d.power ? (
        <>
          <p className="big" style={{ margin: "10px 0 6px" }}>
            {mde != null
              ? full
                ? <>Can detect a lift of <span style={{ color: "var(--accent)" }}>{pct(mde)}</span> or more {where}</>
                : <>This test can see the ads if they raise sales by <span style={{ color: "var(--accent)" }}>{pct(mde)}</span> or more {where}</>
              : tech(level, "This test can see only a very large effect: more than 50% extra sales", "Can't reliably detect lifts under 50% with this design")}
            {" "}({weeks(s.duration)} test)<InfoTip term="mde" />
          </p>
          {mde != null && (
            <p style={{ margin: 0 }}>
              {full && orders ? <>If {one || d.cells.length === 1 ? "the campaign" : "a vendor"}'s true iCPA is worse than <strong>{detText}</strong>, this test probably won't see it.</>
                : orders ? <>In money: if one extra order costs more than <strong>{detText}</strong>, the test will probably miss the effect.</>
                : <>In money: if each 1 {s.currency} of ads brings less than <strong>{detText}</strong> {s.currency} of extra revenue, the test will probably miss the effect.</>}
              <InfoTip term="detectableIcpa" />
            </p>
          )}
          {limitTooFine && (
            <p className="callout warn small">
              {orders ? `Your limit is ${cost(limit, s.currency)} for one extra order.` : `You need ${limit!.toFixed(2)} ${s.currency} back for each 1 ${s.currency} of ads.`}{" "}
              {one || d.cells.length === 1 ? "A campaign" : "A vendor"} that only just reaches it has too small an effect for this test to see.
              A bigger budget or a longer test helps{holdout || cross ? "" : ", and bigger groups help too"}. If you change nothing, expect the answer "the test cannot tell".
            </p>
          )}
          {chosen && mde != null && <SeeTool d={d} s={s} rank={rank} />}
        </>
      ) : (
        <p className="muted">FOSIT did not replay your past sales for this design. It does that for the best 5 only, to save time.</p>
      )}
      {full ? (
        <div className="chips">
          {cross
            ? <span className="chip">Halves track each other within {pct(d.fit[0])} per block<InfoTip term="crossover" /></span>
            : <span className={`chip ${fitOk ? "ok" : "warn"}`}>Fit error{s.result?.fit_period === "week" ? " (weekly)" : ""} {fitText}<InfoTip term="fit" /></span>}
          <span className={`chip ${balOk ? "ok" : "warn"}`}>Balance gap {pct(d.balance_score)}<InfoTip term="balance" /></span>
          {!cross && !holdout && <span className="chip">{pct(d.share_in_test)} of sales in test<InfoTip term="shareInTest" /></span>}
          {holdout && <span className="chip">{pct(d.control_share)} of sales held out<InfoTip term="holdout" /></span>}
          {flagged(d) && <span className="chip warn">⚠ Found fake lifts in past data<InfoTip term="falsePositive" /></span>}
        </div>
      ) : (
        <div className="chips">
          {cross
            ? <span className="chip ok">✓ Halves track each other{level === "guided" ? ` within ${pct(d.fit[0])} per block` : ""}<InfoTip term="crossover" /></span>
            : (level === "guided" || !fitOk) && <span className={`chip ${fitOk ? "ok" : "warn"}`}>{fitOk ? `✓ The twin follows the real sales (${fitText} off)` : `! The twin is ${fitText} off the real sales`}<InfoTip term="fit" /></span>}
          {(level === "guided" || !balOk) && <span className={`chip ${balOk ? "ok" : "warn"}`}>{balOk ? `✓ ${holdout ? "The held-out markets are like the rest" : cross ? "The halves are alike" : d.cells.length > 1 ? "The groups are alike" : "The test markets are like the rest"} (${pct(d.balance_score)} apart)` : `! The groups differ by ${pct(d.balance_score)}`}<InfoTip term="balance" /></span>}
          {flagged(d)
            ? <span className="chip warn">⚠ False alarms on past sales<InfoTip term="falsePositive" /></span>
            : level === "guided" && d.power && <span className="chip ok">✓ No false alarms on past sales<InfoTip term="falsePositive" /></span>}
        </div>
      )}
      <button type="button" className="link-btn small" aria-expanded={open} onClick={expand}>{open ? "Hide details" : tech(level, "Show markets and the twin", "Show markets, fit and sensitivity")}</button>
      {open && (
        <div style={{ marginTop: 12 }}>
          {full && (
            <>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>{one ? "Campaign" : "Cell"}</th><th>Markets</th><th>Share of sales</th><th>{cross ? "Block-to-block noise" : "Fit error"}</th><th>Detectable lift</th><th>{orders ? "Detectable iCPA" : "Detectable iROAS"}</th><th>Fake-lift rate<InfoTip term="falsePositive" /></th></tr></thead>
                  <tbody>
                    {d.cells.map((c, i) => {
                      const cv = curveFor(d, i, s.duration);
                      return (
                        <tr key={i}>
                          <td>{s.labels[i]}</td><td>{c.length}</td><td>{pct(d.shares[i])}</td><td>{pct(d.fit[i])}</td>
                          <td>{pct(cv?.mde)}</td><td>{orders ? cost(det[i], s.currency) : det[i]?.toFixed(2) ?? "–"}</td>
                          <td>{cv ? `${pct(cv.false_positive_rate, 0)} of ${cv.windows} windows` : "–"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <h4>{cross ? "Balance: half A vs. half B" : one ? "Balance: holdout vs. markets with ads" : holdout ? "Balance between cells, and the holdout vs. markets with ads" : "Balance between cells"}<InfoTip term="balance" /></h4>
              <div className="chips">{Object.entries(d.balance).map(([k, v]) => <span key={k} className={`chip ${v <= 0.1 ? "ok" : "warn"}`}>{k}: {pct(v)} gap</span>)}</div>
              {d.power && (
                <div className="grid-2">
                  {d.cells.map((_, i) => (
                    <div key={i}>
                      <h4 style={{ margin: "8px 0 0" }}>{s.labels[i]}: sensitivity<InfoTip term="power" /></h4>
                      <PowerChart title={s.labels[i]} curves={d.power!.cells[i].curves} />
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
          {chart && (
            <>
              {!full && <p className="small muted">{cross
                ? "Before the test, the two halves sell in step. That makes each half a fair comparison for the other."
                : "Before the test, the twin (dashed line) moves with the real sales, also on the shaded days that it did not learn from. That makes the twin a fair comparison."}</p>}
              <div className="grid-2">
                {chart.cells.map((c, i) => (
                  <div key={i}>
                    <h4 style={{ margin: "8px 0 0" }}>{cross ? "Half A vs half B, weekly sales (1 = each half's average)" : one ? "Holdout markets vs their twin (sales index, 1 = average)" : holdout ? `Holdout vs its twin from ${s.labels[i]}'s markets (sales index)` : `${s.labels[i]} vs its twin`}<InfoTip term="twin" /></h4>
                    <FitChart title={cross ? "Halves" : holdout ? "Holdout" : s.labels[i]} dates={chart.dates} observed={c.observed} twin={c.twin} fitEnd={chart.fit_end} index={holdout || cross}
                      labels={cross ? ["Half A", "Half B"] : undefined} />
                  </div>
                ))}
              </div>
            </>
          )}
          {cross && <details><summary>Half A ({d.cells[0].length})</summary><p className="small">{d.cells[0].map((g) => names[g] ?? g).join(" · ")}</p></details>}
          {cross && <details><summary>Half B ({d.control.length})</summary><p className="small">{d.control.map((g) => names[g] ?? g).join(" · ")}</p></details>}
          {holdout && <details><summary>Held-out markets, no ads ({d.control.length})</summary><p className="small">{d.control.map((g) => names[g] ?? g).join(" · ")}</p></details>}
          {!cross && d.cells.map((c, i) => (
            <details key={i}><summary>{one ? "Markets with ads" : `${s.labels[i]} markets`} ({c.length})</summary><p className="small">{c.map((g) => names[g] ?? g).join(" · ")}</p></details>
          ))}
        </div>
      )}
    </article>
  );
}

export function StepFind({ s, set, run, cancel, running, progress, error }: Props) {
  const { level } = useLevel();
  const r = s.result;
  const stale = r && s.resultKey !== searchKey(s);
  const share = progress ? Math.min(1, progress.done / Math.max(progress.total, 1)) : 0;
  const [showAll, setShowAll] = useState(false);
  const holdout = isHoldout(s);
  const cross = isCrossover(s);
  const perDay = ordersPerDay(s);
  return (
    <section className="card">
      <h2>{cross ? "Find balanced halves" : holdout ? "Find a fair holdout" : "Find fair market splits"}</h2>
      <p className="muted">
        {cross
          ? "FOSIT tries hundreds of ways to split the country into two halves with the same sales, people and trends. Then it replays your past sales to see how small an effect the test can see."
          : holdout
          ? "FOSIT tries thousands of random sets of markets to hold out, and keeps the sets that move like the rest of the country. Then it replays your past sales to see how small an effect each one can see."
          : "FOSIT tries thousands of random ways to split your markets, and keeps the fair ones. Then it replays your past sales to see how small an effect each one can see."}
        {" "}This runs on your computer and can take a few minutes.
      </p>
      <div className="row">
        <button className="btn-primary" onClick={run} disabled={running}>{r && !stale ? "Search again" : cross ? "Find balanced halves" : holdout ? "Find a fair holdout" : "Find fair market splits"}</button>
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
          {level !== "brief" && <Funnel r={r} days={s.duration} plannedPre={preDays(s)} holdout={holdout} full={level === "full"} />}
          {r.designs.length === 0 ? (
            <div className="callout err">
              <strong>No design passed all the checks.</strong>{" "}
              {!cross && perDay != null && perDay <= SMALL_BUSINESS_ORDERS_PER_DAY
                ? <>Your file shows about {num(Math.round(perDay))} orders a day, which is small for this type of test. Go back to step 1 and try "{designInfo("crossover").title}".</>
                : <>Try this: leave out fewer markets, use more past sales, or allow {holdout ? "a bigger part with no ads" : "bigger groups"} (step 4, at Guided or Full).</>}
              {level === "full" && r.best_failing.length > 0 && <> The closest had a fit error of {pct(Math.max(...r.best_failing[0].fit))} (limit 10%).</>}
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
              {level !== "brief" && <p className="tiny">Each design is one fair way to split your markets. Design 1 has the closest twin. Move the slider on the chosen design to see what the test can catch.</p>}
              <div style={{ marginTop: 12 }}>
                {(showAll ? r.designs : r.designs.slice(0, level === "brief" ? 3 : 5)).map((d, i) => (
                  <DesignCard key={i} d={d} rank={i + 1} s={s} set={set} chosen={s.chosen === i} />
                ))}
              </div>
              {r.designs.length > (level === "brief" ? 3 : 5) && <button className="link-btn" onClick={() => setShowAll((x) => !x)}>{showAll ? "Show fewer" : `Show ${r.designs.length - (level === "brief" ? 3 : 5)} more designs`}</button>}
            </>
          )}
        </div>
      )}
    </section>
  );
}
