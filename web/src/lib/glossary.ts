// Plain-English explanations behind every ⓘ. Each points to the methodology section and,
// where it helps, the exact code. Keep text to two short sentences (docs/UX_FLOW.md style guide).

export type Term = { title: string; text: string; doc?: [string, string]; code?: string };

export const GLOSSARY = {
  privacy: {
    title: "Your data never leaves this browser",
    text: "Your files are read by your browser and the math runs on your computer. Nothing is uploaded, and our automated tests fail if the app ever sends your data anywhere.",
    code: "web/e2e/privacy.spec.ts",
  },
  incrementality: {
    title: "Incrementality",
    text: "Sales that happened because of the ads and wouldn't have happened otherwise. It's the only part of a vendor's results worth paying for.",
    doc: ["METHODOLOGY.md", "1-the-question-fosit-answers"],
  },
  cell: {
    title: "Cell",
    text: "A group of markets that gets one vendor's ads. FOSIT never knows who's behind a cell and treats every cell exactly the same.",
    doc: ["METHODOLOGY.md", "2-design-cells-markets-and-dates"],
  },
  control: {
    title: "Control markets",
    text: "Markets that get no test ads from anyone. They're the yardstick: each cell's 'twin' is built from them.",
    doc: ["METHODOLOGY.md", "2-design-cells-markets-and-dates"],
  },
  twin: {
    title: "Statistical twin (synthetic control)",
    text: "A weighted mix of control markets that moved just like the cell's markets before the test. During the test it shows what would have happened without the ads.",
    doc: ["METHODOLOGY.md", "4-the-estimator-augmented-synthetic-control"],
    code: "core/fosit/ascm.py",
  },
  icpa: {
    title: "iCPA (incremental cost per acquisition)",
    text: "What each extra order really cost: spend ÷ orders that wouldn't have happened without the ads. Lower is better.",
    doc: ["METHODOLOGY.md", "6-business-metrics"],
  },
  iroas: {
    title: "iROAS (incremental return on ad spend)",
    text: "Extra revenue caused by the ads ÷ spend. 2.0 means each $1 brought back $2 that wouldn't have come otherwise.",
    doc: ["METHODOLOGY.md", "6-business-metrics"],
  },
  targetIcpa: {
    title: "What would make this worth it?",
    text: "The highest iCPA (or lowest iROAS) at which you'd keep buying. It lets FOSIT tell 'no lift worth paying for' apart from 'can't tell yet'.",
    doc: ["METHODOLOGY.md", "8-verdicts"],
  },
  mde: {
    title: "Minimum detectable effect (MDE)",
    text: "The smallest lift this test catches 80% of the time. We find it by replaying your past data with fake lifts added. Smaller is better.",
    doc: ["METHODOLOGY.md", "10-power-simulation-plan"],
    code: "core/fosit/power.py",
  },
  detectableIcpa: {
    title: "Detectable iCPA",
    text: "If a vendor's true iCPA is worse (higher) than this, the test probably won't be able to see its effect. More budget or a longer test lowers the bar.",
    doc: ["METHODOLOGY.md", "102-from-mde-to-money"],
  },
  power: {
    title: "Power",
    text: "How often the test detects a lift of a given size. 80% means it catches that lift 4 times out of 5.",
    doc: ["METHODOLOGY.md", "10-power-simulation-plan"],
  },
  falsePositive: {
    title: "False-positive check",
    text: "How often this design 'found' a lift in past data where no ads ran. It should be around 10%; much higher means the design can't be trusted.",
    doc: ["METHODOLOGY.md", "101-procedure"],
  },
  fit: {
    title: "Fit error",
    text: "How far the twin was from the real markets on days it hadn't seen, as a share of sales: per day, or per week for smaller businesses, where day-to-day chance would hide a good fit. Under 10% is good.",
    doc: ["METHODOLOGY.md", "93-scoring"],
  },
  balance: {
    title: "Balance",
    text: "How similar the cells are in size, share of sales, population, trend and seasonality. A fair split keeps the 'better' vendor from just having better markets.",
    doc: ["METHODOLOGY.md", "93-scoring"],
    code: "core/fosit/selection.py",
  },
  shareInTest: {
    title: "Share of sales in test",
    text: "How much of your business is in test markets. More share means more power, but more sales exposed to the experiment.",
    doc: ["METHODOLOGY.md", "94-ranking"],
  },
  cooldown: {
    title: "Cooldown",
    text: "Days after the ads stop that we keep measuring, to catch people who saw an ad and bought a few days later.",
    doc: ["METHODOLOGY.md", "2-design-cells-markets-and-dates"],
  },
  preperiod: {
    title: "History (pre-period)",
    text: "The weeks before the test used to build each twin. Longer history gives a sharper test; 12+ weeks recommended, up to 26 is better.",
    doc: ["METHODOLOGY.md", "55-permutation-scheme-why-moving-block"],
  },
  geoUnit: {
    title: "Market unit",
    text: "Metro areas (Census CBSAs) are public and most vendors can target them. Check with each vendor before you lock the plan.",
    doc: ["METHODOLOGY.md", "31-geography"],
  },
  permutations: {
    title: "Permutation scheme",
    text: "How we judge whether a gap is bigger than chance. The default is honest about uncertainty; the alternative detects more but is over-confident when sales swing for days at a time.",
    doc: ["METHODOLOGY.md", "55-permutation-scheme-why-moving-block"],
    code: "core/fosit/conformal.py",
  },
  hash: {
    title: "Plan fingerprint",
    text: "A 64-character code computed from the plan. Change one market or one date and it changes completely, so it proves the plan wasn't altered after launch.",
    doc: ["PREREGISTRATION.md", "how-the-hash-is-computed"],
  },
  coinFlip: {
    title: "Coin flip",
    text: "Lets chance decide which vendor gets which market set, so nobody can claim the other got the better markets.",
    doc: ["METHODOLOGY.md", "95-optional-coin-flip-for-vendor-to-cell-assignment"],
  },
  pValue: {
    title: "p-value",
    text: "How often a gap this big shows up by pure chance when the ads do nothing. Under 0.10 means it's unlikely to be luck.",
    doc: ["METHODOLOGY.md", "51-testing-a-hypothesized-effect"],
    code: "core/fosit/conformal.py",
  },
  range: {
    title: "90% range",
    text: "We're 90% confident the true value is in this range. If it includes zero, we can't rule out that the ads did nothing.",
    doc: ["METHODOLOGY.md", "52-confidence-intervals-by-test-inversion"],
  },
  verdict: {
    title: "Verdict",
    text: "Positive: the whole range is above zero. No detectable lift: any lift is too small to be worth it. Inconclusive: the test can't tell either way. All three are honest answers.",
    doc: ["METHODOLOGY.md", "8-verdicts"],
    code: "core/fosit/read.py",
  },
  headToHead: {
    title: "Head-to-head",
    text: "A range for the difference between two cells, built so both cells' uncertainty counts. If it includes zero, you can't tell the vendors apart on this evidence.",
    doc: ["METHODOLOGY.md", "7-head-to-head"],
  },
  planMatch: {
    title: "Plan match",
    text: "We recompute the plan's fingerprint and compare it with the one sent before launch. If anything was changed, it won't match.",
    doc: ["PREREGISTRATION.md", "the-ritual-what-we-ask-users-to-do"],
  },
  leakage: {
    title: "Geo leakage",
    text: "Share of a cell's impressions that landed outside its own markets. Ads in control markets push measured lift toward zero.",
    doc: ["METHODOLOGY.md", "11-honesty-checks-read"],
  },
  shocks: {
    title: "Other changes",
    text: "A promotion, price change or other campaign that hit some markets differently would be mistaken for an ad effect. Only you can know, so we ask.",
    doc: ["METHODOLOGY.md", "11-honesty-checks-read"],
  },
  perThousand: {
    title: "Incremental orders per 1,000 spent",
    text: "The same information as iCPA, flipped. It stays meaningful even when a cell's lift is near zero, so it's the safest way to compare vendors.",
    doc: ["METHODOLOGY.md", "71-what-is-compared"],
  },
  placebo: {
    title: "Placebo check",
    text: "We also run the same analysis on fake cells made of markets that got no ads, over the same dates. If those fake cells show 'effects' more often than they should, we widen the real ranges until they don't.",
    doc: ["METHODOLOGY.md", "56-placebo-calibration"],
    code: "core/fosit/placebo.py",
  },
  holdout: {
    title: "National holdout",
    text: "The campaign runs everywhere except a few markets that get no ads. A twin of those markets, built from the markets with ads, shows what they'd have sold with the ads; the gap is what the ads drive.",
    doc: ["METHODOLOGY.md", "13-national-holdout"],
    code: "core/fosit/holdout.py",
  },
  adsBeforeTest: {
    title: "Why the history period matters",
    text: "The twin learns how the holdout moves with the rest of the country. That only works if the campaign was off everywhere, or on everywhere, during the history it learns from.",
    doc: ["METHODOLOGY.md", "131-when-to-use-it-and-the-one-rule"],
  },
} satisfies Record<string, Term>;

export type TermKey = keyof typeof GLOSSARY;
