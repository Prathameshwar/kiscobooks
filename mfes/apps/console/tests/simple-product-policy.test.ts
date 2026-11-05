import { expect, it } from 'vitest';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import { productImportProfile } from '../app/lib/master-import-profiles';
const company = '01990000-0000-7000-8000-000000000001';
const item = '01990000-0000-7000-8000-000000000002';
const base = `/v1/companies/${company}`;
it.each(['AC/DC', '1/2 inch', 'Dr..Who', 'A\\B'])('allows search punctuation as query data: %s', q => {
  expect(allowedProductRequest('catalog', 'GET', base + '/products?' + new URLSearchParams({ q }))).toBe(true);
});
it.each([
  ['GET', '/products?q=TEA&limit=25&sort=code'],
  ['POST', '/products'],
  ['GET', '/products/field-set?operation=update&object_id=' + item],
  ['GET', '/products/' + item],
  ['PATCH', '/products/' + item],
  ['GET', '/products/' + item + '/attribute-form'],
  ['PUT', '/products/' + item + '/attributes'],
  ['PUT', '/products/' + item + '/categories'],
  ['POST', '/products/' + item + '/category-preview'],
  ['POST', '/products/' + item + '/groups'],
  ['POST', '/products/' + item + '/manufacturers'],
  ['GET', '/product-configuration/authoring'],
  ['PATCH', '/product-configuration/authoring'],
  ['POST', '/product-configuration/authoring/preview'],
  [
    'GET',
    '/entities/catalog.company_product_authoring_configuration/field-set?operation=update',
  ],
])('permits the exact product contract: %s %s', (method, path) => {
  expect(allowedProductRequest('catalog', method!, base + path)).toBe(true);
  expect(allowedProductRequest('identity', method!, base + path)).toBe(false);
});
it.each([
  ['DELETE', '/products/' + item],
  ['POST', '/products/' + item + '/activate'],
  ['PATCH', '/product-configuration/authoring/preview'],
  ['GET', '/products?unknown=1'],
  ['GET', '/products?limit=1&limit=2'],
  ['POST', '/products?sort=code'],
  ['GET', '/products/field-set?operation=read'],
  ['GET', '/products/field-set?object_id=bad'],
  ['GET', '/products/' + item + '?include=all'],
  ['GET', '/products/' + item + '/../../items'],
  ['GET', '/products%2f' + item],
  ['GET', '/products#secret'],
  ['GET', '/products/%2e%2e/products'],
  ['GET', '/products?sort=family_id'],
  ['GET', '/products?limit=0'],
  ['GET', '/products?limit=201'],
  ['GET', '/products?base_unit_id=bad'],
  ['GET', '/products?sellable=1'],
  ['GET', '/products?cursor=%00'],
  ['GET', '/product-configuration/authoring?company_id=' + item],
])('refuses unsupported product transport: %s %s', (method, path) =>
  expect(allowedProductRequest('catalog', method!, base + path)).toBe(false),
);
it('refuses absolute upstream URLs and preserves canonical imported item links', () => {
  expect(
    allowedProductRequest(
      'catalog',
      'GET',
      'https://other.invalid' + base + '/products',
    ),
  ).toBe(false);
  expect(
    productImportProfile.destination('simple_product', item, '/masters/items'),
  ).toContain('/masters/items/' + item);
});
