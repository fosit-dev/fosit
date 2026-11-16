// The pictures of a test: who has the ads where, the numbered steps, the timeline and the chance meter.
// The reports draw the same pictures (core/fosit/templates/page.html), so a plan looks the same on the screen,
// in the file sent to the vendors and in the results. Every picture has a text equivalent (a legend or an aria-label).
import { useState, type ReactNode } from "react";
import { pct } from "../lib/format";
import { daysBetween, toDate } from "../lib/dates";
import type { AnatomyStep, IconKind, Segment } from "../lib/words";

const GROUP = ["var(--p1)", "var(--p2)", "var(--p3)", "var(--p4)", "var(--p5)", "var(--p6)"];

/** Group colors by position: vendors get p1…p6, the markets with no ads are gray, the two halves are p1 and p2. */
export function segmentColors(segments: Segment[]): string[] {
  let k = 0;
  return segments.map((s) => (s.role === "none" ? "var(--p-none)" : GROUP[k++ % GROUP.length]));
}

/** One bar for the whole country, cut by share of sales. `approx` marks example sizes, not measured ones. */
export function ShareBar({ segments, approx = false, mini = false }: { segments: Segment[]; approx?: boolean; mini?: boolean }) {
  const total = segments.reduce((a, s) => a + s.share, 0) || 1;
  const colors = segmentColors(segments);
  const share = (s: Segment) => s.share / total;
  const say = (s: Segment) => `${s.label}: ${s.n != null ? `${s.n} markets, ` : ""}${approx ? "about " : ""}${pct(share(s), 0)} of sales`;
  const bar = (
    <div className={`share ${mini ? "mini" : ""}`} role="img" aria-label={segments.map(say).join("; ")}>
      {segments.map((s, i) => (
        <div key={i} style={{ flex: Math.max(share(s), 0.02), background: colors[i] }}>{!mini && share(s) > 0.08 ? pct(share(s), 0) : ""}</div>
      ))}
    </div>
  );
  if (mini) return bar;
  return (
    <div>
      {bar}
      <div className="keys">{segments.map((s, i) => <span key={i}><i className="swatch" style={{ background: colors[i] }} />{say(s)}</span>)}</div>
    </div>
  );
}

function Icon({ kind }: { kind: IconKind }) {
  const ink = "var(--muted)";
  return (
    <svg width="40" height="28" viewBox="0 0 40 28" aria-hidden>
      {kind === "map" && [0, 1, 2, 3].flatMap((i) => [0, 1, 2].map((j) => (
        <rect key={`${i}${j}`} x={2 + i * 9} y={2 + j * 8} width="7" height="6" rx="1.5" fill={i < 1 ? "var(--p1)" : i < 2 ? "var(--p2)" : "var(--p-none)"} />)))}
      {kind === "tv" && <><rect x="6" y="3" width="28" height="18" rx="3" fill="none" stroke={ink} strokeWidth="2" /><path d="M14 26h12" stroke={ink} strokeWidth="2" strokeLinecap="round" /><path d="M17 8l8 4-8 4z" fill="var(--p1)" /></>}
      {kind === "twin" && <><path d="M2 20 C10 8, 16 18, 22 10 S34 6, 38 8" stroke="var(--p1)" strokeWidth="2.5" fill="none" /><path d="M2 22 C10 10, 16 20, 22 12 S34 8, 38 10" stroke={ink} strokeWidth="2" fill="none" strokeDasharray="4 3" /></>}
      {kind === "compare" && <><path d="M2 22 L14 18 L20 19 L38 6" stroke="var(--p1)" strokeWidth="2.5" fill="none" /><path d="M20 19 L38 17" stroke={ink} strokeWidth="2" fill="none" strokeDasharray="4 3" /><path d="M20 19 L38 6 L38 17 Z" fill="var(--p1)" opacity=".18" /></>}
      {kind === "gap" && <><rect x="4" y="14" width="9" height="12" rx="2" fill="var(--p-none)" /><rect x="16" y="6" width="9" height="20" rx="2" fill="var(--p1)" /><path d="M29 6v8 M27 6h4 M27 14h4" stroke={ink} strokeWidth="2" /></>}
      {kind === "swap" && <path d="M6 9h26l-5-5 M34 19H8l5 5" stroke={ink} strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />}
      {kind === "clock" && <><circle cx="20" cy="14" r="11" fill="none" stroke={ink} strokeWidth="2" /><path d="M20 8v6l4 3" stroke={ink} strokeWidth="2" fill="none" strokeLinecap="round" /></>}
      {kind === "scale" && <><path d="M20 4v20 M8 24h24 M6 10h28" stroke={ink} strokeWidth="2" strokeLinecap="round" /><path d="M6 10l-4 8h8z M34 10l-4 8h8z" fill="var(--p1)" opacity=".6" /></>}
      {kind === "halves" && <><rect x="3" y="4" width="16" height="20" rx="3" fill="var(--p1)" /><rect x="21" y="4" width="16" height="20" rx="3" fill="var(--p2)" /></>}
    </svg>
  );
}

