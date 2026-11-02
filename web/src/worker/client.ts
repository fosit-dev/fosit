// Promise-based client for the Python worker. One worker per page; calls are queued by the worker.
import type { Progress, WorkerRequest, WorkerResponse } from "./protocol";

type Pending = { resolve: (v: any) => void; reject: (e: Error) => void; onProgress?: (p: Progress) => void };

let worker: Worker | null = null;
let nextId = 1;
const pending = new Map<number, Pending>();
const statusListeners = new Set<(s: string) => void>();
let lastStatus = "";
let initPromise: Promise<void> | null = null;

function ensureWorker(): Worker {
  if (worker) return worker;
  worker = new Worker(new URL("./pyworker.ts", import.meta.url), { type: "module" });
  worker.onmessage = (e: MessageEvent<WorkerResponse>) => {
    const msg = e.data;
    if (msg.type === "status") {
      lastStatus = msg.message;
      statusListeners.forEach((l) => l(msg.message));
      return;
    }
    const p = pending.get(msg.id);
    if (!p) return;
    if (msg.type === "progress") p.onProgress?.(msg.value);
    else {
      pending.delete(msg.id);
      if (msg.type === "result") p.resolve(msg.value);
      else p.reject(new Error(msg.message));
    }
  };
  return worker;
}

type WithoutId<T> = T extends unknown ? Omit<T, "id"> : never;

function send<T>(req: WithoutId<WorkerRequest>, onProgress?: (p: Progress) => void): Promise<T> {
  const w = ensureWorker();
  const id = nextId++;
  return new Promise<T>((resolve, reject) => {
    pending.set(id, { resolve, reject, onProgress });
    w.postMessage({ ...req, id } as WorkerRequest);
  });
}

/** Start loading Pyodide in the background. Safe to call many times. */
export function initEngine(): Promise<void> {
  initPromise ??= send<void>({ type: "init", root: new URL("./", document.baseURI).href });
  return initPromise;
}

export function onEngineStatus(listener: (s: string) => void): () => void {
  statusListeners.add(listener);
  if (lastStatus) listener(lastStatus);
  return () => statusListeners.delete(listener);
}

export async function callPython<T>(fn: string, args: Record<string, unknown>, onProgress?: (p: Progress) => void): Promise<T> {
  await initEngine();
  return send<T>({ type: "call", fn, args, withProgress: Boolean(onProgress) }, onProgress);
}

/** Stop a long computation by terminating the worker; the next call starts a fresh one (data must be reloaded). */
export function cancelEngine(): void {
  worker?.terminate();
  worker = null;
  initPromise = null;
  pending.forEach((p) => p.reject(new Error("cancelled")));
  pending.clear();
}
