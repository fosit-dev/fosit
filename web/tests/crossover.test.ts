import { describe, expect, it } from "vitest";
import { fadeHalfLife, fadeSentence } from "../src/lib/plan";
import { crossoverSetup, sizableCrossoverDurations } from "../src/plan/state";

// METHODOLOGY §14.4–14.5: the crossover's planning half-life and the test lengths a history can size.
describe("crossover test lengths", () => {
  it("offers only lengths the history can replay", () => {
    expect(sizableCrossoverDurations("long", 182)).toEqual({ durations: [168], dropped: [224] });   // 26 weeks: 24-week test only
    expect(sizableCrossoverDurations("long", 230)).toEqual({ durations: [168, 224], dropped: [] });
    expect(sizableCrossoverDurations("short", 182)).toEqual({ durations: [112, 168], dropped: [] });
  });
  it("keeps the shortest when nothing fits, so the planner can say why", () => {
    expect(sizableCrossoverDurations("short", 60)).toEqual({ durations: [112], dropped: [168] });
  });
  it("offers everything before a sales file is loaded", () => {
    expect(sizableCrossoverDurations("long", undefined).durations).toEqual(crossoverSetup("long").durations);
  });
});

describe("crossover fade assumption", () => {
  const design = (block_days: number, planning_half_life?: number) =>
    ({ design: { type: "crossover", block_days, washout_days: 3, schedule: "AB", planning_half_life } }) as Parameters<typeof fadeHalfLife>[0];
  it("uses the half-life the plan locked", () => {
    expect(fadeHalfLife(design(14, 3))).toBe(3);
    expect(fadeHalfLife(design(28, 7))).toBe(7);
  });
  it("falls back to the app's value for older plans, and is null for other designs", () => {
    expect(fadeHalfLife(design(28))).toBe(7);
    expect(fadeHalfLife({ design: { type: "national_holdout", ads_before_test: "off" } } as Parameters<typeof fadeHalfLife>[0])).toBeNull();
  });
  it("says what the assumption means in short sentences", () => {
    const s = fadeSentence(3);
    expect(s).toContain("about 3 days");
    for (const sentence of s.split(/(?<=\.)\s+/)) expect(sentence.split(/\s+/).length).toBeLessThanOrEqual(25);
  });
});
