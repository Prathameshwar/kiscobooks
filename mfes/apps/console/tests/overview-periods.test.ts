import { describe, expect, it } from 'vitest';
import {
  addDays, anchorOf, bucketSeries, cumulativeNet, grainFor, overviewLede, parsePeriod, periodRange, signOf, sumMoney, type Anchor,
} from '../app/lib/overview-periods';

const april: Anchor = { yearStart: '2026-04-01', floor: '2026-04-01', today: '2026-11-01' };

const series = (rows: [string, string, string][]) => rows.map(([date, income, expenses]) => ({ date, income, expenses }));

describe('parsePeriod', () => {
  it.each(['ytd', 'quarter', 'month', '30d'])('accepts %s', key => expect(parsePeriod(key)).toBe(key));
  it.each([undefined, null, '', 'YTD', 'year', '<script>', ['month'], 7])('falls back to year to date for %j', value => {
    expect(parsePeriod(value)).toBe('ytd');
  });
});

describe('anchorOf', () => {
  it('floors the range at whichever of year start and retained coverage is later', () => {
    const base = { year_start: '2026-04-01', date_to: '2026-11-01' };
    expect(anchorOf({ ...base, coverage_start: '2026-10-01' }).floor).toBe('2026-10-01');
    expect(anchorOf({ ...base, coverage_start: '2026-01-01' }).floor).toBe('2026-04-01');
    expect(anchorOf({ ...base, coverage_start: '2026-10-01' }).today).toBe('2026-11-01');
  });
});

describe('periodRange', () => {
  it('runs year to date from the year start to the company’s today', () => {
    expect(periodRange('ytd', april)).toEqual({ from: '2026-04-01', to: '2026-11-01', clamped: false });
  });

  it('clamps to retained coverage and says it did', () => {
    const covered = { ...april, floor: '2026-10-15' };
    expect(periodRange('ytd', covered)).toEqual({ from: '2026-10-15', to: '2026-11-01', clamped: true });
    expect(periodRange('month', covered)).toEqual({ from: '2026-11-01', to: '2026-11-01', clamped: false });
    expect(periodRange('quarter', covered)).toEqual({ from: '2026-10-15', to: '2026-11-01', clamped: true });
  });

  it('counts fiscal quarters from the company’s own year start, not from January', () => {
    expect(periodRange('quarter', { ...april, today: '2026-06-30' }).from).toBe('2026-04-01');
    expect(periodRange('quarter', { ...april, today: '2026-07-01' }).from).toBe('2026-07-01');
    expect(periodRange('quarter', { ...april, today: '2026-11-01' }).from).toBe('2026-10-01');
    expect(periodRange('quarter', { ...april, today: '2027-01-15' }).from).toBe('2027-01-01');
    const calendar: Anchor = { yearStart: '2026-01-01', floor: '2026-01-01', today: '2026-02-15' };
    expect(periodRange('quarter', calendar).from).toBe('2026-01-01');
  });

  it('honours a fiscal year that starts on a day other than the 1st', () => {
    const march26: Anchor = { yearStart: '2026-03-26', floor: '2026-03-26', today: '2026-06-10' };
    // the second quarter only begins on 26 June, so 10 June is still in the first
    expect(periodRange('quarter', march26)).toEqual({ from: '2026-03-26', to: '2026-06-10', clamped: false });
    expect(periodRange('quarter', { ...march26, today: '2026-06-26' }).from).toBe('2026-06-26');
    expect(periodRange('quarter', { ...march26, today: '2026-12-25' }).from).toBe('2026-09-26');
    expect(periodRange('quarter', { ...march26, today: '2026-12-26' }).from).toBe('2026-12-26');
  });

  it('clamps a quarter start to the last day of a shorter month rather than overflowing into the next', () => {
    const may31: Anchor = { yearStart: '2026-05-31', floor: '2026-05-31', today: '2026-09-01' };
    expect(periodRange('quarter', may31).from).toBe('2026-08-31');
    // 31 May + 6 months has no 31st: the quarter starts on 30 November, not 1 December
    expect(periodRange('quarter', { ...may31, today: '2026-11-29' }).from).toBe('2026-08-31');
    expect(periodRange('quarter', { ...may31, today: '2026-11-30' }).from).toBe('2026-11-30');
  });

  it('takes the current calendar month and the last thirty days inclusive of today', () => {
    expect(periodRange('month', { ...april, today: '2026-10-17' }).from).toBe('2026-10-01');
    expect(periodRange('30d', april)).toEqual({ from: '2026-10-03', to: '2026-11-01', clamped: false });
    expect(periodRange('30d', { ...april, today: '2026-04-10' })).toEqual({ from: '2026-04-01', to: '2026-04-10', clamped: true });
  });

  it('never starts after today', () => {
    expect(periodRange('ytd', { yearStart: '2026-04-01', floor: '2026-12-01', today: '2026-11-01' }).from).toBe('2026-11-01');
  });
});

