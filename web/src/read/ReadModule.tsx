import { useEffect, useMemo, useState } from "react";
import { InfoTip } from "../components/InfoTip";
import { IssueList, type Issue } from "../components/Issues";
import { APP_VERSION } from "../config";
import { pretty, todayUtc } from "../lib/dates";
import { diffPlans, type Change } from "../lib/diff";
import { downloadBlob, downloadText, slug } from "../lib/download";
import { money, num } from "../lib/format";
import { groupHash, sha256Hex, shortCode } from "../lib/hash";
import { verifyPlan, type LockedPlan } from "../lib/plan";
import { callPython } from "../worker/client";
import type { Progress } from "../worker/protocol";
import { ReadResults } from "./ReadResults";
import type { Check, ReadResult } from "./types";

type Loaded = { fileName: string; sha256: string; ok: boolean; issues: Issue[]; summary?: Record<string, unknown> | null };
type Verify = { recomputed: string; selfConsistent: boolean; matchesAnchor: boolean | null; shortOnly: boolean };
type Shocks = { answer: "unanswered" | "none" | "changed"; note: string };

async function readFile(file: File): Promise<{ text: string; sha256: string }> {
  const bytes = await file.arrayBuffer();
  return { text: new TextDecoder().decode(bytes), sha256: await sha256Hex(bytes) };
}

async function verify(plan: LockedPlan, anchor: string): Promise<Verify> {
  const a = anchor.replace(/\s+/g, "").toLowerCase();
  const v = await verifyPlan(plan, a.length === 64 ? a : undefined);
  const shortOnly = a.length === 8;
  return { recomputed: v.recomputed, selfConsistent: v.selfConsistent, shortOnly,
    matchesAnchor: a.length === 64 ? v.matchesAnchor : shortOnly ? v.recomputed.startsWith(a) : null };
}

function planCheck(v: Verify | null, changes: Change[]): Check {
  if (!v) return { id: "plan_match", title: "Plan match", status: "warn", detail: "Load the locked plan." };
  if (!v.selfConsistent) return { id: "plan_match", title: "Plan match", status: "fail", detail: "The plan file was edited after it was locked: its contents no longer match its own fingerprint." };
  if (v.matchesAnchor === false) return { id: "plan_match", title: "Plan match", status: "fail",
    detail: `This plan's fingerprint doesn't match the one you pasted.${changes.length ? ` ${changes.length} field(s) differ from the original.` : " Load the original plan to see what changed."}` };
  if (v.matchesAnchor === null) return { id: "plan_match", title: "Plan match", status: "warn", detail: "Paste the fingerprint from your pre-launch email to complete this check." };
  if (v.shortOnly) return { id: "plan_match", title: "Plan match", status: "warn", detail: "Matches the 8-character short code. Paste the full 64-character fingerprint for a check that can't be faked." };
  return { id: "plan_match", title: "Plan match", status: "pass", detail: "The plan is exactly the one fingerprinted before launch." };
}

