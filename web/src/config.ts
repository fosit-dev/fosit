// Deployment settings, read at build time from VITE_* environment variables.
// Defaults are deliberately neutral: no vendor names, no contact link, no tracking.

const env = import.meta.env;

/** Public repository; every "Read more" and "See the code" link points here. */
export const REPO_URL: string = env.VITE_REPO_URL || "https://github.com/fosit-dev/fosit";
export const DOCS_BRANCH: string = env.VITE_DOCS_BRANCH || "main";
/** Optional contact link shown in the footer (e.g. the embedding site's contact page). */
export const CONTACT_URL: string = env.VITE_CONTACT_URL || "";
export const CONTACT_LABEL: string = env.VITE_CONTACT_LABEL || "Questions? Contact us";
/** Optional conflict-of-interest disclosure shown in the footer when embedded by a media company. */
export const DISCLOSURE: string = env.VITE_DISCLOSURE || "";
/** Placeholder until an independent review page exists. */
export const REVIEW_URL: string = env.VITE_REVIEW_URL || `${REPO_URL}/blob/${DOCS_BRANCH}/docs/REVIEW.md`;

export const APP_VERSION = "0.1.0";

export const docUrl = (file: string, anchor = "") =>
  `${REPO_URL}/blob/${DOCS_BRANCH}/docs/${file}${anchor ? `#${anchor}` : ""}`;
export const codeUrl = (path: string) => `${REPO_URL}/blob/${DOCS_BRANCH}/${path}`;
