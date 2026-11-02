import { useEffect, useId, useRef, useState } from "react";
import { GLOSSARY, type TermKey } from "../lib/glossary";
import { codeUrl, docUrl } from "../config";

/** The ⓘ button: plain-English explanation, with links to the method and the code for those who want them. */
export function InfoTip({ term, label }: { term: TermKey; label?: string }) {
  const t = GLOSSARY[term] as { title: string; text: string; doc?: [string, string]; code?: string };
  const [open, setOpen] = useState(false);
  const id = useId();
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <span className="infotip" ref={ref}>
      <button type="button" className="infotip-btn" aria-expanded={open} aria-controls={id}
        aria-label={`About ${label ?? t.title}`} onClick={() => setOpen((o) => !o)}>
        i
      </button>
      {open && (
        <span role="dialog" aria-label={t.title} id={id} className="infotip-pop">
          <strong>{t.title}</strong>
          <span>{t.text}</span>
          <span className="infotip-links">
            {t.doc && <a href={docUrl(t.doc[0], t.doc[1])} target="_blank" rel="noreferrer">Read more →</a>}
            {t.code && <a href={codeUrl(t.code)} target="_blank" rel="noreferrer">See the code →</a>}
          </span>
        </span>
      )}
    </span>
  );
}
