export const COMPANY = '11111111-1111-4111-8111-111111111111';
export const GROUP = '44444444-4444-4444-8444-444444444444';
const field = (key: string, label: string) => ({ key, label, source: 'native', visible: true, writable: true, required: false, conditional_access: false, order: 0 });
export function simpleOptions(kind = 'GOODS', gst = false) {
  return {
    company_id: COMPANY, kind, today: '2026-11-04', opening_date: '2026-04-01', currency: 'INR', inventory_enabled: true, gst_enabled: gst,
    default_group_id: GROUP,
    configuration: { options: { brand_mode: 'DISABLED', model_mode: 'DISABLED' }, pricing: { sale_price_mode: 'OPTIONAL', purchase_reference_mode: 'OPTIONAL', mrp_mode: 'DISABLED' } },
    fields: [field('kind', 'Type'), field('name', 'Product name'), field('code', 'Product code'), field('group_id', 'Product group'), field('base_unit_id', 'Base unit'), field('purchase_price', 'Purchase price'), field('sale_price', 'Selling price'), field('brand_id', 'Brand'), field('model_code', 'Model'),
      ...(kind === 'GOODS' ? [field('opening_quantity', 'Opening quantity')] : []),
      ...(gst ? [field('classification_id', kind === 'GOODS' ? 'HSN' : 'SAC'), field('rule_id', 'GST treatment / rate')] : [])],
  };
}

export function configuredSimpleOptions() {
  const options = simpleOptions('GOODS', true);
  options.configuration.options.brand_mode = 'REQUIRED';
  options.configuration.options.model_mode = 'REQUIRED';
  options.configuration.pricing.mrp_mode = 'OPTIONAL';
  options.fields.push(field('mrp', 'MRP'), field('series_id', 'Brand series'));
  return options;
}

export function multiPriceOptions() {
  const options = simpleOptions();
  const levels = ['Retail', 'Wholesale', 'Distributor'].map((name, index) => ({
    price_level_id: `55555555-5555-4555-8555-55555555555${index + 1}`,
    plan_id: `66666666-6666-4666-8666-66666666666${index + 1}`,
    code: 'PRICE' + (index + 1), name, ordinal: index + 1, tax_basis: 'EXCLUSIVE' as const,
    is_default: index === 0, required: index < 2,
  }));
  return { ...options, sale_price_levels: levels,
    configuration: { ...options.configuration, pricing: { ...options.configuration.pricing, multiple_price_levels_mode: 'ENABLED', sale_price_mode: 'REQUIRED', sale_level_count: 2 } },
    fields: [...options.fields.filter(field => field.key !== 'sale_price'), ...levels.map(level => ({
      ...field('sale_prices.' + level.price_level_id, level.name), required: level.required,
    }))],
  };
}

export const SCHEME = '77777777-7777-4777-8777-777777777777';
export const CATEGORY = '88888888-8888-4888-8888-888888888888';
export const MAKER = '99999999-9999-4999-8999-999999999999';
export const SITE = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
export function classificationOptions(mode = 'OPTIONAL', enabled = false, kind = 'GOODS') {
  const options = simpleOptions(kind);
  return { ...options,
    configuration: { ...options.configuration, options: { ...options.configuration.options,
      category_mode: mode, category_default: enabled,
      manufacturer_mode: kind === 'GOODS' ? mode : 'DISABLED', manufacturer_default: enabled,
    } },
    required_category_schemes: mode === 'REQUIRED' ? [{ id: SCHEME, name: 'Product range', membership_mode: 'SINGLE' }] : [],
    fields: [...options.fields, field('category_scheme_id', 'Category scheme'), field('category_id', 'Category'), field('category_is_primary', 'Primary category'),
      ...(kind === 'GOODS' ? [field('manufacturer_id', 'Manufacturer'), field('manufacturer_site_id', 'Manufacturer site')] : [])],
  };
}
