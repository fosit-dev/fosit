import { InfoTip } from "../components/InfoTip";
import { money } from "../lib/format";
import { budgets, isHoldout, withCells, withTemplate, type PlanState, type Template } from "./state";

type Props = { s: PlanState; set: (p: Partial<PlanState>) => void };

const TEMPLATES: { id: Template; title: string; text: string; cells: number }[] = [
  { id: "two_vendor", title: "Two-vendor test", text: "Split one CTV budget between two platforms and find out which one really drives sales.", cells: 2 },
  { id: "single", title: "Single-channel test", text: "Is this channel driving incremental sales at all?", cells: 1 },
  { id: "national_holdout", title: "National campaign with a holdout", text: "Keep the campaign running almost everywhere, leave about a tenth of the country without it, and measure what it really drives.", cells: 1 },
  { id: "custom", title: "Custom", text: "Up to 6 cells, your own settings.", cells: 3 },
];

export function StepTemplate({ s, set }: Props) {
  return (
    <section className="card">
      <h2>What do you want to find out?</h2>
      <div className="choice-grid" role="group" aria-label="Test template">
        {TEMPLATES.map((t) => (
          <button key={t.id} type="button" className="choice" aria-pressed={s.template === t.id}
            onClick={() => set(withTemplate(s, t.id, t.cells))}>
            <strong>{t.title}{t.id === "two_vendor" && <span className="tag">Recommended</span>}</strong>
            <span className="muted small">{t.text}</span>
          </button>
        ))}
      </div>
      {isHoldout(s) && (
        <fieldset className="field" style={{ marginTop: 16 }}>
          <legend style={{ fontWeight: 600 }}>In the weeks before the test, is this campaign running?<InfoTip term="adsBeforeTest" /></legend>
          {([
            ["off", "No, it's off (a new campaign or a new flight)"],
            ["always_on", "Yes, everywhere (always on)"],
            ["some", "Yes, but only in some markets"],
          ] as const).map(([v, text]) => (
            <label key={v} className="check">
              <input type="radio" name="ads-before" checked={s.adsBeforeTest === v} onChange={() => set({ adsBeforeTest: v })} />
              <span>{text}</span>
            </label>
          ))}
          {s.adsBeforeTest === "always_on" && (
            <p className="callout small">Fine. The held-out markets go dark when the test starts. Past ads keep working for a while, so the result will
              understate the campaign a little: a cautious number. Keep the holdout dark through the cooldown too.</p>
          )}
          {s.adsBeforeTest === "some" && (
            <p className="callout err small">FOSIT can't measure this cleanly: the twin would learn from a history where only some markets had the
              campaign. Pause it for a few weeks (so the history is clean), or run it everywhere for a few weeks first, then plan the holdout.</p>
          )}
        </fieldset>
      )}
      {s.template === "custom" && (
        <div className="field" style={{ marginTop: 16, maxWidth: 260 }}>
          <label htmlFor="ncells">Number of cells<InfoTip term="cell" /></label>
          <select id="ncells" value={s.nCells} onChange={(e) => set(withCells(s, Number(e.target.value)))}>
            {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
      )}
    </section>
  );
}

export function StepTest({ s, set }: Props) {
  const b = budgets(s);
  const splitTotal = s.split.reduce((a, x) => a + x, 0);
  return (
    <section className="card">
      <h2>Your test</h2>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="tname">Test name</label>
          <input id="tname" type="text" value={s.testName} placeholder="e.g. Q1 CTV vendor test" onChange={(e) => set({ testName: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="adv">Advertiser <span className="hint">(optional, appears on the plan)</span></label>
          <input id="adv" type="text" value={s.advertiserLabel} onChange={(e) => set({ advertiserLabel: e.target.value })} />
        </div>
      </div>

      {isHoldout(s) ? (
        <>
          <h3>Campaign<InfoTip term="holdout" /></h3>
          <p className="small muted">One campaign: one vendor, or several running together. To compare vendors, choose a two-vendor test instead.</p>
        </>
      ) : (
        <>
          <h3>Cells<InfoTip term="cell" /></h3>
          <p className="small muted">Name them however you like, for example after each vendor. FOSIT never knows who's behind a cell.</p>
        </>
      )}
      <div className="grid-2">
        {s.labels.map((l, i) => (
          <div className="field" key={i}>
            <label htmlFor={`label-${i}`}>{isHoldout(s) ? "Campaign name" : `Cell ${i + 1} name`}</label>
            <input id={`label-${i}`} type="text" value={l}
              onChange={(e) => set({ labels: s.labels.map((x, j) => (j === i ? e.target.value : x)) })} />
          </div>
        ))}
      </div>

      <div className="grid-2">
        <div className="field">
          <label htmlFor="budget">{isHoldout(s) ? "Campaign budget during the test" : "Total test budget"}</label>
          <input id="budget" type="number" min={0} step={1000} value={s.totalBudget}
            onChange={(e) => set({ totalBudget: Math.max(0, Number(e.target.value)) })} />
        </div>
        <div className="field">
          <label htmlFor="currency">Currency</label>
          <select id="currency" value={s.currency} onChange={(e) => set({ currency: e.target.value })}>
            {["USD", "CAD", "EUR", "GBP", "AUD"].map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
      </div>
      {s.nCells > 1 && (
        <div className="field">
          <label>Budget split</label>
          {s.nCells === 2 ? (
            <>
              <input type="range" min={10} max={90} step={5} value={s.split[0]} aria-label={`${s.labels[0]} share of budget`}
                onChange={(e) => set({ split: [Number(e.target.value), 100 - Number(e.target.value)] })} />
              <div className="row small"><span>{s.labels[0]}: {s.split[0]}% · {money(b[0], s.currency)}</span><span className="spacer" /><span>{s.labels[1]}: {s.split[1]}% · {money(b[1], s.currency)}</span></div>
              {s.split[0] !== 50 && <p className="small muted">An uneven split is fine: iCPA and iROAS use each cell's actual spend.</p>}
            </>
          ) : (
            <div className="grid-3">
              {s.split.map((p, i) => (
                <div key={i}>
                  <label htmlFor={`split-${i}`} className="small">{s.labels[i]} (%)</label>
                  <input id={`split-${i}`} type="number" min={0} max={100} value={p}
                    onChange={(e) => set({ split: s.split.map((x, j) => (j === i ? Number(e.target.value) : x)) })} />
                </div>
              ))}
              {splitTotal !== 100 && <p className="small" style={{ color: "var(--err)" }}>The split adds up to {splitTotal}%, not 100%.</p>}
            </div>
          )}
        </div>
      )}

      <h3>What counts as success?</h3>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="kpi">Primary goal</label>
          <select id="kpi" value={s.primaryKpi} onChange={(e) => set({ primaryKpi: e.target.value as PlanState["primaryKpi"] })}>
            <option value="orders">Orders (or conversions)</option>
            <option value="revenue">Revenue</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="basis">What would make this worth it?<InfoTip term="targetIcpa" /></label>
          <select id="basis" value={s.decisionBasis} onChange={(e) => set({ decisionBasis: e.target.value as PlanState["decisionBasis"] })}>
            <option value="planned_mde">I'm not sure yet</option>
            <option value="target_icpa">A target iCPA (cost per extra order)</option>
            <option value="breakeven_iroas">A break-even iROAS</option>
          </select>
        </div>
      </div>
      {s.decisionBasis === "target_icpa" && (
        <div className="field" style={{ maxWidth: 300 }}>
          <label htmlFor="ticpa">Target iCPA ({s.currency})</label>
          <input id="ticpa" type="number" min={0} step={1} value={s.targetIcpa ?? ""} onChange={(e) => set({ targetIcpa: e.target.value ? Number(e.target.value) : null })} />
        </div>
      )}
      {s.decisionBasis === "breakeven_iroas" && (
        <div className="field" style={{ maxWidth: 300 }}>
          <label htmlFor="biroas">Break-even iROAS</label>
          <input id="biroas" type="number" min={0} step={0.1} value={s.breakevenIroas ?? ""} onChange={(e) => set({ breakevenIroas: e.target.value ? Number(e.target.value) : null })} />
        </div>
      )}
    </section>
  );
}

export function templateStepProblems(s: PlanState): string[] {
  if (!isHoldout(s)) return [];
  if (s.adsBeforeTest == null) return ["Tell us whether the campaign is running before the test."];
  if (s.adsBeforeTest === "some") return ["A national holdout needs a history where the campaign was off everywhere or on everywhere."];
  return [];
}

export function testStepProblems(s: PlanState): string[] {
  const p: string[] = [];
  if (!s.testName.trim()) p.push("Give the test a name.");
  const labels = s.labels.map((l) => l.trim());
  if (labels.some((l) => !l) || new Set(labels).size !== labels.length) p.push("Cell names must be filled in and different.");
  if (s.totalBudget <= 0) p.push("Enter a budget.");
  if (s.split.reduce((a, x) => a + x, 0) !== 100 || s.split.some((x) => x <= 0)) p.push("The budget split must add up to 100%.");
  if (s.decisionBasis === "target_icpa" && !(s.targetIcpa && s.targetIcpa > 0)) p.push("Enter a target iCPA, or choose \"I'm not sure yet\".");
  if (s.decisionBasis === "breakeven_iroas" && !(s.breakevenIroas && s.breakevenIroas > 0)) p.push("Enter a break-even iROAS, or choose \"I'm not sure yet\".");
  return p;
}
