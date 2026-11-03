import { useState } from "react";
import { InfoTip } from "../components/InfoTip";
import { APP_VERSION } from "../config";
import { addDays, pretty } from "../lib/dates";
import { downloadBlob, downloadText, slug } from "../lib/download";
import { money, pct, weeks } from "../lib/format";
import { groupHash, sha256Hex, shortCode } from "../lib/hash";
import { buildCommitment, lockPlan, type LockedPlan } from "../lib/plan";
import { readLink } from "../embed";
import { budgets, isHoldout, isOneCampaign, preDays, type PlanState } from "./state";
import { curveFor, detectableIcpa } from "./StepFind";

type Props = { s: PlanState; set: (p: Partial<PlanState>) => void; onRead?: (plan: LockedPlan) => void };

type CoreManifest = { version: string; sha256: string; geo_mapping_sha256: string };

const MAPPING_NAMES = {
  cbsa: "Census 2020 ZCTA-county + OMB July 2023 CBSA delineation (FOSIT geo_data)",
  state: "Census 2020 ZCTA-county relationship, by state (FOSIT geo_data)",
};

/** Fair coin flip using the browser's cryptographic random number generator. */
function shuffle(n: number): number[] {
  const order = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i--) {
    const j = crypto.getRandomValues(new Uint32Array(1))[0] % (i + 1);
    [order[i], order[j]] = [order[j], order[i]];
  }
  return order;
}

