import { useCallback, useEffect, useRef, useState } from "react";
import type { Issue } from "../components/Issues";
import { sha256Hex } from "../lib/hash";
import type { FindResult } from "../lib/plan";
import { addDays, todayUtc } from "../lib/dates";
import { callPython, cancelEngine } from "../worker/client";
import type { Progress } from "../worker/protocol";
import { StepData, dataStepProblems, type DataLoader } from "./StepData";
import { StepFind } from "./StepFind";
import { StepLock } from "./StepLock";
import { StepMarkets, StepTiming } from "./StepsMarketsTiming";
import { StepTemplate, StepTest, testStepProblems } from "./StepsSetup";
import { STEPS, budgets, initialState, preDays, searchKey, type GeoRow, type LoadedData, type PlanState, type Summary } from "./state";

type LoadResult = { ok: boolean; summary: Summary | null; geos: GeoRow[]; issues: Issue[] };
/** The raw text behind the loaded data, kept in memory only, so we can re-validate (e.g. after a unit change or cancel). */
type Raw = { kind: "kpi" | "orders"; text: string; mapping?: string; meta: Omit<LoadedData, "summary" | "geos" | "issues" | "rows"> };

const countRows = (text: string) => Math.max(0, text.trimEnd().split(/\r?\n/).length - 1);

