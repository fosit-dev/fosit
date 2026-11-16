import { InfoTip } from "../components/InfoTip";
import { ConsultCallout } from "../components/Consult";
import { Anatomy, ShareBar, WhyNote } from "../components/Visuals";
import { money } from "../lib/format";
import { LevelPicker, useLevel } from "../lib/level";
import { DESIGNS, GOALS, PLAN_LEVELS, anatomySteps, designInfo, exampleSegments, goalOf, tech } from "../lib/words";
import { budgets, isCampaign, isHoldout, withCells, withTemplate, type PlanState, type Template } from "./state";

type Props = { s: PlanState; set: (p: Partial<PlanState>) => void };

/** Step 1: the question first, then the test types that answer it, each with a picture. No test-design words until Full. */
export function StepTemplate({ s, set }: Props) {
  const { level } = useLevel();
  const goal = goalOf(s.template);
  const pick = (t: Template) => set(withTemplate(s, t, designInfo(t).cells));
  const picture = (
    <>
      <ShareBar segments={exampleSegments(s.template, s.labels)} approx />
      <p className="tiny">Example sizes. FOSIT finds the real groups from your sales.</p>
      <Anatomy steps={anatomySteps(s.template, s.nCells, s.lingering)} />
    </>
  );
  return (
    <>
      <section className="card" aria-labelledby="detail-q">
        <h2 id="detail-q">How much detail do you want?</h2>
        <LevelPicker hints={PLAN_LEVELS} label="How much detail" />
        <p className="tiny" style={{ margin: 0 }}>You can change this at any time with the switch at the top of the page.</p>
      </section>

      <section className="card">
        <h2>What do you want to find out?</h2>
        <div className="goal-grid" role="group" aria-label="What you want to find out">
          {GOALS.map((g) => (
            <button key={g.id} type="button" className="choice" aria-pressed={goal === g.id} onClick={() => goal !== g.id && pick(g.first)}>
              <strong>{g.title}</strong>
              <span className="muted small">{g.text}</span>
            </button>
          ))}
        </div>

        <h3>How do you want to run the test?</h3>
        {level !== "brief" && <WhyNote>Each picture shows the country as one bar. Color shows where the ads run. Gray shows where they do not run.</WhyNote>}
        <div className="choice-grid" role="group" aria-label="Test type">
          {DESIGNS.filter((d) => d.goal === goal).map((d) => (
            <button key={d.id} type="button" className="choice" aria-pressed={s.template === d.id} onClick={() => pick(d.id)}>
              <ShareBar mini segments={exampleSegments(d.id, s.template === d.id ? s.labels : Array(d.cells).fill(""))} approx />
              <strong>{d.title}{d.recommended && <span className="tag">Recommended</span>}</strong>
              <span className="muted small">{d.text}</span>
              <span className="good">{d.good}</span>
              {level === "full" && <span className="also">{d.technical}</span>}
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
              <p className="callout small">That works. The held-out markets go dark when the test starts. Past ads still work for some time,
                so the result is a little too low. Keep the held-out markets dark through the cooldown too.</p>
            )}
            {s.adsBeforeTest === "some" && (
              <p className="callout err small">FOSIT can't measure this cleanly: the twin would learn from a history where only some markets had the
                campaign. Pause it for a few weeks (so the history is clean), or run it everywhere for a few weeks first, then plan the test.</p>
            )}
          </fieldset>
        )}
        {s.template === "vendor_split" && (
          <div className="field" style={{ marginTop: 16, maxWidth: 260 }}>
            <label htmlFor="nvendors">Number of vendors</label>
            <select id="nvendors" value={s.nCells} onChange={(e) => set(withCells(s, Number(e.target.value)))}>
              {[2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        )}
        {s.template === "custom" && (
          <div className="field" style={{ marginTop: 16, maxWidth: 260 }}>
            <label htmlFor="ncells">{tech(level, "Number of vendors", "Number of cells")}<InfoTip term="cell" /></label>
            <select id="ncells" value={s.nCells} onChange={(e) => set(withCells(s, Number(e.target.value)))}>
              {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        )}
      </section>

      <section className="card" aria-labelledby="how-it-works">
        {level === "brief"
          ? <details><summary id="how-it-works">How this test works</summary>{picture}</details>
          : <><h2 id="how-it-works">How this test works</h2>{picture}</>}
      </section>
      <ConsultCallout />
    </>
  );
}

export function StepTest({ s, set }: Props) {
  const { level } = useLevel();
  const b = budgets(s);
  const one = goalOf(s.template) === "one";
  const splitTotal = s.split.reduce((a, x) => a + x, 0);
  const unit = tech(level, "Vendor", "Cell");
  return (
    <section className="card">
      <h2>Your test</h2>
      {level !== "brief" && <WhyNote>These names and numbers go into the plan that you send to everyone before the test starts.</WhyNote>}
      <div className="grid-2">
        <div className="field">
          <label htmlFor="tname">Test name</label>
          <input id="tname" type="text" value={s.testName} placeholder="e.g. Q1 CTV vendor test" onChange={(e) => set({ testName: e.target.value })} />
        </div>
        {level !== "brief" && <div className="field">
          <label htmlFor="adv">Advertiser <span className="hint">(optional, appears on the plan)</span></label>
          <input id="adv" type="text" value={s.advertiserLabel} onChange={(e) => set({ advertiserLabel: e.target.value })} />
        </div>}
      </div>

      {one ? (
        <>
          <h3>Your campaign{isCampaign(s) && <InfoTip term={s.template === "crossover" ? "crossover" : "holdout"} />}</h3>
          <p className="small muted">One campaign: one vendor, or several vendors together. To compare vendors, go back and choose "Which vendor brings more extra sales?".</p>
        </>
      ) : (
        <>
          <h3>{tech(level, "The vendors", "Cells")}<InfoTip term="cell" /></h3>
          <p className="small muted">Use any names. FOSIT never knows who a vendor is, and it treats every vendor in the same way.</p>
        </>
      )}
      <div className="grid-2">
        {s.labels.map((l, i) => (
          <div className="field" key={i}>
            <label htmlFor={`label-${i}`}>{one ? "Campaign name" : `${unit} ${i + 1} name`}</label>
            <input id={`label-${i}`} type="text" value={l}
              onChange={(e) => set({ labels: s.labels.map((x, j) => (j === i ? e.target.value : x)) })} />
          </div>
        ))}
      </div>

      <div className="grid-2">
        <div className="field">
          <label htmlFor="budget">{one ? "Campaign budget during the test" : "Total test budget"}</label>
          <input id="budget" type="number" min={0} step={1000} value={s.totalBudget}
            onChange={(e) => set({ totalBudget: Math.max(0, Number(e.target.value)) })} />
          {level !== "brief" && <span className="hint">The media spend that you plan for the test. FOSIT uses it to show the cost of one extra order.</span>}
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
              {s.split[0] !== 50 && <p className="small muted">{tech(level, "An uneven split is fine. FOSIT uses the real spend of each vendor.", "An uneven split is fine: iCPA and iROAS use each cell's actual spend.")}</p>}
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
          <label htmlFor="kpi">{tech(level, "What do you count?", "Primary KPI")}</label>
          <select id="kpi" value={s.primaryKpi} onChange={(e) => set({ primaryKpi: e.target.value as PlanState["primaryKpi"] })}>
            <option value="orders">Orders (or sign-ups, leads)</option>
            <option value="revenue">Revenue</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="basis">What would make this worth it?<InfoTip term="targetIcpa" /></label>
          <select id="basis" value={s.decisionBasis} onChange={(e) => set({ decisionBasis: e.target.value as PlanState["decisionBasis"] })}>
            <option value="planned_mde">I'm not sure yet</option>
            <option value="target_icpa">{tech(level, "I know the most I can pay for one extra order", "A target iCPA (cost per extra order)")}</option>
            <option value="breakeven_iroas">{tech(level, `I know the revenue I need for each 1 ${s.currency} of ads`, "A break-even iROAS")}</option>
          </select>
        </div>
      </div>
      {s.decisionBasis === "planned_mde" && level !== "brief" && (
        <p className="small muted">That is fine. FOSIT then compares the result with the smallest effect that the test can see.</p>
      )}
      {s.decisionBasis === "target_icpa" && (
        <div className="field" style={{ maxWidth: 360 }}>
          <label htmlFor="ticpa">{tech(level, `The most you can pay for one extra order (${s.currency})`, `Target iCPA (${s.currency})`)}<InfoTip term="icpa" /></label>
          <input id="ticpa" type="number" min={0} step={1} value={s.targetIcpa ?? ""} onChange={(e) => set({ targetIcpa: e.target.value ? Number(e.target.value) : null })} />
          {level !== "brief" && <span className="hint">An extra order is an order that the ads caused. Example: if you earn 80 on an order, you can pay up to 80 for one extra order.</span>}
        </div>
      )}
      {s.decisionBasis === "breakeven_iroas" && (
        <div className="field" style={{ maxWidth: 360 }}>
          <label htmlFor="biroas">{tech(level, `The revenue you need for each 1 ${s.currency} of ads`, "Break-even iROAS")}<InfoTip term="iroas" /></label>
          <input id="biroas" type="number" min={0} step={0.1} value={s.breakevenIroas ?? ""} onChange={(e) => set({ breakevenIroas: e.target.value ? Number(e.target.value) : null })} />
          {level !== "brief" && <span className="hint">Example: 2 means that each 1 {s.currency} of ads must bring 2 {s.currency} of extra revenue.</span>}
        </div>
      )}
    </section>
  );
}

export function templateStepProblems(s: PlanState): string[] {
  if (!isHoldout(s)) return [];
  if (s.adsBeforeTest == null) return ["Tell us whether the campaign is running before the test."];
  if (s.adsBeforeTest === "some") return ["This test needs a history where the campaign was off everywhere or on everywhere."];
  return [];
}

export function testStepProblems(s: PlanState): string[] {
  const p: string[] = [];
  if (!s.testName.trim()) p.push("Give the test a name.");
  const labels = s.labels.map((l) => l.trim());
  if (labels.some((l) => !l) || new Set(labels).size !== labels.length) p.push("Each name must be filled in, and the names must be different.");
  if (s.totalBudget <= 0) p.push("Enter a budget.");
  if (s.split.reduce((a, x) => a + x, 0) !== 100 || s.split.some((x) => x <= 0)) p.push("The budget split must add up to 100%.");
  if (s.decisionBasis === "target_icpa" && !(s.targetIcpa && s.targetIcpa > 0)) p.push("Enter the most you can pay for one extra order, or choose \"I'm not sure yet\".");
  if (s.decisionBasis === "breakeven_iroas" && !(s.breakevenIroas && s.breakevenIroas > 0)) p.push("Enter the revenue you need for each 1 of ads, or choose \"I'm not sure yet\".");
  return p;
}
