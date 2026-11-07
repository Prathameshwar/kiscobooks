import { newSku, newWork, type AdvancedOptions, type AdvancedWork } from '../app/lib/advanced-product-draft';
import { businessSku, emptyBusiness, putBusiness } from '../app/lib/advanced-product-business';
import { openingSku, emptyOpening, putOpening } from '../app/lib/advanced-product-opening';

export const id = (n: number) => `11111111-1111-4111-8111-${String(n).padStart(12, '0')}`;
export const COMPANY = id(1), TYPE = id(2), UNIT = id(3), GROUP = id(4), PLAN = id(5);
const field = (key: string) => ({ key, label: key, source: 'native', visible: true, writable: true, conditional_access: false, required: ['name', 'code'].includes(key), order: 0 });
export function fixture(number: number): { work: AdvancedWork; options: AdvancedOptions } {
  let work = newWork();
  work.profile = { ...work.profile, name: `QA Scenario ${number}`, code: `QA${number}`, group_id: GROUP, product_type_revision_id: TYPE };
  work.skus[0] = { ...work.skus[0]!, sku: `QA${number}-01`, name: 'Test product', base_unit_id: UNIT };
  const options = {
    company_id: COMPANY, kind: 'GOODS', today: '2026-11-07', books_begin_date: '2026-04-01', currency: 'INR',
    mode: { company_id: COMPANY, row_version: 2, policy_generation: 4, product_family_sku_enabled: true },
    selected_type: { id: TYPE, kind: 'GOODS', allow_variants: false, require_brand: false, require_manufacturer: false, require_expiry: false, unit_dimensions: ['COUNT'], inventory_modes: ['STOCK'], tracking_modes: [] },
    inventory_enabled: true, gst_enabled: false, price_levels_accessible: true, max_skus_per_draft: 64,
    defaults: { product_type_revision_id: TYPE,
      quantity: { unit_id: UNIT, quantity_decimal_places: 0, quantity_increment: '1', fractional_entry: false },
      price: { price_basis_quantity: '1', price_decimal_places: 2 },
      configuration: { source_version: 9, policy_generation: 4,
        options: { variants_mode: 'DISABLED', brand_mode: 'DISABLED', model_mode: 'DISABLED', category_mode: 'DISABLED', manufacturer_mode: 'DISABLED', barcode_mode: 'DISABLED', alternate_units_mode: 'DISABLED' },
        pricing: { sale_price_mode: 'OPTIONAL', purchase_reference_mode: 'OPTIONAL', mrp_mode: 'DISABLED', multiple_price_levels_mode: 'DISABLED' }, profiles: {} } },
    family_fields: { company_id: COMPANY, entity_type: 'catalog.product_family', source_version: 1, fields: ['name', 'code', 'group_id', 'product_type_revision_id', 'brand_id', 'series_id', 'model_code', 'description'].map(field) },
    sku_fields: { company_id: COMPANY, entity_type: 'catalog.item', source_version: 1, fields: ['sku', 'name', 'base_unit_id', 'sellable', 'purchasable', 'barcode'].map(field) },
    sale_price_levels: [{ plan_id: PLAN, price_level_id: id(6), name: 'Retail', tax_basis: 'EXCLUSIVE', required: false }],
    batch: { available: false, required: false }, serial: { enabled: false, requirements: [] }, required_category_schemes: [], attribute_members: [],
  } as unknown as AdvancedOptions;
  const config = options.defaults.configuration;
  const price = (purchase: string, sale: string, mrp = '') => {
    work = putBusiness(work, work.skus[0]!, { ...emptyBusiness(), purchase_amount: purchase, purchase_source: purchase ? 'QA quotation' : '', sale_prices: sale ? { [PLAN]: sale } : {}, mrp_amount: mrp, mrp_jurisdiction: mrp ? 'IN' : '', mrp_source: mrp ? 'QA list' : '' });
  };
  const opening = (quantity: string, cost: string) => { work = putOpening(work, work.skus[0]!, { ...emptyOpening(), decision: 'OPEN', opening_date: options.books_begin_date!, opening_quantity: quantity, purchase_price: cost }); };
  if (number === 1) { options.inventory_enabled = false; options.selected_type!.inventory_modes = []; }
  if (number === 2 || number === 9) {
    options.gst_enabled = true;
    config.pricing = { ...config.pricing, purchase_reference_mode: 'REQUIRED', sale_price_mode: 'REQUIRED', mrp_mode: 'REQUIRED' };
    options.sale_price_levels![0]!.required = true;
    price('85.00', '120.00', '150.00');
    work = putBusiness(work, work.skus[0]!, { ...workBusiness(work), classification_id: id(7), rule_id: id(8) });
    opening('20', '80.00');
  }
  if (number === 3) {
    config.options.variants_mode = 'OPTIONAL'; config.options.brand_mode = 'REQUIRED'; config.options.category_mode = 'REQUIRED';
    options.selected_type!.allow_variants = true;
    work.profile.brand_id = id(10);
    work.profile.categories = [{ key: 'category', scheme_id: id(11), category_id: id(12), is_primary: true }];
    options.required_category_schemes = [{ id: id(11), name: 'Clothing', membership_mode: 'SINGLE' }];
    work.axes = [13, 14].map(n => ({ key: `axis${n}`, definition_id: id(n), label: n === 13 ? 'Colour' : 'Size', value_type: 'TEXT', options: [] }));
    work.skus = [0, 1, 2, 3].map(n => ({ ...newSku(), sku: `SHIRT-${n}`, name: `Shirt ${n}`, base_unit_id: UNIT, attributes: [{ definition_id: id(13), value_type: 'TEXT', option_id: id(20 + Math.floor(n / 2)) }, { definition_id: id(14), value_type: 'TEXT', option_id: id(22 + n % 2) }] }));
    work.skus.forEach((sku, n) => {
      work = putBusiness(work, sku, { ...emptyBusiness(), purchase_amount: '200.00', purchase_source: 'QA quote', sale_prices: { [PLAN]: '300.00' } });
      if (n < 2) work = putOpening(work, sku, { ...emptyOpening(), decision: 'OPEN', opening_date: options.books_begin_date!, opening_quantity: '10', purchase_price: '180.00' });
    });
  }
  if (number === 4) {
    work.profile.kind = 'SERVICE'; options.kind = 'SERVICE'; options.selected_type!.kind = 'SERVICE'; options.selected_type!.inventory_modes = []; options.selected_type!.unit_dimensions = ['TIME']; options.gst_enabled = true;
    config.pricing.sale_price_mode = 'REQUIRED'; config.pricing.multiple_price_levels_mode = 'ENABLED';
    options.sale_price_levels = [...options.sale_price_levels!.map(level => ({ ...level, required: true })), { ...options.sale_price_levels![0]!, plan_id: id(25), price_level_id: id(26), name: 'Corporate', required: true }];
    price('600.00', '1000.00'); work = putBusiness(work, work.skus[0]!, { ...workBusiness(work), classification_id: id(7), rule_id: id(8), sale_prices: { [PLAN]: '1000.00', [id(25)]: '850.00' } });
  }
  if (number === 5) {
    options.batch = { available: true, required: true, manufacture_date_required: true, expiry_enabled: true, expiry_required: true };
    config.pricing.mrp_mode = 'REQUIRED'; config.pricing.purchase_reference_mode = 'REQUIRED'; config.pricing.sale_price_mode = 'REQUIRED'; options.sale_price_levels![0]!.required = true;
    price('60.00', '90.00', '100.00');
    work = putOpening(work, work.skus[0]!, { ...emptyOpening(), decision: 'OPEN', opening_date: options.books_begin_date!, batches: [0, 1].map(n => ({ key: `batch${n}`, code: `FOOD-${n}`, opening_quantity: n ? '20' : '10', purchase_price: n ? '55.00' : '50.00', purchase_reference: n ? '65.00' : '60.00', sale_prices: { [id(6)]: n ? '95.00' : '90.00' }, manufactured_on: '2026-03-01', expires_on: '2027-05-01', mrp: n ? '110.00' : '100.00', serials: [] })) });
  }
  if (number === 6) {
    options.serial = { enabled: true, requirements: [{ identifier_type: 'SERIAL', min_count: 1, max_count: 1, requires_slot: false, namespace_rule: 'COMPANY' }] };
    price('21000.00', '25000.00'); opening('2', '20000.00');
    work = putOpening(work, work.skus[0]!, { ...workOpening(work), serials: [0, 1].map(n => ({ key: `serial${n}`, identifiers: [{ identifier_type: 'SERIAL', value: `QA-SN-${n}` }] })) });
  }
  if (number === 7) {
    config.options.alternate_units_mode = 'OPTIONAL'; options.selected_type!.unit_dimensions = ['MASS'];
    options.defaults.quantity = { ...options.defaults.quantity!, quantity_decimal_places: 3, quantity_increment: '0.005', fractional_entry: true };
    work.skus[0]!.units = [{ key: 'gram', code: 'GRAM', unit_id: id(30), role: 'BOTH', pack_type_id: '', numerator: '1', denominator: '1000', quantity_decimal_places: '0', quantity_increment: '1' }, { key: 'bag', code: 'BAG', unit_id: id(31), role: 'PACK', pack_type_id: id(32), numerator: '25', denominator: '1', quantity_decimal_places: '0', quantity_increment: '1' }];
    price('44.00', '55.00'); opening('12.345', '42.50');
  }
  if (number === 8) {
    config.options.brand_mode = 'REQUIRED'; config.options.model_mode = 'REQUIRED'; config.options.category_mode = 'REQUIRED'; config.options.manufacturer_mode = 'REQUIRED'; config.options.barcode_mode = 'REQUIRED';
    work.profile.brand_id = id(40); work.profile.model_code = 'MODEL-01'; work.profile.manufacturer_id = id(41); work.profile.manufacturer_site_id = id(42); work.profile.categories = [{ key: 'category', scheme_id: id(43), category_id: id(44), is_primary: true }];
    work.skus[0]!.barcode = 'QA-MANAGED-01';
    options.attribute_members = [{ definition_id: id(45), name: 'Allowed', value_type: 'BOOLEAN', is_required: true, is_variant_capable: false, allow_variant_axis: false, position: 0 }, { definition_id: id(46), name: 'Count', value_type: 'INTEGER', is_required: true, is_variant_capable: false, allow_variant_axis: false, position: 1 }];
    work.skus[0]!.attributes = [{ definition_id: id(45), value_type: 'BOOLEAN', value_boolean: false }, { definition_id: id(46), value_type: 'INTEGER', value_integer: '0' }];
    price('', '75.00');
  }
  if (number === 10) {
    price('50.00', '60.00'); config.options.alternate_units_mode = 'OPTIONAL';
    config.pricing = { ...config.pricing, unit_prices_mode: 'ENABLED', quantity_tiers_mode: 'ENABLED', channel_prices_mode: 'ENABLED', additional_currencies_mode: 'ENABLED', formula_prices_mode: 'ENABLED' };
  }
  return { work, options };
}
const workBusiness = (work: AdvancedWork) => businessSku(work, work.skus[0]!);
const workOpening = (work: AdvancedWork) => openingSku(work, work.skus[0]!);
