import { expect, it, vi } from 'vitest';
import { customerLedgerLookup, verifyOverview } from '../app/lib/company-overview';
import { serviceCall } from '../app/lib/service-call';
import { overviewFixture } from './overview-fixture';
vi.mock('../app/lib/service-call', () => ({ serviceCall: vi.fn() }));
const company = '01234567-89ab-4cde-8fab-0123456789ab';
const value = overviewFixture({ company, from: '2026-10-29', to: '2026-10-29', quiet: true, change: { coverage_start: '2026-10-29' } });
const populated = overviewFixture({ company });
const buckets = populated.receivables.buckets;
it('accepts a populated overview whose breakdowns reconcile to its totals, for the range asked', () => {
  expect(() => verifyOverview(company, company)(populated)).not.toThrow();
  expect(() => verifyOverview(company, company, { from: populated.date_from, to: populated.date_to })(populated)).not.toThrow();
  expect(() => verifyOverview(company, company)(value)).not.toThrow();
});
it('accepts a negative "all other expenses" that reconciles, because a credit-balance ledger nets expenses down', () => {
  const total = Number(populated.totals.expenses);
  const change = { top_expenses: [{ ...populated.top_expenses[0]!, amount: (total + 100).toFixed(4) }], other_expenses: '-100.0000' };
  expect(() => verifyOverview(company, company)({ ...populated, ...change })).not.toThrow();
});
it('turns any malformed payload into the same refusal, never an unhandled error', () => {
  const refusal = (payload: unknown) => { try { verifyOverview(company, company)(payload as never); } catch (error) { return error; } return null; };
  for (const hostile of [null, undefined, 7, 'text', {}, { ...populated, totals: null }, { ...populated, series: [null] }]) {
    expect(refusal(hostile)).toMatchObject({ status: 502 });
  }
});
it('refuses a response for a different range than the one requested', () => {
  expect(() => verifyOverview(company, company, { from: '2026-10-02', to: populated.date_to })(populated)).toThrow();
});
it.each([
  ['a position series of the wrong length', { position: populated.position.slice(1) }],
  ['a closing balance that is not cash plus bank', { position: populated.position.map((row, index) => index === populated.position.length - 1 ? { ...row, cash_and_bank: '1.0000' } : row) }],
  ['a position on the wrong day', { position: populated.position.map((row, index) => index === 0 ? { ...row, date: '2026-09-30' } : row) }],
  ['buckets that do not add up to the gross', { receivables: { ...populated.receivables, buckets: { ...buckets, current: '0.0000' } } }],
  ['an overdue figure that is not the late buckets', { payables: { ...populated.payables, overdue: '1.0000' } }],
  ['a net that is not the tile figure', { receivables: { ...populated.receivables, advances: '0.0000', net: populated.receivables.gross } }],
  ['more than five parties', { receivables: { ...populated.receivables, parties: Array.from({ length: 6 }, () => populated.receivables.parties[0]!) } }],
  ['a party with a foreign identifier', { receivables: { ...populated.receivables, parties: [{ ...populated.receivables.parties[0]!, party_id: 'not-an-id' }] } }],
  ['expenses that do not add up', { other_expenses: '0.0000' }],
  ['more than five expense ledgers', { top_expenses: Array.from({ length: 6 }, () => populated.top_expenses[0]!) }],
  ['a float where money belongs', { other_expenses: '322.5' }],
  ['no breakdowns at all', { receivables: undefined }],
  ['the same party twice', { receivables: { ...populated.receivables, parties: [populated.receivables.parties[0]!, populated.receivables.parties[0]!] } }],
  ['a party with no positive balance', { receivables: { ...populated.receivables, parties: [{ ...populated.receivables.parties[0]!, outstanding: '0.0000' }] } }],
  ['the same expense ledger twice', { top_expenses: [populated.top_expenses[0]!, populated.top_expenses[0]!], other_expenses: '0.0000' }],
  ['an expense ledger with no positive amount', { top_expenses: [{ ...populated.top_expenses[0]!, amount: '0.0000' }], other_expenses: populated.totals.expenses }],
  ['a null row among the position days', { position: populated.position.map((row, index) => index === 3 ? null : row) }],
  ['a null party', { receivables: { ...populated.receivables, parties: [null] } }],
  ['a null expense ledger', { top_expenses: [null], other_expenses: populated.totals.expenses }],
])('refuses %s', (_label, change) => {
  expect(() => verifyOverview(company, company)({ ...populated, ...change } as typeof populated)).toThrow();
});
it.each([
  { totals: { ...value.totals, income: '0.1000' } },
  { date_to: '2026-13-01' },
  { series: [{ date: '2026-10-28', income: '0.0000', expenses: '0.0000' }] },
  { series: [] }, { currency: 'invalid' }, { source_created_at: 'unknown' },
  { earlier_history_unavailable: false }, { fiscal_year_id: 'unknown' },
])('refuses an unverified overview %j', change => {
  expect(() => verifyOverview(company, company)({ ...value, ...change })).toThrow();
});
it('uses real scoped customer role filters, signed cursors and native names', async () => {
  vi.mocked(serviceCall).mockResolvedValue({ items: [{ id: company, company_id: company, name: 'Actual customer', code: 'QA1' }], page: { limit: 50, next_cursor: 'signed-next' } });
  const loader = customerLedgerLookup(company);
  const result = await loader({ q: 'QA', cursor: null, signal: new AbortController().signal });
  expect(result.items[0]).toEqual({ id: company, label: 'Actual customer', meta: 'QA1' });
  expect(result.nextCursor).toBe('signed-next');
  const request = vi.mocked(serviceCall).mock.calls.at(-1)![1];
  const path = new URL(request.path, 'http://test.invalid');
  expect(path.pathname).toBe(`/v1/companies/${company}/parties`);
  expect(path.searchParams.get('role')).toBe('CUSTOMER');
  expect(path.searchParams.get('q')).toBe('QA');
  expect(path.searchParams.get('limit')).toBe('50');
});
it('refuses a foreign customer row', async () => {
  vi.mocked(serviceCall).mockResolvedValue({ items: [{ id: company, company_id: '11234567-89ab-4cde-8fab-0123456789ab', name: 'Wrong scope' }], page: { limit: 50, next_cursor: null } });
  await expect(customerLedgerLookup(company)({ q: '', cursor: null, signal: new AbortController().signal })).rejects.toMatchObject({ status: 502 });
});
