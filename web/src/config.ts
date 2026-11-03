// Deployment settings, read at build time from VITE_* environment variables.
// Defaults are deliberately neutral: no vendor names, no contact link, no tracking.

const env = import.meta.env;

/** Public repository; every "Read more" and "See the code" link points here. */
export const REPO_URL: string = env.VITE_REPO_URL || "https://github.com/fosit-dev/fosit";
export const DOCS_BRANCH: string = env.VITE_DOCS_BRANCH || "main";
/** Optional contact link shown in the footer (e.g. the embedding site's contact page). */
export const CONTACT_URL: string = env.VITE_CONTACT_URL || "";
export const CONTACT_LABEL: string = env.VITE_CONTACT_LABEL || "Questions? Contact us";
/** Optional offer of a free planning call, shown in the header, the intro and the first Plan step.
 *  "" = off (default). "host" = ask the embedding page to open its own contact form (embed mode only).
 *  Anything else is a URL, opened in a new tab. The click sends nothing from the tool. */
export const CONSULT: string = env.VITE_CONSULT || "";
export const CONSULT_LABEL: string = env.VITE_CONSULT_LABEL || "Book a free call with a data analyst";
export const CONSULT_SHORT: string = env.VITE_CONSULT_SHORT || "Free analyst call";
export const CONSULT_TEXT: string = env.VITE_CONSULT_TEXT ||
  "Finding this a lot to set up? A data analyst can plan and run the test with you on a free call, no strings attached.";
/** Optional conflict-of-interest disclosure shown in the footer when embedded by a media company. */
export const DISCLOSURE: string = env.VITE_DISCLOSURE || "";
/** Placeholder until an independent review page exists. */
export const REVIEW_URL: string = env.VITE_REVIEW_URL || `${REPO_URL}/blob/${DOCS_BRANCH}/docs/REVIEW.md`;

export const APP_VERSION = "0.1.0";

export const docUrl = (file: string, anchor = "") =>
  `${REPO_URL}/blob/${DOCS_BRANCH}/docs/${file}${anchor ? `#${anchor}` : ""}`;
export const codeUrl = (path: string) => `${REPO_URL}/blob/${DOCS_BRANCH}/${path}`;
