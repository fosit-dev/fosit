/// <reference lib="webworker" />
// Runs FOSIT's Python core (core/fosit) inside Pyodide, off the main thread so the UI stays responsive.
// Everything is loaded from this site's own origin (public/pyodide, public/fosit-core.zip):
// no third-party request is ever made, and user data never leaves this worker except back to the page.

import type { WorkerRequest, WorkerResponse } from "./protocol";

declare const self: DedicatedWorkerGlobalScope;

type Pyodide = {
  loadPackage: (names: string[], options?: { messageCallback?: (m: string) => void }) => Promise<unknown>;
  unpackArchive: (buffer: ArrayBuffer, format: string, options?: { extractDir?: string }) => void;
  runPython: (code: string) => unknown;
  globals: { get: (name: string) => (...args: unknown[]) => string };
};

let ready: Promise<Pyodide> | null = null;

const post = (msg: WorkerResponse) => self.postMessage(msg);

const BRIDGE = `
import json, sys
sys.path.insert(0, "/home/pyodide/fosit_core")
from fosit import api

def fosit_call(name, args_json, progress=None):
    args = json.loads(args_json)
    fn = getattr(api, name)
    if progress is not None:
        result = fn(**args, progress=lambda p: progress(json.dumps(api._clean(p))))
    else:
        result = fn(**args)
    return json.dumps(result)
`;

async function boot(root: string): Promise<Pyodide> {
  post({ type: "status", message: "Loading the Python engine (one-time, about 30 MB, cached afterwards)…" });
  const { loadPyodide } = await import(/* @vite-ignore */ `${root}pyodide/pyodide.mjs`);
  const pyodide: Pyodide = await loadPyodide({ indexURL: `${root}pyodide/` });
  post({ type: "status", message: "Loading numpy, scipy and pandas…" });
  await pyodide.loadPackage(["numpy", "scipy", "pandas"]);
  post({ type: "status", message: "Loading FOSIT's statistics code…" });
  const bundle = await fetch(`${root}fosit-core.zip`).then((r) => {
    if (!r.ok) throw new Error(`fosit-core.zip: HTTP ${r.status}`);
    return r.arrayBuffer();
  });
  pyodide.unpackArchive(bundle, "zip", { extractDir: "/home/pyodide/fosit_core" });
  pyodide.runPython(BRIDGE);
  post({ type: "status", message: "Ready" });
  return pyodide;
}

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  const msg = event.data;
  try {
    if (msg.type === "init") {
      ready ??= boot(msg.root);
      await ready;
      post({ type: "result", id: msg.id, value: "ready" });
      return;
    }
    if (!ready) throw new Error("Worker not initialised");
    const py = await ready;
    const call = py.globals.get("fosit_call");
    const onProgress = (json: string) => post({ type: "progress", id: msg.id, value: JSON.parse(json) });
    const out = msg.withProgress ? call(msg.fn, JSON.stringify(msg.args), onProgress) : call(msg.fn, JSON.stringify(msg.args));
    post({ type: "result", id: msg.id, value: JSON.parse(out) });
  } catch (err) {
    post({ type: "error", id: msg.id, message: err instanceof Error ? err.message : String(err) });
  }
};
