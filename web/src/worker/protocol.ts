export type WorkerRequest =
  | { type: "init"; id: number; root: string }
  | { type: "call"; id: number; fn: string; args: Record<string, unknown>; withProgress?: boolean };

export type WorkerResponse =
  | { type: "status"; message: string }
  | { type: "progress"; id: number; value: Progress }
  | { type: "result"; id: number; value: unknown }
  | { type: "error"; id: number; message: string };

export type Progress = { stage: string; done: number; total: number; design?: number; designs?: number };
