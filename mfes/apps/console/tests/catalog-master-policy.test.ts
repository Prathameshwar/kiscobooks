import { describe, expect, it } from 'vitest';
import { allowedProductRequest as allowed } from '../app/lib/product-request-policy';
const base = '/v1/companies/01900000-0000-7000-8000-000000000001';
const id = '01900000-0000-7000-8000-000000000002';
describe('Catalog master proxy boundary', () => {
  it.each(['units', 'manufacturers', 'item-groups'])('allows the %s workflows', resource => {
    expect(allowed('catalog', 'POST', `${base}/${resource}`)).toBe(true);
    expect(allowed('catalog', 'PATCH', `${base}/${resource}/${id}`)).toBe(true);
    expect(allowed('catalog', 'POST', `${base}/${resource}/${id}/deactivate`)).toBe(true);
    expect(allowed('catalog', 'DELETE', `${base}/${resource}/${id}`)).toBe(false);
  });
  it('accepts master metadata without unsupported object scope', () => {
    expect(allowed('catalog', 'GET', `${base}/entities/catalog.manufacturer/field-set?operation=create`)).toBe(true);
    expect(allowed('catalog', 'GET', `${base}/entities/catalog.manufacturer/field-set?operation=update&object_id=${id}`)).toBe(false);
  });
  it.each(['?is_active=true&is_active=false', '?tenant_id=other', '?limit=201', '?dimension=OTHER', '?q=x'])('rejects invalid or ambiguous query %s', query => {
    expect(allowed('catalog', 'GET', `${base}/units${query}`)).toBe(false);
  });
  it('rejects query on writes, malformed IDs and unsupported routes', () => {
    expect(allowed('catalog', 'POST', `${base}/units?is_active=true`)).toBe(false);
    expect(allowed('catalog', 'POST', `${base}/units/${'-'.repeat(36)}/activate`)).toBe(false);
    expect(allowed('catalog', 'POST', `${base}/manufacturers/${id}/reparent`)).toBe(false);
    expect(allowed('catalog', 'POST', `${base}/item-groups/${id}/reparent`)).toBe(true);
  });
});
