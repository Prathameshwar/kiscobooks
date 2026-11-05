import { describe, expect, it } from 'vitest';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import { structureReturn, structureLink, structureReceipt } from '../app/lib/warehouse-structure';

const company = '01990000-0000-7000-8000-000000000001', id = '01990000-0000-7000-8000-000000000002', base = '/v1/companies/' + company;
describe('closed warehouse structure proxy', () => {
  it.each(['warehouse-groups', 'warehouse-bins'])('allows native %s CRUD and lifecycle', resource => {
    for (const [method, suffix] of [['GET', ''], ['POST', ''], ['GET', '/' + id], ['PATCH', '/' + id], ['POST', '/' + id + '/activate'], ['POST', '/' + id + '/deactivate']]) expect(allowedProductRequest('catalog', method!, base + '/' + resource + suffix)).toBe(true);
    expect(allowedProductRequest('catalog', 'DELETE', base + '/' + resource + '/' + id)).toBe(false);
  });
  it.each(['warehouse_group', 'warehouse_bin', 'warehouse_group_parent', 'warehouse_group_assignment'])('allows protected %s fields', entity => expect(allowedProductRequest('catalog', 'GET', base + '/entities/catalog.' + entity + '/field-set?operation=update')).toBe(true));
  it.each([['PUT', '/warehouses/' + id + '/primary-group'], ['GET', '/warehouses/' + id + '/group-history?limit=25&sort=-valid_from'], ['POST', '/warehouse-groups/' + id + '/reparent'], ['GET', '/warehouse-groups/' + id + '/parents?valid_at=2026-10-25'], ['GET', '/warehouse-groups/' + id + '/members?valid_at=2026-10-25'], ['GET', '/warehouse-groups/' + id + '/children?valid_at=2026-10-25'], ['GET', '/warehouse-structure?resource=bins']])('supports %s %s', (method, suffix) => expect(allowedProductRequest('catalog', method, base + suffix)).toBe(true));
  it.each(['/warehouse-structure', '/warehouse-structure?resource=other', '/warehouse-groups?q=a', '/warehouse-bins?limit=201', '/warehouse-bins?limit=25&limit=50', '/warehouse-groups/' + id + '/parents?q=test', '/warehouse-groups/' + id + '/children', '/warehouse-groups/' + id + '/members?valid_at=2026-02-30', '/warehouse-bins/' + id + '/parents', '/warehouse-bins/' + id + '/reparent', '/warehouse-groups?warehouse_id=' + id, '/warehouses/' + id + '/group-history?unknown=1', '/warehouse-bins?warehouse_id=bad'])('rejects unsupported %s', suffix => expect(allowedProductRequest('catalog', 'GET', base + suffix)).toBe(false));
  it('does not grant another service access', () => expect(allowedProductRequest('identity', 'GET', base + '/warehouse-groups')).toBe(false));
});
describe('warehouse return links and receipts', () => {
  it('preserves directory filters and warehouse scope', () => {
    const back = '/masters/warehouse-bins?warehouse_id=' + id + '&q=rack&is_active=true&limit=25'; expect(structureReturn(back)).toBe(back); expect(structureLink('/masters/warehouse-bins/' + id, back)).toContain('returnTo=');
  });
  it('preserves the directory through detail and edit back links', () => {
    const directory = '/masters/warehouse-bins?warehouse_id=' + id + '&q=rack';
    const detail = structureLink('/masters/warehouse-bins/' + id, directory);
    expect(new URL(structureReturn(detail), 'https://console.invalid').searchParams.get('returnTo')).toBe(directory);
  });
  it.each(['https://evil.example', '//evil.example', '/masters/warehouses/../users', '/masters/warehouse-bins%2Fnew', '/masters/warehouse-bins#bad', '/organisation'])('rejects unsafe return %s', value => expect(structureReturn(value)).toBe('/masters/warehouses'));
  it('verifies company, object and advancing version', () => {
    expect(() => structureReceipt({ id, company_id: company, row_version: 5 }, company, id, 4)).not.toThrow();
    for (const row of [{ id, company_id: id, row_version: 5 }, { id, company_id: company, row_version: 4 }, { id, company_id: company }, { id: 'bad', company_id: company, row_version: 5 }]) expect(() => structureReceipt(row, company, id, 4)).toThrow();
  });
});
