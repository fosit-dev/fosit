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
