import fields from './tax-fields.json';
import type { TaxField, TaxRow } from '../app/lib/tax-masters';
import type { ServiceRequest } from '../app/lib/service-call';

export const COMPANY = '01990000-0000-7000-8000-000000000001', CATEGORY = '01990000-0000-7000-8000-000000000002', RULE = '01990000-0000-7000-8000-000000000003', SERIES = '01990000-0000-7000-8000-000000000004', RATE = '01990000-0000-7000-8000-000000000005', CLASSIFICATION = '01990000-0000-7000-8000-000000000006', FRESH = '01990000-0000-7000-8000-000000000007';
export const context = { company_id: COMPANY, country_code: 'IN', default_tax_system: 'gst_in', timezone: 'Asia/Kolkata', business_date: '2026-10-25', policy_generation: 10, source_version: 50 };
export const page = { limit: 50, has_more: false, next_cursor: null };
export const evidence = { source_reference: 'Synthetic fixture, not a statutory rate', source_url: 'https://cbic.gov.in/document.pdf', source_sha256: 'ab'.repeat(32) };
const base = { company_id: COMPANY, row_version: 4, created_at: '2026-10-25T00:00:00Z', updated_at: '2026-10-25T00:00:00Z' };
export const category: TaxRow = { ...base, id: CATEGORY, code: 'TEST', name: 'Test category', is_active: true };
export const rule: TaxRow = { ...base, ...evidence, id: RULE, code: 'TEST', name: 'Test rule', is_active: true, tax_category_id: CATEGORY, item_kind: 'GOODS', treatment: 'TAXABLE', classification_scope: 'SPECIFIC', tax_system: 'gst_in', jurisdiction: 'IN' };
export const series: TaxRow = { ...base, id: SERIES, rule_id: RULE, applicability: 'INTRA_STATE' };
export const rate: TaxRow = { ...base, ...evidence, id: RATE, series_id: SERIES, valid_from: '2026-11-01', valid_to: null };
export const classification: TaxRow = { ...base, ...evidence, id: CLASSIFICATION, code_system: 'HSN', code: '1234', item_kind: 'GOODS', jurisdiction: 'IN', description: 'Synthetic classification', valid_from: '2026-11-01', valid_to: null };
export function taxFields(entity: string, update = false): TaxField[] {
  return (fields as Record<string, TaxField[]>)[entity]!.map(field => ({ ...field, writable: field.writable && (!update || ['catalog.tax_category', 'catalog.tax_rule'].includes(entity) && ['name', 'is_active'].includes(field.key)) }));
}
export function fixtureResponse(request: ServiceRequest): unknown {
  const path = new URL(request.path, 'https://api.invalid'), resource = path.pathname.split('/')[4];
  if (request.path.includes('/entities/')) {
    const entity = path.pathname.split('/entities/')[1]!.split('/')[0]!;
    return { company_id: COMPANY, entity_type: entity, source_version: 50, fields: taxFields(entity, path.searchParams.get('operation') === 'update') };
  }
  if (resource === 'tax-administration') return context;
  if (resource === 'tax-rate-previews') { const body = request.body as Record<string, unknown>; return { valid: true, series_id: body.series_id, applicability: 'INTRA_STATE', treatment: 'TAXABLE', policy_generation: 10, source_version: 50, components: body.components }; }
  if (request.method === 'POST' || request.method === 'PATCH') return { id: request.method === 'PATCH' ? path.pathname.split('/').at(-1)! : FRESH, row_version: 5, policy_generation: 11, source_version: 50 };
  const row = resource === 'tax-categories' ? category : resource === 'tax-rules' ? rule : resource === 'tax-rate-series' ? series : resource === 'tax-rates' ? rate : resource === 'tax-classifications' ? classification : null;
  if (path.pathname.split('/').length === 6 && row) return row;
  if (resource === 'tax-rate-components') return { items: ['CGST', 'SGST'].map((component, index) => ({ ...base, id: '01990000-0000-7000-8000-' + String(index + 20).padStart(12, '0'), rate_id: RATE, component_key: component, component, kind: 'PERCENT', percentage: '2.5', amount: null, basis_quantity: null, rounding_mode: 'HALF_UP', position: index })), page };
  return { items: row ? [row] : [], page };
}
