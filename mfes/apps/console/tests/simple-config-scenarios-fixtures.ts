import type { components } from '@janso/api-client/catalog';
import { COMPANY, GROUP, simpleOptions, multiPriceOptions, classificationOptions } from './simple-product-ready-fixtures';

type Options = components['schemas']['SimpleCreationOptions'] & { fields: NonNullable<components['schemas']['SimpleCreationOptions']['fields']> };
export const UNIT = '33333333-3333-4333-8333-333333333333';
export { COMPANY, GROUP };
const field = (key: string, label: string, required = false) => ({ key, label, source: 'native' as const, visible: true, writable: true, conditional_access: false, required, order: 0 });
export function scenario(number: number): { options: Options; entries: Record<string, string> } {
  let options = simpleOptions() as unknown as Options;
  let entries: Record<string, string> = {};
  options.configuration.options = { ...options.configuration.options, brand_mode: 'DISABLED', model_mode: 'DISABLED', barcode_mode: 'DISABLED', category_mode: 'DISABLED', manufacturer_mode: 'DISABLED' };
  // Native options omit disabled controls; construct each snapshot accordingly.
  options.fields = options.fields.filter(row => !['brand_id', 'model_code'].includes(row.key));
  if (number === 1) {
    options.inventory_enabled = false;
    options.configuration.pricing = { ...options.configuration.pricing, sale_price_mode: 'DISABLED', purchase_reference_mode: 'DISABLED', mrp_mode: 'DISABLED' };
    options.fields = options.fields.filter(row => !['purchase_price', 'sale_price', 'opening_quantity', 'opening_unit_cost'].includes(row.key));
  }
  if (number === 2) {
    options.gst_enabled = true;
    options.configuration.pricing = { ...options.configuration.pricing, purchase_reference_mode: 'REQUIRED', sale_price_mode: 'REQUIRED', mrp_mode: 'REQUIRED' };
    options.fields.push(field('mrp', 'MRP', true), field('classification_id', 'HSN', true), field('rule_id', 'GST treatment / rate', true));
    entries = { 'Purchase price': '85', 'Selling price': '120', MRP: '150', 'Opening quantity': '20', 'Opening unit cost': '80' };
  }
  if (number === 3 || number === 4) {
    options = classificationOptions(number === 4 ? 'REQUIRED' : 'OPTIONAL', false) as unknown as Options;
    const mode = number === 4 ? 'REQUIRED' : 'OPTIONAL';
    options.configuration.options = { ...options.configuration.options, brand_mode: mode, model_mode: mode, barcode_mode: mode, brand_default: false, model_default: false, barcode_default: false };
    options.fields.push(field('series_id', 'Brand series'), field('barcode_value', 'Barcode value'), { ...field('barcode_symbology', 'Barcode format'), control: { kind: 'select', choices: [{ value: 'CODE128', label: 'Code 128' }] } } as never);
    if (number === 4) entries = { Model: 'MODEL-4', 'Barcode value': 'SIM004' };
  }
  if (number === 5) {
    options = simpleOptions('SERVICE', true) as unknown as Options;
    entries = { 'Selling price': '750' };
  }
  if (number === 6) {
    options = multiPriceOptions() as unknown as Options;
    entries = { 'Purchase price': '70', Retail: '120', Wholesale: '100' };
  }
  if (number === 7 || number === 8) {
    options.fields.push(...['batch_enabled', 'batch_code', 'batch_manufactured_on', 'batch_expires_on', 'batch_mrp_amount', 'serial_identifiers'].map(key => field(key, key)));
    options.batch = { available: number === 7, required: number === 7, expiry_enabled: number === 7, expiry_required: number === 7, manufacture_date_required: number === 7 };
    if (number === 8) options.serial = { enabled: true, requirements: [{ identifier_type: 'SERIAL', namespace_rule: 'COMPANY', min_count: 1, max_count: 1, requires_slot: false }] };
  }
  if (number === 9) entries = { 'Opening quantity': '12.345', 'Opening unit cost': '42.5', 'Purchase price': '45', 'Selling price': '60' };
  if (number === 10) {
    options.fields.push(...[
      { key: 'cf_note', label: 'Required note', data_type: 'text', default_value: 'Fixture note' },
      { key: 'cf_count', label: 'Required count', data_type: 'integer', default_value: '0' },
      { key: 'cf_flag', label: 'Required flag', data_type: 'boolean', default_value: false },
    ].map(value => ({ ...field('custom_fields.' + value.key, value.label, true), source: 'custom', custom: { ...value, is_active: true, is_immutable_after_create: false, validation: { required: true }, choices: [] } })) as never[]);
  }
  return { options, entries };
}
