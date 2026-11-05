'use client';
import type { components } from '@janso/api-client/accounting';
import { serviceCall, type ServiceRequest } from './service-call';
import { sessionFetch } from './session-fetch';
import { trackingId } from './stock-tracking-resources';
import { allowedFinancialOpeningRequest } from './financial-opening-policy';
import { decimal, sum } from './opening-stock';
export { decimal, sum };
type Schema = components['schemas'];
export type Declaration = Schema['OpeningDeclaration-Input'];
export type Entry = NonNullable<Declaration['entries']>[number];
export type Document = NonNullable<Entry['documents']>[number];
export type Workspace = Schema['OpeningWorkspaceDetail'];
export type Readiness = Schema['FinancialOpeningReadiness'];
export type Preview = Schema['FinancialOpeningPreview'];
export type Reconciliation = Schema['OpeningReconciliation'];
export type ImportJob = Schema['FinancialOpeningImportDetail'];
export type FieldSet = Schema['FieldSet'];
export type Native = { title?: string; type?: string; readOnly?: boolean; properties?: Record<string, Native>; items?: Native; $ref?: string; enum?: string[]; required?: string[]; anyOf?: Native[] };
export type CaptureMetadata = { schema_version: number; capture: Native & { $defs?: Record<string, Native> }; native_field_sets: string[]; capture_permissions: { journal_lines: Record<string, boolean>; open_items: Record<string, boolean> } };
export type Metadata = CaptureMetadata & { native: FieldSet[] };
export type Access = { manage: boolean; post: boolean; export: boolean; period?: boolean; cancel?: boolean };
export const base = (company: string) => `/v1/companies/${company}/opening-batches`;
export const importBase = (company: string) => `/v1/companies/${company}/financial-opening-imports`;
export const request = <T>(value: ServiceRequest) => serviceCall<T>('/api/financial-opening', { service: 'accounting', ...value }, 'account and party opening');
export const metadataRequest = async <T>(value: ServiceRequest): Promise<T> => {
  const data = await request<CaptureMetadata>(value);
  const prefix = value.path.split('/opening-batches/')[0] + '/finance/field-sets/';
  if (data.schema_version !== 1 || !data.capture?.properties || !data.capture.$defs || !Array.isArray(data.native_field_sets) ||
      data.native_field_sets.length !== 4 || data.native_field_sets.some(path => !path.startsWith(prefix) || !allowedFinancialOpeningRequest('accounting', 'GET', path))) throw { status: 502, message: 'Opening form metadata could not be verified.' };
  if (!data.capture_permissions || !data.capture_permissions.journal_lines || !data.capture_permissions.open_items || Object.values(data.capture_permissions).some(fields => Object.values(fields).some(value => typeof value !== 'boolean')))
    throw { status: 502, message: 'Opening capture permissions could not be verified.' };
  const native = await Promise.all(data.native_field_sets.map(path => request<FieldSet>({ path, signal: value.signal })));
  if (native.some(set => !Array.isArray(set.fields))) throw { status: 502, message: 'Opening field permissions could not be verified.' };
  return { ...data, native } as T;
};
export function owned(company: string) {
  return (value: { company_id: string }) => {
    if (!value || value.company_id !== company) throw { status: 502, message: 'Opening ownership could not be verified. Reload the current company.' };
  };
}
export function verifyWorkspace(company: string) {
  return (value: Workspace) => {
    owned(company)(value);
    if (!trackingId.test(value.id) || !Number.isSafeInteger(value.expected_version) || value.expected_version < 1 ||
      !/^[a-f0-9]{64}$/.test(value.manifest_hash) || !Array.isArray(value.journal_ids) || !value.journal_ids.every(id => trackingId.test(id)) ||
      !Array.isArray(value.blockers)) throw { status: 502, message: 'The opening receipt could not be verified. Retry the same request.' };
  };
}
export function verifyJob(company: string) {
  return (value: ImportJob) => {
    owned(company)(value);
    if (!trackingId.test(value.id) || !Number.isSafeInteger(value.row_version) || value.row_version < 1 ||
      !Array.isArray(value.issues) || !Array.isArray(value.journal_ids) ||
      value.review_hash !== null && !/^[a-f0-9]{64}$/.test(value.review_hash)) throw { status: 502, message: 'The import receipt could not be verified. Retry the same request.' };
  };
}
export function previousDate(date: string): string {
  const parsed = new Date(date + 'T00:00:00Z');
  if (Number.isNaN(parsed.getTime())) return '';
  parsed.setUTCDate(parsed.getUTCDate() - 1);
  return parsed.toISOString().slice(0, 10);
}
export function initialDeclaration(ready: Readiness): Declaration {
  return { version: 1, posting_date: ready.books_begin_date, currency: ready.currency,
    covered_through: previousDate(ready.books_begin_date), source_system: 'manual', source_id: crypto.randomUUID(),
    coverage_mode: 'POST_CUTOVER_ONLY', reason: '', entries: [] };
}
export function newEntry(currency: string, account = ''): Entry {
  return { source_key: crypto.randomUUID(), account_id: account, side: 'DEBIT', currency, amount: '', exchange_rate: '1', base_amount: '', documents: [] };
}
const source = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/;
export function entryError(entry: Entry, declaration: Declaration): string | null {
  if (!trackingId.test(entry.account_id)) return 'Select an active ledger account.';
  if (!source.test(entry.source_key)) return 'Enter a valid unique source reference.';
  if (!/^[A-Z]{3}$/.test(entry.currency)) return 'Enter a three-letter currency code.';
  if (!decimal(entry.amount, true) || !decimal(entry.base_amount ?? '', true)) return 'Enter positive amounts and an explicit historical base value, with up to four decimals.';
  if (!/^(?:0|[1-9]\d{0,10})(?:\.\d{1,8})?$/.test(entry.exchange_rate) || !/[1-9]/.test(entry.exchange_rate)) return 'Enter a positive exchange rate, with up to eight decimals.';
  if (entry.currency === declaration.currency && (sum([entry.amount]) !== sum([entry.base_amount!]) || !/^1(?:\.0+)?$/.test(entry.exchange_rate))) return 'For base currency, use rate 1 and the same amount and base value.';
  const docs = entry.documents ?? [];
  for (const doc of docs) {
    if (!doc.reference.trim() || doc.reference.length > 120 || /[\x00-\x1f]/.test(doc.reference)) return 'Enter a printable reference for every opening document.';
    if (!decimal(doc.amount, true) || !decimal(doc.base_amount ?? '', true)) return 'Enter each document’s outstanding amount and historical base value.';
    if (doc.original_amount && (!decimal(doc.original_amount, true) || BigInt(sum([doc.amount]).replace('.', '')) > BigInt(sum([doc.original_amount]).replace('.', '')))) return 'Outstanding cannot exceed the original document amount.';
    if (doc.document_kind !== 'ON_ACCOUNT' && (!doc.document_date || !doc.due_date || doc.document_date > declaration.covered_through || doc.due_date < doc.document_date)) return 'Document dates must be within source coverage; due date cannot precede the document date.';
  }
  if (docs.length && (sum(docs.map(row => row.amount)) !== sum([entry.amount]) || sum(docs.map(row => row.base_amount!)) !== sum([entry.base_amount!]))) return 'Document outstanding and base values must equal this account line.';
  return null;
}
export function declarationError(value: Declaration): string | null {
  if (!value.reason.trim() || value.reason.trim().length < 3 || /[\x00-\x1f]/.test(value.reason)) return 'Explain the opening source and reason using at least three printable characters.';
  if (!source.test(value.source_id) || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,59}$/.test(value.source_system)) return 'Enter valid source system and migration references.';
  if (!value.covered_through || value.covered_through > value.posting_date || value.covered_through === value.posting_date && !value.same_day_reviewed) return 'Coverage must precede books begin, unless same-day overlap was explicitly reviewed.';
  if (value.coverage_mode === 'YTD_SUMMARY' && (!value.originating_year_start || value.originating_year_start > value.covered_through || value.covered_through !== previousDate(value.posting_date) || !value.ytd_summary)) return 'Imported YTD requires the originating year start and coverage through the day before books begin.';
  if (value.credit_cash_reviewed && (value.credit_cash_reason?.trim().length ?? 0) < 3) return 'Explain the reviewed credit cash balance.';
  if (value.clearing_account_id && !trackingId.test(value.clearing_account_id)) return 'Select a valid migration clearing account.';
  if (!value.entries.length) return 'Add at least two balanced account lines. Use company setup to confirm a genuinely zero opening.';
  if (value.entries.length > 10000 || value.entries.reduce((n, row) => n + (row.documents?.length ?? 0), 0) > 10000) return 'A declaration supports at most 10,000 account lines and 10,000 documents.';
  if (new Set(value.entries.map(row => row.source_key.toLowerCase())).size !== value.entries.length) return 'Each account line needs a unique source reference.';
  for (const row of value.entries) { const error = entryError(row, value); if (error) return error; }
  const documentReferences = new Set<string>(), documentSources = new Set<string>();
  for (const row of value.entries) for (const doc of row.documents ?? []) {
    const reference = [row.account_id.toLowerCase(), row.currency, doc.reference.toLowerCase()].join(':');
    const sourceKey = doc.source_key?.toLowerCase();
    if (documentReferences.has(reference) || sourceKey && documentSources.has(sourceKey)) return 'Each outstanding document needs a unique reference per account and currency, and a unique source key across the declaration.';
    documentReferences.add(reference); if (sourceKey) documentSources.add(sourceKey);
  }
  if (sum(value.entries.filter(row => row.side === 'DEBIT').map(row => row.base_amount!)) !== sum(value.entries.filter(row => row.side === 'CREDIT').map(row => row.base_amount!))) return 'Base-currency debit and credit totals must balance before preview.';
  for (const row of value.ytd_summary ?? []) if (!trackingId.test(row.account_id) || !/^[A-Z]{3}$/.test(row.currency) || !decimal(row.amount, true) || !decimal(row.base_amount, true)) return 'Complete every imported YTD amount using a valid nominal account and exact positive values.';
  return null;
}
export const blockerLabels: Record<string, string> = {
  ACCOUNTING_NOT_INITIALIZED: 'Initialize the chart of accounts in accounting setup.',
  BOOKS_BEGIN_PERIOD_NOT_OPEN: 'Open the financial period containing books begin.',
  LATER_BOOKS_CLOSED: 'Later books are closed. Ask a controller to review period locks.',
  CONFIRMATION_PENDING: 'Posting confirmation is still being delivered. Refresh to check again.',
  EXECUTION_UNCONFIRMED: 'A native journal is waiting for posting confirmation.',
  FINANCIAL_OPENING_FINALIZED: 'The financial opening is already finalized.',
  OPENING_ALREADY_FINALIZED: 'The financial opening is already finalized.',
  LEGACY_ACTIVITY_REQUIRES_REVIEW: 'Earlier activity exists. Review company readiness before recording an opening.',
  FINANCIAL_SETUP_NOT_INITIALIZED: 'Set up the company financial year and periods first.',
};
export const blockerLabel = (code: string) => blockerLabels[code] ?? code.toLowerCase().replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
export async function download(ticketPath: string, company: string) {
  const ticket = await request<Schema['FinancialOpeningExportTicket']>({ path: ticketPath });
  if (!ticket.download_path.startsWith(`/v1/companies/${company}/`) || !allowedFinancialOpeningRequest('accounting', 'GET', ticket.download_path)) throw new Error('The export destination could not be verified.');
  const response = await sessionFetch('/api/financial-opening', { method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ service: 'accounting', method: 'GET', path: ticket.download_path }) }, true);
  if (!response.ok || !response.headers.get('content-type')?.startsWith('text/csv')) throw new Error('Export is unavailable or access has changed. Reload and try again.');
  saveFile(await response.blob(), 'account-party-opening.csv');
}
export function saveFile(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob), anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
