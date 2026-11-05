import type { Access, Declaration, Entry, Metadata, Readiness, Workspace } from '../app/lib/financial-opening';
export const COMPANY = '01990000-0000-7000-8000-000000000001', ACCOUNT = '01990000-0000-7000-8000-000000000002', OTHER = '01990000-0000-7000-8000-000000000003', BATCH = '01990000-0000-7000-8000-000000000004', JOURNAL = '01990000-0000-7000-8000-000000000005', JOB = '01990000-0000-7000-8000-000000000006';
export const access: Access = { manage: true, post: true, export: true };
export const readiness: Readiness = { company_id: COMPANY, books_begin_date: '2026-04-01', currency: 'INR', batch_id: BATCH, status: 'DRAFT', blockers: [], can_prepare: false };
export const line = (account = ACCOUNT, side: Entry['side'] = 'DEBIT'): Entry => ({ source_key: 'opening-' + side, account_id: account, side, currency: 'INR', amount: '100', base_amount: '100', exchange_rate: '1', documents: [] });
export const declaration = (): Declaration => ({ version: 1, posting_date: '2026-04-01', covered_through: '2026-03-31', currency: 'INR', source_system: 'manual', source_id: 'migration-a', coverage_mode: 'POST_CUTOVER_ONLY', reason: 'Reviewed migration balances', entries: [line(), line(OTHER, 'CREDIT')] });
export const workspace: Workspace = { id: BATCH, company_id: COMPANY, status: 'DRAFT', posting_date: '2026-04-01', expected_version: 1, revision_id: OTHER, manifest_hash: 'a'.repeat(64), currency: 'INR', coverage_mode: 'POST_CUTOVER_ONLY', entry_count: 2, document_count: 0, expected_debit: '100', expected_credit: '100', journal_ids: [], posted_journals: 0, blockers: [], effect_kind: 'PREPARATION' };
const properties = (keys: string[]) => Object.fromEntries(keys.map(key => [key, { type: 'string', title: key }]));
export const metadata: Metadata = {
  schema_version: 1,
  capture_permissions: {
    journal_lines: Object.fromEntries(['account_id', 'side', 'currency', 'amount', 'exchange_rate', 'base_amount', 'opening_base_amount', 'description'].map(key => [key, true])),
    open_items: Object.fromEntries(['account_id', 'party_id', 'role', 'direction', 'reference', 'currency', 'amount', 'base_currency', 'base_amount', 'document_date', 'due_date', 'posting_date', 'terms'].map(key => [key, true])),
  },
  capture: { properties: properties(['posting_date', 'covered_through', 'source_system', 'source_id', 'coverage_mode', 'originating_year_start', 'reason', 'clearing_account_id', 'same_day_reviewed', 'credit_cash_reviewed']), $defs: { OpeningEntry: { properties: properties(['account_id', 'side', 'currency', 'amount', 'exchange_rate', 'base_amount', 'source_key', 'description', 'documents']) } } },
  native_field_sets: ['opening-batches', 'journals', 'journal-lines', 'open-items'].map(resource => `/v1/companies/${COMPANY}/finance/field-sets/${resource}`),
  native: [{ resource: 'journal-lines', fields: ['account_id', 'side', 'currency', 'amount', 'exchange_rate', 'base_amount', 'opening_base_amount', 'description'].map(key => ({ key, label: key, required: true, visible: true, readable: true, writable: true, definition: {} })) },
    { resource: 'open-items', fields: ['account_id', 'party_id', 'role', 'direction', 'reference', 'currency', 'amount', 'base_currency', 'base_amount', 'document_date', 'due_date', 'posting_date', 'terms'].map(key => ({ key, label: key, required: true, visible: true, readable: true, writable: true, definition: {} })) }],
};
export const page = { limit: 25, has_more: false, next_cursor: null };
