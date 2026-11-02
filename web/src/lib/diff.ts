// Field-by-field differences between two plans, for the "plan match" check (PREREGISTRATION.md step 5).

export type Change = { path: string; before: string; after: string };

const show = (v: unknown) => (v === undefined ? "(missing)" : typeof v === "string" ? v : JSON.stringify(v));

export function diffPlans(before: unknown, after: unknown, path = "commitment", out: Change[] = []): Change[] {
  if (out.length >= 50) return out;
  if (Array.isArray(before) && Array.isArray(after) && [...before, ...after].every((x) => typeof x === "string")) {
    const removed = (before as string[]).filter((x) => !(after as string[]).includes(x));
    const added = (after as string[]).filter((x) => !(before as string[]).includes(x));
    if (removed.length || added.length)
      out.push({ path, before: removed.length ? `removed ${removed.join(", ")}` : "", after: added.length ? `added ${added.join(", ")}` : "" });
    return out;
  }
  if (before && after && typeof before === "object" && typeof after === "object") {
    const keys = new Set([...Object.keys(before as object), ...Object.keys(after as object)]);
    for (const k of [...keys].sort())
      diffPlans((before as Record<string, unknown>)[k], (after as Record<string, unknown>)[k], Array.isArray(before) ? `${path}[${k}]` : `${path}.${k}`, out);
    return out;
  }
  if (JSON.stringify(before) !== JSON.stringify(after)) out.push({ path, before: show(before), after: show(after) });
  return out;
}
