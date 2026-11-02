// Calendar-date helpers on YYYY-MM-DD strings, in UTC so time zones never shift a day.

export const toDate = (s: string) => new Date(`${s}T00:00:00Z`);
export const fmt = (d: Date) => d.toISOString().slice(0, 10);
export const addDays = (s: string, n: number) => fmt(new Date(toDate(s).getTime() + n * 86_400_000));
export const daysBetween = (a: string, b: string) => Math.round((toDate(b).getTime() - toDate(a).getTime()) / 86_400_000);
export const todayUtc = () => fmt(new Date());

/** The first Monday at least `minDays` after `from`. */
export function nextMonday(from: string, minDays: number): string {
  let d = addDays(from, minDays);
  while (toDate(d).getUTCDay() !== 1) d = addDays(d, 1);
  return d;
}

export const pretty = (s: string) =>
  toDate(s).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
