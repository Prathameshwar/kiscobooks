import { expect, it } from 'vitest';
import { acceptDefinitionGeneration, intentStorage, type AdvancedIntent } from '../app/lib/advanced-product-api';
import type { AdvancedOptions } from '../app/lib/advanced-product-draft';

it('accepts only the generation caused by its own submitted definition', () => {
  const intent = {
    company: '11111111-1111-4111-8111-111111111111',
    creation_id: '22222222-2222-4222-8222-222222222222',
    definition: { policy_generation: 19, source_version: 100, mode_version: 1 },
    reviewed_policy_generation: 19, reviewed_source_version: 100, reviewed_mode_version: 1,
    work: { profile: { product_type_revision_id: '33333333-3333-4333-8333-333333333333' } },
  } as AdvancedIntent;
  const options = {
    mode: { policy_generation: 20, row_version: 1 },
    defaults: { configuration: { source_version: 100 } },
    selected_type: { id: intent.work.profile.product_type_revision_id },
  } as AdvancedOptions;
  sessionStorage.clear();
  expect(acceptDefinitionGeneration(intent, options, false)).toBe(true);
  expect(JSON.parse(sessionStorage.getItem(intentStorage(intent.company))!).reviewed_policy_generation).toBe(20);
  expect(acceptDefinitionGeneration(intent, { ...options, mode: { ...options.mode, policy_generation: 22 } }, false)).toBe(false);
  expect(acceptDefinitionGeneration(intent, { ...options, defaults: { ...options.defaults, configuration: { ...options.defaults.configuration, source_version: 101 } } }, false)).toBe(false);
  expect(acceptDefinitionGeneration(intent, { ...options, mode: { ...options.mode, policy_generation: 21 } }, true)).toBe(false);
});
