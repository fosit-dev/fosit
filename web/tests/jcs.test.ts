import { describe, expect, it } from "vitest";
import { canonicalize } from "../src/lib/jcs";

const ch = (...codes: number[]) => String.fromCharCode(...codes);
const BS = ch(0x5c); // backslash
const QT = ch(0x22); // double quote

// Test vectors from RFC 8785 itself (sections 3.2.2 and 3.2.3). Characters are built from code
// points so no editor or tool can silently change an escape sequence.
describe("RFC 8785 canonicalization", () => {
  it("matches the RFC's serialization example", () => {
    // "€$\u000F\u000aA'B"\\\\"\/" from the RFC, as code points:
    const value = ch(0x20ac) + "$" + ch(0x0f) + ch(0x0a) + "A'" + ch(0x42) + QT + BS + BS + QT + "/";
    const input = { numbers: [333333333.33333329, 1e30, 4.5, 2e-3, 0.000000000000000000000000001], string: value, literals: [null, true, false] };
    const expectedString = QT + ch(0x20ac) + "$" + BS + "u000f" + BS + "n" + "A'B" + BS + QT + BS + BS + BS + BS + BS + QT + "/" + QT;
    const expected = '{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],"string":' + expectedString + "}";
    expect(canonicalize(input)).toBe(expected);
  });

  it("sorts keys by UTF-16 code units like the RFC's sorting example", () => {
    const keys = [ch(0x20ac), ch(0x0d), ch(0xfb33), "1", ch(0xd83d, 0xde00), ch(0x80), ch(0xf6)];
    const out = canonicalize(Object.fromEntries(keys.map((k, i) => [k, i])));
    const expectedOrder = [ch(0x0d), "1", ch(0x80), ch(0xf6), ch(0x20ac), ch(0xd83d, 0xde00), ch(0xfb33)];
    const positions = expectedOrder.map((k) => out.indexOf(JSON.stringify(k) + ":"));
    expect(positions.every((p) => p >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it("drops undefined members and refuses non-finite numbers", () => {
    expect(canonicalize({ b: 1, a: undefined })).toBe('{"b":1}');
    expect(() => canonicalize({ x: Infinity })).toThrow();
  });
});
