import { expect, it } from 'vitest';
import { masterConfig } from '../app/lib/catalog-masters';
import { catalogBack, catalogReceipt, classificationBody, nativeCatalogBody, validateTypeRequirements } from '../app/lib/product-classification';
import { typeRevisionDefaults } from '../app/lib/product-classification-resources';
import { configBack } from '../app/lib/product-configuration';
import { COMPANY, RECORD, SOURCE, fields, record } from './product-classification-fixtures';
it('preserves exact SKU quantities and protected fields on partial edits', () => {
  const config = masterConfig('items')!,
    meta = fields(config.entity, 'update'),
    old = record('items');
  const result = classificationBody(
    config,
    meta,
    { ...old, name: 'Updated SKU', min_sale_quantity: '900719925474099.0001' },
    old,
  );
  expect(result.errors).toEqual({});
  expect(result.body).toEqual({
    expected_version: 4,
    name: 'Updated SKU',
    min_sale_quantity: '900719925474099.0001',
  });
  const protectedFields = meta.map((field) =>
    field.key === 'min_sale_quantity'
      ? { ...field, visible: false, writable: false }
      : field,
  );
  expect(
    classificationBody(
      config,
      protectedFields,
      { ...old, name: 'Updated SKU', min_sale_quantity: 'bogus' },
      old,
    ).body,
  ).toEqual({ expected_version: 4, name: 'Updated SKU' });
});
it.each(['0', '-1', '1.00001', '1e4', 'NaN', '1000000000000000'])(
  'rejects invalid exact quantity %s',
  (value) => {
    const config = masterConfig('items')!,
      old = record('items');
    expect(
      classificationBody(
        config,
        fields(config.entity, 'update'),
        { ...old, min_sale_quantity: value },
        old,
      ).errors.min_sale_quantity,
    ).toBeTruthy();
  },
);
it('validates native codes and dependent country, state and series references', () => {
  for (const code of ['small', '-BAD', 'BAD CODE'])
    expect(
      classificationBody(
        masterConfig('brands')!,
        fields('catalog.brand', 'create'),
        { code, name: 'Brand' },
      ).errors.code,
    ).toBeTruthy();
  const site = record('manufacturer-sites');
  expect(
    classificationBody(
      masterConfig('manufacturer-sites')!,
      fields('catalog.manufacturer_site', 'update'),
      { ...site, state_code: 'US-CA' },
      site,
    ).errors.state_code,
  ).toBeTruthy();
  const family = record('product-families');
  expect(
    classificationBody(
      masterConfig('product-families')!,
      fields('catalog.product_family', 'update'),
      { ...family, brand_id: null, series_id: SOURCE },
      family,
    ).errors.series_id,
  ).toBeTruthy();
});
it('enforces type requirement combinations and keeps exact ratio strings', () => {
  expect(validateTypeRequirements(typeRevisionDefaults, 'SERVICE')).toEqual({});
  expect(
    validateTypeRequirements(
      { ...typeRevisionDefaults, inventory_modes: ['STOCK'] },
      'SERVICE',
    ).inventory_modes,
  ).toBeTruthy();
  expect(
    validateTypeRequirements(
      {
        ...typeRevisionDefaults,
        tracking_modes: ['SERIAL'],
        unit_dimensions: ['MASS'],
      },
      'GOODS',
    ).unit_dimensions,
  ).toBeTruthy();
  expect(
    validateTypeRequirements(
      { ...typeRevisionDefaults, require_expiry: true },
      'GOODS',
    ).require_expiry,
  ).toBeTruthy();
  const meta = fields('catalog.item_unit_revision', 'create');
  expect(
    nativeCatalogBody(meta, ['numerator', 'denominator'], {
      numerator: '9223372036854775807',
      denominator: '1',
    }).body.numerator,
  ).toBe('9223372036854775807');
  expect(
    nativeCatalogBody(meta, ['numerator'], { numerator: '9223372036854775808' })
      .errors.numerator,
  ).toBeTruthy();
});
it('fails closed on unverifiable receipts and retains safe product return navigation', () => {
  expect(() =>
    catalogReceipt(
      { ...record('brands'), company_id: SOURCE },
      COMPANY,
      RECORD,
    ),
  ).toThrow();
  expect(() =>
    catalogReceipt(
      { ...record('brands'), row_version: undefined },
      COMPANY,
      RECORD,
    ),
  ).toThrow();
  for (const path of [
    'https://evil.invalid',
    '//evil.invalid',
    '/masters/items/../../escape',
    '/masters/%69tems',
  ])
    expect(catalogBack(path)).toBe('/settings');
  expect(
    catalogBack(
      '/masters/items/' +
        RECORD +
        '?returnTo=' +
        encodeURIComponent('/masters/items?status=DRAFT'),
    ),
  ).toBe('/settings');
  expect(configBack('/masters/items/' + RECORD)).toBe(
    '/products/configuration',
  );
});
