import { useMemo, useState } from "react";
import { InfoTip } from "../components/InfoTip";
import { addDays, pretty, todayUtc, daysBetween } from "../lib/dates";
import { pct, weeks } from "../lib/format";
import { DURATION_OPTIONS, isHoldout, preDays, type PlanState } from "./state";

type Props = { s: PlanState; set: (p: Partial<PlanState>) => void };

export function StepMarkets({ s, set }: Props) {
  const [query, setQuery] = useState("");
  const geos = s.data?.geos ?? [];
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q ? geos.filter((g) => g.name.toLowerCase().includes(q) || g.geo_id.toLowerCase().includes(q)) : geos;
    return list.slice(0, 200);
  }, [geos, query]);
  const excludedIds = Object.keys(s.excluded);
  const toggle = (id: string, on: boolean) => {
    const next = { ...s.excluded };
    if (on) next[id] = next[id] ?? "";
    else delete next[id];
    set({ excluded: next });
  };

  return (
    <section className="card">
      <h2>Markets</h2>
      {isHoldout(s) ? (
        <div className="callout warn">
          <strong>Before you lock the plan:</strong> the campaign's vendor(s) must be able to keep every held-out market completely dark
          {s.geoUnit === "cbsa" ? " (metro areas, by ZIP list if needed)" : ""} while running everywhere else. Confirm this with each vendor. You'll be asked to tick it off at the end.
        </div>
      ) : (
        <div className="callout warn">
          <strong>Before you lock the plan:</strong> every vendor must be able to target exactly the markets they're given
          {s.geoUnit === "cbsa" ? " (metro areas, by ZIP list if needed)" : ""}. Confirm this with each vendor. You'll be asked to tick it off at the end.
        </div>
      )}

      <h3>Leave any markets out?</h3>
      <p className="small muted">Exclude markets with something unusual going on during the test: a local promotion, a store opening, a market a vendor can't reach. Excluded markets are dropped from the analysis entirely{isHoldout(s) ? " (the campaign can still run there; they just aren't measured)" : ""}.</p>
      <div className="field">
        <label htmlFor="geo-search" className="sr-only">Search markets</label>
        <input id="geo-search" type="search" placeholder={`Search ${geos.length} markets by name or code`} value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <div className="geo-list" role="group" aria-label="Markets">
        {shown.map((g) => {
          const on = g.geo_id in s.excluded;
          return (
            <div key={g.geo_id} className="geo-item">
              <input type="checkbox" id={`ex-${g.geo_id}`} checked={on} onChange={(e) => toggle(g.geo_id, e.target.checked)} />
              <label htmlFor={`ex-${g.geo_id}`} style={{ fontWeight: 400, margin: 0, flex: 1 }}>
                {g.name} <span className="muted small">{g.geo_id !== g.name ? g.geo_id : ""} · {pct(g.share, 2)} of sales</span>
              </label>
              {on && (
                <input type="text" aria-label={`Reason for excluding ${g.name}`} placeholder="reason (optional)" value={s.excluded[g.geo_id]}
                  onChange={(e) => set({ excluded: { ...s.excluded, [g.geo_id]: e.target.value } })} />
              )}
            </div>
          );
        })}
      </div>
      <p className="small muted">{excludedIds.length ? `${excludedIds.length} excluded.` : "None excluded."} {geos.length > 200 && !query ? "Showing the 200 largest; search to find others." : ""}</p>

      <details>
        <summary>{isHoldout(s) ? "Advanced: how big can the holdout be?" : "Advanced: how big can each cell be?"}</summary>
        <p className="small muted">
          {isHoldout(s)
            ? "The held-out markets' share of your national sales. A bigger holdout costs more reach but makes the twin's ranges more trustworthy; 10–20% is the default."
            : "Each cell's share of your national sales. Bigger cells detect smaller lifts but expose more of your business to the test."}
          <InfoTip term={isHoldout(s) ? "holdout" : "shareInTest"} />
        </p>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="smin">Minimum {isHoldout(s) ? "held out" : "per cell"}: {pct(s.shareMin, 0)}</label>
            <input id="smin" type="range" min={0.01} max={isHoldout(s) ? 0.2 : 0.1} step={0.01} value={s.shareMin} onChange={(e) => set({ shareMin: Math.min(Number(e.target.value), s.shareMax - 0.01) })} />
          </div>
          <div className="field">
            <label htmlFor="smax">Maximum {isHoldout(s) ? "held out" : "per cell"}: {pct(s.shareMax, 0)}</label>
            <input id="smax" type="range" min={0.05} max={0.3} step={0.01} value={s.shareMax} onChange={(e) => set({ shareMax: Math.max(Number(e.target.value), s.shareMin + 0.01) })} />
          </div>
        </div>
      </details>
    </section>
  );
}

