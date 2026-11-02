import { docUrl } from "./config";

/** Placeholder until the Read module ships (next build step). Honest about what's missing. */
export function ReadSoon({ onPlan }: { onPlan: () => void }) {
  return (
    <section className="card">
      <h1>Read results</h1>
      <div className="callout warn">
        <strong>Not built yet.</strong> The Read module is the next step. It will load your locked plan, check its fingerprint,
        run six honesty checks, and report lift, iCPA and iROAS per cell with ranges, plus a head-to-head comparison.
      </div>
      <p>Until then you can plan and lock a test, which is what has to happen before the campaign launches.</p>
      <div className="row">
        <button className="btn-primary" onClick={onPlan}>Plan a test</button>
        <a href={docUrl("METHODOLOGY.md", "11-honesty-checks-read")} target="_blank" rel="noreferrer">How results will be read →</a>
      </div>
    </section>
  );
}
