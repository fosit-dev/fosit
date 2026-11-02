// RFC 8785 JSON Canonicalization Scheme (JCS).
// In JavaScript the RFC's rules coincide with JSON.stringify for strings and numbers
// (ECMAScript Number serialization), so canonicalization reduces to sorting object keys
// by UTF-16 code units (the default Array.prototype.sort order) and removing whitespace.

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export function canonicalize(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("JCS: non-finite numbers cannot be canonicalized");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(",")}]`;
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).filter((k) => obj[k] !== undefined).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalize(obj[k])}`).join(",")}}`;
  }
  throw new Error(`JCS: unsupported type ${typeof value}`);
}
