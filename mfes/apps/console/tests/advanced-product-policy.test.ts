import { expect, it } from 'vitest';
import { allowedProductRequest } from '../app/lib/product-request-policy';
const company = '11111111-1111-4111-8111-111111111111';
const draft = '22222222-2222-4222-8222-222222222222';
const root = `/v1/companies/${company}/advanced-product-creations`;
it('allows only the reviewed options and actor-scoped draft transport paths', () => {
  expect(allowedProductRequest('catalog', 'GET', root + '/options?kind=GOODS')).toBe(true);
  expect(allowedProductRequest('catalog', 'GET', root + `/options?kind=SERVICE&product_type_revision_id=${draft}`)).toBe(true);
  expect(allowedProductRequest('catalog', 'GET', root + '/drafts')).toBe(true);
  expect(allowedProductRequest('catalog', 'POST', root + '/drafts')).toBe(true);
  expect(allowedProductRequest('catalog', 'PUT', root + '/drafts/' + draft)).toBe(true);
  for (const path of [root + '/options?kind=BOGUS', root + '/options?kind=GOODS&kind=SERVICE', root + '/options?group_id=evil', root + '/drafts/../other', root + '/definitions', root + '/drafts/' + draft + '?scope=all']) expect(allowedProductRequest('catalog', 'GET', path)).toBe(false);
  expect(allowedProductRequest('catalog', 'PATCH', root + '/drafts/' + draft)).toBe(false);
});
