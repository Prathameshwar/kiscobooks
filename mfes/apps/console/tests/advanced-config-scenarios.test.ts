import { afterAll, expect, it } from 'vitest';
import { writeFileSync } from 'node:fs';
import { fixture, id, PLAN } from './advanced-config-scenarios-fixtures';
import { profileErrors, skuErrors, newSku } from '../app/lib/advanced-product-draft';
import { businessErrors, businessSku, putBusiness } from '../app/lib/advanced-product-business';
import { openingErrors, openingSku, putOpening } from '../app/lib/advanced-product-opening';
import { definitionBody, setupBody, openingBody } from '../app/lib/advanced-product-api';

// Optional evidence export lets the local native schemas check these exact client bodies.
afterAll(() => {
  if (!process.env.ADVANCED_SCENARIO_WIRE_PATH) return;
  const cases = Array.from({ length: 10 }, (_, i) => {
    const { work, options } = fixture(i + 1);
    return { scenario: i + 1, definition: definitionBody(work, options), setup: work.skus.map((_, n) => setupBody(work, options, n, 1, 1, 1)), opening: work.skus.map((_, n) => openingBody(work, n)) };
  });
  writeFileSync(process.env.ADVANCED_SCENARIO_WIRE_PATH, JSON.stringify(cases, null, 2));
});

it.each([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])('scenario %i accepts valid configuration and keeps exact native payloads', number => {
  const { work, options } = fixture(number);
  expect(profileErrors(work, options)).toEqual({});
  expect(skuErrors(work, options)).toEqual({});
  expect(businessErrors(work, options)).toEqual({});
  expect(openingErrors(work, options)).toEqual({});
  expect(definitionBody(work, options).skus).toHaveLength(work.skus.length);
  work.skus.forEach((sku, i) => {
    const setup = setupBody(work, options, i, 1, 1, 1);
    expect(setup.setup.units![0]!.unit_id).toBe(sku.base_unit_id);
    const business = businessSku(work, sku);
    if (business.purchase_amount) expect(setup.purchase_reference?.amount).toBe(business.purchase_amount);
    if (business.mrp_amount) expect(setup.mrp?.amount).toBe(business.mrp_amount);
    const opening = openingBody(work, i);
    if (opening.decision === 'OPEN') {
      expect(opening.opening_date).toBe('2026-04-01');
      if (number === 2 || number === 9) expect(opening).toMatchObject({ opening_quantity: '20', opening_unit_cost: '80.00' });
      if (number === 5) expect(opening.batches).toMatchObject([{ opening_quantity: '10', opening_unit_cost: '50.00', purchase_price: '60.00' }, { opening_quantity: '20', opening_unit_cost: '55.00', purchase_price: '65.00' }]);
      if (number === 6) expect(opening.serials).toHaveLength(2);
      if (number === 7) expect(opening).toMatchObject({ opening_quantity: '12.345', opening_unit_cost: '42.50' });
    }
  });
});

it('01 rejects retained disabled profile assignments before definition creation', () => {
  const { work, options } = fixture(1);
  work.profile.brand_id = id(10); work.profile.model_code = 'old'; work.profile.manufacturer_id = id(11);
  work.profile.categories = [{ key: 'old', scheme_id: id(12), category_id: id(13), is_primary: true }];
  expect(profileErrors(work, options)).toMatchObject({ brand_id: expect.any(String), model_code: expect.any(String), manufacturer_id: expect.any(String), categories: expect.any(String) });
});

it('02 identifies missing price sources, MRP jurisdiction, cost and wrong opening date', () => {
  let { work, options } = fixture(2);
  work = putBusiness(work, work.skus[0]!, { ...businessSku(work, work.skus[0]!), purchase_source: '', mrp_source: '', mrp_jurisdiction: '' });
  expect(businessErrors(work, options)).toMatchObject({ 'business.skus.0.purchase_source': expect.any(String), 'business.skus.0.mrp_source': expect.any(String), 'business.skus.0.mrp_jurisdiction': expect.any(String) });
  work = putOpening(work, work.skus[0]!, { ...openingSku(work, work.skus[0]!), opening_date: '2026-04-02', purchase_price: '' });
  expect(openingErrors(work, options)).toMatchObject({ 'opening.skus.0.opening_date': expect.any(String), 'opening.skus.0.opening_unit_cost': expect.any(String) });
});

it('03 rejects missing configured brand and disabled variant axes even for one SKU', () => {
  const { work, options } = fixture(3);
  work.profile.brand_id = '';
  expect(profileErrors(work, options).brand_id).toBeDefined();
  work.skus = [work.skus[0]!]; options.defaults.configuration.options.variants_mode = 'DISABLED';
  expect(skuErrors(work, options).skus).toBeDefined();
});

it('03 rejects duplicate codes and combinations', () => {
  const { work, options } = fixture(3);
  work.skus[1] = { ...work.skus[0]!, key: 'duplicate' };
  expect(skuErrors(work, options)).toMatchObject({ 'skus.1.sku': expect.any(String), 'skus.1.variants': expect.any(String) });
});

