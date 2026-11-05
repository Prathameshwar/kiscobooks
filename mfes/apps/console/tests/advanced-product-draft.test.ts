import { expect, it } from 'vitest';
import { newWork, profileErrors, skuErrors, type AdvancedOptions } from '../app/lib/advanced-product-draft';

const id = '11111111-1111-4111-8111-111111111111';
const options = { selected_type: { id, allow_variants: true, require_brand: false }, defaults: { configuration: { options: { variants_mode: 'OPTIONAL' } } }, family_fields: { fields: [{ key: 'name', label: 'Profile name', required: true, visible: true, writable: true }, { key: 'code', label: 'Code', required: true, visible: true, writable: true }] }, sku_fields: { fields: [] } } as unknown as AdvancedOptions;
it('requires a complete native Profile and never treats a hidden required field as optional', () => {
  const work = newWork();
  expect(profileErrors(work, options)).toMatchObject({ name: expect.any(String), code: expect.any(String), product_type_revision_id: expect.any(String), group_id: expect.any(String) });
  work.profile = { ...work.profile, name: 'Tea', code: 'TEA', group_id: id, product_type_revision_id: id };
  expect(profileErrors(work, options)).toEqual({});
  const denied = { ...options, family_fields: { ...options.family_fields, fields: options.family_fields.fields.map(field => field.key === 'code' ? { ...field, writable: false } : field) } };
  expect(profileErrors(work, denied).code).toMatch(/access/);
});
it('detects duplicate codes and duplicate variant signatures before submission', () => {
  const work = newWork();
  work.axes = [{ key: 'axis', definition_id: id, label: 'Size', value_type: 'TEXT', options: [] }];
  work.skus = [
    { ...work.skus[0]!, sku: 'TEA-S', name: 'Tea small', base_unit_id: id, attributes: [{ definition_id: id, option_id: id, value_type: 'TEXT' }] },
    { ...work.skus[0]!, key: 'second', sku: 'TEA-S', name: 'Tea small again', base_unit_id: id, attributes: [{ definition_id: id, option_id: id, value_type: 'TEXT' }] },
  ];
  expect(skuErrors(work, options)).toMatchObject({ 'skus.1.sku': expect.any(String), 'skus.1.variants': expect.any(String) });
  expect(skuErrors(work, { ...options, selected_type: { ...options.selected_type!, allow_variants: false } }).skus).toMatch(/one SKU/);
});
it('requires exact alternate-unit ratios only when enabled', () => {
  const work = newWork();
  work.skus[0] = { ...work.skus[0]!, sku: 'TEA', name: 'Tea', base_unit_id: id };
  const required = { ...options, defaults: { ...options.defaults, configuration: { ...options.defaults.configuration, options: { ...options.defaults.configuration.options, alternate_units_mode: 'REQUIRED' as const } } } };
  expect(skuErrors(work, required)['skus.0.units']).toMatch(/required/);
  work.skus[0]!.units = [{ key: 'one', code: 'BOX', unit_id: id, role: 'PACK', pack_type_id: '', numerator: '1.5', denominator: '0', quantity_decimal_places: '0', quantity_increment: '1' }];
  expect(skuErrors(work, required)).toMatchObject({ 'skus.0.units.0.ratio': expect.any(String), 'skus.0.units.0.pack_type_id': expect.any(String) });
});
