// Small, dependency-free SVG charts. Each has an accessible name and a data-table alternative.
import { useEffect, useRef, useState } from "react";
import type { PowerCurve } from "../lib/plan";
import { pct, weeks } from "../lib/format";

const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

export function Sparkline({ values, label }: { values: number[]; label: string }) {
  if (!values.length) return null;
  const w = 320, h = 56;
  const max = Math.max(...values), min = Math.min(...values);
  const x = (i: number) => (i / Math.max(values.length - 1, 1)) * w;
  const y = (v: number) => h - 4 - ((v - min) / (max - min || 1)) * (h - 8);
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  return (
    <svg className="sparkline" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label} preserveAspectRatio="none">
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function TableToggle({ children, label }: { children: React.ReactNode; label: string }) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <button type="button" className="link-btn small" onClick={() => setShow((s) => !s)} aria-expanded={show}>
        {show ? "Hide" : "Show"} {label} as a table
      </button>
      {show && children}
    </div>
  );
}

/** Power vs lift, one line per test length, with the 80% target. */
export function PowerChart({ curves, target = 0.8, title }: { curves: PowerCurve[]; target?: number; title: string }) {
  const W = 420, H = 220, L = 44, R = 12, T = 12, B = 34;
  const maxX = Math.max(0.1, ...curves.flatMap((c) => c.points.map((p) => p.effect)));
  const x = (e: number) => L + (e / maxX) * (W - L - R);
  const y = (p: number) => T + (1 - p) * (H - T - B);
  const ticks = [0, maxX / 4, maxX / 2, (3 * maxX) / 4, maxX];
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}: chance of detecting each lift size, by test length`}>
        {[0, 0.25, 0.5, 0.75, 1].map((p) => (
          <g key={p}>
            <line x1={L} x2={W - R} y1={y(p)} y2={y(p)} stroke="var(--grid)" />
            <text x={L - 6} y={y(p) + 4} textAnchor="end" className="tick">{pct(p, 0)}</text>
          </g>
        ))}
        {ticks.map((e) => (
          <text key={e} x={x(e)} y={H - B + 16} textAnchor="middle" className="tick">{pct(e, 0)}</text>
        ))}
        <line x1={L} x2={W - R} y1={y(target)} y2={y(target)} stroke="var(--muted)" strokeDasharray="4 4" />
        <text x={W - R} y={y(target) - 4} textAnchor="end" className="tick">{pct(target, 0)} target</text>
        {curves.map((c, i) => (
          <g key={c.test_days}>
            <path fill="none" stroke={SERIES[i % SERIES.length]} strokeWidth="2.25"
              d={c.points.map((p, j) => `${j ? "L" : "M"}${x(p.effect).toFixed(1)},${y(p.power).toFixed(1)}`).join("")} />
            {c.points.map((p) => <circle key={p.effect} cx={x(p.effect)} cy={y(p.power)} r="2.5" fill={SERIES[i % SERIES.length]} />)}
          </g>
        ))}
        <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle" className="axis-label">True lift during the test</text>
      </svg>
      <figcaption className="legend">
        {curves.map((c, i) => (
          <span key={c.test_days}><i style={{ background: SERIES[i % SERIES.length] }} aria-hidden />{weeks(c.test_days)}</span>
        ))}
      </figcaption>
      <TableToggle label="power">
        <table className="data-table">
          <thead><tr><th>Test length</th><th>Lift</th><th>Power</th><th>Past windows</th></tr></thead>
          <tbody>
            {curves.flatMap((c) => c.points.map((p) => (
              <tr key={`${c.test_days}-${p.effect}`}><td>{weeks(c.test_days)}</td><td>{pct(p.effect)}</td><td>{pct(p.power, 0)}</td><td>{c.windows}</td></tr>
            )))}
          </tbody>
        </table>
      </TableToggle>
    </figure>
  );
}

/** A cell's average daily KPI vs its twin; the shaded part is the holdout the twin never saw. */
export function FitChart({ dates, observed, twin, fitEnd, title }: { dates: string[]; observed: number[]; twin: number[]; fitEnd: number; title: string }) {
  const W = 420, H = 170, L = 40, R = 8, T = 10, B = 24;
  const all = [...observed, ...twin];
  const max = Math.max(...all), min = Math.min(...all);
  const x = (i: number) => L + (i / Math.max(dates.length - 1, 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - min) / (max - min || 1)) * (H - T - B);
  const path = (vs: number[]) => vs.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}: real markets vs their twin before the test`}>
        <rect x={x(fitEnd)} y={T} width={x(dates.length - 1) - x(fitEnd)} height={H - T - B} fill="var(--shade)" />
        <text x={x(fitEnd) + 4} y={T + 12} className="tick">holdout</text>
        <path d={path(twin)} fill="none" stroke="var(--series-2)" strokeWidth="2" strokeDasharray="5 3" />
        <path d={path(observed)} fill="none" stroke="var(--series-1)" strokeWidth="1.75" />
        <text x={L} y={H - 6} className="tick">{dates[0]}</text>
        <text x={W - R} y={H - 6} textAnchor="end" className="tick">{dates[dates.length - 1]}</text>
      </svg>
      <figcaption className="legend">
        <span><i style={{ background: "var(--series-1)" }} aria-hidden />Real markets (avg per market)</span>
        <span><i className="dashed" style={{ borderColor: "var(--series-2)" }} aria-hidden />Twin</span>
      </figcaption>
      <TableToggle label="fit">
        <table className="data-table">
          <thead><tr><th>Date</th><th>Real</th><th>Twin</th></tr></thead>
          <tbody>{dates.map((d, i) => <tr key={d}><td>{d}</td><td>{observed[i].toFixed(1)}</td><td>{twin[i].toFixed(1)}</td></tr>)}</tbody>
        </table>
      </TableToggle>
    </figure>
  );
}

