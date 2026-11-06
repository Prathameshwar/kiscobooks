import { expect, it } from 'vitest';
import { newWork, skuErrors, type AdvancedOptions } from '../app/lib/advanced-product-draft';
import { checkRecoveryIntent, definitionBody, reviseIntent, setupBody } from '../app/lib/advanced-product-api';
import { openingCommand, openingErrors, putOpening } from '../app/lib/advanced-product-opening';

const company = '11111111-1111-4111-8111-111111111111';
const item = '22222222-2222-4222-8222-222222222222';
const creation = '33333333-3333-4333-8333-333333333333';
const unit = '66666666-6666-4666-8666-666666666666';
const options = {
  today: '2026-11-05', books_begin_date: '2026-04-01', currency: 'INR', inventory_enabled: true,
  mode: { row_version: 2, policy_generation: 4 },
  defaults: { configuration: { source_version: 9, policy_generation: 4, options: { barcode_mode: 'OPTIONAL', alternate_units_mode: 'OPTIONAL', variants_mode: 'OPTIONAL' }, pricing: { mrp_mode: 'DISABLED' } }, quantity: { unit_id: unit, quantity_decimal_places: 0, quantity_increment: '1', fractional_entry: false }, price: { price_basis_quantity: '1', price_decimal_places: 2 } },
  batch: { available: true, required: false }, serial: { enabled: true, requirements: [] },
  selected_type: { inventory_modes: ['STOCK'] }, sale_price_levels: [], gst_enabled: false,
  sku_fields: { fields: ['sku', 'name', 'base_unit_id', 'sellable', 'purchasable'].map(key => ({ key, label: key, visible: true, writable: true, conditional_access: false })) },
} as unknown as AdvancedOptions;

function reviewedWork() {
  const work = newWork();
  work.profile.name = 'Tea'; work.profile.code = 'TEA'; work.profile.group_id = '55555555-5555-4555-8555-555555555555'; work.profile.product_type_revision_id = '44444444-4444-4444-8444-444444444444';
  work.skus[0]!.sku = 'TEA'; work.skus[0]!.name = 'Tea'; work.skus[0]!.base_unit_id = unit; work.skus[0]!.barcode = 'TEA001';
  return work;
}

it('binds the base unit on books-begin when opening precedes creation and includes the barcode', () => {
  const work = reviewedWork();
  const opening = putOpening(work, work.skus[0]!, { decision: 'OPEN', opening_date: '2026-04-01', warehouse_id: '', opening_quantity: '2', purchase_price: '10', batches: [], serials: [] });
  const body = setupBody(opening, options, 0, 1, 1, 1);
  expect(body.setup.units).toMatchObject([{ role: 'BASE', unit_id: unit, valid_from: '2026-04-01', quantity_increment: '1' }]);
  expect(body.setup.barcodes).toMatchObject([{ value: 'TEA001', symbology: 'CODE128' }]);
});

it('rejects edits to completed setup and preserves the original definition for remaining work', () => {
  const work = reviewedWork();
  const previous = { company, key: crypto.randomUUID(), definition: definitionBody(work, options), work, creation_id: creation, commands: {} };
  const status = { id: creation, company_id: company, sku_ids: [item], sku_progress: [{ item_id: item, setup_done: true, opening_state: 'NOT_REQUESTED' as const }] } as Parameters<typeof reviseIntent>[3];
  const changed = structuredClone(work);
  changed.skus[0]!.barcode = 'OTHER';
  expect(() => reviseIntent(previous, changed, options, status)).toThrow();
  expect(reviseIntent(previous, work, options, status).definition).toEqual(previous.definition);
});

it('cannot start another definition when an existing creation loses its saved receipt', () => {
  expect(() => checkRecoveryIntent(null, creation)).toThrow();
  const work = reviewedWork();
  const pending = { company, key: crypto.randomUUID(), definition: definitionBody(work, options), work, creation_id: creation, commands: {} };
  expect(() => checkRecoveryIntent(pending, null)).toThrow();
  expect(() => checkRecoveryIntent(pending, creation)).not.toThrow();
});

it('accepts exact serial counts with padded decimals and preserves named batch prices', () => {
  const work = reviewedWork();
  const sku = work.skus[0]!;
  const opening = putOpening(work, sku, { decision: 'OPEN', opening_date: '2026-04-01', warehouse_id: '', opening_quantity: '2.0000', purchase_price: '10', batches: [], serials: [{ key: 'a', identifiers: [] }, { key: 'b', identifiers: [] }] });
  expect(openingErrors(opening, options)['opening.skus.0.serials']).toBeUndefined();
  expect(openingCommand({ decision: 'OPEN', opening_date: '2026-04-01', warehouse_id: '', opening_quantity: '', purchase_price: '', serials: [], batches: [{ key: 'batch', code: 'B01', opening_quantity: '1', purchase_price: '10', sale_prices: { '77777777-7777-4777-8777-777777777777': '12' }, manufactured_on: '', expires_on: '', mrp: '', serials: [] }] }).batches?.[0]?.sale_prices).toMatchObject([{ amount: '12' }]);
});

it('declares a required non-axis Product Type attribute with the SKU value', () => {
  const work = reviewedWork();
  const definition = '88888888-8888-4888-8888-888888888888';
  const option = '99999999-9999-4999-8999-999999999999';
  const configured = { ...options, selected_type: { ...options.selected_type!, attribute_set_revision_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' }, attribute_members: [{ definition_id: definition, name: 'Material', value_type: 'TEXT', measurement_dimension: null, position: 0, is_required: true, allow_variant_axis: false, is_variant_capable: false }] } as AdvancedOptions;
  expect(skuErrors(work, configured)[`skus.0.attributes.${definition}`]).toBeTruthy();
  work.skus[0]!.attributes = [{ definition_id: definition, value_type: 'TEXT', option_id: option }];
  expect(skuErrors(work, configured)[`skus.0.attributes.${definition}`]).toBeUndefined();
  expect(definitionBody(work, configured).attributes).toMatchObject([{ definition_id: definition, is_required: true, is_axis: false, options: [option] }]);
  work.skus[0]!.attributes = [{ definition_id: definition, value_type: 'TEXT', value_text: '   ' }];
  expect(skuErrors(work, configured)[`skus.0.attributes.${definition}`]).toBeTruthy();
});
