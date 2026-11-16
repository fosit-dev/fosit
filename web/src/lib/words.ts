// The plain words of the Plan screens: what each test type is called, how it works step by step, and the pictures.
// Style: ASD-STE100 (docs/UX_FLOW.md): one idea per sentence, at most 25 words, one word for one meaning
// (extra sales, twin, range, held-out markets). The technical name of an idea shows only at the Full level,
// or inside the ⓘ of the thing the person selected. tests/words.test.ts checks the sentence lengths.
import type { Level } from "./level";
import type { Template } from "../plan/state";

/** What the person wants to find out. It decides which test types are offered. */
export type Goal = "compare" | "one";

export const GOALS: { id: Goal; title: string; text: string; first: Template }[] = [
  { id: "compare", title: "Which vendor brings more extra sales?", text: "Two or more vendors. FOSIT gives each vendor a fair group of markets and compares them.", first: "two_vendor" },
  { id: "one", title: "Do my ads bring extra sales?", text: "One campaign or one channel. FOSIT measures the sales that it adds.", first: "single" },
];

export type DesignInfo = { id: Template; goal: Goal; cells: number; title: string; text: string; good: string; technical: string; recommended?: boolean };

export const DESIGNS: DesignInfo[] = [
  { id: "two_vendor", goal: "compare", cells: 2, recommended: true, title: "Each vendor in a few markets",
    text: "Each vendor gets its own small group of markets. Most of the country gets no test ads.",
    good: "Good for a first test. It needs the smallest budget.", technical: "Geo test, one cell per vendor" },
  { id: "vendor_split", goal: "compare", cells: 2, title: "Vendors split the country",
    text: "Each vendor runs in its own part of the country, for example 40% each. A small part gets no CTV, for example 20%.",
    good: "Good when each vendor must run at full size.", technical: "Vendor split with a no-CTV holdout" },
  { id: "custom", goal: "compare", cells: 3, title: "More vendors, or my own settings",
    text: "Up to 6 groups of markets. You choose the number of groups.",
    good: "Good for three or more vendors.", technical: "Custom geo cells" },
  { id: "single", goal: "one", cells: 1, title: "Ads in a few markets",
    text: "The ads run in a small group of markets. Most of the country gets no test ads.",
    good: "Good for a new channel and a small test budget.", technical: "Geo test, one cell" },
  { id: "national_holdout", goal: "one", cells: 1, title: "Ads everywhere, except a small part",
    text: "The campaign runs in most of the country. About a tenth of the country gets no ads.",
    good: "Good for a campaign that runs in the whole country.", technical: "National holdout" },
  { id: "crossover", goal: "one", cells: 1, title: "Two halves take turns",
    text: "Two halves of the country take turns with the ads every few weeks. A random draw sets the order before the test.",
    good: "Good for a small business: a few hundred orders a day or less.", technical: "Geo crossover" },
];

export const designInfo = (t: Template) => DESIGNS.find((d) => d.id === t)!;
export const goalOf = (t: Template): Goal => designInfo(t).goal;

/** The name a group of markets gets before the person types one. Never a real vendor's name (docs/UX_FLOW.md, principle 5). */
export const defaultLabel = (t: Template, i: number) => (goalOf(t) === "one" ? "Campaign" : `Vendor ${"ABCDEF"[i] ?? i + 1}`);
export const isDefaultLabel = (l: string) => /^(Cell \d+|Vendor [A-F]|Campaign)$/.test(l.trim());

/** Plain words at Brief and Guided, the technical name at Full. */
export const tech = (level: Level, plain: string, technical: string) => (level === "full" ? technical : plain);

/** What the Plan screens show at each level (the same switch as the reports: lib/level.tsx). */
export const PLAN_LEVELS: Record<Level, string> = {
  brief: "The fewest questions. FOSIT chooses the rest.",
  guided: "Each step explained, with pictures.",
  full: "Every setting, with the technical names.",
};

// ------------------------------------------------------------------ pictures

/** One part of the country in a picture: who has the ads there, and about how much of the sales it holds. */
export type Segment = { label: string; share: number; role: "ads" | "none" | "half"; n?: number };

/** Example sizes for the picture of a test type, before FOSIT has seen any sales. */
export function exampleSegments(t: Template, labels: string[]): Segment[] {
  const name = (i: number) => labels[i]?.trim() || defaultLabel(t, i);
  if (t === "crossover") return [{ label: "Half A", share: 0.5, role: "half" }, { label: "Half B", share: 0.5, role: "half" }];
  if (t === "national_holdout") return [{ label: `${name(0)}: ads`, share: 0.85, role: "ads" }, { label: "No ads", share: 0.15, role: "none" }];
  const n = labels.length || designInfo(t).cells;
  if (t === "vendor_split") return [...Array.from({ length: n }, (_, i): Segment => ({ label: name(i), share: 0.8 / n, role: "ads" })), { label: "No CTV", share: 0.2, role: "none" }];
  const each = n <= 2 ? 0.1 : 0.08;
  return [...Array.from({ length: n }, (_, i): Segment => ({ label: name(i), share: each, role: "ads" })), { label: "No test ads", share: 1 - n * each, role: "none" }];
}

// ------------------------------------------------------------------ how each test works

export type IconKind = "map" | "tv" | "twin" | "compare" | "gap" | "swap" | "clock" | "scale" | "halves";
/** One numbered step: a title, one sentence, and a little more for the person who opens it. */
export type AnatomyStep = { icon: IconKind; t: string; x: string; m: string };

