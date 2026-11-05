'use client';
import type { SearchSelectLoader } from '@janso/ui';
import type { components } from '@janso/api-client/reports';
import type { components as accounting } from '@janso/api-client/accounting';
import { serviceCall, type ServiceRequest } from './service-call';
import { trackingId } from './stock-tracking-resources';

export type Overview = components['schemas']['CompanyOverview'];
export const overviewRequest = <T,>(request: ServiceRequest) => serviceCall<T>('/api/product-fields', { ...request, service: 'reports' }, 'company overview');
const money = /^-?(?:0|[1-9]\d{0,14})\.\d{4}$/;
const date = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value + 'T00:00:00Z')) && new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) === value;
const total = (values: readonly string[]) => values.reduce((sum, value) => sum + BigInt(value.replace('.', '')), 0n);

/**
 * The breakdowns beside the totals must reconcile to them exactly — cents included — or the page
 * would show a card that disagrees with the tile above it. Anything that does not is refused whole.
 */
function breakdownsReconcile(value: Overview): boolean {
  const { totals, series, position, receivables, payables, top_expenses: topExpenses, other_expenses: other } = value;
  if (!Array.isArray(position) || position.length !== series.length || !position.length ||
    position.some((row, index) => row.date !== series[index]!.date || !money.test(row.cash_and_bank)) ||
    total([position[position.length - 1]!.cash_and_bank]) !== total([totals.cash, totals.bank])) return false;
  for (const [items, net] of [[receivables, totals.net_receivable], [payables, totals.net_payable]] as const) {
    const buckets = items?.buckets;
    if (!buckets) return false;
    const parts = [buckets.current, buckets.days_1_30, buckets.days_31_60, buckets.days_61_90, buckets.days_over_90, buckets.unknown];
    if (![items.gross, items.advances, items.net, items.overdue, ...parts].every(amount => typeof amount === 'string' && money.test(amount)) ||
      total(parts) !== total([items.gross]) ||
      total([items.overdue]) !== total(parts.slice(1, 5)) ||
      total([items.gross]) - total([items.advances]) !== total([items.net]) || total([items.net]) !== total([net]) ||
      !Array.isArray(items.parties) || items.parties.length > 5 ||
      items.parties.some(party => !trackingId.test(party.party_id) || typeof party.name !== 'string' || !money.test(party.outstanding) || !money.test(party.overdue) || total([party.outstanding]) <= 0n) ||
      new Set(items.parties.map(party => party.party_id)).size !== items.parties.length) return false;
  }
  // `other_expenses` is what falls outside the ranked ledgers, net of any credit-balance ledger, so it may be negative.
  return Array.isArray(topExpenses) && topExpenses.length <= 5 && typeof other === 'string' && money.test(other) &&
    topExpenses.every(row => trackingId.test(row.account_id) && typeof row.name === 'string' && money.test(row.amount) && total([row.amount]) > 0n) &&
    new Set(topExpenses.map(row => row.account_id)).size === topExpenses.length &&
    total(topExpenses.map(row => row.amount)) + total([other]) === total([totals.expenses]);
}

export type OverviewRange = { from: string; to: string };

/** The read path for a company, year and optional explicit range. No range is the server's default. */
export function overviewPath(company: string, year?: string, range?: OverviewRange | null) {
  const params = new URLSearchParams();
  if (year) params.set('fiscal_year_id', year);
  if (range) { params.set('date_from', range.from); params.set('date_to', range.to); }
  const query = params.toString();
  return `/v2/companies/${company}/overview${query ? '?' + query : ''}`;
}

export function verifyOverview(company: string, year?: string, range?: OverviewRange | null) {
  return (value: Overview) => {
    const invalid = () => { throw { status: 502, message: 'The company overview could not be verified. Refresh and retry.' }; };
    // A malformed row (a null where an object belongs) must be the same refusal, not an unhandled TypeError.
    try {
    if (!value || value.company_id !== company || year && value.fiscal_year_id !== year ||
      range && (value.date_from !== range.from || value.date_to !== range.to) ||
      ![value.generation_id, value.snapshot_id, value.fiscal_year_id].every(id => trackingId.test(id)) ||
      !/^[A-Z]{3}$/.test(value.currency) || !Number.isFinite(Date.parse(value.source_created_at)) ||
      ![value.year_start, value.coverage_start, value.date_from, value.date_to].every(date) ||
      value.date_from < value.coverage_start || value.date_from < value.year_start || value.date_from > value.date_to ||
      typeof value.earlier_history_unavailable !== 'boolean' || value.earlier_history_unavailable !== (value.coverage_start > value.year_start) ||
      !value.totals || !['cash', 'bank', 'net_receivable', 'net_payable', 'income', 'expenses', 'net_income'].every(key => money.test(value.totals[key as keyof Overview['totals']])) ||
      !Array.isArray(value.series) || value.series.length > 366) invalid();
    const days = (Date.parse(value.date_to) - Date.parse(value.date_from)) / 86400000 + 1;
    if (value.series.length !== days || value.series.some((row, index) => !date(row.date) || Date.parse(row.date) !== Date.parse(value.date_from) + index * 86400000 || !money.test(row.income) || !money.test(row.expenses))) invalid();
    if (total(value.series.map(row => row.income)) !== total([value.totals.income]) ||
      total(value.series.map(row => row.expenses)) !== total([value.totals.expenses]) ||
      total([value.totals.income]) - total([value.totals.expenses]) !== total([value.totals.net_income]) ||
      !breakdownsReconcile(value)) invalid();
    } catch { invalid(); }
  };
}

export function customerLedgerLookup(company: string): SearchSelectLoader {
  return async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ role: 'CUSTOMER', status: 'ACTIVE', limit: '50', ...(q ? { q: q.trim().slice(0, 200) } : {}), ...(cursor ? { cursor } : {}) });
    const result = await serviceCall<{ items: accounting['schemas']['PartyListItem'][]; page: { next_cursor: string | null; limit: number } }>('/api/product-fields', { service: 'accounting', method: 'GET', path: `/v1/companies/${company}/parties?${params}`, signal }, 'customer ledger lookup');
    if (!Array.isArray(result.items) || result.items.length > 50 || !result.page || result.page.limit > 50 ||
      result.page.next_cursor !== null && typeof result.page.next_cursor !== 'string' ||
      result.items.some(row => !trackingId.test(row.id) || row.company_id && row.company_id !== company)) throw { status: 502, message: 'The customer lookup could not be verified.' };
    return { items: result.items.filter(row => row.name || row.code).map(row => ({ id: row.id, label: row.name ?? row.code!, meta: row.code ?? undefined })), nextCursor: result.page.next_cursor };
  };
}