export function ReadModule() {
  const [plan, setPlan] = useState<LockedPlan | null>(null);
  const [planName, setPlanName] = useState("");
  const [planError, setPlanError] = useState<string | null>(null);
  const [anchor, setAnchor] = useState("");
  const [v, setV] = useState<Verify | null>(null);
  const [changes, setChanges] = useState<Change[]>([]);
  const [kpi, setKpi] = useState<Loaded | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [spend, setSpend] = useState<Loaded | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<ReadResult | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shocks, setShocks] = useState<Shocks>({ answer: "unanswered", note: "" });
  const [isExample, setIsExample] = useState(false);

  useEffect(() => { if (plan) verify(plan, anchor).then(setV); }, [plan, anchor]);

  const reset = () => { setResult(null); setShocks({ answer: "unanswered", note: "" }); setError(null); };

  const acceptPlan = (p: LockedPlan, name: string) => {
    if (p?.fosit_plan_version !== "1.0" || !p.commitment || !p.hash?.value) throw new Error("This doesn't look like a FOSIT plan file (*.fosit-plan.json).");
    setPlan(p); setPlanName(name); setPlanError(null); setKpi(null); setSpend(null); setChanges([]); reset();
  };

  const loadPlanFile = async (file: File) => {
    try { acceptPlan(JSON.parse(await file.text()), file.name); setIsExample(false); }
    catch (e) { setPlanError(e instanceof Error ? e.message : String(e)); }
  };

  const loadOriginal = async (file: File) => {
    const orig = JSON.parse(await file.text()) as LockedPlan;
    setChanges(diffPlans(orig.commitment, plan!.commitment));
  };

  const loadKpiText = async (text: string, fileName: string, sha256: string, p: LockedPlan = plan!) => {
    setBusy("Checking your sales file…");
    try {
      const out = await callPython<{ ok: boolean; issues: Issue[]; summary: Record<string, unknown>; geos: { geo_id: string; name: string }[] }>(
        "load_history", { csv_text: text, geo_unit: p.commitment.geo.unit });
      setKpi({ fileName, sha256, ok: out.ok, issues: out.issues, summary: out.summary });
      setNames(Object.fromEntries(out.geos.map((g) => [g.geo_id, g.name])));
      reset();
    } finally { setBusy(null); }
  };

  const loadSpendText = async (text: string, fileName: string, sha256: string, p: LockedPlan = plan!) => {
    setBusy("Checking the spend file…");
    try {
      const out = await callPython<{ ok: boolean; issues: Issue[]; summary: Record<string, unknown> | null }>("load_spend", { csv_text: text, commitment: p.commitment });
      setSpend({ fileName, sha256, ok: out.ok, issues: out.issues, summary: out.summary });
      reset();
    } finally { setBusy(null); }
  };

  const loadExample = async () => {
    setBusy("Loading the example…");
    try {
      const base = new URL("./examples/two_vendor/", document.baseURI);
      const get = (f: string) => fetch(new URL(f, base)).then((r) => { if (!r.ok) throw new Error(`${f}: HTTP ${r.status}`); return r.text(); });
      const p = JSON.parse(await get("plan.fosit-plan.json")) as LockedPlan;
      acceptPlan(p, "Example: two-vendor test (synthetic)");
      setIsExample(true);
      setAnchor(p.hash.value);
      const kText = await get("kpi_history.csv");
      const sText = await get("spend_delivery.csv");
      // pass the plan explicitly: React hasn't applied setPlan yet inside this handler
      await loadKpiText(kText, "example kpi_history.csv", await sha256Hex(kText), p);
      await loadSpendText(sText, "example spend_delivery.csv", await sha256Hex(sText), p);
    } catch (e) { setPlanError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  const run = async () => {
    reset();
    setBusy("Running the analysis…");
    try {
      const out = await callPython<ReadResult>("run_read", { commitment: plan!.commitment, plan_hash: v!.recomputed, today: todayUtc(), appendix: plan!.appendix ?? null }, setProgress);
      if (!out.ok) setError((out.errors ?? []).join(" "));
      else setResult(out);
    } catch (e) { setError(`The analysis failed: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setBusy(null); setProgress(null); }
  };

  const checks: Check[] = useMemo(() => {
    if (!result) return [];
    const shockCheck: Check = shocks.answer === "none"
      ? { id: "shocks", title: "Other changes", status: "pass", detail: "You confirmed no other channel, promotion, pricing or stock change differed across cells or vs. control." }
      : shocks.answer === "changed"
        ? { id: "shocks", title: "Other changes", status: "warn", detail: `You reported a change: ${shocks.note || "(no description)"}` }
        : { id: "shocks", title: "Other changes", status: "warn", detail: "Waiting for your answer below." };
    return [planCheck(v, changes), ...result.checks, shockCheck];
  }, [result, v, changes, shocks]);

  const mismatch = v ? !v.selfConsistent || v.matchesAnchor === false : false;
  const c = plan?.commitment;
  const canRun = plan && kpi?.ok && !busy;

  const analysisConfig = async () => {
    const core = await fetch(new URL("./fosit-core.json", document.baseURI)).then((r) => r.json()).catch(() => ({}));
    return {
      fosit_analysis_version: "1.0",
      generated_at: new Date().toISOString(),
      tool: { name: "FOSIT", version: APP_VERSION, core_sha256: core.sha256 ?? null },
      plan,
      plan_check: { recomputed: v?.recomputed, self_consistent: v?.selfConsistent, anchor_provided: anchor.replace(/\s+/g, "") || null, matches_anchor: v?.matchesAnchor, changes },
      inputs: { kpi_history: kpi && { file: kpi.fileName, sha256: kpi.sha256 }, spend_delivery: spend && { file: spend.fileName, sha256: spend.sha256 } },
      read_date: todayUtc(),
      external_shocks: shocks,
      how_to_rerun: "Load this plan and the input files with these SHA-256 fingerprints into the FOSIT version above (or call core/fosit/api.py: load_history, load_spend, run_read). Every analysis setting comes from the plan, so the numbers will be identical.",
    };
  };

  return (
    <div>
      <h1 style={{ fontSize: "1.8rem" }}>Read results</h1>
      <p className="muted">Load the locked plan, your sales through the end of the test, and each vendor's spend. Everything stays in this browser.</p>

      <section className="card">
        <h2>1 · The locked plan</h2>
        <div className="row">
          <label className="btn btn-primary">Choose plan file (.fosit-plan.json)
            <input type="file" accept=".json,application/json" className="sr-only" data-testid="plan-file" onChange={(e) => { const f = e.target.files?.[0]; if (f) loadPlanFile(f); e.target.value = ""; }} />
          </label>
          <button type="button" className="btn-ghost" onClick={loadExample} disabled={!!busy}>Try it with the example (two vendors, synthetic)</button>
        </div>
        {planError && <div className="callout err">{planError}</div>}
        {plan && c && (
          <div style={{ marginTop: 14 }}>
            <p><strong>{c.test_name}</strong>{c.advertiser_label ? ` · ${c.advertiser_label}` : ""} <span className="muted small">({planName})</span></p>
            <p className="small">{c.cells.map((x) => `${x.label}: ${x.geo_ids.length} markets, ${money(x.budget, c.currency)}`).join(" · ")} · {c.control.geo_ids.length} control markets</p>
            <p className="small">Ads {pretty(c.dates.test_start)} – {pretty(c.dates.test_end)}, cooldown to {pretty(c.dates.cooldown_end)}. Primary goal: {c.kpi.primary}.</p>
            <div className="field" style={{ marginTop: 10 }}>
              <label htmlFor="anchor">Paste the fingerprint from your pre-launch email<InfoTip term="planMatch" /></label>
              <input id="anchor" type="text" value={anchor} onChange={(e) => setAnchor(e.target.value)} placeholder="64 characters (spaces are fine)" spellCheck={false} />
              {isExample && <span className="hint">Filled in for the example. In a real test, paste it from the email you sent before launch.</span>}
            </div>
            {v && <p className="small">This file's fingerprint: <code>{groupHash(v.recomputed)}</code> (short code {shortCode(v.recomputed)})</p>}
            {mismatch && (
              <div className="callout err">
                <strong>This isn't the plan that was locked before launch.</strong> Results will be marked "NOT THE PRE-REGISTERED ANALYSIS".
                <div style={{ marginTop: 8 }}>
                  <label className="small">Load the original plan to see exactly what changed:{" "}
                    <input type="file" accept=".json" onChange={(e) => { const f = e.target.files?.[0]; if (f) loadOriginal(f); }} /></label>
                </div>
                {changes.length > 0 && (
                  <ul className="small">{changes.map((ch) => <li key={ch.path}><code>{ch.path}</code>: {ch.before}{ch.before && ch.after ? " → " : ""}{ch.after}</li>)}</ul>
                )}
              </div>
            )}
          </div>
        )}
      </section>

      {plan && (
        <section className="card">
          <h2>2 · Your data</h2>
          <div className="grid-2">
            <div>
              <h3>Sales by market and day</h3>
              <p className="small muted">Same format as for planning, now running through {pretty(c!.dates.cooldown_end)}.</p>
              <label className="btn">Choose sales file
                <input type="file" accept=".csv,text/csv" className="sr-only" data-testid="read-kpi-file" disabled={!!busy}
                  onChange={async (e) => { const f = e.target.files?.[0]; if (f) { const { text, sha256 } = await readFile(f); await loadKpiText(text, f.name, sha256); } e.target.value = ""; }} />
              </label>
              {kpi && <div style={{ marginTop: 10 }}><p className="small">{kpi.fileName}</p><IssueList issues={kpi.issues}
                ok={kpi.ok && kpi.summary ? [`${num(Number(kpi.summary.days))} days, ${String(kpi.summary.first_date)} to ${String(kpi.summary.last_date)}, ${num(Number(kpi.summary.geos))} markets`] : []} /></div>}
            </div>
            <div>
              <h3>Spend & delivery</h3>
              <p className="small muted">date, cell, geo_id, impressions, spend: one file with every vendor's rows. Optional, but without it there's no iCPA, iROAS or leakage check.</p>
              <label className="btn">Choose spend file
                <input type="file" accept=".csv,text/csv" className="sr-only" data-testid="spend-file" disabled={!!busy}
                  onChange={async (e) => { const f = e.target.files?.[0]; if (f) { const { text, sha256 } = await readFile(f); await loadSpendText(text, f.name, sha256); } e.target.value = ""; }} />
              </label>
              {spend && <div style={{ marginTop: 10 }}><p className="small">{spend.fileName}</p><IssueList issues={spend.issues}
                ok={spend.ok ? c!.cells.map((x) => { const s = (spend.summary as Record<string, { spend: number }> | null)?.[x.id]; return `${x.label}: ${money(s?.spend ?? 0, c!.currency)} spent`; }) : []} /></div>}
            </div>
          </div>
          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn-primary" disabled={!canRun} onClick={run}>Run the analysis</button>
            {busy && <span className="muted small" aria-live="polite">⏳ {busy}{progress ? ` (${progress.done}/${progress.total})` : ""}</span>}
          </div>
          {error && <div className="callout err">{error}</div>}
        </section>
      )}

      {result && plan && (
        <>
          {mismatch && <p className="watermark">NOT THE PRE-REGISTERED ANALYSIS</p>}
          <section className="card" aria-labelledby="checks">
            <h2 id="checks">3 · Honesty checks</h2>
            <div className="check-tiles">
              {checks.map((ch) => (
                <div key={ch.id} className={`check-tile ${ch.status}`}>
                  <strong>{ch.status === "pass" ? "✓" : ch.status === "warn" ? "!" : "✕"} {ch.title}
                    {ch.id === "plan_match" && <InfoTip term="planMatch" />}{ch.id === "leakage" && <InfoTip term="leakage" />}{ch.id === "shocks" && <InfoTip term="shocks" />}</strong>
                  <span className="small">{ch.detail}</span>
                </div>
              ))}
            </div>
            <fieldset style={{ border: 0, padding: 0, marginTop: 16 }}>
              <legend style={{ fontWeight: 600 }}>During the test, did anything else change differently across cells or vs. control? (another channel, a promotion, prices, stock-outs)<InfoTip term="shocks" /></legend>
              <label className="check"><input type="radio" name="shocks" checked={shocks.answer === "none"} onChange={() => setShocks({ answer: "none", note: "" })} /><span>No, nothing else changed differently</span></label>
              <label className="check"><input type="radio" name="shocks" checked={shocks.answer === "changed"} onChange={() => setShocks({ ...shocks, answer: "changed" })} /><span>Yes, something changed</span></label>
              {shocks.answer === "changed" && <input type="text" aria-label="What changed" placeholder="What changed, where and when? (goes into the report)" value={shocks.note} onChange={(e) => setShocks({ ...shocks, note: e.target.value })} />}
            </fieldset>
          </section>

          {shocks.answer === "unanswered" ? (
            <p className="callout">Answer the question above to see the results.</p>
          ) : (
            <>
              <ReadResults r={result} plan={plan} names={names} />
              <section className="card">
                <h2>Export</h2>
                <div className="row">
                  <button className="btn-primary" onClick={async () => {
                    const { reportPdf } = await import("../lib/report"); // jsPDF is large: load it only when needed
                    downloadBlob(reportPdf({ plan, result, checks, mismatch, recomputed: v!.recomputed, shocks, names }), `${slug(c!.test_name)}-report.pdf`);
                  }}>Download report (PDF)</button>
                  <button onClick={() => downloadText(result.csv, `${slug(c!.test_name)}-results.csv`, "text/csv")}>Results (CSV)</button>
                  <button onClick={async () => downloadText(JSON.stringify(await analysisConfig(), null, 2), `${slug(c!.test_name)}.fosit-analysis.json`)}>Analysis config (re-run it yourself)</button>
                </div>
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
