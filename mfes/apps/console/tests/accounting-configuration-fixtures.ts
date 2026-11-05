import fields from './accounting-configuration-fields.json';
import type { AccountingForm, AccountingRecord, AccountingResource } from '../app/lib/accounting-configuration-resources';
export const COMPANY = '01990000-0000-7000-8000-000000000001', ID = '01990000-0000-7000-8000-000000000002', PARTY = '01990000-0000-7000-8000-000000000003', GROUP = '01990000-0000-7000-8000-000000000004';
export const page = { limit: 25, has_more: false, next_cursor: null };
/** Public metadata exported from the native API; contains no actor or business data. */
export function form(resource: AccountingResource, operation = 'create'): AccountingForm {
  const result = structuredClone(fields[resource]) as AccountingForm;
  result.operation = operation as AccountingForm['operation'];
  if (operation === 'read') result.fields.forEach(field => { field.editable = false; });
  if (operation === 'update') result.fields.forEach(field => { if (['code', 'party_id', 'account_id', 'payment_term_id', 'group_id'].includes(field.key)) field.editable = false; });
  return result;
}
export function record(resource: AccountingResource = 'parties'): AccountingRecord {
  const values = Object.fromEntries(form(resource).fields.map(field => [field.key, field.initial ?? null]));
  const overrides = { code: 'RETAIL', name: 'Retail supplier', legal_name: 'Retail supplier LLP', country_code: 'IN', party_id: resource === 'accounts' ? null : PARTY, account_id: ID, offset_account_id: GROUP, group_id: GROUP, payment_term_id: ID, currency: 'INR', kind: resource === 'accounts' ? 'GENERAL' : values.kind, party_role: null, role: 'SUPPLIER', label: 'Primary', alias: 'Primary alias', deductee_type: 'COMPANY', rate_percent: '2.0000', no_pan_rate_percent: '20.0000', rate: '5.0000', method: 'INTEREST', accrual_start_date: '2030-01-01', tax_treatment: 'NON_TAXABLE', tax_reason: 'Reviewed non-taxable charge', valid_from: '2030-01-01', source_reference: 'Reviewed official source', source_url: 'https://incometaxindia.gov.in/pages/acts/income-tax-act.aspx', source_sha256: 'a'.repeat(64) };
  return { ...values, ...Object.fromEntries(Object.entries(overrides).filter(([key]) => key in values)), id: ID, company_id: COMPANY, row_version: 3, created_at: '2026-10-25T00:00:00Z', ...(form(resource).lifecycle === 'status' ? { status: 'DRAFT' } : {}), ...(resource === 'party-bank-accounts' ? { account_number_last4: '4321' } : {}) };
}
export const preview = { version: 'base-v1', content_hash: 'a'.repeat(64), groups: ['SALES', 'PURCHASES'], accounts: ['GENERAL_SALES'], conflicts: [], installed: false };
export function response(path: string, method = 'GET', body: unknown = {}) {
  const url = new URL(path, 'https://console.invalid'), parts = url.pathname.split('/').filter(Boolean), resource = parts[3] as AccountingResource;
  if (resource === 'exchange-rates' as string) {
    if (parts[4] === 'context') return { company_id: COMPANY, base_currency: 'INR', allowed_currencies: ['USD'], multi_currency: true };
    const quote = { id: ID, company_id: COMPANY, row_version: 1, from_currency: 'USD', to_currency: 'INR', purpose: 'ACCOUNTING', effective_date: '2030-01-01', rate: '83.123456789012', source_kind: 'MANUAL', source_reference: 'Reviewed bank quotation', source_sha256: 'a'.repeat(64), status: 'CANDIDATE', created_by: PARTY, approved_by: null, approved_at: null, approval_reason: null, withdrawn_by: null, withdrawn_at: null, withdrawal_reason: null };
    return parts[4] ? quote : { items: [quote], page };
  }
  if (resource === 'configuration' as string) {
    if (parts[4] === 'options') { const source = parts[5], value = url.searchParams.get('value'); return { items: [{ value: value ?? (['countries', 'currencies', 'states'].includes(source) ? source === 'countries' ? 'IN' : source === 'currencies' ? 'INR' : 'MH' : source === 'parties' ? PARTY : GROUP), label: source === 'countries' ? 'India' : source === 'currencies' ? 'Indian rupee' : 'General reference', code: 'GENERAL' }], page }; }
    return form(parts[4] as AccountingResource, url.searchParams.get('operation') ?? 'read');
  }
  if (resource === 'history' as string) return { items: [{ id: ID, object_version: 3, action: 'updated', changed_fields: ['name'], created_at: '2026-10-25T00:00:00Z' }], page };
  if (resource === 'accounting-setup') {
    if (parts[4] === 'preview') return preview;
    if (parts[4] === 'install') return { installation_id: ID, groups_created: 2, accounts_created: 1, groups_updated: 0 };
    if (parts[4] === 'initialize') return record(resource);
    return { items: [], page };
  }
  if (resource === 'bank-accounts' as string || resource === 'tax-registrations' as string) { const row = { id: ID, company_id: COMPANY, label: 'Company settlement bank', bank_name: 'Local bank', tax_system: 'GST', jurisdiction_code: 'IN', number: '27TEST0000A1ZZ' }; return parts[4] ? row : { items: [row], page }; }
  if (resource === 'tax-rules' as string) return { id: ID, company_id: COMPANY, code: 'REVIEWED', name: 'Reviewed GST rule' };
  if (resource === 'option-sources' as string) return { items: [{ value: ID, label: 'Reviewed GST rule', code: 'REVIEWED' }], page };
  if (resource === 'parties' && parts[4] === 'create-with-details' && method === 'POST')
    return { ...record('parties'), ...(body as object), row_version: 2, status: 'ACTIVE' };
  if (method === 'POST' || method === 'PATCH') return { ...record(resource), ...body as object, row_version: method === 'PATCH' ? 4 : parts[5] ? 4 : 1, status: parts[5] === 'activate' ? 'ACTIVE' : parts[5] === 'deactivate' ? 'INACTIVE' : 'DRAFT' };
  return parts[4] ? record(resource) : { items: [record(resource)], page };
}