export function StepTiming({ s, set }: Props) {
  const historyWeeks = Math.floor((s.data?.summary.days ?? 0) / 7);
  const maxPre = Math.max(4, Math.min(26, historyWeeks));
  const pre = preDays(s);
  const gauge = pre < 56 ? "err" : pre < 84 ? "warn" : "ok";
  const leadDays = daysBetween(todayUtc(), s.testStart);
  const longest = Math.max(...s.durations, 0);
  return (
    <section className="card">
      <h2>Timing</h2>
      <div className="field">
        <label>Test lengths to compare</label>
        <div className="row">
          {DURATION_OPTIONS.map((d) => (
            <label key={d} className="check" style={{ marginBottom: 0 }}>
              <input type="checkbox" checked={s.durations.includes(d)}
                onChange={(e) => {
                  const next = e.target.checked ? [...s.durations, d].sort((a, b) => a - b) : s.durations.filter((x) => x !== d);
                  if (next.length) set({ durations: next, duration: next.includes(s.duration) ? s.duration : next[0] });
                }} />
              <span>{weeks(d)}</span>
            </label>
          ))}
        </div>
        <p className="small muted">We'll show how sensitive each length is. Longer tests catch smaller lifts.</p>
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="start">Planned start date</label>
          <input id="start" type="date" value={s.testStart} min={addDays(todayUtc(), 1)} onChange={(e) => e.target.value && set({ testStart: e.target.value })} />
          <span className="hint">{leadDays < 7 ? "⚠ Less than a week away: leave time to send the plan and set up targeting." : `In ${leadDays} days. Ads run until ${pretty(addDays(s.testStart, longest - 1))} at the longest.`}</span>
        </div>
        <div className="field">
          <label htmlFor="cooldown">Cooldown after ads stop<InfoTip term="cooldown" /></label>
          <select id="cooldown" value={s.cooldown} onChange={(e) => set({ cooldown: Number(e.target.value) })}>
            {[0, 7, 14].map((c) => <option key={c} value={c}>{c} days</option>)}
          </select>
          {isHoldout(s) && <span className="hint">The held-out markets stay dark until the cooldown ends.</span>}
        </div>
      </div>
      <div className="field">
        <label htmlFor="pre">History to build the twins from: {s.preWeeks} weeks<InfoTip term="preperiod" /></label>
        {isHoldout(s) && s.adsBeforeTest === "off" && <p className="small muted" style={{ margin: "0 0 6px" }}>This history should be a time the campaign was off everywhere.</p>}
        {isHoldout(s) && s.adsBeforeTest === "always_on" && <p className="small muted" style={{ margin: "0 0 6px" }}>This history should be a time the campaign ran everywhere the same way.</p>}
        <input id="pre" type="range" min={4} max={maxPre} step={1} value={Math.min(s.preWeeks, maxPre)} onChange={(e) => set({ preWeeks: Number(e.target.value) })} />
        <div className={`callout ${gauge}`} style={{ marginTop: 6 }}>
          {gauge === "ok" && "✓ Enough history. More (up to 26 weeks) still sharpens the test."}
          {gauge === "warn" && "Under 12 weeks: the test works, but its ranges will be wider. 12+ weeks is recommended."}
          {gauge === "err" && "Under 8 weeks: the twins and power estimates are unreliable. Get more history if you can."}
          <span className="small"> Your file has {historyWeeks} weeks. The plan will use the {Math.round(pre / 7)} weeks right before the test starts, so your Read data must include them.</span>
        </div>
      </div>
      <details>
        <summary>Advanced: statistics settings</summary>
        <div className="field">
          <label htmlFor="perm">How to judge chance<InfoTip term="permutations" /></label>
          <select id="perm" value={s.permutations} onChange={(e) => set({ permutations: e.target.value as PlanState["permutations"] })}>
            <option value="moving_block">Moving-block (default, honest about uncertainty)</option>
            <option value="iid">Random days (GeoLift's default; more power, over-confident)</option>
          </select>
        </div>
        <p className="small muted">Decision level: 90% intervals (95% also reported). Random seed: <code>{s.seed}</code>, recorded in the plan so anyone can re-run the market search.</p>
      </details>
    </section>
  );
}
