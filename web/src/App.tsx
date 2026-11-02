import { useEffect, useState } from "react";
import { Why } from "./Why";
import { PlanWizard } from "./plan/PlanWizard";
import { ReadSoon } from "./ReadSoon";
import { InfoTip } from "./components/InfoTip";
import { CONTACT_LABEL, CONTACT_URL, DISCLOSURE, REPO_URL, REVIEW_URL, docUrl } from "./config";
import { initEngine } from "./worker/client";

type Screen = "why" | "plan" | "read";
type Theme = "system" | "light" | "dark";

function loadTheme(): Theme {
  try {
    return (localStorage.getItem("fosit-theme") as Theme) || "system";
  } catch {
    return "system";
  }
}

export function App() {
  const [screen, setScreen] = useState<Screen>("why");
  const [sample, setSample] = useState(false);
  const [theme, setTheme] = useState<Theme>(loadTheme);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("fosit-theme", theme);
    } catch {
      /* private mode: theme just isn't remembered */
    }
  }, [theme]);

  // Start loading the Python engine in the background while people read the intro.
  useEffect(() => {
    initEngine().catch(() => undefined);
  }, []);

  const go = (s: Screen, withSample = false) => {
    setSample(withSample);
    setScreen(s);
    window.scrollTo(0, 0);
  };

  return (
    <>
      <a className="sr-only" href="#main">Skip to content</a>
      <div className="banner" role="note">
        <div className="banner-inner">
          <span aria-hidden>🔒</span>
          <strong>Your data never leaves this browser.</strong>
          <InfoTip term="privacy" />
        </div>
      </div>
      <header className="topbar">
        <div className="topbar-inner">
          <button className="brand" onClick={() => go("why")} aria-label="FOSIT home">
            <span className="brand-mark" aria-hidden>
              <svg width="18" height="18" viewBox="0 0 32 32"><path d="M6 23l6-8 5 4 9-11" stroke="white" strokeWidth="3.5" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </span>
            <span>FOSIT <small>Free Open-Source Incrementality Tool</small></span>
          </button>
          <div className="row">
            <button className={`btn-ghost small ${screen === "plan" ? "" : ""}`} onClick={() => go("plan")} aria-current={screen === "plan" ? "page" : undefined}>Plan</button>
            <button className="btn-ghost small" onClick={() => go("read")} aria-current={screen === "read" ? "page" : undefined}>Read</button>
            <label className="sr-only" htmlFor="theme">Theme</label>
            <select id="theme" value={theme} onChange={(e) => setTheme(e.target.value as Theme)} style={{ width: "auto" }}>
              <option value="system">Auto</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </div>
        </div>
      </header>
      <main id="main" className="page">
        {screen === "why" && <Why onPlan={(s) => go("plan", s)} onRead={() => go("read")} />}
        {screen === "plan" && <PlanWizard startWithSample={sample} />}
        {screen === "read" && <ReadSoon onPlan={() => go("plan")} />}
      </main>
      <footer className="footer">
        <div className="footer-inner">
          <a href={REPO_URL} target="_blank" rel="noreferrer">GitHub repository</a>
          <a href={docUrl("METHODOLOGY.md")} target="_blank" rel="noreferrer">METHODOLOGY.md</a>
          <a href={REVIEW_URL} target="_blank" rel="noreferrer">Independent review</a>
          <span className="muted">Apache 2.0</span>
          {CONTACT_URL && <a href={CONTACT_URL} target="_blank" rel="noreferrer">{CONTACT_LABEL}</a>}
          {DISCLOSURE && <p className="disclosure">{DISCLOSURE}</p>}
        </div>
      </footer>
    </>
  );
}
