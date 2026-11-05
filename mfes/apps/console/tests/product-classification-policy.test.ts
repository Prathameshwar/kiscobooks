import { expect, it } from 'vitest';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import { classificationResources } from '../app/lib/product-classification-resources';
import { COMPANY, RECORD, SOURCE } from './product-classification-fixtures';
const base = `/v1/companies/${COMPANY}`;
it.each(classificationResources)(
  'allows native %s reads and updates with closed queries',
  (resource) => {
    expect(
      allowedProductRequest(
        'catalog',
        'GET',
        `${base}/${resource}?limit=25&sort=-id`,
      ),
    ).toBe(true);
    expect(
      allowedProductRequest('catalog', 'GET', `${base}/${resource}/${RECORD}`),
    ).toBe(true);
    expect(
      allowedProductRequest(
        'catalog',
        'PATCH',
        `${base}/${resource}/${RECORD}`,
      ),
    ).toBe(true);
    expect(
      allowedProductRequest('catalog', 'POST', `${base}/${resource}`),
    ).toBe(resource !== 'items');
    for (const query of [
      'limit=201',
      'q=x',
      'sort=custom_fields',
      'code=A&code=B',
      'unknown=true',
      'cursor=',
    ])
      expect(
        allowedProductRequest('catalog', 'GET', `${base}/${resource}?${query}`),
      ).toBe(false);
    expect(
      allowedProductRequest(
        'catalog',
        'DELETE',
        `${base}/${resource}/${RECORD}`,
      ),
    ).toBe(false);
    expect(
      allowedProductRequest(
        'catalog',
        'PATCH',
        `${base}/${resource}/${RECORD}?force=true`,
      ),
    ).toBe(false);
  },
);
it('admits reviewed transitions, parent moves, type publication and product setup', () => {
  for (const path of [
    `category-schemes/${RECORD}/transition-preview`,
    `category-schemes/${RECORD}/transition`,
    `brands/${RECORD}/reparent`,
    `item-categories/${RECORD}/reparent`,
    `product-types/${RECORD}/revisions/${SOURCE}/publish`,
    `items/${RECORD}/activation-preview`,
    `items/${RECORD}/activate`,
    `items/${RECORD}/unit-bindings`,
    `items/${RECORD}/barcodes`,
    `product-families/${RECORD}/manufacturers`,
  ])
    expect(allowedProductRequest('catalog', 'POST', base + '/' + path)).toBe(
      true,
    );
  expect(
    allowedProductRequest(
      'catalog',
      'PUT',
      `${base}/product-families/${RECORD}/categories`,
    ),
  ).toBe(true);
  expect(
    allowedProductRequest(
      'catalog',
      'GET',
      `${base}/product-types/${RECORD}/revisions?published=true&sort=-revision&limit=25`,
    ),
  ).toBe(true);
  expect(
    allowedProductRequest(
      'catalog',
      'GET',
      `${base}/items/${RECORD}/requirements?as_of=2026-10-25`,
    ),
  ).toBe(true);
  expect(
    allowedProductRequest(
      'catalog',
      'GET',
      `${base}/items/${RECORD}/configuration-adoption/preview?as_of=2026-10-25`,
    ),
  ).toBe(true);
  expect(
    allowedProductRequest(
      'catalog',
      'GET',
      `${base}/product-configuration/options/attribute-set-revisions?limit=50`,
    ),
  ).toBe(true);
});
it('restricts publication/object metadata and rejects forged route forms', () => {
  expect(
    allowedProductRequest(
      'catalog',
      'GET',
      `${base}/entities/catalog.item/field-set?operation=update&object_id=${RECORD}`,
    ),
  ).toBe(true);
  expect(
    allowedProductRequest(
      'catalog',
      'GET',
      `${base}/entities/catalog.product_type_revision/field-set?operation=publish`,
    ),
  ).toBe(true);
  expect(
    allowedProductRequest(
      'catalog',
      'GET',
      `${base}/entities/catalog.item/field-set?operation=publish`,
    ),
  ).toBe(false);
  expect(
    allowedProductRequest(
      'catalog',
      'GET',
      `${base}/entities/catalog.brand/field-set?operation=update&object_id=${RECORD}`,
    ),
  ).toBe(false);
  for (const path of [
    `brands/${RECORD}/revisions`,
    `items/${RECORD}/deactivate`,
    `product-families/${RECORD}/activate`,
    `brand-series/${RECORD}/reparent`,
    `brands/${RECORD}/edit`,
    `items/${RECORD}/activation-preview?force=true`,
  ])
    expect(allowedProductRequest('catalog', 'POST', base + '/' + path)).toBe(
      false,
    );
});