/** Daily totals: what happened vs the twin's "no ads" estimate. Test days shaded, cooldown lighter. */
export function ImpactChart({ dates, observed, counterfactual, nPre, testDays, title, unit }: {
  dates: string[]; observed: number[]; counterfactual: number[]; nPre: number; testDays: number; title: string; unit: string;
}) {
  const from = Math.max(0, nPre - 56);
  const d = dates.slice(from), o = observed.slice(from), c = counterfactual.slice(from);
  const pre = nPre - from;
  // draw at the container's real width so labels stay readable on phones and desktops alike
  const box = useRef<HTMLElement>(null);
  const [W, setW] = useState(640);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = W < 500 ? 200 : 260, L = 52, R = 8, T = 10, B = 24;
  const all = [...o, ...c];
  const max = Math.max(...all), min = Math.min(0, ...all);
  const x = (i: number) => L + (i / Math.max(d.length - 1, 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - min) / (max - min || 1)) * (H - T - B);
  const path = (vs: number[]) => vs.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const testEnd = Math.min(pre + testDays - 1, d.length - 1);
  return (
    <figure className="chart" ref={box}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}: daily ${unit}, real vs the twin's estimate without ads`}>
        <rect x={x(pre)} y={T} width={x(testEnd) - x(pre)} height={H - T - B} fill="var(--shade)" />
        {testEnd < d.length - 1 && <rect x={x(testEnd)} y={T} width={x(d.length - 1) - x(testEnd)} height={H - T - B} fill="var(--shade)" opacity="0.45" />}
        <text x={x(pre) + 4} y={T + 12} className="tick">ads on</text>
        {[max, (max + min) / 2, min].map((v) => (
          <text key={v} x={L - 6} y={y(v) + 4} textAnchor="end" className="tick">{Math.round(v).toLocaleString()}</text>
        ))}
        <path d={path(c)} fill="none" stroke="var(--series-2)" strokeWidth="2" strokeDasharray="5 3" />
        <path d={path(o)} fill="none" stroke="var(--series-1)" strokeWidth="1.75" />
        <text x={L} y={H - 6} className="tick">{d[0]}</text>
        <text x={W - R} y={H - 6} textAnchor="end" className="tick">{d[d.length - 1]}</text>
      </svg>
      <figcaption className="legend">
        <span><i style={{ background: "var(--series-1)" }} aria-hidden />What happened</span>
        <span><i className="dashed" style={{ borderColor: "var(--series-2)" }} aria-hidden />Twin: what would have happened without ads</span>
      </figcaption>
      <TableToggle label="daily results">
        <table className="data-table">
          <thead><tr><th>Date</th><th>Real</th><th>Twin</th><th>Gap</th></tr></thead>
          <tbody>{d.map((day, i) => <tr key={day}><td>{day}{i >= pre ? " (test)" : ""}</td><td>{o[i].toFixed(0)}</td><td>{c[i].toFixed(0)}</td><td>{(o[i] - c[i]).toFixed(0)}</td></tr>)}</tbody>
        </table>
      </TableToggle>
    </figure>
  );
}
