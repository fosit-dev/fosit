import { CONSULT, CONSULT_LABEL, CONSULT_TEXT } from "../config";
import { EMBEDDED, requestConsult } from "../embed";

// Optional offer of a free planning call (VITE_CONSULT). "host" asks the embedding page to open its
// contact form; otherwise CONSULT is a URL opened in a new tab. Nothing from the tool is sent either way.

const enabled = () => !!CONSULT && (CONSULT !== "host" || EMBEDDED);

export function ConsultButton({ className = "", label = CONSULT_LABEL }: { className?: string; label?: string }) {
  if (!enabled()) return null;
  if (CONSULT === "host") return <button type="button" className={`btn-ghost ${className}`} onClick={requestConsult}>{label}</button>;
  return <a className={`btn btn-ghost ${className}`} href={CONSULT} target="_blank" rel="noreferrer">{label}</a>;
}

/** A short callout with the offer, for the intro and the first Plan step. */
export function ConsultCallout() {
  if (!enabled()) return null;
  return (
    <div className="callout consult">
      <p style={{ margin: "0 0 8px" }}>{CONSULT_TEXT}</p>
      <ConsultButton />
    </div>
  );
}
