# Security and privacy

FOSIT's core promise is that **user data never leaves the browser**. A bug that breaks that promise is a security issue, even if no attacker is involved.

## Reporting

Please report privately via GitHub: **Security → Report a vulnerability** on this repository. Don't open a public issue for:

- any network request that carries user data, or any request to a third-party origin;
- a way to make a locked plan's fingerprint match a changed plan;
- anything that lets a host page read data loaded into an embedded FOSIT.

We'll acknowledge within 5 working days and credit you in the CHANGELOG unless you'd rather stay anonymous.

## What protects users today

- No backend: the app is static files, and all computation runs in the browser (Pyodide in a Web Worker).
- A Content-Security-Policy with `connect-src 'self'` blocks requests to other origins.
- `web/e2e/privacy.spec.ts` runs on every change and fails if any request leaves the origin, isn't a GET, or carries test data.
- Pyodide and its packages are self-hosted and SHA-256 checked at build time.
