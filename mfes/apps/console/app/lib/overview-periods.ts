import * as fx from './fixed-decimal';
import type { Overview } from './company-overview';

/**
 * The overview's period choices, and the arithmetic that turns the daily series into chart buckets.
 *
 * Everything here works on `YYYY-MM-DD` business-date strings through UTC calendar maths, never
 * through a local `Date`: a business date has no instant attached, so a browser west of UTC must
 * not render 1 October as 30 September (design-system §5.4). Amounts are summed as scaled
 * integers with `fixed-decimal`, never as JS numbers.
 */

export const PERIOD_KEYS = ['ytd', 'quarter', 'month', '30d'] as const;
export type PeriodKey = (typeof PERIOD_KEYS)[number];
export const DEFAULT_PERIOD: PeriodKey = 'ytd';

export const PERIOD_LABELS: Record<PeriodKey, string> = {
  ytd: 'Year to date',
  quarter: 'This quarter',
  month: 'This month',
  '30d': 'Last 30 days',
};

/** Anything that is not an allow-listed key — a hand-edited URL included — is the default. */
export function parsePeriod(value: unknown): PeriodKey {
  return typeof value === 'string' && (PERIOD_KEYS as readonly string[]).includes(value)
    ? (value as PeriodKey)
    : DEFAULT_PERIOD;
}

/**
 * What every response of one company and year agrees on: where the year starts, the earliest
 * covered day, and the company's own "today" (the default range ends there). Presets are computed
 * from this — never from the browser clock, which can be on another day than the company.
 */
export type Anchor = { yearStart: string; floor: string; today: string };

export function anchorOf(
  value: Pick<Overview, 'year_start' | 'coverage_start' | 'date_to'>,
): Anchor {
  return {
    yearStart: value.year_start,
    floor: value.coverage_start > value.year_start ? value.coverage_start : value.year_start,
    today: value.date_to,
  };
}

const DAY = 86_400_000;
const toMs = (iso: string): number => {
  const [year, month, day] = iso.split('-').map(Number) as [number, number, number];
  return Date.UTC(year, month - 1, day);
};
const toIso = (ms: number): string => new Date(ms).toISOString().slice(0, 10);

export function addDays(iso: string, days: number): string {
  return toIso(toMs(iso) + days * DAY);
}

/** The same day of a later month, or that month's last day when it has no such day (31 Aug + 3 months is 30 Nov). */
function addMonths(iso: string, months: number): string {
  const [year, month, day] = iso.split('-').map(Number) as [number, number, number];
  const index = year * 12 + (month - 1) + months;
  const target = [Math.floor(index / 12), index % 12] as const;
  const lastDay = new Date(Date.UTC(target[0], target[1] + 1, 0)).getUTCDate();
  return toIso(Date.UTC(target[0], target[1], Math.min(day, lastDay)));
}

const later = (a: string, b: string): string => (a > b ? a : b);

export type PeriodRange = { from: string; to: string; clamped: boolean };

export function periodRange(key: PeriodKey, anchor: Anchor): PeriodRange {
  const { yearStart, floor, today } = anchor;
  let wanted: string;
  if (key === 'ytd') wanted = yearStart;
  else if (key === 'month') wanted = today.slice(0, 8) + '01';
  else if (key === '30d') wanted = addDays(today, -29);
  else {
    // Fiscal quarters count from the company's own year start — its month *and* its day, not
    // January and not the 1st: the latest quarter start that is not after today.
    wanted = yearStart;
    for (let quarter = 1; quarter < 4; quarter += 1) {
      const start = addMonths(yearStart, quarter * 3);
      if (start <= today) wanted = start;
    }
  }
  // A year start after today (a year generated but not yet begun) leaves nothing to preset.
  const from = later(wanted, floor);
  return { from: from > today ? today : from, to: today, clamped: wanted < floor };
}

export type Grain = 'day' | 'week' | 'month';

export function grainFor(days: number): Grain {
  return days <= 31 ? 'day' : days <= 120 ? 'week' : 'month';
}

export const GRAIN_NOUN: Record<Grain, string> = { day: 'day', week: 'week', month: 'month' };

export type Bucket = { from: string; income: string; expenses: string; net: string };

function bucketKey(date: string, grain: Grain): string {
  if (grain === 'day') return date;
  if (grain === 'month') return date.slice(0, 7);
  // ISO weeks start on Monday; the key is that Monday.
  const weekday = (new Date(toMs(date)).getUTCDay() + 6) % 7;
  return addDays(date, -weekday);
}

/**
 * Sums the daily posted series into chart buckets. A bucket is labelled by the first covered day
 * it contains, so a partial first week starts on the period's own first date. Zero days are kept:
 * a quiet week is a fact, and dropping it would stretch the time axis.
 */
export function bucketSeries(series: Overview['series']): { grain: Grain; buckets: Bucket[] } {
  const grain = grainFor(series.length);
  const order: string[] = [];
  const sums = new Map<string, { from: string; income: fx.Fixed; expenses: fx.Fixed }>();
  for (const row of series) {
    const key = bucketKey(row.date, grain);
    let bucket = sums.get(key);
    if (!bucket) {
      bucket = { from: row.date, income: fx.ZERO, expenses: fx.ZERO };
      sums.set(key, bucket);
      order.push(key);
    }
    bucket.income += fx.parse(row.income) ?? fx.ZERO;
    bucket.expenses += fx.parse(row.expenses) ?? fx.ZERO;
  }
  return {
    grain,
    buckets: order.map((key) => {
      const { from, income, expenses } = sums.get(key)!;
      return { from, income: fx.format(income), expenses: fx.format(expenses), net: fx.format(income - expenses) };
    }),
  };
}

/** Running net result, one value per bucket, ending at the period's net result. */
export function cumulativeNet(buckets: readonly Bucket[]): string[] {
  let running = fx.ZERO;
  return buckets.map((bucket) => {
    running += fx.parse(bucket.net) ?? fx.ZERO;
    return fx.format(running);
  });
}

/** `a + b` for two decimal strings; an unparseable input counts as no amount, never as zero. */
export function sumMoney(a: string, b: string): string | null {
  const left = fx.parse(a);
  const right = fx.parse(b);
  return left === null || right === null ? null : fx.format(left + right);
}

export function signOf(value: string): -1 | 0 | 1 {
  const parsed = fx.parse(value);
  return parsed === null ? 0 : parsed < 0n ? -1 : parsed > 0n ? 1 : 0;
}

/** The page's second line: which company and financial year the figures belong to. */
export function overviewLede(companyName?: string, yearLabel?: string): string {
  return [companyName, yearLabel].filter(Boolean).join(' · ') || 'Balances and posted activity from the latest verified source.';
}
