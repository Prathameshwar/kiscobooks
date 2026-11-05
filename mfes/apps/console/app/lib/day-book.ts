import { businessToday, type DisplayConfig } from '@janso/ui';
import type { FiscalYearChoice } from './company-context';
import { VOUCHER_KINDS } from './voucher-kinds';

export const DAY_BOOK_CODE = 'DAY_BOOK_ACTIVITY';
export const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const kindLabel = (value: string) => VOUCHER_KINDS.find(item => item.value === value)?.label.split(' — ')[0]
  ?? ({ MANUAL: 'Journal', INVOICE: 'Invoice', OPENING: 'Opening', REVERSAL: 'Reversal' }[value] ?? value.replaceAll('_', ' ').toLowerCase());
export const kindOptions = [...VOUCHER_KINDS.map(item => ({ id: item.value, label: kindLabel(item.value) })), ...['MANUAL', 'INVOICE', 'OPENING', 'REVERSAL'].map(id => ({ id, label: kindLabel(id) + ' (accounting)' }))];
export const statusLabel = (value: string) => value.toLowerCase().replaceAll('_', ' ').replace(/^./, text => text.toUpperCase());
export type Condition = { field: 'number' | 'narration' | 'kind'; operator: 'contains' | 'equals' | 'not_contains'; value: string };
export type DayBookFilters = {
  scope: 'POSTED' | 'ALL'; date_from: string; date_to: string; kinds: string[];
  type_id: string; type_label: string; type_revision_ids: string[];
  party_id: string; party_label: string; account_id: string; account_label: string;
  q: string; status: string; basis: 'BASE' | 'TRANSACTION'; currency: string;
  amount_min: string; amount_max: string; conditions: Condition[]; match: 'ALL' | 'ANY';
  mode: 'VOUCHERS' | 'ACCOUNTING'; group_by: 'date' | 'kind' | 'particulars' | 'none';
  sort: 'date' | '-date' | 'number' | '-amount';
};
export type DayBookEntry = { line_id?: string; journal_id: string; date: string; number: string; account_code: string; account_name: string; debit: string; credit: string; currency: string };
export type DayBookRow = {
  id: string; voucher_id?: string | null; journal_id?: string; date: string; number: string | null;
  kind: string; particulars: string; narration: string; currency: string; status: string;
  debit?: string; credit?: string; profile?: string; type_name?: string; type_code?: string;
  journal_count?: number; line_count?: number; entries?: DayBookEntry[];
  journals?: (DayBookRow & { entries: DayBookEntry[]; reversal_of_id?: string | null })[];
  account_code?: string; account_name?: string; line_id?: string;
};
export type DayBookGroup = { count: number; debit: string; credit: string };
export type DayBookSummary = {
  voucher_count: number; activity_count?: number; journal_count?: number; line_count?: number; debit?: string; credit?: string;
  currency?: string; by_kind: Record<string, DayBookGroup | number>; by_status?: Record<string, number>;
  groups?: Record<string, DayBookGroup>;
};
export type SavedDayBookView = { id: string; name: string; filters: DayBookFilters };
const day = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value + 'T00:00:00Z')) && new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) === value;
export function defaultDayBookFilters(display: DisplayConfig, year?: FiscalYearChoice | null): DayBookFilters {
  const today = businessToday(display.timezone);
  const date = year && (today < year.startDate || today > year.endDate) ? year.endDate : today;
  return { scope: 'POSTED', date_from: date, date_to: date, kinds: [], type_id: '', type_label: '', type_revision_ids: [],
    party_id: '', party_label: '', account_id: '', account_label: '', q: '', status: '', basis: 'BASE', currency: '',
    amount_min: '', amount_max: '', conditions: [], match: 'ALL', mode: 'VOUCHERS', group_by: 'date', sort: 'date' };
}
export function filterError(value: DayBookFilters): string {
  if (!day(value.date_from) || !day(value.date_to)) return 'Enter a valid start and end date.';
  if (value.date_from > value.date_to) return 'The start date must be on or before the end date.';
  if ((Date.parse(value.date_to) - Date.parse(value.date_from)) / 86400000 > 3660) return 'Choose a period of ten years or less.';
  if (value.q.length > 120) return 'Search can contain up to 120 characters.';
  for (const key of ['party_id', 'account_id', 'type_id'] as const) if (value[key] && !UUID.test(value[key])) return 'Choose a valid ' + key.replace('_id', '') + '.';
  if (value.basis === 'TRANSACTION' && !/^[A-Z]{3}$/.test(value.currency)) return 'Select a three-letter transaction currency.';
  if (value.scope === 'POSTED' && value.status) return 'Document status filters apply to All vouchers.';
  if (value.scope === 'ALL' && (value.mode !== 'VOUCHERS' || value.group_by !== 'date')) return 'Live document activity uses the voucher view, grouped by date.';
  if (value.type_revision_ids.length && !value.type_id) return 'Choose a configured voucher type for its revision filter.';
  if (value.scope === 'ALL' && (value.account_id || value.amount_min || value.amount_max || value.sort === '-amount')) return 'Account and posting-value filters apply to the posted book. Clear them or switch to Posted book.';
  for (const key of ['amount_min', 'amount_max'] as const) if (value[key] && !/^\d{1,15}(\.\d{1,4})?$/.test(value[key])) return 'Enter a positive posting value with up to four decimal places.';
  if (value.amount_min && value.amount_max && decimalUnits(value.amount_min) > decimalUnits(value.amount_max)) return 'Minimum posting value must not exceed maximum.';
  if (value.conditions.length > 8 || value.conditions.some(item => !item.value.trim() || item.value.length > 120)) return 'Complete each condition using up to 120 characters.';
  return '';
}
function decimalUnits(value: string): bigint { const [whole, part = ''] = value.split('.'); return BigInt(whole) * 10000n + BigInt(part.padEnd(4, '0')); }
export function readDayBookFilters(raw: unknown, fallback: DayBookFilters): DayBookFilters | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const result = { ...fallback };
  const data = raw as Record<string, unknown>;
  for (const key of Object.keys(result) as (keyof DayBookFilters)[]) {
    if (key === 'conditions') continue;
    const value = data[key];
    if (value === undefined) continue;
    if (Array.isArray(result[key])) {
      if (!Array.isArray(value) || value.length > 2000 || value.some(item => typeof item !== 'string' || item.length > 100)) return null;
    } else if (typeof value !== 'string' || value.length > 200) return null;
    Object.assign(result, { [key]: value });
  }
  if (!['POSTED', 'ALL'].includes(result.scope) || !['BASE', 'TRANSACTION'].includes(result.basis)
    || !['VOUCHERS', 'ACCOUNTING'].includes(result.mode) || !['date', 'kind', 'particulars', 'none'].includes(result.group_by)
    || !['date', '-date', 'number', '-amount'].includes(result.sort) || !['ALL', 'ANY'].includes(result.match)) return null;
  if (data.conditions !== undefined) {
    if (!Array.isArray(data.conditions) || data.conditions.length > 8) return null;
    for (const condition of data.conditions) if (!condition || !['number', 'narration', 'kind'].includes(condition.field)
      || !['contains', 'equals', 'not_contains'].includes(condition.operator) || typeof condition.value !== 'string') return null;
    result.conditions = data.conditions;
  }
  if (result.type_revision_ids.some(id => !UUID.test(id)) || result.kinds.length > 30) return null;
  return filterError(result) ? null : result;
}
export function reportParameters(filters: DayBookFilters) {
  const { date_from, date_to, kinds, type_revision_ids, q, basis, mode, group_by, sort, conditions, match } = filters;
  return { date_from, date_to, kinds, type_revision_ids, q, basis, mode, group_by, sort, conditions, match,
    ...(filters.party_id ? { party_id: filters.party_id } : {}), ...(filters.account_id ? { account_id: filters.account_id } : {}),
    ...(basis === 'TRANSACTION' ? { currency: filters.currency } : {}),
    ...(filters.amount_min ? { amount_min: filters.amount_min } : {}), ...(filters.amount_max ? { amount_max: filters.amount_max } : {}) };
}
export function liveParameters(filters: DayBookFilters, cursor: string | null) {
  return { date_from: filters.date_from, date_to: filters.date_to, kinds: filters.kinds, q: filters.q,
    conditions: filters.conditions, match: filters.match, sort: filters.sort === '-amount' ? 'date' : filters.sort,
    ...(filters.type_id ? { type_id: filters.type_id } : {}), ...(filters.party_id ? { party_id: filters.party_id } : {}),
    ...(filters.status ? { status: filters.status } : {}), ...(filters.basis === 'TRANSACTION' ? { currency: filters.currency } : {}),
    limit: 50, cursor, include_summary: true };
}
export function dayBookHref(row: DayBookRow, returnTo: string): string | null {
  return row.voucher_id && UUID.test(row.voucher_id) ? '/vouchers/' + row.voucher_id + '?returnTo=' + encodeURIComponent(returnTo) : null;
}
export const preferencesKey = (actor: string, company: string) => 'kiscobooks:day-book:v1:' + actor + ':' + company;


