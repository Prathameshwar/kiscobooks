import { expect, it } from 'vitest';
import { fixture, id } from './advanced-config-scenarios-fixtures';
import { advancedProductErrors } from '../app/lib/advanced-product-validation';
import type { components } from '@janso/api-client/catalog';

it('does not revalidate immutable completed setup against changed authoring requirements', () => {
  const { work, options } = fixture(3);
  options.defaults.configuration.options.brand_mode = 'DISABLED';
  options.defaults.configuration.pricing.purchase_reference_mode = 'DISABLED';
  const state: components['schemas']['AdvancedDefinitionStatus'] = { id: id(90), company_id: options.company_id, family_id: id(91), row_version: 2, status: 'SETUP', step: 'SETUP', sku_ids: work.skus.map((_, i) => id(100 + i)), sku_progress: work.skus.map((_, i) => ({ item_id: id(100 + i), setup_done: i === 0, activated: false, opening_state: i === 0 ? 'POSTED' : 'NOT_REQUESTED' })) };
  const errors = advancedProductErrors(work, options, state);
  expect(errors.brand_id).toBeUndefined();
  expect(errors['business.skus.0.purchase_amount']).toBeUndefined();
  expect(errors['business.skus.1.purchase_amount']).toBeDefined();
});