export function StepLock({ s, set, onRead }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const d = s.result && s.chosen != null ? s.result.designs[s.chosen] : null;
  if (!d || !s.data) return <section className="card"><p>Choose a design in the previous step first.</p></section>;
  const b = budgets(s);
  const order = s.coinFlip ?? d.cells.map((_, i) => i);
  const setFor = (cell: number) => order.indexOf(cell);
  const names = Object.fromEntries(s.data.geos.map((g) => [g.geo_id, g.name]));
  const ready = s.confirmed.every(Boolean) && s.datesFinal;
  const testEnd = addDays(s.testStart, s.duration - 1);
  const holdout = isHoldout(s);
  const one = isOneCampaign(s);

  const lock = async () => {
    setError(null);
    try {
      const core: CoreManifest = await fetch(new URL("./fosit-core.json", document.baseURI)).then((r) => r.json());
      const data = s.data!;
      const mappingName = s.geoUnit === "custom" ? data.mappingName ?? "Custom market IDs as provided (no ZIP mapping file)" : MAPPING_NAMES[s.geoUnit];
      const mappingSha = s.geoUnit === "custom"
        ? data.mappingSha256 ?? (await sha256Hex(data.geos.map((g) => g.geo_id).sort().join("\n")))
        : core.geo_mapping_sha256;
      const commitment = buildCommitment({
        testName: s.testName, advertiserLabel: s.advertiserLabel, currency: s.currency,
        geoUnit: s.geoUnit, mappingName, mappingSha256: mappingSha,
        primaryKpi: s.primaryKpi, secondaryKpis: data.summary.kpis.filter((k) => k !== s.primaryKpi),
        labels: s.labels.map((l) => l.trim()), budgets: b,
        testStart: s.testStart, testDays: s.duration, cooldownDays: s.cooldown, preDays: preDays(s),
        design: d, designRank: s.chosen! + 1, candidatesSearched: s.result!.funnel.generated,
        designType: holdout ? { type: "national_holdout", ads_before_test: s.adsBeforeTest === "always_on" ? "always_on" : "off" } : { type: "geo_cells" },
        excluded: s.excluded, permutations: s.permutations, alpha: 0.1, seed: s.seed,
        decisionBasis: s.decisionBasis, targetIcpa: s.targetIcpa ?? undefined, breakevenIroas: s.breakevenIroas ?? undefined,
        coinFlip: s.coinFlip,
        plannedMde: d.cells.map((_, i) => curveFor(d, i, s.duration)?.mde ?? null),
        dataFingerprint: { kpi_history_sha256: data.sha256, rows: data.rows, geos: data.summary.geos, first_date: data.summary.first_date, last_date: data.summary.last_date },
        toolVersion: APP_VERSION, coreSha256: core.sha256, createdAt: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      });
      const appendix = {
        note: "Design diagnostics. Not part of the fingerprint; safe to delete before sharing.",
        design: { fit: d.fit, shares: d.shares, balance: d.balance, balance_score: d.balance_score, share_in_test: d.share_in_test,
          ...(holdout ? { holdout_share: d.control_share } : {}) },
        mde: commitment.cells.map((cell, k) => {
          const cv = curveFor(d, setFor(k), s.duration);
          return { label: cell.label, test_days: s.duration, mde: cv?.mde ?? null, detectable_icpa: detectableIcpa(cv, cell.budget), windows: cv?.windows ?? 0, false_positive_rate: cv?.false_positive_rate ?? null };
        }),
        search_settings: s.result!.settings,
      };
      set({ locked: await lockPlan(commitment, appendix) });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const fileBase = s.locked ? `${slug(s.testName)}-${shortCode(s.locked.hash.value).toLowerCase()}` : "";
  const planForDownload = (p: LockedPlan): LockedPlan => (s.includeDiagnostics ? p : { ...p, appendix: undefined });
  const email = s.locked
    ? `Subject: Locked test plan: ${s.testName} (fingerprint ${shortCode(s.locked.hash.value)})\n\n` +
      (holdout && !one
        ? `Hi all,\n\nAttached is the locked plan for "${s.testName}" (PDF and JSON). Ads run ${pretty(s.testStart)} to ${pretty(testEnd)}, each vendor only in the markets listed for its cell. The ${d.control.length} held-out markets must get no CTV from anyone until ${pretty(addDays(testEnd, s.cooldown))}.\n\n` +
          `Plan fingerprint (SHA-256):\n${s.locked.hash.value}\n\nPlease confirm you can target exactly your cell's markets. When we read the results, this fingerprint is checked to show the plan wasn't changed.\n\nAfter the cooldown ends (${pretty(addDays(testEnd, s.cooldown))}), read the results here: ${readLink()}\n`
        : holdout
        ? `Hi all,\n\nAttached is the locked plan for "${s.testName}" (PDF and JSON). From ${pretty(s.testStart)} to ${pretty(addDays(testEnd, s.cooldown))} the campaign runs everywhere except the ${d.control.length} held-out markets listed in the plan, which must get no ads at all.\n\n` +
          `Plan fingerprint (SHA-256):\n${s.locked.hash.value}\n\nPlease confirm you can keep every held-out market dark for those dates. When we read the results, this fingerprint is checked to show the plan wasn't changed.\n\nAfter the cooldown ends (${pretty(addDays(testEnd, s.cooldown))}), read the results here: ${readLink()}\n`
        : `Hi all,\n\nAttached is the locked plan for "${s.testName}" (PDF and JSON). Ads run ${pretty(s.testStart)} to ${pretty(testEnd)} in the markets listed for each cell; control markets get no test ads.\n\n` +
          `Plan fingerprint (SHA-256):\n${s.locked.hash.value}\n\nPlease confirm you can target exactly your cell's markets. When we read the results, this fingerprint is checked to show the plan wasn't changed.\n\nAfter the cooldown ends (${pretty(addDays(testEnd, s.cooldown))}), read the results here: ${readLink()}\n`)
    : "";

  if (s.locked) {
    const h = s.locked.hash.value;
    return (
      <section className="card">
        <h2>🔒 Plan locked</h2>
        <p>Plan fingerprint<InfoTip term="hash" />, short code <span className="short-code">{shortCode(h)}</span></p>
        <div className="hash" data-testid="plan-hash">{groupHash(h)}</div>
        <div className="callout ok" style={{ marginTop: 16 }}>
          <strong>Now email the PDF, the JSON and this fingerprint to the advertiser and every vendor, before {pretty(s.testStart)}.</strong>{" "}
          That email is your proof the plan was set in advance. FOSIT has no server, so it can't be your witness, and that's on purpose.
        </div>
        <label className="check"><input type="checkbox" checked={s.includeDiagnostics} onChange={(e) => set({ includeDiagnostics: e.target.checked })} />
          <span>Include design diagnostics (shows your share of sales per cell). They're not part of the fingerprint, so you can leave them out of the vendors' copies.</span></label>
        <div className="row">
          <button className="btn-primary" onClick={async () => {
            const { planPdf } = await import("../lib/pdf"); // jsPDF is large: load it only when needed
            downloadBlob(planPdf(planForDownload(s.locked!), names, s.includeDiagnostics, readLink()), `${fileBase}.pdf`);
          }}>Download plan PDF</button>
          <button onClick={() => downloadText(JSON.stringify(planForDownload(s.locked!), null, 2), `${fileBase}.fosit-plan.json`)}>Download plan JSON</button>
          <button onClick={async () => { try { await navigator.clipboard.writeText(email); setCopied(true); } catch { setCopied(false); } }}>{copied ? "✓ Copied" : "Copy email text"}</button>
        </div>
        <details><summary>Email text</summary><pre className="small" style={{ whiteSpace: "pre-wrap" }}>{email}</pre></details>
        <div className="callout" style={{ marginTop: 16 }}>
          <strong>When the test is over</strong>, come back to <a href={readLink()} target="_top">{readLink()}</a> (it's in the email and the PDF too),
          load the plan JSON, and FOSIT reads the results.
          {onRead && <div style={{ marginTop: 8 }}><button onClick={() => onRead(s.locked!)}>Go to Read results with this plan →</button></div>}
        </div>
        <p className="small muted" style={{ marginTop: 16 }}>Need to change something? Go back and edit. Locking again creates a new plan with a new fingerprint; mention the old one in your email.</p>
        <button className="link-btn small" onClick={() => set({ locked: null })}>Unlock and edit</button>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>Lock & share</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Cell</th><th>Budget</th><th>Markets</th><th>Share of sales</th><th>Detectable lift</th></tr></thead>
          <tbody>
            {s.labels.map((l, k) => {
              const set_ = setFor(k);
              return (
                <tr key={k}><td>{l}</td><td>{money(b[k], s.currency)}</td><td>{d.cells[set_].length} (market set {set_ + 1})</td><td>{pct(d.shares[set_])}</td><td>{pct(curveFor(d, set_, s.duration)?.mde)}</td></tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="small muted">Ads {pretty(s.testStart)} – {pretty(testEnd)} ({weeks(s.duration)}), cooldown to {pretty(addDays(testEnd, s.cooldown))}.{" "}
        {holdout ? `${d.control.length} markets held out (${pct(d.control_share)} of sales), dark until ${pretty(addDays(testEnd, s.cooldown))}.` : `${d.control.length} control markets.`}{" "}
        {Object.keys(s.excluded).length} excluded.</p>

      {d.cells.length > 1 && (
        <div className="callout">
          <strong>🪙 Let a coin decide which cell gets which market set?</strong><InfoTip term="coinFlip" />
          <p className="small" style={{ margin: "4px 0 8px" }}>Then neither vendor can say the other got the better markets.</p>
          <div className="row">
            <button onClick={() => set({ coinFlip: shuffle(d.cells.length) })}>{s.coinFlip ? "Flip again" : "Flip the coin"}</button>
            {s.coinFlip && <button className="btn-ghost" onClick={() => set({ coinFlip: null })}>Undo: assign in order</button>}
            {s.coinFlip && <span className="small">Result: {s.labels.map((l, k) => `${l} → market set ${s.coinFlip!.indexOf(k) + 1}`).join(", ")}</span>}
          </div>
        </div>
      )}

      <h3>Before you lock</h3>
      {s.labels.map((l, k) => (
        <label key={k} className="check">
          <input type="checkbox" checked={s.confirmed[k] ?? false} onChange={(e) => set({ confirmed: s.confirmed.map((c, j) => (j === k ? e.target.checked : c)) })} />
          {holdout && !one
            ? <span><strong>{l}</strong>'s vendor confirmed they can target exactly these {d.cells[setFor(k)].length} markets, and nothing in the {d.control.length} held-out markets.</span>
            : holdout
            ? <span><strong>{l}</strong>'s vendor(s) confirmed they can keep all {d.control.length} held-out markets free of ads from {pretty(s.testStart)} to {pretty(addDays(testEnd, s.cooldown))}.</span>
            : <span><strong>{l}</strong>'s vendor confirmed they can target exactly these {d.cells[setFor(k)].length} markets, and nothing in control.</span>}
        </label>
      ))}
      <label className="check">
        <input type="checkbox" checked={s.datesFinal} onChange={(e) => set({ datesFinal: e.target.checked })} />
        <span>Dates and budgets are final.</span>
      </label>
      {error && <div className="callout err">{error}</div>}
      <button className="btn-primary" disabled={!ready} onClick={lock}>Lock plan</button>
      {!ready && <p className="small muted">Tick every box to lock.</p>}
    </section>
  );
}
