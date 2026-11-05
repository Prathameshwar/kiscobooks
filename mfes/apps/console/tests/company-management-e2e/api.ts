export const companyId = '01990000-0000-7000-8000-000000000001';
export const yearId = '01990000-0000-7000-8000-000000000002';
const fiscalYear = { id: yearId, company_id: companyId, code: 'FY2026-2027', start_date: '2026-04-01', end_date: '2027-03-31', row_version: 1 };
const periods = Array.from({ length: 12 }, (_, index) => {
  const start = new Date(Date.UTC(2026, 3 + index, 1)), end = new Date(Date.UTC(2026, 4 + index, 0));
  return { id: 'period-' + (index + 1), company_id: companyId, fiscal_year_id: yearId, sequence: index + 1, code: 'P' + (index + 1),
    start_date: start.toISOString().slice(0, 10), end_date: end.toISOString().slice(0, 10), status: 'FUTURE', row_version: 1 };
});
const data: Record<string, unknown> = { id: companyId, display_name: 'Acme Manufacturing', legal_name: 'Acme Manufacturing Private Limited', code: 'ACME-01',
  country_code: 'IN', state_code: 'MH', status: 'active', visibility: 'listed', base_currency: 'INR', entity_type: 'pvt_ltd',
  books_begin_date: '2026-04-01', amount_precision: 2, quantity_precision: 3, default_tax_system: 'gst_in',
  first_posted_at: '2026-04-01T00:00:00Z', updated_at: '2026-10-23T00:00:00Z',
  terms_and_conditions: 'Payment is due within thirty days of the invoice date.',
  custom_fields: { cf_segment: 'Manufacturing' }, default_payment_terms_days: 30 };
const fields = Object.entries({ display_name: 'identity', legal_name: 'identity', code: 'identity', entity_type: 'identity',
  country_code: 'identity', state_code: 'identity', base_currency: 'financial', books_begin_date: 'financial', amount_precision: 'financial', quantity_precision: 'financial',
  default_tax_system: 'tax', default_payment_terms_days: 'commercial', terms_and_conditions: 'branding' }).map(([key, group]) => ({
    key, group, label: key, source: 'native', is_visible: true, writable: !['code', 'country_code', 'state_code', 'base_currency', 'amount_precision', 'quantity_precision'].includes(key),
    required: key !== 'terms_and_conditions', data_type: key === 'terms_and_conditions' ? 'long_text' : key === 'books_begin_date' ? 'date' : key === 'default_payment_terms_days' ? 'integer' : 'string',
    validation: key === 'default_payment_terms_days' ? { min: 0, max: 3650 } : {},
    choices: key === 'entity_type' ? [{ value: 'pvt_ltd', label: 'Private limited company' }] : undefined,
  }));
fields.push({ key: 'custom_field:cf_segment', group: 'custom', label: 'Market segment', source: 'custom', is_visible: true, writable: true, required: false,
  data_type: 'text', validation: {}, choices: undefined, custom: { key: 'cf_segment', data_type: 'text' } } as never);
export async function companyCall(_service: string, path: string, request: { method?: string; body?: Record<string, unknown> } = {}) {
  await new Promise(resolve => setTimeout(resolve, 80));
  if (path.includes('/finance/field-sets/')) return { fields: ['start_year', 'status', 'reason', 'expected_version'].map(key => ({ key, label: key === 'start_year' ? 'Starting year' : key, visible: true, readable: true, writable: true, required: true, definition: {} })) };
  if (path.endsWith('/financial-setup')) return { company_id: companyId, fiscal_year_start_month: 4, fiscal_year_start_day: 1, books_begin_date: '2026-04-01', row_version: 1 };
  if (path.endsWith('/display-config')) return { base_currency: 'INR', date_format: 'dd MMM yyyy', timezone: 'Asia/Kolkata' };
  if (path.endsWith('/fiscal-years/generate')) return fiscalYear;
  if (path.includes('/fiscal-years?')) return { items: [fiscalYear], page: { has_more: false, next_cursor: null } };
  if (path.endsWith('/fiscal-years/' + yearId)) return fiscalYear;
  if (path.includes('/fiscal-periods?')) return { items: periods, page: { has_more: false, next_cursor: null } };
  if (path.endsWith('/transition')) {
    const period = periods.find(item => path.includes('/' + item.id + '/'))!;
    period.status = String(request.body?.status); period.row_version++; return { ...period };
  }
  if (request.method === 'PATCH') { Object.assign(data, request.body); return { ...data }; }
  if (path.includes('/field-set')) return { fields };
  if (path.startsWith('/v1/companies?')) return { items: [{ ...data }], page: { has_more: false, next_cursor: null } };
  if (path === '/v1/reference/countries') return [{ code: 'IN', name: 'India', jurisdiction_supported: true, tax_systems: ['gst_in'] }];
  if (path === '/v1/reference/currencies') return [{ code: 'INR', name: 'Indian rupee' }];
  if (path.endsWith('/states')) return [{ code: 'MH', name: 'Maharashtra' }];
  if (path === '/v1/company-classifications') return { business_categories: [], business_roles: [], store_formats: [] };
  return { ...data };
}
export const companyFailure = (error: unknown) => error;
