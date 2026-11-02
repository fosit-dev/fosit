export const pct = (x: number | null | undefined, digits = 1) =>
  x == null || !Number.isFinite(x) ? "–" : `${(x * 100).toFixed(digits)}%`;

export const num = (x: number | null | undefined, digits = 0) =>
  x == null || !Number.isFinite(x) ? "–" : x.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });

export function money(x: number | null | undefined, currency = "USD", digits = 0) {
  if (x == null || !Number.isFinite(x)) return "–";
  try {
    return x.toLocaleString("en-US", { style: "currency", currency, maximumFractionDigits: digits, minimumFractionDigits: digits });
  } catch {
    return `${currency} ${num(x, digits)}`;
  }
}

export const weeks = (days: number) => (days % 7 === 0 ? `${days / 7} weeks` : `${days} days`);
