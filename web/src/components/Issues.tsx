export type Issue = { severity: "error" | "warning" | "info"; code: string; message: string; count: number; examples: (string | number)[] };

const ICON = { error: "✕", warning: "!", info: "✓" } as const;

/** Plain-English list of what we found in a file. Errors explain the fix; warnings are carried into the report. */
export function IssueList({ issues, ok }: { issues: Issue[]; ok?: string[] }) {
  return (
    <ul className="issues" aria-label="File check results">
      {(ok ?? []).map((m) => (
        <li key={m} className="issue info"><span className="issue-icon" aria-hidden>✓</span><span>{m}</span></li>
      ))}
      {issues.map((i) => (
        <li key={i.code} className={`issue ${i.severity}`}>
          <span className="issue-icon" aria-hidden>{ICON[i.severity]}</span>
          <span>
            <span className="sr-only">{i.severity}: </span>
            {i.message}
            {i.examples.length > 0 && i.severity !== "info" && (
              <span className="issue-examples">
                {typeof i.examples[0] === "number" ? "Rows: " : "e.g. "}
                {i.examples.slice(0, 8).join(", ")}{i.examples.length > 8 ? "…" : ""}
              </span>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}
