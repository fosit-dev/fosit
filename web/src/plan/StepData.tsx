import { useEffect, useState } from "react";
import { InfoTip } from "../components/InfoTip";
import { IssueList } from "../components/Issues";
import { Sparkline } from "../components/Charts";
import { docUrl } from "../config";
import { downloadText } from "../lib/download";
import { num } from "../lib/format";
import { useLevel } from "../lib/level";
import { designInfo, goalOf, tech } from "../lib/words";
import { WhyNote } from "../components/Visuals";
import { onEngineStatus } from "../worker/client";
import { withTemplate, type PlanState } from "./state";

/** METHODOLOGY §14.1: at a few hundred orders a day or less, a test in a few markets seldom sees a useful effect,
 * and below about 100 a day no such test passes the checks (§9.3). The halves-take-turns test is made for this size. */
export const SMALL_BUSINESS_ORDERS_PER_DAY = 400;
export const TOO_SMALL_FOR_GEO_ORDERS_PER_DAY = 100;
export function ordersPerDay(s: PlanState): number | null {
  const sum = s.data?.summary;
  return sum?.totals?.orders != null && sum.days > 0 ? sum.totals.orders / sum.days : null;
}

export type DataLoader = {
  loadKpiFile: (file: File) => Promise<void>;
  loadOrdersFile: (file: File, mapping: File | null) => Promise<void>;
  loadSample: () => Promise<void>;
  changeUnit: (unit: PlanState["geoUnit"]) => Promise<void>;
  busy: boolean;
  error: string | null;
};

const TEMPLATE_CSV = "date,geo_id,orders,revenue\n2026-06-01,35620,412,38211.50\n2026-06-01,31080,298,27002.10\n2026-06-02,35620,397,36940.00\n";

export function StepData({ s, loader, set }: { s: PlanState; loader: DataLoader; set: (p: Partial<PlanState>) => void }) {
  const { level } = useLevel();
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
        ...(level === "brief" ? [] : [`File fingerprint ${d.sha256.slice(0, 12)}… (recorded in the plan; the file itself never leaves your computer)`]),
      ]
    : [];
  const hasError = d?.issues.some((i) => i.severity === "error");
  const perDay = ordersPerDay(s);
  const small = perDay != null && perDay <= SMALL_BUSINESS_ORDERS_PER_DAY && s.template !== "crossover";

  return (
    <section className="card">
      <h2>Your sales history</h2>
      {level !== "brief" && <WhyNote>FOSIT learns how your markets sell in normal weeks. Then it can find fair groups, and it can tell what the test will see. The file stays on your computer.</WhyNote>}
      <fieldset style={{ border: 0, padding: 0, margin: "0 0 16px" }}>
        <legend style={{ fontWeight: 600, marginBottom: 6 }}>{tech(level, "What are the markets in your file?", "Market unit")}<InfoTip term="geoUnit" /></legend>
        {([
          ["cbsa", tech(level, "US metro areas (codes such as 35620 for New York)", "US metro & micro areas (Census CBSA codes, e.g. 35620)"), "Recommended"],
          ["state", "US states (two-letter codes such as NY)", ""],
          ["custom", "My own list of markets (for example my DMA list)", ""],
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
        <p className="small muted">One row for each day and market. Columns: date, geo_id, orders and/or revenue. Read on your computer, never uploaded.</p>
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
        {level !== "brief" && !d && (
          <div className="filepic" aria-label="Example of the file">
            <table>
              <thead><tr><th>date</th><th>geo_id</th><th>orders</th><th>revenue</th></tr></thead>
              <tbody>
                <tr><td>2026-06-01</td><td>{s.geoUnit === "state" ? "NY" : "35620"}</td><td>412</td><td>38211.50</td></tr>
                <tr><td>2026-06-01</td><td>{s.geoUnit === "state" ? "CA" : "31080"}</td><td>298</td><td>27002.10</td></tr>
                <tr><td>2026-06-02</td><td>{s.geoUnit === "state" ? "NY" : "35620"}</td><td>397</td><td>36940.00</td></tr>
              </tbody>
            </table>
          </div>
        )}
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
          {!hasError && small && perDay != null && (
            <div className="callout warn" data-testid="small-business">
              <strong>Your file shows about {num(Math.round(perDay))} orders a day.</strong>{" "}
              {perDay < TOO_SMALL_FOR_GEO_ORDERS_PER_DAY
                ? "At this size, FOSIT usually finds no test of this type that passes its checks."
                : "At this size, a test of this type often cannot see a useful effect."}{" "}
              The test "{designInfo("crossover").title}" is made for a small business.
              {goalOf(s.template) === "compare" ? " It measures one campaign, so it cannot compare vendors." : ""}
              <div style={{ marginTop: 8 }}>
                <button type="button" onClick={() => set(withTemplate(s, "crossover", 1))}>Switch to "{designInfo("crossover").title}"</button>
              </div>
            </div>
          )}
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
