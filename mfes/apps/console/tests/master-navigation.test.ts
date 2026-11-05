import { catalogBack } from '../app/lib/product-classification';
import { expect, it } from 'vitest';
import { masterConfig } from '../app/lib/catalog-masters';
import { masterReturnTo } from '../app/components/CatalogMasterDirectory';
import { identifierReturn } from '../app/lib/units-identifiers';
import { attributeReturn } from '../app/lib/attribute-masters';
import { pricingReturn } from '../app/lib/pricing-masters';
import { profileReturn } from '../app/lib/product-profiles';
import { configBack } from '../app/lib/product-configuration';
import { accountingBack } from '../app/lib/accounting-configuration-resources';
import { RECORD, SOURCE } from './units-identifiers-fixtures';
import {
  catalogRelatedLinks,
  masterReferencePath,
  masterReturn,
  masterRevisionActions,
} from '../app/lib/master-navigation';
import { access } from './product-classification-fixtures';
const family = `/masters/brands/${RECORD}?returnTo=${encodeURIComponent('/masters/brands?q=Basic&sort=name')}`;
it.each([
  [
    'unit detail',
    (value: string) => masterReturnTo(masterConfig('units')!, value),
  ],
  ['identifier', identifierReturn],
  ['classification', catalogBack],
  ['attributes', attributeReturn],
  ['pricing', pricingReturn],
  ['profile', profileReturn],
  ['configuration', configBack],
  ['party', accountingBack],
] as const)(
  'preserves the source classification and its filtered directory from %s',
  (_name, check) => {
    const result = new URL(check(family), 'https://console.invalid');
    expect(result.pathname).toBe('/masters/brands/' + RECORD);
    expect(result.searchParams.get('returnTo')).toBe(
      '/masters/brands?q=Basic&sort=name',
    );
  },
);
it('returns a unit editor to its detail view instead of losing it at the directory', () => {
  const detail = `/masters/units/${SOURCE}?returnTo=${encodeURIComponent('/masters/units?q=Box')}`;
  expect(
    new URL(
      masterReturnTo(masterConfig('units')!, detail),
      'https://console.invalid',
    ).pathname,
  ).toBe('/masters/units/' + SOURCE);
});
it.each([
  'https://example.com/masters/items/' + RECORD,
  '//example.com/masters/items/' + RECORD,
  '/masters/unknown/' + RECORD,
  '/masters/brands/' + RECORD + '/revisions/' + SOURCE,
])('does not admit unsupported or external return pages: %s', (value) => {
  expect(identifierReturn(value, '/masters/units')).toBe('/masters/units');
  expect(catalogBack(value, '/masters/items')).toBe('/masters/items');
});
it('requires a verified native parent to link to published revisions', () => {
  expect(masterReferencePath('product-type-revisions', SOURCE)).toBeNull();
  expect(masterReferencePath('product-type-revisions', SOURCE, RECORD)).toBe(
    '/masters/product-types/' + RECORD + '/revisions/' + SOURCE,
  );
  expect(masterReferencePath('attribute-set-revisions', SOURCE, RECORD)).toBe(
    '/masters/attribute-sets/' + RECORD + '/revisions/' + SOURCE,
  );
  expect(masterReferencePath('warranty-revisions', SOURCE, RECORD)).toBe(
    '/masters/warranty-policies/' + RECORD + '/revisions/' + SOURCE,
  );
  expect(
    masterReferencePath('product-type-revisions', SOURCE, '../../other'),
  ).toBeNull();
  expect(masterReferencePath('constructor', SOURCE, RECORD)).toBeNull();
  expect(masterReferencePath('brands', '../other')).toBeNull();
});
it('keeps filter context while dropping duplicate, unsupported and control-character query values', () => {
  expect(
    masterReturn(
      '/masters/items?family_id=' +
        RECORD +
        '&q=Basic&limit=50&sort=name&token=secret',
    ),
  ).toBe('/masters/items?family_id=' + RECORD + '&q=Basic&limit=50&sort=name');
  expect(
    masterReturn('/masters/brands?q=One&q=Two&sort=constructor&name=%00'),
  ).toBe('/masters/brands');
  expect(masterReturn('/masters/unit-conversions/' + RECORD + '/edit')).toBe(
    '/settings',
  );
  expect(masterReturn('/masters/%62rands/' + RECORD)).toBe('/settings');
});
it('offers related records only with read permission and readable verified references', () => {
  const row = { id: RECORD, family_id: SOURCE, base_unit_id: SOURCE };
  expect(
    catalogRelatedLinks(
      'items',
      row,
      () => false,
      { ...access, attributes: false },
      family,
    ),
  ).toEqual([]);
  expect(
    catalogRelatedLinks(
      'items',
      row,
      () => true,
      {
        ...access,
        items: false,
        units: false,
        'product-families': false,
        attributes: false,
      },
      family,
    ),
  ).toEqual([]);
  const links = catalogRelatedLinks('items', row, () => true, access, family);
  expect(links.map((link) => link.id)).toEqual([
    'related-base_unit_id',
  ]);
  expect(
    new URL(links[0]!.href, 'https://console.invalid').searchParams.get(
      'returnTo',
    ),
  ).toBe(family);
});
it.each([null, '2026-10-25T01:00:00Z', undefined])(
  'limits draft actions to verified editable drafts: %s',
  (published_at) => {
    const root = '/masters/product-types/' + RECORD + '/revisions';
    const row = { id: SOURCE, published_at };
    expect(
      masterRevisionActions(root, row, family, true, false).map(
        (item) => item.id,
      ),
    ).toEqual(published_at === null ? ['view', 'draft'] : ['view']);
    expect(
      masterRevisionActions(root, row, family, false, false).map(
        (item) => item.id,
      ),
    ).toEqual(['view']);
    expect(
      masterRevisionActions(root, row, family, true, true).every(
        (item) => !!item.disabledReason,
      ),
    ).toBe(true);
  },
);