/** The numbered steps of a test. Each step is one sentence; selecting it shows a little more. */
export function Anatomy({ steps }: { steps: AnatomyStep[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <>
      <div className="anatomy">
        {steps.map((s, i) => (
          <button key={s.t} type="button" className="anatomy-step" aria-expanded={open === i} onClick={() => setOpen(open === i ? null : i)}>
            <span className="n" aria-hidden>{i + 1}</span>
            <Icon kind={s.icon} />
            <span className="t"><span className="sr-only">Step {i + 1}: </span>{s.t}</span>
            <span className="x">{s.x}</span>
            {open === i && <span className="more">{s.m}</span>}
          </button>
        ))}
      </div>
      <p className="tiny">Select a step to read more.</p>
    </>
  );
}

const short = (s: string) => toDate(s).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

export type TimelinePart = { t: string; from: string; to: string; say?: string; kind: "history" | "ads" | "cool" };

/** History, ads, cooldown, read: the dates of a test in one strip, each part as wide as it is long. */
export function Timeline({ parts, readFrom }: { parts: TimelinePart[]; readFrom: string }) {
  const days = (p: TimelinePart) => daysBetween(p.from, p.to) + 1;
  const total = parts.reduce((a, p) => a + days(p), 0) || 1;
  return (
    <div className="timeline" role="group" aria-label="Timeline of the test">
      {parts.map((p) => (
        <div key={p.t} className={p.kind} style={{ flex: Math.max(0.16, days(p) / total) }}>
          <div className="t">{p.t}</div>
          <div>{short(p.from)} – {short(p.to)}</div>
          {p.say && <div className="tiny">{p.say}</div>}
        </div>
      ))}
      <div className="read"><div className="t">Read</div><div>from {short(readFrom)}</div></div>
    </div>
  );
}

/** A crossover's blocks: the letter is the half with the ads, the striped part is the skipped start of each block. */
export function BlockStrip({ order, blockDays, washoutDays, note }: { order: ("A" | "B")[]; blockDays: number; washoutDays: number; note?: ReactNode }) {
  return (
    <div>
      <div className="blocks" role="img" aria-label={`Blocks of ${blockDays / 7} weeks. Ads in half ${order.join(", then ")}.`}>
        {order.map((on, i) => (
          <div key={i} style={{ background: on === "A" ? "var(--p1)" : "var(--p2)" }}><i style={{ width: `${(100 * washoutDays) / blockDays}%` }} />{on}</div>
        ))}
      </div>
      <p className="tiny">Each box is one block of {blockDays / 7} weeks. The letter shows the half with the ads. FOSIT skips the striped days. {note}</p>
    </div>
  );
}

/** A filled bar for a chance from 0 to 1, with its tone. The sentence beside it says the same in words. */
export function Meter({ p, tone, label }: { p: number; tone: "ok" | "warn" | "err"; label: string }) {
  return (
    <div className="meter" role="img" aria-label={label}>
      <div style={{ width: `${Math.round(100 * Math.max(0, Math.min(1, p)))}%`, background: `var(--${tone})` }} />
    </div>
  );
}

/** "Why we ask": one or two plain sentences under a question, for the Guided and Full levels. */
export function WhyNote({ children }: { children: ReactNode }) {
  return <p className="why-note"><span aria-hidden>💡</span><span>{children}</span></p>;
}
