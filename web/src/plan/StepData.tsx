import { useEffect, useState } from "react";
import { InfoTip } from "../components/InfoTip";
import { IssueList } from "../components/Issues";
import { Sparkline } from "../components/Charts";
import { docUrl } from "../config";
import { downloadText } from "../lib/download";
import { num } from "../lib/format";
import { onEngineStatus } from "../worker/client";
import type { PlanState } from "./state";

export type DataLoader = {
  loadKpiFile: (file: File) => Promise<void>;
  loadOrdersFile: (file: File, mapping: File | null) => Promise<void>;
  loadSample: () => Promise<void>;
  changeUnit: (unit: PlanState["geoUnit"]) => Promise<void>;
  busy: boolean;
  error: string | null;
};

const TEMPLATE_CSV = "date,geo_id,orders,revenue\n2026-06-01,35620,412,38211.50\n2026-06-01,31080,298,27002.10\n2026-06-02,35620,397,36940.00\n";

export function StepData({ s, loader }: { s: PlanState; loader: DataLoader }) {
  const [drag, setDrag] = useState(false);
  const [status, setStatus] = useState("");
  const [ordersFile, setOrdersFile] = useState<File | null>(null);
  const [mappingFile, setMappingFile] = useState<File | null>(null);
  useEffect(() => onEngineStatus(setStatus), []);

  const d = s.data;
  const okLines = d?.summary
    ? [
        `${num(d.summary.days)} days (${d.summary.weeks} weeks) of history, ${d.summary.first_date} to ${d.summary.last_date}`,
        `${num(d.summary.geos)} markets`,
        `Found: ${d.summary.kpis.join(" and ")}`,
        `File fingerprint ${d.sha256.slice(0, 12)}… (recorded in the plan; the file itself never leaves your computer)`,
      ]
    : [];
  const hasError = d?.issues.some((i) => i.severity === "error");

  return (
    <section className="card">
      <h2>Your sales history</h2>
      <fieldset style={{ border: 0, padding: 0, margin: "0 0 16px" }}>
        <legend style={{ fontWeight: 600, marginBottom: 6 }}>Your markets are…<InfoTip term="geoUnit" /></legend>
        {([
          ["cbsa", "US metro & micro areas (Census CBSA codes, e.g. 35620)", "Recommended"],
          ["state", "US states (two-letter codes, e.g. NY)", ""],
          ["custom", "My own market IDs (e.g. my DMA list)", ""],
        ] as const).map(([v, text, tag]) => (
          <label key={v} className="check">
            <input type="radio" name="unit" value={v} checked={s.geoUnit === v} disabled={loader.busy}
              onChange={() => loader.changeUnit(v)} />
            <span>{text}{tag && <span className="tag">{tag}</span>}</span>
          </label>
        ))}
        {s.geoUnit === "custom" && <p className="small muted">Your geo_id values are used as they are. FOSIT doesn't ship Nielsen DMA definitions because they're proprietary.</p>}
      </fieldset>

      <div className={`dropzone ${drag ? "drag" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) loader.loadKpiFile(f); }}>
        <p style={{ marginBottom: 8 }}><strong>Drop a CSV with daily sales by market</strong></p>
        <p className="small muted">Columns: date, geo_id, orders and/or revenue. Read on your computer, never uploaded.</p>
        <label className="btn btn-primary" style={{ display: "inline-flex" }}>
          Choose file
          <input type="file" accept=".csv,text/csv" className="sr-only" data-testid="kpi-file" disabled={loader.busy}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) loader.loadKpiFile(f); e.target.value = ""; }} />
        </label>
        <div className="row" style={{ justifyContent: "center", marginTop: 12 }}>
          <a href={docUrl("SCHEMA.md", "1-kpi-history-kpi_historycsv")} target="_blank" rel="noreferrer" className="small">See the format</a>
          <button type="button" className="link-btn small" onClick={() => downloadText(TEMPLATE_CSV, "fosit-kpi-history-template.csv", "text/csv")}>Download a template</button>
          <button type="button" className="link-btn small" onClick={loader.loadSample} disabled={loader.busy}>Use sample data</button>
        </div>
      </div>

      <details style={{ marginTop: 12 }}>
        <summary>Only have an order export with ZIP codes? We'll turn it into markets for you.</summary>
        <p className="small muted">Columns: order_date, shipping_zip, and optionally revenue and order_id. ZIPs are placed into markets with the Census crosswalk shipped in FOSIT{s.geoUnit === "custom" ? ", or with your own ZIP → market file" : ""}.</p>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="orders-file">Order export (CSV)</label>
            <input id="orders-file" type="file" accept=".csv,text/csv" onChange={(e) => setOrdersFile(e.target.files?.[0] ?? null)} />
          </div>
          {s.geoUnit === "custom" && (
            <div className="field">
              <label htmlFor="map-file">ZIP → market mapping (zip, geo_id)</label>
              <input id="map-file" type="file" accept=".csv,text/csv" onChange={(e) => setMappingFile(e.target.files?.[0] ?? null)} />
            </div>
          )}
        </div>
        <button type="button" disabled={!ordersFile || loader.busy || (s.geoUnit === "custom" && !mappingFile)}
          onClick={() => ordersFile && loader.loadOrdersFile(ordersFile, mappingFile)}>Build market history</button>
      </details>

      <div aria-live="polite" style={{ marginTop: 16 }}>
        {loader.busy && <p className="muted">⏳ {status && status !== "Ready" ? status : "Checking your file…"}</p>}
        {loader.error && <div className="callout err">{loader.error}</div>}
      </div>

      {d && !loader.busy && (
        <div style={{ marginTop: 8 }}>
          <h3>{hasError ? "We need you to fix something" : "Looks good"} · <span className="muted small">{d.fileName}</span></h3>
          {!hasError && d.summary && <Sparkline values={d.summary.daily_totals} label={`Total daily ${d.summary.chart_kpi} across all markets`} />}
          <IssueList issues={d.issues} ok={hasError ? [] : okLines} />
          {d.source === "sample" && <p className="callout small">This is <strong>synthetic sample data</strong> on real metro areas, for trying FOSIT out. It isn't anyone's real sales.</p>}
        </div>
      )}
    </section>
  );
}

export function dataStepProblems(s: PlanState): string[] {
  if (!s.data) return ["Load your sales history (or use the sample data)."];
  if (s.data.issues.some((i) => i.severity === "error")) return ["Fix the errors in the file first."];
  return [];
}
