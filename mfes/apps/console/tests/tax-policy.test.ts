import { describe, expect, it } from 'vitest';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import { taxBody, taxConfig, taxInitial, taxLink, taxReturn } from '../app/lib/tax-masters';
import { initialTaxComponents, taxComponentsBody } from '../app/lib/tax-rate-form';
import { COMPANY, CATEGORY, RATE, context, evidence, taxFields } from './tax-fixtures';

const root = '/v1/companies/' + COMPANY;
describe('tax proxy boundary and navigation', () => {
  it.each(['tax-categories', 'tax-rules', 'tax-classifications', 'tax-rates', 'tax-rate-series', 'tax-rate-components', 'tax-rule-applicabilities', 'tax-history-actions'])('allows only supported reads for %s', resource => {
    expect(allowedProductRequest('catalog', 'GET', root + '/' + resource + '?limit=50&sort=-id')).toBe(true);
    expect(allowedProductRequest('catalog', 'DELETE', root + '/' + resource + '/' + RATE)).toBe(false);
    expect(allowedProductRequest('catalog', 'GET', root + '/' + resource + '?limit=50&limit=10')).toBe(false);
    expect(allowedProductRequest('catalog', 'GET', root + '/' + resource + '?unknown=1')).toBe(false);
  });
  it.each(['//evil.invalid/path', '/v1/companies/' + COMPANY + '/tax-rules/%2f', root + '/tax-rules?limit=201', root + '/tax-rules?sort=source_sha256', root + '/tax-rates?q=ab', root + '/tax-classifications?is_active=true'])('rejects unsupported request %s', path => expect(allowedProductRequest('catalog', 'GET', path)).toBe(false));
  it('permits publication and metadata but never immutable patching', () => {
    expect(allowedProductRequest('catalog', 'POST', root + '/tax-rates')).toBe(true);
    expect(allowedProductRequest('catalog', 'POST', root + '/tax-withdrawals')).toBe(true);
    expect(allowedProductRequest('catalog', 'POST', root + '/tax-rate-previews')).toBe(true);
    expect(allowedProductRequest('catalog', 'GET', root + '/entities/catalog.tax_rate/field-set?operation=create')).toBe(true);
    expect(allowedProductRequest('catalog', 'PATCH', root + '/tax-rates/' + RATE)).toBe(false);
    expect(allowedProductRequest('catalog', 'GET', root + '/tax-administration?ignored=true')).toBe(false);
  });
  it('preserves filtered directories and the related-page parent chain', () => {
    const origin = '/tax/rules?q=TEST&is_active=true';
    const detail = taxLink('/tax/rules/' + RATE, origin);
    expect(taxReturn(detail)).toBe(detail);
    expect(new URL(taxLink('/tax/rates?series_id=' + RATE, detail), 'https://console.invalid').searchParams.get('returnTo')).toBe(detail);
    expect(taxReturn('//evil.invalid')).toBe('/tax'); expect(taxReturn('/tax/rates/new')).toBe('/tax');
    expect(taxReturn('/tax/rules?q=x&limit=999&sort=source_url')).toBe('/tax/rules');
  });
});
describe('strict tax form payloads', () => {
  it.each(['categories', 'classifications', 'rules'])('validates required native inputs for %s', key => {
    const config = taxConfig(key)!;
    expect(Object.keys(taxBody(config, taxFields(config.entity), taxInitial(config, context.business_date), context).errors).length).toBeGreaterThan(0);
  });
  it('sends only editable category fields and preserves the expected version', () => {
    const config = taxConfig('categories')!, previous = { id: CATEGORY, row_version: 4, code: 'TEST', name: 'Before', is_active: true };
    expect(taxBody(config, taxFields(config.entity, true), { ...previous, code: 'ATTACK', name: 'After' }, context, previous).body).toEqual({ name: 'After', is_active: true, expected_version: 4 });
  });
  it('preserves a protected status while changing an allowed name', () => {
    const config = taxConfig('categories')!, previous = { id: CATEGORY, row_version: 4, name: 'Before', is_active: true };
    const fields = taxFields(config.entity, true).map(field => ({ ...field, writable: field.writable && field.key !== 'is_active' }));
    expect(taxBody(config, fields, { name: 'After', is_active: false }, context, previous).body).toEqual({ name: 'After', is_active: true, expected_version: 4 });
  });
  it('rejects unofficial evidence, invalid codes and backdated replacements', () => {
    const config = taxConfig('classifications')!;
    const result = taxBody(config, taxFields(config.entity), { ...taxInitial(config, context.business_date), ...evidence, source_url: 'https://example.com/document.pdf', code: '9912', description: 'Test' }, context, { id: RATE, row_version: 4 }, true);
    expect(result.errors).toMatchObject({ source_url: expect.any(String), code: expect.any(String), valid_from: expect.any(String) });
  });
  it('requires full access rather than supplying protected values', () => {
    const config = taxConfig('categories')!;
    const fields = taxFields(config.entity).map(field => ({ ...field, writable: field.key !== 'code' }));
    const result = taxBody(config, fields, { code: 'TEST', name: 'Test' }, context);
    expect(result.body).not.toHaveProperty('code');
  });
  it('keeps exact decimals as strings and enforces paired GST components', () => {
    const fields = taxFields('catalog.tax_rate_component'), rows = initialTaxComponents('INTRA_STATE').map(row => ({ ...row, percentage: '2.5000' }));
    const result = taxComponentsBody(rows, fields, 'INTRA_STATE', 'TAXABLE');
    expect(result.errors).toEqual({}); expect(result.components[0]?.percentage).toBe('2.5000');
    expect(taxComponentsBody([{ ...rows[0]!, percentage: '2.5' }, { ...rows[1]!, percentage: '3' }], fields, 'INTRA_STATE', 'TAXABLE').errors.components).toBeTruthy();
  });
  it.each(['1e-2', '-1', '0.00001', 'NaN', '21'])('rejects invalid GST percentage %s', percentage => {
    const rows = initialTaxComponents('INTRA_STATE').map(row => ({ ...row, percentage }));
    expect(Object.keys(taxComponentsBody(rows, taxFields('catalog.tax_rate_component'), 'INTRA_STATE', 'TAXABLE').errors).length).toBeGreaterThan(0);
  });
  it('requires zero rates for nil-rated rules and positive GST for taxable rules', () => {
    const fields = taxFields('catalog.tax_rate_component'), rows = initialTaxComponents('INTER_STATE', true);
    expect(taxComponentsBody(rows, fields, 'INTER_STATE', 'NIL_RATED').errors).toEqual({});
    expect(taxComponentsBody(rows, fields, 'INTER_STATE', 'TAXABLE').errors.components).toBeTruthy();
    expect(taxComponentsBody([...rows, { ...rows[0]!, component: 'CESS', component_key: 'CESS', percentage: '1' }], fields, 'INTER_STATE', 'NIL_RATED').errors.components).toBeTruthy();
  });
});