describe('addDays', () => {
  it('crosses month ends and leap days through UTC calendar maths', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
    expect(addDays('2028-02-28', 1)).toBe('2028-02-29');
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
    expect(addDays('2026-01-01', -29)).toBe('2025-12-03');
  });
});

describe('grainFor', () => {
  it.each([[1, 'day'], [31, 'day'], [32, 'week'], [120, 'week'], [121, 'month'], [366, 'month']] as const)('%i days is %s', (days, grain) => {
    expect(grainFor(days)).toBe(grain);
  });
});

describe('bucketSeries', () => {
  it('keeps one bucket per day for a short range, zero days included', () => {
    const { grain, buckets } = bucketSeries(series([['2026-10-01', '10.0000', '0.0000'], ['2026-10-02', '0.0000', '0.0000'], ['2026-10-03', '0.0000', '4.0000']]));
    expect(grain).toBe('day');
    expect(buckets.map(bucket => [bucket.from, bucket.income, bucket.expenses, bucket.net])).toEqual([
      ['2026-10-01', '10.0000', '0.0000', '10.0000'],
      ['2026-10-02', '0.0000', '0.0000', '0.0000'],
      ['2026-10-03', '0.0000', '4.0000', '-4.0000'],
    ]);
  });

  it('groups a mid-length range by Monday-start week, labelled by its first covered day', () => {
    const start = '2026-10-01'; // a Thursday
    const days = Array.from({ length: 40 }, (_, index): [string, string, string] => [addDays(start, index), '1.0000', '0.5000']);
    const { grain, buckets } = bucketSeries(series(days));
    expect(grain).toBe('week');
    // the first bucket is the partial week Thursday to Sunday: four days
    expect(buckets[0]).toEqual({ from: '2026-10-01', income: '4.0000', expenses: '2.0000', net: '2.0000' });
    expect(buckets[1]).toEqual({ from: '2026-10-05', income: '7.0000', expenses: '3.5000', net: '3.5000' });
  });

  it('groups a long range by calendar month', () => {
    const days = Array.from({ length: 130 }, (_, index): [string, string, string] => [addDays('2026-04-01', index), '2.0000', '1.0000']);
    const { grain, buckets } = bucketSeries(series(days));
    expect(grain).toBe('month');
    expect(buckets.map(bucket => bucket.from)).toEqual(['2026-04-01', '2026-05-01', '2026-06-01', '2026-07-01', '2026-08-01']);
    expect(buckets[0]).toMatchObject({ income: '60.0000', expenses: '30.0000' });
  });

  it('adds decimals exactly rather than through floats', () => {
    const { buckets } = bucketSeries(series([['2026-10-01', '0.1000', '0.2000'], ['2026-10-02', '0.2000', '0.1000']]));
    expect(buckets.map(bucket => bucket.income)).toEqual(['0.1000', '0.2000']);
    const merged = bucketSeries(series(Array.from({ length: 40 }, (_, index): [string, string, string] => [addDays('2026-10-05', index), '0.1000', '0.2000']))).buckets;
    expect(merged[0]).toMatchObject({ income: '0.7000', expenses: '1.4000', net: '-0.7000' });
  });

  it('preserves the series total across every grain', () => {
    const rows = Array.from({ length: 200 }, (_, index): [string, string, string] => [addDays('2026-04-01', index), (index % 7).toFixed(4), (index % 3).toFixed(4)]);
    const total = rows.reduce((sum, row) => sum + Number(row[1]), 0);
    const { buckets } = bucketSeries(series(rows));
    expect(buckets.reduce((sum, bucket) => sum + Number(bucket.income), 0)).toBe(total);
  });
});

describe('cumulativeNet', () => {
  it('runs the net result forward and ends at the period’s net', () => {
    const { buckets } = bucketSeries(series([['2026-10-01', '10.0000', '0.0000'], ['2026-10-02', '0.0000', '4.0000'], ['2026-10-03', '1.5000', '0.0000']]));
    expect(cumulativeNet(buckets)).toEqual(['10.0000', '6.0000', '7.5000']);
  });
});

describe('money helpers', () => {
  it('sums two decimal strings exactly, and reports an unparseable one as no figure', () => {
    expect(sumMoney('0.1000', '0.2000')).toBe('0.3000');
    expect(sumMoney('-5.0000', '2.5000')).toBe('-2.5000');
    expect(sumMoney('n/a', '1.0000')).toBeNull();
  });

  it('reads a sign without a float', () => {
    expect(signOf('-0.0001')).toBe(-1);
    expect(signOf('0.0000')).toBe(0);
    expect(signOf('12.0000')).toBe(1);
    expect(signOf('x')).toBe(0);
  });
});

describe('overviewLede', () => {
  it('names the company and year, whichever are known, with a plain fallback', () => {
    expect(overviewLede('Janso Retail', 'FY 2026-27')).toBe('Janso Retail · FY 2026-27');
    expect(overviewLede('Janso Retail')).toBe('Janso Retail');
    expect(overviewLede(undefined, 'FY 2026-27')).toBe('FY 2026-27');
    expect(overviewLede()).toMatch(/verified source/);
  });
});
