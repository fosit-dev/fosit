// How much detail to show. Leaders want the answer and the money; marketers want the steps; analysts want every number.
// The same three levels exist in the interactive HTML pages (core/fosit/templates/page.html), so a file sent to a CMO
// can open on "Brief" and the analyst can switch it to "Full".
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Level = "brief" | "guided" | "full";

export const LEVELS: { id: Level; label: string; hint: string }[] = [
  { id: "brief", label: "Brief", hint: "The answer and the money. For leaders." },
  { id: "guided", label: "Guided", hint: "The answer, how the test works, and what to do. For marketers." },
  { id: "full", label: "Full", hint: "Every number, check and setting. For analysts." },
];

const KEY = "fosit-level";

function load(): Level {
  try {
    const v = localStorage.getItem(KEY);
    return v === "brief" || v === "guided" || v === "full" ? v : "guided";
  } catch {
    return "guided";
  }
}

const Ctx = createContext<{ level: Level; setLevel: (l: Level) => void }>({ level: "guided", setLevel: () => undefined });

export function LevelProvider({ children }: { children: ReactNode }) {
  const [level, setLevel] = useState<Level>(load);
  useEffect(() => {
    document.documentElement.dataset.level = level;
    try {
      localStorage.setItem(KEY, level);
    } catch {
      /* private mode: the level just isn't remembered */
    }
  }, [level]);
  return <Ctx.Provider value={{ level, setLevel }}>{children}</Ctx.Provider>;
}

export const useLevel = () => useContext(Ctx);

export function LevelSwitch() {
  const { level, setLevel } = useLevel();
  return (
    <div className="levels" role="radiogroup" aria-label="How much detail">
      {LEVELS.map((l) => (
        <button key={l.id} type="button" role="radio" aria-checked={level === l.id} title={l.hint} onClick={() => setLevel(l.id)}>{l.label}</button>
      ))}
    </div>
  );
}