it('04 rejects a Goods-only Type and retained physical MRP for a Service', () => {
  let { work, options } = fixture(4);
  options.selected_type!.kind = 'GOODS';
  expect(profileErrors(work, options).product_type_revision_id).toBeDefined();
  work = putBusiness(work, work.skus[0]!, { ...businessSku(work, work.skus[0]!), mrp_amount: '100', mrp_source: 'old', mrp_jurisdiction: 'IN' });
  expect(businessErrors(work, options)['business.skus.0.mrp_amount']).toBeDefined();
});

it('05 rejects expiry and duplicate batches with specific row errors', () => {
  let { work, options } = fixture(5);
  const opening = openingSku(work, work.skus[0]!);
  opening.batches[1] = { ...opening.batches[1]!, code: opening.batches[0]!.code, expires_on: '2026-02-01' };
  work = putOpening(work, work.skus[0]!, opening);
  expect(openingErrors(work, options)).toMatchObject({ 'opening.skus.0.batches.1.code': expect.any(String), 'opening.skus.0.batches.1.expires_on': expect.any(String) });
});

it('05 rejects saved batch prices whose level is no longer offered', () => {
  const { work, options } = fixture(5);
  options.sale_price_levels = [];
  expect(openingErrors(work, options)['opening.skus.0.batches.0.sale_prices.' + id(6)]).toBeDefined();
});

it('05 rejects invalid calendar dates and normalized duplicate batch codes', () => {
  let { work, options } = fixture(5);
  const opening = openingSku(work, work.skus[0]!);
  opening.batches[0]!.manufactured_on = '2026-02-30';
  opening.batches[1]!.code = 'ＦＯＯＤ－０';
  work = putOpening(work, work.skus[0]!, opening);
  expect(openingErrors(work, options)).toMatchObject({ 'opening.skus.0.batches.0.manufactured_on': expect.any(String), 'opening.skus.0.batches.1.code': expect.any(String) });
});

it('06 rejects duplicated and missing serial identifiers', () => {
  let { work, options } = fixture(6);
  const opening = openingSku(work, work.skus[0]!);
  opening.serials[1]!.identifiers = [...opening.serials[0]!.identifiers];
  work = putOpening(work, work.skus[0]!, opening);
  expect(Object.keys(openingErrors(work, options))).toContain('opening.skus.0.serials.1.identifiers.0.value');
  opening.serials[1]!.identifiers = [];
  work = putOpening(work, work.skus[0]!, opening);
  expect(Object.keys(openingErrors(work, options)).length).toBeGreaterThan(0);
});

it('07 rejects a quantity increment that exceeds its binding precision', () => {
  const { work, options } = fixture(7);
  work.skus[0]!.units[0]!.quantity_increment = '0.005';
  expect(skuErrors(work, options)['skus.0.units.0.grid']).toBeDefined();
});

it('08 respects false/zero attributes and rejects missing required custom fields', () => {
  const { work, options } = fixture(8);
  expect(skuErrors(work, options)).toEqual({});
  options.family_fields.fields.push({ key: 'cf_note', label: 'Product note', source: 'custom', visible: true, writable: true, required: true, conditional_access: false, order: 0, custom: { key: 'cf_note', data_type: 'text', is_active: true, is_immutable_after_create: false, default_value: null, visibility: null, choices: [], validation: { required: true, max_length: 100 } } } as typeof options.family_fields.fields[number]);
  expect(profileErrors(work, options)['custom_fields.cf_note']).toBeDefined();
});

it('08 blocks missing required price levels and denied pricing without inventing defaults', () => {
  const { work, options } = fixture(2);
  options.sale_price_levels = []; options.price_levels_accessible = false;
  expect(businessErrors(work, options)['business.skus.0.sale_prices']).toBeDefined();
});

it('09 rejects retained disabled prices and inactive price plans instead of silently dropping them', () => {
  const { work, options } = fixture(2);
  options.defaults.configuration.pricing.purchase_reference_mode = 'DISABLED'; options.defaults.configuration.pricing.mrp_mode = 'DISABLED'; options.sale_price_levels = [];
  expect(businessErrors(work, options)).toMatchObject({ 'business.skus.0.purchase_amount': expect.any(String), 'business.skus.0.mrp_amount': expect.any(String), [`business.skus.0.sale_prices.${PLAN}`]: expect.any(String) });
});

it('rejects an empty SKU list and more than the bounded SKU count', () => {
  const { work, options } = fixture(3);
  work.skus = [];
  expect(skuErrors(work, options).skus).toBeDefined();
  work.skus = Array.from({ length: 65 }, (_, n) => ({ ...newSku(), sku: `SKU-${n}`, name: 'Bounded', base_unit_id: id(3) }));
  expect(skuErrors(work, options).skus).toBeDefined();
});
