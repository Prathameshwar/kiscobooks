import { expect, it } from 'vitest';
import { newWork, type AdvancedOptions } from '../app/lib/advanced-product-draft';
import { setupBody } from '../app/lib/advanced-product-api';
import { emptyBusiness, putBusiness } from '../app/lib/advanced-product-business';
import { openingErrors, putOpening } from '../app/lib/advanced-product-opening';

const unit = '11111111-1111-4111-8111-111111111111';
const options = {
  today: '2026-11-06', books_begin_date: '2026-11-06', inventory_enabled: true,
  batch: { available: true, required: false }, serial: { enabled: false },
  selected_type: { inventory_modes: ['STOCK'] },
  defaults: {
    configuration: { source_version: 1, pricing: { sale_price_mode: 'OPTIONAL', mrp_mode: 'DISABLED' } },
    quantity: { unit_id: unit, quantity_decimal_places: 4, fractional_entry: true },
  },
  mode: { policy_generation: 1 }, sale_price_levels: [],
} as unknown as AdvancedOptions;

it('submits explicit nonbatch setup for an untouched optional checkbox and ordinary opening', () => {
  const work = newWork();
  work.skus[0]!.base_unit_id = unit;
  const reviewed = putOpening(work, work.skus[0]!, {
    decision: 'OPEN', opening_date: options.today, opening_quantity: '3.0000',
    purchase_price: '20.2500', warehouse_id: '', batches: [], serials: [],
  });
  expect(openingErrors(reviewed, options)).toEqual({});
  expect(setupBody(reviewed, options, 0, 1, 1, 1).setup.batch_enabled).toBe(false);
});

it.each([true, false])('preserves an explicit batch selection of %s', enabled => {
  const work = newWork(); work.skus[0]!.base_unit_id = unit;
  const reviewed = putBusiness(work, work.skus[0]!, { ...emptyBusiness(), batch_enabled: enabled });
  expect(setupBody(reviewed, options, 0, 1, 1, 1).setup.batch_enabled).toBe(enabled);
});

it('uses the checked required default when batch tracking is required', () => {
  const work = newWork(); work.skus[0]!.base_unit_id = unit;
  expect(setupBody(work, { ...options, batch: { ...options.batch!, required: true } }, 0, 1, 1, 1).setup.batch_enabled).toBe(true);
});

it('omits batch choice when it is unavailable for a Service', () => {
  const work = newWork(); work.profile.kind = 'SERVICE'; work.skus[0]!.base_unit_id = unit;
  expect(setupBody(work, { ...options, batch: { ...options.batch!, available: false } }, 0, 1, 1, 1).setup).not.toHaveProperty('batch_enabled');
});
