import { useEffect, useMemo, useState } from "react";
import { InfoTip } from "../components/InfoTip";
import { addDays, pretty, todayUtc, daysBetween } from "../lib/dates";
import { pct, weeks } from "../lib/format";
import { useLevel } from "../lib/level";
import { tech } from "../lib/words";
import { BlockStrip, ShareBar, Timeline, WhyNote, type TimelinePart } from "../components/Visuals";
import { DURATION_OPTIONS, crossoverSetup, isCrossover, isHoldout, isOneCampaign, preDays, sizableCrossoverDurations, type PlanState } from "./state";

type Props = { s: PlanState; set: (p: Partial<PlanState>) => void };

export function StepMarkets({ s, set }: Props) {
  const { level } = useLevel();
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
      {isCrossover(s) ? (
        <div className="callout warn">
          <strong>Before you lock the plan:</strong> the campaign's vendor(s) must be able to switch the ads between two halves of the
          country on fixed dates, every {s.lingering === "long" ? "4" : "2"} weeks{s.geoUnit === "cbsa" ? " (metro areas, by ZIP list if needed)" : ""}.
          Confirm this with each vendor. You'll be asked to tick it off at the end.
        </div>
      ) : isHoldout(s) && !isOneCampaign(s) ? (
        <div className="callout warn">
          <strong>Before you lock the plan:</strong> each vendor must be able to target exactly the markets they're given
          {s.geoUnit === "cbsa" ? " (metro areas, by ZIP list if needed)" : ""}, and no one may run CTV in the held-out markets. Confirm this with each vendor. You'll be asked to tick it off at the end.
        </div>
      ) : isHoldout(s) ? (
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
      <p className="small muted">Leave out a market if something unusual happens there during the test: a local promotion, a store opening, or a vendor that cannot reach it. FOSIT does not use these markets at all{isHoldout(s) ? " (the campaign can still run there; FOSIT does not measure them)" : ""}. Most tests leave out none.</p>
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

      {!isCrossover(s) && level !== "brief" && <details open={level === "full"}>
        <summary>{isHoldout(s) ? "How big can the part with no ads be?" : tech(level, "How big can each vendor's group be?", "Advanced: how big can each cell be?")}</summary>
        <p className="small muted">
          {isHoldout(s)
            ? `The held-out markets' share of your national sales. A bigger part with no ads costs more reach, but it makes the ranges more trustworthy. FOSIT starts at ${isOneCampaign(s) ? "10–20%" : "15–25%"}.${isOneCampaign(s) ? "" : " The vendors split every other market evenly."}`
            : "Each group's share of your national sales. A bigger group lets the test see a smaller effect, but it puts more of your business in the test."}
          <InfoTip term={isHoldout(s) ? "holdout" : "shareInTest"} />
        </p>
        <ShareBar approx segments={isHoldout(s)
          ? [{ label: "With ads", share: 1 - (s.shareMin + s.shareMax) / 2, role: "ads" }, { label: "No ads", share: (s.shareMin + s.shareMax) / 2, role: "none" }]
          : [...s.labels.map((l) => ({ label: l, share: (s.shareMin + s.shareMax) / 2, role: "ads" as const })),
             { label: "No test ads", share: Math.max(0.02, 1 - s.nCells * (s.shareMin + s.shareMax) / 2), role: "none" as const }]} />
        <p className="tiny">The picture shows the middle of your limits. FOSIT picks the real sizes inside them.</p>
        <div className="grid-2" style={{ marginTop: 10 }}>
          <div className="field">
            <label htmlFor="smin">{isHoldout(s) ? "At least" : "Each group, at least"}: {pct(s.shareMin, 0)} of sales</label>
            <input id="smin" type="range" min={0.01} max={isHoldout(s) ? 0.2 : 0.1} step={0.01} value={s.shareMin} onChange={(e) => set({ shareMin: Math.min(Number(e.target.value), s.shareMax - 0.01) })} />
          </div>
          <div className="field">
            <label htmlFor="smax">{isHoldout(s) ? "At most" : "Each group, at most"}: {pct(s.shareMax, 0)} of sales</label>
            <input id="smax" type="range" min={0.05} max={0.3} step={0.01} value={s.shareMax} onChange={(e) => set({ shareMax: Math.max(Number(e.target.value), s.shareMin + 0.01) })} />
          </div>
        </div>
      </details>}
    </section>
  );
}

export function StepTiming({ s, set }: Props) {
  const { level } = useLevel();
  const historyWeeks = Math.floor((s.data?.summary.days ?? 0) / 7);
  const maxPre = Math.max(4, Math.min(26, historyWeeks));
  const pre = preDays(s);
  const gauge = pre < 56 ? "err" : "ok";   // 8 weeks is enough: never send people back for more data they don't need
  const leadDays = daysBetween(todayUtc(), s.testStart);
  const longest = Math.max(...s.durations, 0);
  const shortest = Math.min(...s.durations);
  const sizable = sizableCrossoverDurations(s.lingering, s.data?.summary.days);
  const cross = isCrossover(s);
  const xs = crossoverSetup(s.lingering);
  const adsEnd = addDays(s.testStart, longest - 1);
  const lengths = shortest === longest ? weeks(longest) : `${shortest / 7} to ${weeks(longest)}`;
  const parts: TimelinePart[] = [
    { kind: "history", t: "Past sales", from: addDays(s.testStart, -pre), to: addDays(s.testStart, -1), say: "FOSIT learns from these weeks." },
    { kind: "ads", t: cross ? "Test: halves take turns" : "Ads run", from: s.testStart, to: adsEnd, say: cross ? `${lengths}. The ads move between the halves.` : `${lengths}. You choose the length after the search.` },
    ...(!cross && s.cooldown > 0 ? [{ kind: "cool" as const, t: "Cooldown", from: addDays(adsEnd, 1), to: addDays(adsEnd, s.cooldown), say: "No test ads. FOSIT counts late orders." }] : []),
  ];
  // Offer only the crossover lengths this history can size (§14.4); a longer one would come back without a sensitivity.
  useEffect(() => {
    if (isCrossover(s) && sizable.durations.join() !== s.durations.join())
      set({ durations: sizable.durations, duration: sizable.durations.includes(s.duration) ? s.duration : sizable.durations[0] });
  }, [s.template, s.lingering, s.data?.summary.days]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <section className="card">
      <h2>Timing</h2>
      {level !== "brief" && <WhyNote>The picture shows the dates of your test. It changes when you change a date or a length.</WhyNote>}
      <Timeline parts={parts} readFrom={addDays(adsEnd, (cross ? 0 : s.cooldown) + 1)} />
      {cross && (
        <BlockStrip blockDays={xs.blockDays} washoutDays={xs.washoutDays}
          order={Array.from({ length: longest / xs.blockDays }, (_, i) => (i % 2 ? "B" : "A"))}
          note="This order is an example. A random draw sets the real order when you lock the plan." />
      )}
      {!cross && level === "brief" && (
        <p className="small muted" style={{ marginTop: 10 }}>FOSIT compares tests of {s.durations.map((d) => d / 7).join(", ")} weeks, with {s.cooldown} days of cooldown after the ads stop. Choose Guided to change this.</p>
      )}
      <div style={{ height: 12 }} />
      {isCrossover(s) ? (
        <>
          <fieldset className="field">
            <legend style={{ fontWeight: 600 }}>How long does your advertising keep working after it stops?<InfoTip term="crossover" /></legend>
            {([["short", "A few days (most performance CTV)", "the halves swap every 2 weeks"],
               ["long", "A week or more (brand campaigns)", "the halves swap every 4 weeks, and the test runs longer"]] as const).map(([v, text, hint]) => (
              <label key={v} className="check">
                <input type="radio" name="lingering" checked={s.lingering === v}
                  onChange={() => { const x = sizableCrossoverDurations(v, s.data?.summary.days); set({ lingering: v, durations: x.durations, duration: x.durations[0] }); }} />
                <span>{text} <span className="muted small">: {hint}</span></span>
              </label>
            ))}
          </fieldset>
          <div className="callout warn small">
            <strong>Choose carefully.</strong> If the ads keep working longer than your choice, the test shows too little of their effect,
            and its range can miss the true number. For example, if the effect fades by half in a week, 2-week turns show about half of it
            and 4-week turns about three quarters. If you are not sure, choose "A week or more". The test takes longer, but the error is smaller.
          </div>
          <p className="small muted">{s.durations.length > 1
            ? `FOSIT compares a ${s.durations[0] / 7}-week and a ${s.durations[s.durations.length - 1] / 7}-week test. A longer test sees a smaller effect.`
            : `FOSIT plans a ${s.durations[0] / 7}-week test.`}
            {sizable.dropped.length > 0 && ` A ${sizable.dropped[0] / 7}-week test needs at least ${weeks(sizable.dropped[0])} of sales history to plan, and your file has ${historyWeeks} weeks.`}</p>
        </>
      ) : level === "brief" ? null : (
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
        <p className="small muted">FOSIT shows what each length can see. A longer test sees a smaller effect.</p>
      </div>
      )}
      <div className="grid-2">
        <div className="field">
          <label htmlFor="start">Planned start date</label>
          <input id="start" type="date" value={s.testStart} min={addDays(todayUtc(), 1)} onChange={(e) => e.target.value && set({ testStart: e.target.value })} />
          <span className="hint">{leadDays < 7 ? "⚠ Less than a week away: leave time to send the plan and set up targeting." : `In ${leadDays} days. Ads run until ${pretty(addDays(s.testStart, longest - 1))} at the longest.`}</span>
        </div>
        {!isCrossover(s) && level !== "brief" && <div className="field">
          <label htmlFor="cooldown">Cooldown after the ads stop<InfoTip term="cooldown" /></label>
          <select id="cooldown" value={s.cooldown} onChange={(e) => set({ cooldown: Number(e.target.value) })}>
            {[0, 7, 14].map((c) => <option key={c} value={c}>{c} days</option>)}
          </select>
          {isHoldout(s) && <span className="hint">The held-out markets stay dark until the cooldown ends.</span>}
        </div>}
      </div>
      <div className="field">
        <label htmlFor="pre">{tech(level, "Past sales that FOSIT learns from", "History to build the twins from (pre-period)")}: {Math.round(pre / 7)} weeks<InfoTip term="preperiod" /></label>
        {isHoldout(s) && s.adsBeforeTest === "off" && <p className="small muted" style={{ margin: "0 0 6px" }}>This history should be a time the campaign was off everywhere.</p>}
        {isHoldout(s) && s.adsBeforeTest === "always_on" && <p className="small muted" style={{ margin: "0 0 6px" }}>This history should be a time the campaign ran everywhere the same way.</p>}
        {level !== "brief" && <input id="pre" type="range" min={4} max={maxPre} step={1} value={Math.min(s.preWeeks, maxPre)} onChange={(e) => set({ preWeeks: Number(e.target.value) })} />}
        <div className={`callout ${gauge}`} style={{ marginTop: 6 }}>
          {gauge === "ok" && "✓ Enough history. You do not need more."}
          {gauge === "err" && "Under 8 weeks: FOSIT needs at least 8 weeks to build reliable twins. Add older sales if you have them."}
          <span className="small"> Your file has {historyWeeks} weeks. The plan will use the {Math.round(pre / 7)} weeks right before the test starts, so your Read data must include them.</span>
        </div>
      </div>
      {level === "full" && <details open>
        <summary>Advanced: statistics settings</summary>
        <div className="field">
          <label htmlFor="perm">How to judge chance<InfoTip term="permutations" /></label>
          <select id="perm" value={s.permutations} onChange={(e) => set({ permutations: e.target.value as PlanState["permutations"] })}>
            <option value="moving_block">Moving-block (default, honest about uncertainty)</option>
            <option value="iid">Random days (GeoLift's default; more power, over-confident)</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="fitp">Judge how well a twin fits<InfoTip term="fit" /></label>
          <select id="fitp" value={s.fitPeriod} onChange={(e) => set({ fitPeriod: e.target.value as PlanState["fitPeriod"] })}>
            <option value="auto">Automatically (weekly totals when sales are small)</option>
            <option value="day">Day by day</option>
            <option value="week">On weekly totals</option>
          </select>
        </div>
        <p className="small muted">Decision level: 90% intervals (95% also reported). Random seed: <code>{s.seed}</code>, recorded in the plan so anyone can re-run the market search.</p>
      </details>}
    </section>
  );
}
