import type { components } from '@janso/api-client/catalog';
import { COMPANY, SOURCE } from './units-identifiers-fixtures';
export function entryConfiguration(
  date: string,
  kind: 'GOODS' | 'SERVICE' = 'GOODS',
): components['schemas']['EffectiveConfiguration'] {
  const options = Object.fromEntries(
    [
      'variants',
      'barcode',
      'brand',
      'category',
      'manufacturer',
      'alternate_units',
      'compound_units',
      'measured_units',
    ].flatMap((key) => [
      [
        key + '_mode',
        kind === 'SERVICE' && ['manufacturer', 'measured_units'].includes(key)
          ? 'DISABLED'
          : 'OPTIONAL',
      ],
      [
        key + '_default',
        kind === 'SERVICE' && ['manufacturer', 'measured_units'].includes(key)
          ? null
          : true,
      ],
    ]),
  );
  const profiles = Object.fromEntries(
    [
      'goods_type_revision',
      'service_type_revision',
      'inventory_template_revision',
      'warranty_revision',
      'return_policy_revision',
      'handling_revision',
      'identifier_profile',
    ].flatMap((key) => [
      [key + '_mode', 'INHERIT'],
      [key + '_id', null],
    ]),
  );
  return {
    company_id: COMPANY,
    as_of: date,
    kind,
    policy_generation: 8,
    source_version: 8,
    sources: [],
    settings: [],
    options,
    profiles,
    pricing: {
      purchase_reference_mode: 'OPTIONAL',
      sale_price_mode: 'OPTIONAL',
      mrp_mode: kind === 'SERVICE' ? 'DISABLED' : 'OPTIONAL',
      sale_level_count: 1,
    },
    numeric_defaults: [],
    activation_supported: true,
  } as components['schemas']['EffectiveConfiguration'];
}
export function entryDefaults(
  params: URLSearchParams,
): components['schemas']['AuthoringDefaults'] {
  const configuration = entryConfiguration(
    params.get('as_of')!,
    params.get('kind') === 'SERVICE' ? 'SERVICE' : 'GOODS',
  );
  const unit = params.get('unit_id');
  return {
    configuration,
    product_type_revision_id: params.get('product_type_revision_id') ?? SOURCE,
    quantity: unit
      ? {
          unit_id: unit,
          quantity_decimal_places: 2,
          quantity_increment: '0.2500',
          fractional_entry: true,
        }
      : null,
    price: null,
    missing: unit ? [] : ['unit'],
    adjustments: [],
    acceptance: {
      as_of: configuration.as_of,
      group_id: null,
      expected_generation: 8,
      expected_source_version: 8,
    },
  };
}