/** Compare normalized server parameters without depending on JSON property order. */
export function matchingDayBookParameters(filters: DayBookFilters, retained: Record<string, unknown>): boolean {
  const expected = reportParameters(filters) as Record<string, unknown>;
  const empty = (value: unknown) => value === null || value === undefined || value === '' || Array.isArray(value) && value.length === 0;
  const canonical = (value: unknown): string => {
    if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
    if (value && typeof value === 'object') return '{' + Object.entries(value).filter(([, item]) => !empty(item)).sort(([left], [right]) => left.localeCompare(right)).map(([key, item]) => JSON.stringify(key) + ':' + canonical(item)).join(',') + '}';
    return JSON.stringify(value);
  };
  return canonical(expected) === canonical(retained);
}
export type DayBookPosition = { index: number; cursors: (string | null)[] };
export function readDayBookPosition(raw: unknown): DayBookPosition | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const value = raw as DayBookPosition;
  if (!Number.isInteger(value.index) || value.index < 0 || value.index > 100000 || !Array.isArray(value.cursors) || value.cursors.length > 2000 || value.cursors[0] !== null || value.cursors.some(item => item !== null && (typeof item !== 'string' || item.length > 4000)) || value.index >= value.cursors.length) return undefined;
  return value;
}
/** Only same-company Day Book URLs may be used by voucher back navigation. */
export function dayBookReturnTo(value: unknown, company: string): string | null {
  if (typeof value !== 'string' || value.length > 20000 || !value.startsWith('/books/day-book?')) return null;
  try {
    const url = new URL(value, 'https://local.invalid');
    return url.pathname === '/books/day-book' && url.searchParams.get('company') === company && !url.hash ? url.pathname + url.search : null;
  } catch { return null; }
}