export function PlanWizard({ startWithSample }: { startWithSample: boolean }) {
  const [s, setState] = useState<PlanState>(initialState);
  const [step, setStep] = useState(startWithSample ? 2 : 0);
  const [maxStep, setMaxStep] = useState(step);
  const [busy, setBusy] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const raw = useRef<Raw | null>(null);
  const engineHasData = useRef(false);
  const set = useCallback((p: Partial<PlanState>) => setState((prev) => ({ ...prev, ...p })), []);

  const validate = useCallback(async (r: Raw, unit: PlanState["geoUnit"]) => {
    let kpiText = r.text;
    let extraIssues: Issue[] = [];
    if (r.kind === "orders") {
      const agg = await callPython<{ ok: boolean; csv: string | null; issues: Issue[] }>("aggregate_orders", { csv_text: r.text, geo_unit: unit, mapping_text: r.mapping ?? null });
      extraIssues = agg.issues;
      if (!agg.ok || !agg.csv) {
        set({ data: { ...r.meta, rows: countRows(r.text), summary: null as unknown as Summary, geos: [], issues: agg.issues }, result: null, chosen: null, locked: null });
        engineHasData.current = false;
        return;
      }
      kpiText = agg.csv;
    }
    const out = await callPython<LoadResult>("load_history", { csv_text: kpiText, geo_unit: unit });
    engineHasData.current = out.ok;
    set({
      geoUnit: unit,
      data: { ...r.meta, rows: countRows(r.text), summary: out.summary as Summary, geos: out.geos, issues: [...extraIssues, ...out.issues] },
      excluded: {}, result: null, chosen: null, locked: null, coinFlip: null,
    });
  }, [set]);

  const guarded = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true);
    setDataError(null);
    try {
      await fn();
    } catch (e) {
      setDataError(`Something went wrong reading the file: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }, []);

  const loader: DataLoader = {
    busy,
    error: dataError,
    loadKpiFile: (file) => guarded(async () => {
      const bytes = await file.arrayBuffer();
      raw.current = { kind: "kpi", text: new TextDecoder().decode(bytes), meta: { source: "upload", fileName: file.name, sha256: await sha256Hex(bytes) } };
      await validate(raw.current, s.geoUnit);
    }),
    loadOrdersFile: (file, mapping) => guarded(async () => {
      const bytes = await file.arrayBuffer();
      const mapText = mapping ? await mapping.text() : undefined;
      raw.current = {
        kind: "orders", text: new TextDecoder().decode(bytes), mapping: mapText,
        meta: { source: "orders", fileName: file.name, sha256: await sha256Hex(bytes),
          ...(mapping && mapText ? { mappingName: `User mapping file ${mapping.name}`, mappingSha256: await sha256Hex(mapText) } : {}) },
      };
      await validate(raw.current, s.geoUnit);
    }),
    loadSample: () => guarded(async () => {
      const text = await callPython<string>("sample_history", { end: addDays(todayUtc(), -1) });
      raw.current = { kind: "kpi", text, meta: { source: "sample", fileName: "FOSIT sample data (synthetic)", sha256: await sha256Hex(text) } };
      await validate(raw.current, "cbsa");
      if (!s.testName) set({ testName: "Sample two-vendor CTV test" });
    }),
    changeUnit: (unit) => {
      set({ geoUnit: unit });
      return raw.current ? guarded(() => validate(raw.current!, unit)) : Promise.resolve();
    },
  };

  useEffect(() => {
    if (startWithSample) loader.loadSample();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runSearch = async () => {
    setRunning(true);
    setSearchError(null);
    setProgress(null);
    try {
      if (!engineHasData.current && raw.current) await validate(raw.current, s.geoUnit);
      const key = searchKey(s);
      const result = await callPython<FindResult>("find_designs", {
        config: {
          n_cells: s.nCells, kpi: s.primaryKpi, pre_days: preDays(s), durations: s.durations, cooldown_days: s.cooldown,
          share_min: s.shareMin, share_max: s.shareMax, excluded: Object.keys(s.excluded), seed: s.seed,
          permutations: s.permutations, budgets: budgets(s), alpha: 0.1,
        },
      }, setProgress);
      const firstGood = result.designs.length ? 0 : null;
      set({ result, resultKey: key, chosen: firstGood, locked: null, coinFlip: null, duration: s.durations.includes(s.duration) ? s.duration : s.durations[0] });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg !== "cancelled") setSearchError(`The search failed: ${msg}`);
    } finally {
      setRunning(false);
    }
  };

  const cancel = () => {
    cancelEngine();
    engineHasData.current = false;
  };

  const problems: string[] =
    step === 1 ? testStepProblems(s)
    : step === 2 ? dataStepProblems(s)
    : step === 3 && s.primaryKpi === "revenue" && !s.data?.summary.kpis.includes("revenue") ? ["Your file has no revenue column. Go back and choose Orders as the goal."]
    : step === 5 ? (s.chosen == null || !s.result || s.resultKey !== searchKey(s) ? ["Run the search and choose a design."] : [])
    : [];

  const goTo = (i: number) => {
    setStep(i);
    setMaxStep((m) => Math.max(m, i));
    window.scrollTo({ top: 0 });
  };

  return (
    <div>
      <h1 style={{ fontSize: "1.8rem" }}>Plan a test</h1>
      <nav aria-label="Plan steps">
        <ol className="stepper">
          {STEPS.map((name, i) => (
            <li key={name} className={i === step ? "current" : i < step || i <= maxStep ? "done" : ""}>
              <button onClick={() => goTo(i)} disabled={i > maxStep} aria-current={i === step ? "step" : undefined}>
                {i + 1}.<span className="step-name"> {name}</span>
              </button>
            </li>
          ))}
        </ol>
      </nav>

      {step === 0 && <StepTemplate s={s} set={set} />}
      {step === 1 && <StepTest s={s} set={set} />}
      {step === 2 && <StepData s={s} loader={loader} />}
      {step === 3 && <StepMarkets s={s} set={set} />}
      {step === 4 && <StepTiming s={s} set={set} />}
      {step === 5 && <StepFind s={s} set={set} run={runSearch} cancel={cancel} running={running} progress={progress} error={searchError} />}
      {step === 6 && <StepLock s={s} set={set} />}

      {problems.length > 0 && (
        <ul className="small" style={{ color: "var(--muted)" }} aria-live="polite">{problems.map((p) => <li key={p}>{p}</li>)}</ul>
      )}
      <div className="nav">
        <button onClick={() => goTo(step - 1)} disabled={step === 0}>← Back</button>
        {step < STEPS.length - 1 && (
          <button className="btn-primary" onClick={() => goTo(step + 1)} disabled={problems.length > 0 || busy || running}>Continue →</button>
        )}
      </div>
    </div>
  );
}
