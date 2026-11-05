import { describe, expect, it } from 'vitest';
import { allowedProductRequest } from '../app/lib/product-request-policy';
const id = '01900000-0000-7000-8000-000000000001';
const root = `/v1/companies/${id}`;
describe('BOM proxy contracts', () => {
  it('admits only native scoped authoring and non-posting reads', () => {
    for (const [method, path] of [
      ['GET', '/boms/authoring-context'], ['GET', '/boms/options/goods?q=SKU'],
      ['GET', `/boms/options/units?item_id=${id}&as_of=2090-01-01`],
      ['POST', `/boms/${id}/drafts`], ['PATCH', `/boms/${id}/drafts/${id}`],
      ['POST', `/boms/${id}/drafts/${id}/publish`], ['POST', `/boms/${id}/revisions/${id}/retire`],
      ['GET', `/boms/${id}/drafts/${id}/components?limit=200&sort=sequence,id`],
      ['POST', `/boms/${id}/drafts/${id}/preview`], ['POST', '/bom-assignments'],
      ['GET', `/bom-assignments/resolve?item_id=${id}&as_of=2090-01-01`],
    ]) expect(allowedProductRequest('catalog', method!, root + path)).toBe(true);
  });
  it('closes unsupported execution, partial writes, malformed scope and arbitrary filters', () => {
    for (const [method, path] of [
      ['POST', `/boms/${id}/execute`], ['POST', `/boms/${id}/revisions`],
      ['PATCH', `/boms/${id}/revisions/${id}`], ['POST', `/boms/${id}/revisions/${id}/publish`],
      ['POST', `/boms/${id}/drafts/${id}/retire`], ['POST', `/boms/${id}/drafts/${id}/components`],
      ['DELETE', `/boms/${id}`], ['GET', '/boms?tenant_id=other'], ['GET', '/boms?limit=1&limit=2'],
      ['GET', '/boms/options/units'], ['GET', '/boms/options/goods?kind=SERVICE'],
      ['GET', '/bom-assignments/resolve'], ['GET', '/boms/options/units?item_id=bad&as_of=2090-01-01'],
    ]) expect(allowedProductRequest('catalog', method!, root + path)).toBe(false);
    expect(allowedProductRequest('identity', 'POST', root + '/boms')).toBe(false);
  });
});
