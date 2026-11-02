# FOSIT web app

React + TypeScript + Vite. The Python core (`/core`) runs in the browser through Pyodide, inside a Web Worker. Static build, no backend, embeddable via iframe.

```bash
pnpm install
pnpm prepare-runtime   # copies Pyodide into public/ and downloads numpy/scipy/pandas wheels (SHA-256 checked); packs /core
pnpm dev               # http://localhost:5173
pnpm test              # Vitest: RFC 8785 canonicalization, plan hashing (cross-checked with Python)
pnpm test:e2e          # Playwright: full Plan flow in a real browser + the privacy test
pnpm build             # dist/ — host anywhere; all paths are relative
```

Re-run `python3 scripts/build_core_bundle.py` after changing anything in `/core`: the bundle's SHA-256 is written into every locked plan as `tool.core_sha256`.

## Privacy by construction

- Pyodide and its packages are served from this site (`public/pyodide/`), never from a CDN.
- `index.html` sets a Content-Security-Policy with `connect-src 'self'`, so the page can't send anything elsewhere even by mistake.
- `e2e/privacy.spec.ts` runs the whole Plan flow on a file full of canary values and fails if any request leaves the origin, carries the canary, or isn't a GET.
- No analytics, no fonts or images from elsewhere, no cookies. The only browser storage is the theme choice.

## Deployment settings (build-time environment variables)

| Variable | Purpose | Default |
|---|---|---|
| `VITE_REPO_URL` | Public repository for "Read more" / "See the code" links | `https://github.com/fosit-dev/fosit` |
| `VITE_DOCS_BRANCH` | Branch for doc links | `main` |
| `VITE_CONTACT_URL`, `VITE_CONTACT_LABEL` | Optional footer contact link | none |
| `VITE_DISCLOSURE` | Optional conflict-of-interest line, e.g. when a media company embeds it | none |
| `VITE_REVIEW_URL` | Independent review page | `docs/REVIEW.md` in the repo |

Defaults name no vendor and no company.

## Embedding

Serve `dist/` from its own (sub)domain and embed it with an `<iframe>`. The iframe's origin isolates FOSIT from the host page, so the host's scripts and analytics can't read anything the user loads into FOSIT.