const RANGE = "Each number comes with a range. If the range includes zero, the test cannot tell.";

/** The five steps of a test type, in the present tense (the plan is not locked yet). The reports tell the same
 * story in the past tense (core/fosit/templates/page.html). */
export function anatomySteps(t: Template, nCells: number, lingering: "short" | "long" = "short"): AnatomyStep[] {
  if (t === "crossover") {
    const long = lingering === "long";
    return [
      { icon: "halves", t: "Two halves", x: "FOSIT splits the country into two halves with almost the same sales.", m: "Each market gets the ads for half of the test. So each market is in the test and in the comparison." },
      { icon: "swap", t: "Take turns", x: `Every ${long ? 4 : 2} weeks, the ads move to the other half.`, m: "A fair random draw sets the order when you lock the plan. Each half has the ads in the same number of blocks." },
      { icon: "clock", t: "Skip the fade", x: `FOSIT skips the first ${long ? 5 : 3} days of each block.`, m: "Ads from the last block still work on these days. An effect that lasts much longer makes the result too low." },
      { icon: "compare", t: "Compare halves", x: "In each block, FOSIT compares the half with ads to the half without ads.", m: "Both halves have the same season, weather and news at the same time. So the gap shows what the ads do." },
      { icon: "scale", t: "Average and test", x: "FOSIT averages the gap over all blocks.", m: "A test against every other fair order gives the range. Chance alone seldom gives a large gap in every block." },
    ];
  }
  if (t === "national_holdout" || t === "vendor_split") {
    const split = t === "vendor_split";
    return [
      { icon: "map", t: split ? "Split the country" : "Hold out markets", x: split ? "The vendors split the markets. A small part of the country gets no CTV." : "A small part of the country gets no ads. The campaign runs everywhere else.",
        m: "FOSIT picks the held-out markets at random. It checks that they are like the rest of the country." },
      { icon: "tv", t: "Run the ads", x: split ? "Each vendor runs ads only in its own markets. The held-out markets stay dark." : "The ads run. The held-out markets stay dark.",
        m: "The held-out markets stay dark until the cooldown ends. Then late effects cannot leak in." },
      { icon: "twin", t: split ? "A twin per vendor" : "Build a twin", x: split ? "For each vendor, FOSIT builds a twin of the held-out markets from that vendor's markets." : "FOSIT mixes markets with ads into a twin of the held-out markets.",
        m: "Before the test, the twin's sales move like the held-out markets. FOSIT compares each market to its own normal level." },
      { icon: "compare", t: "Compare", x: "The twin shows the held-out markets with the ads. Their real sales show them without the ads.", m: "The gap between the two lines is the share of sales that the ads drive." },
      { icon: "gap", t: split ? "Compare vendors" : "Scale up", x: split ? "Each vendor's share gives its extra sales. Then FOSIT compares the vendors." : "FOSIT applies that share to the markets with ads. This gives the extra sales.", m: RANGE },
    ];
  }
  const many = nCells > 1;
  return [
    { icon: "map", t: "Split the markets", x: many ? "FOSIT gives each vendor its own group of markets. The other markets get no test ads." : "FOSIT picks a small group of markets for the ads. The other markets get no test ads.",
      m: "FOSIT tries thousands of random splits. It keeps the splits where the groups are alike in sales, trend and size." },
    { icon: "tv", t: "Run the ads", x: many ? "Each vendor runs ads only in its own markets." : "The ads run only in the test markets.",
      m: "The other markets get no test ads. Your other marketing continues the same in all markets." },
    { icon: "twin", t: "Build a twin", x: many ? "For each vendor, FOSIT mixes markets with no test ads into a twin." : "FOSIT mixes markets with no test ads into a twin of the test markets.",
      m: "Before the test, the twin's sales move like the test markets. FOSIT fixes the mix before the test starts." },
    { icon: "compare", t: "Compare", x: "During the test, FOSIT compares the real sales with the twin.", m: "The twin shows the sales without the ads. Season, weather and news change both lines in the same way." },
    { icon: "gap", t: "Count the gap", x: "The gap is the extra sales that the ads caused.", m: RANGE },
  ];
}

// ------------------------------------------------------------------ numbers for the sliders

/** A round number near x, for a slider's start. */
export function nice(x: number): number {
  if (!Number.isFinite(x) || x <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(x));
  const m = x / p;
  return (m < 1.5 ? 1 : m < 2.25 ? 2 : m < 3.5 ? 2.5 : m < 7.5 ? 5 : 10) * p;
}
/** Two significant digits, so a slider shows $84 and not $83.71. */
export function snap(v: number): number {
  if (!Number.isFinite(v) || v <= 0) return v;
  const step = 10 ** (Math.floor(Math.log10(v)) - 1);
  return Math.round(v / step) * step;
}

/** How to say a chance in plain words, for the person who does not read percentages for a living. */
export function chanceWords(p: number): { tone: "ok" | "warn" | "err"; text: string } {
  const n = Math.round(p * 100);
  if (p >= 0.8) return { tone: "ok", text: `The test sees it ${n}% of the time. Good.` };
  if (p >= 0.5) return { tone: "warn", text: `The test sees it ${n}% of the time. It can miss it.` };
  if (p >= 0.05) return { tone: "err", text: `The test sees it only ${n}% of the time. It will probably miss it.` };
  return { tone: "err", text: "The test will not see an effect this small." };
}
