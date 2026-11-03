// Embed mode: FOSIT running inside an <iframe> on a host page (e.g. adte.com).
// Turned on by ?embed=1. The frame reports its height so the host can size it (no inner
// scrollbar) and asks the host to scroll to the frame's top when the user changes step.
// Messages go only to the frame's own origin and carry layout numbers, never user data.

const params = new URLSearchParams(window.location.search);

export const EMBEDDED = params.get("embed") === "1" && window.parent !== window;
export const INITIAL_THEME = params.get("theme");

function post(message: Record<string, unknown>) {
  if (EMBEDDED) window.parent.postMessage({ source: "fosit", ...message }, window.location.origin);
}

/** The page people should come back to: the host page when embedded (same origin), else this page. */
export function pageUrl(): string {
  try {
    const loc = EMBEDDED ? window.parent.location : window.location;
    return `${loc.origin}${loc.pathname}`;
  } catch {
    return `${window.location.origin}${window.location.pathname}`;
  }
}

/** Link that opens straight on Read results (#read on this page, or on the host page). */
export const readLink = () => `${pageUrl()}#read`;

export const OPEN_READ = (() => {
  try {
    return (EMBEDDED ? window.parent.location.hash : window.location.hash) === "#read";
  } catch {
    return false;
  }
})();

/** Ask the host page to open its contact form (VITE_CONSULT=host). Sends no user data. */
export function requestConsult() {
  post({ type: "consult" });
}

export function scrollToTop() {
  if (EMBEDDED) post({ type: "scroll-top" });
  else window.scrollTo({ top: 0 });
}

export function startEmbed() {
  if (!EMBEDDED) return;
  document.documentElement.setAttribute("data-embed", "");
  let last = 0;
  const report = () => {
    const h = Math.ceil(document.documentElement.scrollHeight);
    if (h !== last) {
      last = h;
      post({ type: "height", height: h });
    }
  };
  new ResizeObserver(report).observe(document.body);
  report();
}
