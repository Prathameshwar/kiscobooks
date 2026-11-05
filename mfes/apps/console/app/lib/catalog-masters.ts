import type { components } from '@janso/api-client/catalog';
import { customCondition, customPatch, type CustomField } from '@janso/ui';
import { companyCustomFields } from './company-form';
import { classificationDefinitions, type ClassificationResource } from './product-classification-resources';
import { profileDefinitions, type ProductProfileResource } from './product-profile-resources';

export type MasterResource = 'promotion-limits' | 'boms' | ClassificationResource | ProductProfileResource | 'units' | 'manufacturers' | 'item-groups' | 'warehouses' | 'warehouse-groups' | 'warehouse-bins' | 'unit-conversions' | 'pack-types' | 'identifier-types' | 'identifier-namespaces' | 'identifier-profiles' | 'attribute-definitions' | 'attribute-options' | 'attribute-sets' | 'sales-channels' | 'price-levels' | 'price-plans';
export type MasterField = components['schemas']['FieldMetadata'];
export type MasterFieldSet = components['schemas']['FieldSet'];
export type MasterRow = Record<string, unknown> & { id: string; company_id?: string; name?: string; code?: string; is_active?: boolean; row_version?: number; policy_generation?: number; custom_fields?: Record<string, unknown> };
type Input = { label: string; max?: number; choices?: readonly string[]; hint?: string; optional?: boolean; pattern?: string; type?: 'integer' | 'decimal' | 'party' | 'country' | 'state' | 'timezone' | 'department' | 'tax-registration' };
export type MasterConfig = { resource: MasterResource; title: string; singular: string; entity: string; permission: string; inputs: Record<string, Input>; initial: Record<string, unknown> };
export const dimensions = ['COUNT', 'MASS', 'VOLUME', 'LENGTH', 'AREA', 'TIME', 'JOB'] as const;
export const kinds = ['GOODS', 'SERVICE', 'BOTH'] as const;
const labels: Record<string, Input> = {
  code: { label: 'Code', max: 30, hint: 'Use uppercase letters, numbers, dots, hyphens or underscores. Start with a letter or number.' },
  name: { label: 'Name', max: 100 },
};
const configs: Record<MasterResource, MasterConfig> = {
  'promotion-limits': { resource: 'promotion-limits', title: 'Promotion limit definitions', singular: 'promotion limit', entity: 'catalog.promotion_limit_definition', permission: 'promotion_limit', inputs: { ...labels, scope_kind: { label: 'Quota scope', choices: ['CAMPAIGN', 'PROMOTION', 'PROGRAM'] }, metric: { label: 'Quota measure', choices: ['TOTAL_USES', 'PER_CUSTOMER_USES', 'PER_ORDER_USES', 'REWARD_UNITS', 'BUDGET'] }, period_basis: { label: 'Usage period', choices: ['LIFETIME', 'DAY', 'MONTH', 'YEAR', 'ORDER'] }, timezone: { label: 'Period timezone', max: 64 }, currency: { label: 'Budget currency', pattern: '^[A-Z]{3}$', optional: true }, unit_id: { label: 'Reward count unit', pattern: '^[0-9a-f-]{36}$', optional: true } }, initial: { code: '', name: '', scope_kind: 'PROMOTION', metric: 'TOTAL_USES', period_basis: 'LIFETIME', timezone: 'UTC', currency: null, unit_id: null } },
  boms: { resource: 'boms', title: 'Bills of materials', singular: 'BOM', entity: 'catalog.bom', permission: 'bom', inputs: labels, initial: { code: '', name: '' } },
  'manufacturing-routes': { resource: 'manufacturing-routes', ...profileDefinitions['manufacturing-routes'], inputs: labels, initial: { code: '', name: '' } },
  'manufacturing-operations': { resource: 'manufacturing-operations', ...profileDefinitions['manufacturing-operations'], inputs: labels, initial: { code: '', name: '' } },
  'items': { resource: 'items', ...classificationDefinitions['items'], inputs: labels },
  'product-families': { resource: 'product-families', ...classificationDefinitions['product-families'], inputs: labels },
  'product-types': { resource: 'product-types', ...classificationDefinitions['product-types'], inputs: labels },
  'category-schemes': { resource: 'category-schemes', ...classificationDefinitions['category-schemes'], inputs: labels },
  'item-categories': { resource: 'item-categories', ...classificationDefinitions['item-categories'], inputs: labels },
  'brands': { resource: 'brands', ...classificationDefinitions['brands'], inputs: labels },
  'brand-series': { resource: 'brand-series', ...classificationDefinitions['brand-series'], inputs: labels },
  'manufacturer-sites': { resource: 'manufacturer-sites', ...classificationDefinitions['manufacturer-sites'], inputs: labels },
  'inventory-templates': { resource: 'inventory-templates', ...profileDefinitions['inventory-templates'], inputs: labels, initial: { code: '', name: '' } },
  'warranty-policies': { resource: 'warranty-policies', ...profileDefinitions['warranty-policies'], inputs: labels, initial: { code: '', name: '' } },
  'return-policies': { resource: 'return-policies', ...profileDefinitions['return-policies'], inputs: labels, initial: { code: '', name: '' } },
  'handling-profiles': { resource: 'handling-profiles', ...profileDefinitions['handling-profiles'], inputs: labels, initial: { code: '', name: '' } },
  'sales-channels': { resource: 'sales-channels', title: 'Sales channels', singular: 'sales channel', entity: 'catalog.sales_channel', permission: 'sales_channel', inputs: labels, initial: { code: '', name: '' } },
  'price-levels': { resource: 'price-levels', title: 'Price levels', singular: 'price level', entity: 'catalog.price_level', permission: 'price_plan', inputs: { ...labels, ordinal: { label: 'Level number', type: 'integer' } }, initial: { code: '', name: '', ordinal: '4' } },
  'price-plans': { resource: 'price-plans', title: 'Price plans', singular: 'price plan', entity: 'catalog.price_plan', permission: 'price_plan', inputs: { ...labels, purpose: { label: 'Purpose', choices: ['SALE', 'PURCHASE', 'REFERENCE_RETAIL'] }, currency: { label: 'Currency', pattern: '^[A-Z]{3}$' }, tax_basis: { label: 'Tax basis', choices: ['EXCLUSIVE', 'INCLUSIVE'] } }, initial: { code: '', name: '', purpose: 'SALE', price_level_id: null, currency: '', tax_basis: 'EXCLUSIVE', custom_fields: {} } },
  'attribute-definitions': { resource: 'attribute-definitions', title: 'Attribute definitions', singular: 'attribute definition', entity: 'catalog.attribute_definition', permission: 'attribute_definition', inputs: {}, initial: { code: '', name: '', value_type: 'TEXT', measurement_dimension: null, is_variant_capable: false } },
  'attribute-options': { resource: 'attribute-options', title: 'Attribute options', singular: 'attribute option', entity: 'catalog.attribute_option', permission: 'attribute_option', inputs: {}, initial: { code: '', name: '', definition_id: null, value_text: '', value_integer: '', value_decimal: '', value_boolean: null, value_date: '', unit_id: null } },
  'attribute-sets': { resource: 'attribute-sets', title: 'Attribute sets / templates', singular: 'attribute set', entity: 'catalog.attribute_set', permission: 'attribute_set', inputs: {}, initial: { code: '', name: '' } },
  'unit-conversions': { resource: 'unit-conversions', title: 'Unit conversions', singular: 'unit conversion', entity: 'catalog.unit_conversion', permission: 'unit', inputs: {}, initial: { from_unit_id: null, canonical_unit_id: null, numerator: '1', denominator: '1' } },
  'pack-types': { resource: 'pack-types', title: 'Pack types', singular: 'pack type', entity: 'catalog.pack_type', permission: 'pack_type', inputs: labels, initial: { code: '', name: '' } },
  'identifier-types': { resource: 'identifier-types', title: 'Identifier types', singular: 'identifier type', entity: 'catalog.identifier_type', permission: 'identifier_type', inputs: labels, initial: { code: '', name: '', is_barcode: false } },
  'identifier-namespaces': { resource: 'identifier-namespaces', title: 'Identifier namespaces', singular: 'identifier namespace', entity: 'catalog.identifier_namespace', permission: 'identifier_namespace', inputs: { code: { ...labels.code!, max: 40 }, name: { label: 'Name', max: 120 } }, initial: { code: '', name: '' } },
  'identifier-profiles': { resource: 'identifier-profiles', title: 'Identifier profiles', singular: 'identifier profile', entity: 'catalog.identifier_profile', permission: 'identifier_profile', inputs: labels, initial: { code: '', name: '' } },
  'warehouse-groups': { resource: 'warehouse-groups', title: 'Warehouse groups', singular: 'warehouse group', entity: 'catalog.warehouse_group', permission: 'warehouse_group', inputs: labels, initial: { code: '', name: '' } },
  'warehouse-bins': { resource: 'warehouse-bins', title: 'Bins / racks', singular: 'bin / rack', entity: 'catalog.warehouse_bin', permission: 'warehouse_bin', inputs: { ...labels, warehouse_id: { label: 'Warehouse', pattern: '^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$' } }, initial: { code: '', name: '', warehouse_id: null } },
  warehouses: { resource: 'warehouses', title: 'Warehouses', singular: 'warehouse', entity: 'catalog.warehouse', permission: 'warehouse',
    inputs: { ...labels, kind: { label: 'Location kind', choices: ['STORE', 'GODOWN'] },
      address_line1: { label: 'Address line 1', max: 120, optional: true }, address_line2: { label: 'Address line 2', max: 120, optional: true }, city: { label: 'City', max: 60, optional: true }, postal_code: { label: 'Postal code', max: 20, optional: true },
      country_code: { label: 'Country', type: 'country', pattern: '^[A-Z]{2}$', optional: true }, state_code: { label: 'State', type: 'state', pattern: '^[A-Z0-9-]{1,6}$', optional: true }, timezone: { label: 'Timezone', type: 'timezone', max: 64, optional: true },
      department_id: { label: 'Department', type: 'department', optional: true, pattern: '^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$' }, tax_registration_id: { label: 'Tax registration', type: 'tax-registration', optional: true, pattern: '^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$' } },
    initial: { code: '', name: '', kind: 'STORE', address_line1: null, address_line2: null, city: null, postal_code: null, country_code: null, state_code: null, timezone: null, department_id: null, tax_registration_id: null } },
  units: { resource: 'units', title: 'Units', singular: 'unit', entity: 'catalog.unit_of_measure', permission: 'unit',
    inputs: { ...labels, symbol: { label: 'Symbol', max: 20 }, dimension: { label: 'Dimension', choices: dimensions }, decimal_places: { label: 'Decimal places', type: 'integer', choices: ['0', '1', '2', '3', '4'] }, quantity_increment: { label: 'Quantity increment', type: 'decimal', hint: 'Smallest quantity step, for example 1 or 0.001. It must fit the selected decimal places.' } },
    initial: { code: '', name: '', symbol: '', dimension: 'COUNT', decimal_places: '0', quantity_increment: '1' } },
  manufacturers: { resource: 'manufacturers', title: 'Manufacturers', singular: 'manufacturer', entity: 'catalog.manufacturer', permission: 'manufacturer',
    inputs: { ...labels, party_id: { label: 'Accounting party', type: 'party', hint: 'Optional. Link an existing party in this company.' } }, initial: { code: '', name: '', party_id: null, custom_fields: {} } },
  'item-groups': { resource: 'item-groups', title: 'Item groups', singular: 'item group', entity: 'catalog.item_group', permission: 'item_group',
    inputs: { ...labels, allowed_kind: { label: 'Allowed item kind', choices: kinds } }, initial: { code: '', name: '', allowed_kind: 'BOTH', custom_fields: {}, parent_group_id: null } },
};
export function masterConfig(resource: string): MasterConfig | null { return Object.hasOwn(configs, resource) ? configs[resource as MasterResource] : null; }
export function masterLabel(config: MasterConfig, field: MasterField) {
  return field.label && field.label !== field.key ? field.label : config.inputs[field.key]?.label ?? field.key.replaceAll('_', ' ');
}
export function masterCustomFields(fields: readonly MasterField[]): CustomField[] {
  return companyCustomFields(fields.filter(field => field.source === 'custom' && field.custom).map(field => ({ ...field,
    is_visible: field.visible, group: field.display_group ?? 'custom', hideable: true, renameable: true, requires_feature: null,
  })));
}
/** Resolve defaults and conditions like CustomFields before deciding what can be saved. */
export function masterCustomDraft(config: MasterConfig, fields: readonly MasterField[], draft: Record<string, unknown>, creating: boolean) {
  const definitions = masterCustomFields(fields);
  const values = { ...Object.fromEntries(creating ? definitions.filter(field => field.custom?.is_active).map(field => [field.key, field.custom?.default_value]) : []), ...(draft.custom_fields as Record<string, unknown> ?? {}) };
  const numeric = new Set([...definitions.filter(field => ['decimal', 'integer'].includes(field.custom?.data_type ?? '')).map(field => field.key),
    ...Object.keys(config.inputs).filter(key => ['decimal', 'integer'].includes(config.inputs[key]?.type ?? ''))]);
  return { values, fields: definitions.filter(field => field.visible && field.writable && field.custom?.is_active && field.custom.data_type !== 'auto_number'
    && (creating || !field.custom.is_immutable_after_create) && customCondition(field.custom.visibility, { ...draft, ...values }, numeric)) };
}
export function validMasterDate(value: unknown) {
  return typeof value === 'string' && /^\d{4}-\d\d-\d\d$/.test(value) && value >= '1000-01-01' && Number.isFinite(Date.parse(value)) && new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) === value;
}
export function masterBody(config: MasterConfig, fields: readonly MasterField[], draft: Record<string, unknown>, previous?: MasterRow) {
  const body: Record<string, unknown> = previous ? { expected_version: previous.row_version } : {}, errors: Record<string, string> = {};
  if (previous && (!Number.isSafeInteger(previous.row_version) || Number(previous.row_version) < 1)) errors.row_version = 'The record version is unavailable. Reload before saving.';
  for (const field of fields) {
    const input = config.inputs[field.key];
    if (field.source !== 'native' || !field.visible || !field.writable || !input || !(field.key in draft)) continue;
    if (previous && config.resource === 'warehouses' && ['code', 'kind'].includes(field.key)) continue;
    let value = draft[field.key];
    if (typeof value === 'string' && input.type !== 'decimal') value = value.trim();
    if (input.optional && (value === '' || value == null)) value = null;
    if (input.type === 'integer' && value !== '' && value != null) value = Number(value);
    if (previous && JSON.stringify(value) === JSON.stringify(previous[field.key])) continue;
    if (field.required && (value == null || value === '')) { errors[field.key] = `${masterLabel(config, field)} is required.`; continue; }
    if (input.choices && !input.choices.includes(String(value))) { errors[field.key] = 'Choose an available option.'; continue; }
    if (input.max && !(input.optional && value === null) && (typeof value !== 'string' || !value || value.length > input.max || /[\x00-\x1f\x7f]/.test(value))) { errors[field.key] = `Enter printable text with up to ${input.max} characters.`; continue; }
    if (value != null && input.pattern && !new RegExp(input.pattern).test(String(value))) { errors[field.key] = 'Choose an available option.'; continue; }
    if (field.key === 'code' && !/^[A-Z0-9][A-Z0-9_.-]*$/.test(String(value))) { errors.code = 'Use a valid uppercase code.'; continue; }
    if (input.type === 'party' && value != null && !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(String(value))) { errors[field.key] = 'Choose an available party.'; continue; }
    body[field.key] = input.type === 'integer' ? Number(value) : value;
  }
  if (config.resource === 'warehouses') {
    if (!previous && ['MAIN', 'TRANSIT'].includes(String(draft.code))) errors.code = 'Main and transit are created by the system. Choose another code.';
    if (draft.state_code && !draft.country_code && ('state_code' in body || 'country_code' in body)) errors.state_code = 'Choose a country before selecting a state.';
    if (draft.state_code && draft.country_code && !String(draft.state_code).startsWith(String(draft.country_code) + '-') && ('state_code' in body || 'country_code' in body)) errors.state_code = 'Choose a state in the selected country.';
  }
  if (config.resource === 'units' && ('quantity_increment' in body || 'decimal_places' in body)) {
    const increment = draft.quantity_increment, precision = draft.decimal_places == null ? undefined : Number(draft.decimal_places);
    // A read-denied counterpart is omitted from detail responses. Validate the
    // submitted value here; the API checks it against the protected stored rule.
    if (increment !== undefined) {
      const text = String(increment), invalid = typeof increment !== 'string' || !/^\d{1,15}(?:\.\d{1,4})?$/.test(text) || !/[1-9]/.test(text);
      const mismatch = precision !== undefined && (text.split('.')[1] ?? '').replace(/0+$/, '').length > precision;
      if (invalid || mismatch) errors['quantity_increment' in body ? 'quantity_increment' : 'decimal_places'] = 'Enter a positive increment that fits the selected decimal places (up to four).';
    }
  }
  const custom = masterCustomDraft(config, fields, draft, !previous);
  const patch: Record<string, unknown> = {};
  for (const field of custom.fields) {
    const value = custom.values[field.key];
    if (field.required && (value == null || value === '' || (Array.isArray(value) && !value.length))) errors['custom_fields.' + field.key] = `${field.label} is required.`;
    try { Object.assign(patch, customPatch([field], custom.values, previous?.custom_fields ?? {})); }
    catch (error) { errors['custom_fields.' + field.key] = error instanceof Error ? error.message : 'Check this custom field value.'; }
  }
  if (Object.keys(patch).length) body.custom_fields = patch;
  if (!previous && config.resource === 'item-groups') {
    if (!validMasterDate(draft.valid_from)) errors.valid_from = 'Choose a valid effective date.';
    if (draft.parent_group_id != null && (typeof draft.parent_group_id !== 'string' || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(draft.parent_group_id))) errors.parent_group_id = 'Choose an available parent group.';
    body.valid_from = draft.valid_from; body.parent_group_id = draft.parent_group_id ?? null;
  }
  return { body, errors };
}
