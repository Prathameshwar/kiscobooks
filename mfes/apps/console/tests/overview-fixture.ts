import type { Overview } from '../app/lib/company-overview';

/**
 * A verified-looking company overview for tests and design review. It lives under `tests/` on
 * purpose: the application never carries sample figures, and nothing in `app/` may import this.
 * Every breakdown reconciles to its totals, exactly as a real response must.
 */
const day = 86_400_000;
const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10);
export const fixed = (cents: number) => (cents / 100).toFixed(4);
const id = (n: number) => `0123456${n}-89ab-4cde-8fab-0123456789ab`;

export type Daily = (date: string, index: number) => { income: number; expenses: number };
export type FixtureOptions = {
  company: string;
  from?: string;
  to?: string;
  /** No postings and no balances: a verified empty source. */
  quiet?: boolean;
  /** Cents of income and expenses per day; the default is a few round postings. */
  daily?: Daily;
  /** Multiplies every opening balance and open bill, for design review at realistic size. */
  scale?: number;
  change?: Partial<Overview>;
};

const SPARSE: Record<string, { income: number; expenses: number }> = {
  '2026-10-05': { income: 100_000, expenses: 0 },
  '2026-10-06': { income: 0, expenses: 40_000 },
  '2026-10-12': { income: 200_000, expenses: 0 },
  '2026-10-13': { income: 0, expenses: 100_000 },
};
export const sparse: Daily = date => SPARSE[date] ?? { income: 0, expenses: 0 };

export function overviewFixture({ company, from = '2026-10-01', to = '2026-11-01', quiet = false, daily = sparse, scale = 1, change = {} }: FixtureOptions): Overview {
  const days = (Date.parse(to) - Date.parse(from)) / day + 1;
  const rows = Array.from({ length: days }, (_, index) => {
    const date = iso(Date.parse(from) + index * day);
    return { date, ...(quiet ? { income: 0, expenses: 0 } : daily(date, index)) };
  });
  const income = rows.reduce((sum, row) => sum + row.income, 0);
  const expenses = rows.reduce((sum, row) => sum + row.expenses, 0);
  const cash = quiet ? 0 : 400_000 * scale, bank = quiet ? 0 : 100_000 * scale;
  // Closing balance per day: today's total, walked backwards through each day's net movement.
  let closing = cash + bank;
  const position = rows.map(() => ({ date: '', cash_and_bank: '' }));
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    position[index] = { date: rows[index]!.date, cash_and_bank: fixed(closing) };
    closing -= rows[index]!.income - rows[index]!.expenses;
  }
  const scaled = (cents: number) => quiet ? 0 : cents * scale;
  const items = (current: number, d30: number, d60: number, d90: number, over: number, unknown: number, advances: number, parties: [string, number, number][]) => {
    const buckets = [current, d30, d60, d90, over, unknown].map(scaled);
    const gross = buckets.reduce((sum, value) => sum + value, 0);
    return {
      gross: fixed(gross), advances: fixed(scaled(advances)), net: fixed(gross - scaled(advances)),
      overdue: fixed(buckets.slice(1, 5).reduce((sum, value) => sum + value, 0)),
      buckets: { current: fixed(buckets[0]!), days_1_30: fixed(buckets[1]!), days_31_60: fixed(buckets[2]!), days_61_90: fixed(buckets[3]!), days_over_90: fixed(buckets[4]!), unknown: fixed(buckets[5]!) },
      parties: quiet ? [] : parties.map(([name, outstanding, overdue], index) => ({ party_id: id(index + 1), name, outstanding: fixed(outstanding * scale), overdue: fixed(overdue * scale) })),
    };
  };
  const receivables = items(150_000, 100_000, 60_000, 40_000, 0, 0, 50_000, [['Meridian Wholesale', 200_000, 140_000], ['Northline Traders', 100_000, 60_000]]);
  const payables = items(40_000, 30_000, 0, 0, 0, 0, 20_000, [['Sunridge Packaging', 50_000, 30_000]]);
  const shares: [string, number][] = [['Rent', 0.3], ['Salaries', 0.22], ['Electricity', 0.12], ['Freight', 0.08], ['Packaging', 0.05]];
  const top = quiet || expenses === 0 ? [] : shares.map(([name, share], index) => ({ account_id: id(index + 1), name, amount: Math.floor(expenses * share) }));
  const other = expenses - top.reduce((sum, row) => sum + row.amount, 0);
  return {
    company_id: company, generation_id: company, snapshot_id: company, fiscal_year_id: company,
    source_created_at: '2026-11-01T03:44:00Z', year_start: '2026-04-01', coverage_start: '2026-10-01',
    date_from: from, date_to: to, currency: 'INR', earlier_history_unavailable: true,
    totals: {
      cash: fixed(cash), bank: fixed(bank),
      net_receivable: receivables.net, net_payable: payables.net,
      income: fixed(income), expenses: fixed(expenses), net_income: fixed(income - expenses),
    },
    series: rows.map(row => ({ date: row.date, income: fixed(row.income), expenses: fixed(row.expenses) })),
    position, receivables, payables,
    top_expenses: top.map(row => ({ ...row, amount: fixed(row.amount) })),
    other_expenses: fixed(other),
    ...change,
  } as Overview;
}
