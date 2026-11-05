import type { ConfigField, ConfigMetadata, ConfigValues } from '../app/lib/product-configuration';
import { metadata, response } from './product-configuration-fixtures';

const requirements = metadata.options[0]!.control!.choices;
const field = (key: string, label: string, control: NonNullable<ConfigField['control']>, group?: string): ConfigField => ({ key, label: key, source: 'native', visible: true, writable: true, required: !control.nullable, conditional_access: false, order: 0, display_group: group, control: { ...control, label } });
const options = [
  ['variants', 'Variants'], ['barcode', 'Barcode'], ['brand', 'Brand'], ['model', 'Model'], ['category', 'Category'], ['manufacturer', 'Manufacturer'],
  ['alternate_units', 'Alternate units and fixed conversion'], ['compound_units', 'Compound quantities'], ['measured_units', 'Measured conversion'],
];
export const completeMetadata: ConfigMetadata = {
  ...metadata,
  options: options.flatMap(([key, label], index) => [
    { ...field(key + '_mode', label!, { kind: 'select', label: label!, choices: requirements }, index >= 6 ? 'unit_conversion' : undefined), help_text: key === 'model' ? 'Allow the existing model code on a product. Model does not require a brand.' : key === 'brand' ? 'Allow a product brand and its optional brand series.' : index >= 6 ? 'Allow this quantity entry option. Base-unit entry is always available.' : undefined },
    field(key + '_default', 'Enable ' + key!.replaceAll('_', ' ') + ' by default', { kind: 'boolean', label: '', choices: [], nullable: true, depends_on: key + '_mode', show_when: 'OPTIONAL' }, index >= 6 ? 'unit_conversion' : undefined),
  ]),
  profiles: [
    ['goods_type_revision', 'Goods product type', 'product-type-revisions'], ['service_type_revision', 'Service product type', 'product-type-revisions'],
    ['inventory_template_revision', 'Inventory profile', 'inventory-template-revisions'], ['warranty_revision', 'Warranty profile', 'warranty-revisions'],
    ['return_policy_revision', 'Return policy', 'return-policy-revisions'], ['handling_revision', 'Handling profile', 'handling-revisions'], ['identifier_profile', 'Identifier profile', 'identifier-profiles'],
  ].flatMap(([key, label, source]) => [
    field(key + '_mode', label + ' default', { kind: 'select', label: '', choices: metadata.profiles[0]!.control!.choices }),
    field(key + '_id', label!, { kind: 'reference', label: '', choices: [], nullable: true, depends_on: key + '_mode', show_when: 'VALUE', reference_source: source }),
  ]),
  pricing: [
    ...metadata.pricing,
    ...['purchase_reference', 'mrp'].map(key => field(key + '_mode', key.replaceAll('_', ' '), { kind: 'select', label: '', choices: requirements })),
    ...[
      ['multiple_price_levels', 'Multiple selling-price levels'], ['unit_prices', 'Separate prices by unit or pack'], ['quantity_tiers', 'Quantity-slab prices'],
      ['channel_prices', 'Sales-channel prices'], ['additional_currencies', 'Additional price currencies'], ['formula_prices', 'Formula-based prices'],
    ].map(([key, label]) => field(key + '_mode', label!, { kind: 'select', label: '', choices: ['INHERIT', 'DISABLED', 'ENABLED'].map(value => ({ value, label: value === 'INHERIT' ? 'Use system default' : value.charAt(0) + value.slice(1).toLowerCase() })) }, 'pricing_options')),
  ],
};

export function completeResponse(path: string, method?: string) {
  const value = structuredClone(response(path, method));
  if (value && typeof value === 'object' && 'fields' in value) {
    const section = Object.keys(metadata).find(key => JSON.stringify(value.fields) === JSON.stringify(metadata[key as keyof ConfigMetadata]));
    if (section) value.fields = completeMetadata[section as keyof ConfigMetadata];
  }
  if (value && typeof value === 'object' && 'options' in value) {
    for (const section of ['options', 'profiles', 'pricing'] as const) {
      const values = value[section] as ConfigValues;
      for (const entry of completeMetadata[section]) if (!(entry.key in values)) values[entry.key] = entry.key.endsWith('_mode') ? section === 'profiles' ? 'CLEAR' : 'DISABLED' : null;
    }
  }
  return value;
}
