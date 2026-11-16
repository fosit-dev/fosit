import { useState } from "react";
import { InfoTip } from "./components/InfoTip";
import { docUrl, REPO_URL } from "./config";
import { ConsultCallout } from "./components/Consult";
import { Anatomy, ShareBar } from "./components/Visuals";
import { anatomySteps, designInfo, exampleSegments } from "./lib/words";
import type { Template } from "./plan/state";

/** The test types shown on the intro, by the situation a newcomer recognizes. */
const DEMOS: { id: Template; label: string }[] = [
  { id: "two_vendor", label: "Compare two vendors" },
  { id: "single", label: "Test one campaign" },
  { id: "national_holdout", label: "A national campaign" },
  { id: "crossover", label: "A small business" },
];

/** Screen 0: why this exists (docs/UX_FLOW.md). Skippable: every CTA works from here. */
export function Why({ onPlan, onRead }: { onPlan: (sample: boolean) => void; onRead: () => void }) {
  const [demo, setDemo] = useState<Template>("two_vendor");
  return (
    <article>
      <h1>Don't trust any vendor. Including us. Check the math.</h1>
      <p className="muted" style={{ fontSize: "1.1rem" }}>
        FOSIT helps you find out what your CTV and other click-less media <em>really</em> drive. Free, open source,
        and it runs entirely in your browser.
      </p>
      <div className="hero-cta">
        <button className="btn-primary" onClick={() => onPlan(false)}>Plan a test</button>
        <button onClick={onRead}>I already have a locked plan → Read results</button>
        <button className="btn-ghost" onClick={() => onPlan(true)}>Try it with sample data</button>
      </div>
      <p className="tiny" style={{ marginTop: 10 }}>Never ran a test like this? FOSIT explains each step in plain words, with pictures. You do not need statistics.</p>
      <ConsultCallout />

      <section className="card" style={{ marginTop: 28 }} aria-labelledby="story">
        <h2 id="story">Why this exists: the flyer guy</h2>
        <div className="story-layout">
          <figure className="story-figure">
            <img src="flyer-story.webp" width={1024} height={1010} loading="lazy"
              alt="A man in a yellow jacket smiles as he hands a flyer to a customer who is already walking through the restaurant's door, while the owner watches from inside." />
          </figure>
          <div className="story">
            <p>You own a restaurant. A flyer guy makes you an offer: <em>"Pay me $5 for every new customer who walks in holding my flyer."</em> Sounds fair. You only pay for results.</p>
            <p>Business looks great. Dozens of flyers a day. You're paying him more every week.</p>
            <p>Then one evening you step outside and see him standing <strong>right at your front door</strong>, handing flyers to people who were already walking in.</p>
            <p><strong>You weren't buying new customers. You were paying a toll on the ones you already had.</strong></p>
          </div>
        </div>
        <p>A lot of digital advertising is measured the same way: a platform gets credit for anyone who saw or clicked an ad, including people who were going to buy anyway.</p>
        <p>CTV has the <strong>opposite</strong> problem. Nobody clicks a TV, so click-based reports undercount it, and it gets cut even when it works.</p>
        <p>The only fair question is: <strong>how many customers came in <em>because</em> of the ad?</strong> That's incrementality.<InfoTip term="incrementality" /></p>
      </section>

      <section aria-labelledby="how">
        <h2 id="how">How FOSIT answers it</h2>
        <div className="steps-3">
          <div><h3>1 · Plan</h3><p className="small">FOSIT picks fair groups of markets: one for each vendor, and a group that sees no test ads. <span className="muted">Like handing out flyers on some streets and not on others.</span></p></div>
          <div><h3>2 · Run</h3><p className="small">Each vendor runs only in its own markets. Everyone gets the same locked plan before the test starts, so nobody can change the rules later.</p></div>
          <div><h3>3 · Read</h3><p className="small">FOSIT compares each group with a twin<InfoTip term="twin" />: a mix of markets with no test ads that sells in step with the group. The gap is what the ads really did.</p></div>
        </div>
        <div className="card" aria-labelledby="see-how">
          <h3 id="see-how">See how a test works</h3>
          <div className="row" role="group" aria-label="Kind of test">
            {DEMOS.map((d) => (
              <button key={d.id} type="button" className={demo === d.id ? "btn-primary small" : "small"} aria-pressed={demo === d.id} onClick={() => setDemo(d.id)}>{d.label}</button>
            ))}
          </div>
          <p className="small muted" style={{ margin: "10px 0 0" }}>{designInfo(demo).text} {designInfo(demo).good}</p>
          <ShareBar segments={exampleSegments(demo, [])} approx />
          <p className="tiny">The bar is the whole country. Color shows where the ads run. These sizes are examples.</p>
          <Anatomy steps={anatomySteps(demo, designInfo(demo).cells)} />
        </div>
        <div className="card">
          <h3>What you walk away with</h3>
          <p style={{ marginBottom: 0 }}>
            What each vendor <em>really</em> delivered: the extra orders that its ads caused, the cost of one extra order<InfoTip term="icpa" /> and
            the return for each $1 of ads<InfoTip term="iroas" />, each with an honest range. Invest in media like an investor, and bring your
            CFO numbers that hold up.
          </p>
        </div>
      </section>

      <ul className="trust" aria-label="Why you can trust this">
        <li>🔒 Runs in your browser</li>
        <li>📖 <a href={REPO_URL} target="_blank" rel="noreferrer">Open source (Apache 2.0)</a></li>
        <li>🧮 <a href={docUrl("METHODOLOGY.md")} target="_blank" rel="noreferrer">Every number shows its method</a></li>
        <li>✅ Checked against Meta's GeoLift on every code change</li>
        <li>🤷 "Inconclusive" is an allowed answer</li>
        <li>🚫 No sign-up, no email, no tracking</li>
      </ul>
    </article>
  );
}
