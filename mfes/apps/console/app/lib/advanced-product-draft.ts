import type { components } from '@janso/api-client/catalog';
import { advancedNativeLabel } from './advanced-product-presentation';
import { advancedCustomErrors, unavailableProfileFields } from './advanced-product-compatibility';

export type AdvancedOptions = components['schemas']['AdvancedCreationOptions'];
export type AdvancedDraft = components['schemas']['AdvancedDraftDetail'];
export type AdvancedDraftList = components['schemas']['AdvancedDraftListItem'];
export type ProductProfileValues = {
  kind: 'GOODS' | 'SERVICE'; name: string; code: string; group_id: string;
  product_type_id: string; product_type_revision_id: string; brand_id: string;
  series_id: string; model_code: string; description: string;
  manufacturer_id: string; manufacturer_site_id: string;
  categories: { key: string; scheme_id: string; category_id: string; is_primary: boolean }[];
  custom_fields: Record<string, unknown>;
};
export type ProductSkuValues = {
  key: string; sku: string; name: string; base_unit_id: string;
  barcode: string; barcode_symbology: 'GTIN' | 'CODE128' | 'QR';
  sellable: boolean; purchasable: boolean; min_sale_quantity: string;
  custom_fields: Record<string, unknown>;
  attributes: components['schemas']['AttributeSelection-Input'][];
  units: { key: string; code: string; unit_id: string; role: 'SALE' | 'PURCHASE' | 'BOTH' | 'PACK'; pack_type_id: string; numerator: string; denominator: string; quantity_decimal_places: string; quantity_increment: string }[];
};
export type ProductAxis = { key: string; definition_id: string; label: string; value_type: ProductSkuValues['attributes'][number]['value_type']; options: { id: string; label: string }[] };
export type AdvancedWork = { profile: ProductProfileValues; axes: ProductAxis[]; skus: ProductSkuValues[]; business: Record<string, unknown>; opening: Record<string, unknown> };
export const newSku = (): ProductSkuValues => ({ key: crypto.randomUUID(), sku: '', name: '', base_unit_id: '', barcode: '', barcode_symbology: 'CODE128', sellable: true, purchasable: true, min_sale_quantity: '', custom_fields: {}, attributes: [], units: [] });
export const newWork = (): AdvancedWork => ({ profile: { kind: 'GOODS', name: '', code: '', group_id: '', product_type_id: '', product_type_revision_id: '', brand_id: '', series_id: '', model_code: '', description: '', manufacturer_id: '', manufacturer_site_id: '', categories: [], custom_fields: {} }, axes: [], skus: [newSku()], business: {}, opening: {} });
export function readWork(content: components['schemas']['AdvancedDraftContent']): AdvancedWork {
  const fresh = newWork();
  const profile = content.profile ?? {};
  const skus = Array.isArray(content.skus) ? content.skus : [];
  const string = (value: unknown) => typeof value === 'string' ? value : '';
  const categories = Array.isArray(profile.categories) ? profile.categories : [];
  const values: ProductProfileValues = { ...fresh.profile, kind: profile.kind === 'SERVICE' ? 'SERVICE' : 'GOODS', name: string(profile.name), code: string(profile.code), group_id: string(profile.group_id), product_type_id: string(profile.product_type_id), product_type_revision_id: string(profile.product_type_revision_id), brand_id: string(profile.brand_id), series_id: string(profile.series_id), model_code: string(profile.model_code), description: string(profile.description), manufacturer_id: string(profile.manufacturer_id), manufacturer_site_id: string(profile.manufacturer_site_id), categories: categories.map(row => ({ key: string(row.key) || crypto.randomUUID(), scheme_id: string(row.scheme_id), category_id: string(row.category_id), is_primary: row.is_primary === true })), custom_fields: typeof profile.custom_fields === 'object' && profile.custom_fields && !Array.isArray(profile.custom_fields) ? profile.custom_fields as Record<string, unknown> : {} };
  const axes = Array.isArray(profile.axes) ? profile.axes : [];
  return { profile: values, axes: axes.filter(row => row && typeof row === 'object' && typeof row.definition_id === 'string').map(row => ({ key: string(row.key) || crypto.randomUUID(), definition_id: string(row.definition_id), label: string(row.label), value_type: ['TEXT', 'INTEGER', 'DECIMAL', 'BOOLEAN', 'DATE'].includes(row.value_type) ? row.value_type as ProductAxis['value_type'] : 'TEXT', options: Array.isArray(row.options) ? row.options.filter((option: { id?: unknown }) => option && typeof option.id === 'string').map((option: { id: string; label: string }) => ({ id: string(option.id), label: string(option.label) })) : [] })), skus: skus.length ? skus.map((row) => ({ ...newSku(), key: string(row.key) || crypto.randomUUID(), sku: string(row.sku), name: string(row.name), base_unit_id: string(row.base_unit_id), barcode: string(row.barcode), barcode_symbology: ['GTIN', 'CODE128', 'QR'].includes(string(row.barcode_symbology)) ? string(row.barcode_symbology) as ProductSkuValues['barcode_symbology'] : 'CODE128', sellable: row.sellable !== false, purchasable: row.purchasable !== false, min_sale_quantity: string(row.min_sale_quantity), custom_fields: typeof row.custom_fields === 'object' && row.custom_fields && !Array.isArray(row.custom_fields) ? row.custom_fields as Record<string, unknown> : {}, attributes: Array.isArray(row.attributes) ? row.attributes as ProductSkuValues['attributes'] : [], units: Array.isArray(row.units) ? row.units.map(unit => ({ key: string(unit.key) || crypto.randomUUID(), code: string(unit.code), unit_id: string(unit.unit_id), role: ['SALE', 'PURCHASE', 'BOTH', 'PACK'].includes(unit.role) ? unit.role : 'BOTH', pack_type_id: string(unit.pack_type_id), numerator: string(unit.numerator), denominator: string(unit.denominator), quantity_decimal_places: string(unit.quantity_decimal_places), quantity_increment: string(unit.quantity_increment) })) : [] })) : fresh.skus, business: content.business ?? {}, opening: content.opening ?? {} };
}
export function profileErrors(work: AdvancedWork, options: AdvancedOptions): Record<string, string> {
  const fields = options.family_fields.fields;
  const permitted = (key: string) => fields.find(field => field.key === key);
  const required = (key: string) => { const field = permitted(key); return !field || (field.required && (!field.visible || !field.writable || field.conditional_access)); };
  const errors: Record<string, string> = {};
  const modes = options.defaults.configuration.options;
  if (options.selected_type?.kind && options.selected_type.kind !== 'BOTH' && options.selected_type.kind !== work.profile.kind) errors.product_type_revision_id = 'Choose a Product Type that allows this product kind.';
  for (const key of unavailableProfileFields(work.profile, options)) errors[key] = `${advancedNativeLabel(key)} is no longer allowed. Remove the unavailable saved details before continuing.`;
  if (!work.profile.name.trim()) errors.name = 'Enter a Profile name.';
  if (!/^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(work.profile.code)) errors.code = 'Use 1–30 uppercase letters, digits, dots, dashes or underscores.';
  if (!work.profile.product_type_revision_id || options.selected_type?.id !== work.profile.product_type_revision_id) errors.product_type_revision_id = 'Choose a published Product Type revision.';
  if (!work.profile.group_id) errors.group_id = 'Choose a product group.';
  for (const key of ['name', 'code', 'product_type_revision_id', 'brand_id', 'series_id', 'model_code', 'description'] as const) {
    const field = permitted(key);
    if (field?.required && !String(work.profile[key] ?? '').trim()) errors[key] = `${advancedNativeLabel(key, field)} is required.`;
    if (required(key) && (field?.required || key === 'name' || key === 'code')) errors[key] = `${advancedNativeLabel(key, field)} access is required to continue.`;
  }
  if (options.selected_type?.require_brand && !work.profile.brand_id) errors.brand_id = 'This Product Type requires a brand.';
  if (modes.brand_mode === 'REQUIRED' && !work.profile.brand_id) errors.brand_id = 'Choose the required brand.';
  if (modes.model_mode === 'REQUIRED' && !work.profile.model_code.trim()) errors.model_code = 'Enter the required model code.';
  if (modes.category_mode === 'REQUIRED' && !work.profile.categories.some(row => row.scheme_id && row.category_id)) errors.categories = 'Choose the required product category.';
  for (const key of ['brand_id', 'model_code'] as const) {
    const needed = key === 'brand_id' ? modes.brand_mode === 'REQUIRED' || options.selected_type?.require_brand : modes.model_mode === 'REQUIRED';
    const access = permitted(key);
    if (needed && (!access?.visible || !access.writable || access.conditional_access)) errors[key] = `${advancedNativeLabel(key, access)} access is required to continue.`;
  }
  if (work.profile.series_id && !work.profile.brand_id) errors.series_id = 'Choose a brand first.';
  if (work.profile.kind === 'GOODS' && (options.selected_type?.require_manufacturer || options.defaults.configuration.options.manufacturer_mode === 'REQUIRED') && !work.profile.manufacturer_id) errors.manufacturer_id = 'Choose a manufacturer.';
  if (work.profile.manufacturer_site_id && !work.profile.manufacturer_id) errors.manufacturer_site_id = 'Choose a manufacturer first.';
  for (const scheme of options.required_category_schemes ?? []) if (!work.profile.categories.some(row => row.scheme_id === scheme.id && row.category_id)) errors['categories.' + scheme.id] = `Choose a category in ${scheme.name}.`;
  for (const row of work.profile.categories) if (row.scheme_id && !row.category_id) errors['categories.' + row.key] = 'Choose a category for the selected scheme.';
  Object.assign(errors, advancedCustomErrors(fields, work.profile, work.profile.custom_fields));
  return errors;
}
export function skuErrors(work: AdvancedWork, options: AdvancedOptions): Record<string, string> {
  const errors: Record<string, string> = {};
  const codes = new Set<string>();
  work.skus.forEach((sku, index) => {
    const prefix = `skus.${index}.`;
    if (!/^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(sku.sku)) errors[prefix + 'sku'] = 'Use 1–30 uppercase letters, digits, dots, dashes or underscores.';
    if (codes.has(sku.sku)) errors[prefix + 'sku'] = 'SKU codes must be distinct.';
    codes.add(sku.sku);
    if (!sku.name.trim()) errors[prefix + 'name'] = 'Enter a SKU name.';
    if (!sku.base_unit_id) errors[prefix + 'base_unit_id'] = 'Choose a base unit.';
    if (options.defaults.configuration.options.barcode_mode === 'REQUIRED' && !sku.barcode.trim()) errors[prefix + 'barcode'] = 'Enter the required barcode or GTIN.';
    if (options.defaults.configuration.options.barcode_mode === 'DISABLED' && sku.barcode.trim()) errors[prefix + 'barcode'] = 'Barcode entry is disabled for this SKU.';
    if (!sku.sellable && !sku.purchasable) errors[prefix + 'sellable'] = 'Choose at least one trade direction.';
    if (sku.min_sale_quantity && !/^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/.test(sku.min_sale_quantity)) errors[prefix + 'min_sale_quantity'] = 'Enter a positive quantity with up to four decimals.';
    if (sku.min_sale_quantity && !/[1-9]/.test(sku.min_sale_quantity)) errors[prefix + 'min_sale_quantity'] = 'Minimum sale quantity must be greater than zero.';
    const alternate = options.defaults.configuration.options.alternate_units_mode;
    if (alternate === 'REQUIRED' && !sku.units.length) errors[prefix + 'units'] = 'Add the required alternate unit.';
    if (alternate === 'DISABLED' && sku.units.length) errors[prefix + 'units'] = 'Alternate units are disabled for this product.';
    if (sku.units.length > 7) errors[prefix + 'units'] = 'Use at most seven alternate units alongside the base unit.';
    const unitCodes = new Set(['BASE']);
    sku.units.forEach((unit, unitIndex) => {
      const path = `${prefix}units.${unitIndex}.`;
      if (!/^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(unit.code)) errors[path + 'code'] = 'Enter an uppercase unit binding code.';
      if (unitCodes.has(unit.code)) errors[path + 'code'] = 'Use a distinct unit code; BASE is reserved for the base unit.';
      unitCodes.add(unit.code);
      if (!unit.unit_id) errors[path + 'unit_id'] = 'Choose an alternate unit.';
      if (!/^[1-9]\d{0,17}$/.test(unit.numerator) || !/^[1-9]\d{0,17}$/.test(unit.denominator)) errors[path + 'ratio'] = 'Enter positive whole-number numerator and denominator.';
      if (!/^[0-4]$/.test(unit.quantity_decimal_places) || !/^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/.test(unit.quantity_increment) || !/[1-9]/.test(unit.quantity_increment)) errors[path + 'grid'] = 'Enter a valid quantity precision and positive increment.';
      if ((unit.quantity_increment.split('.')[1] ?? '').replace(/0+$/, '').length > Number(unit.quantity_decimal_places)) errors[path + 'grid'] = 'Quantity increment must fit the selected decimal places.';
      if (unit.role === 'PACK' && !unit.pack_type_id) errors[path + 'pack_type_id'] = 'Choose a pack type.';
    });
    for (const key of ['sku', 'name', 'base_unit_id', 'sellable', 'purchasable'] as const) {
      const field = options.sku_fields.fields.find(row => row.key === key);
      if (!field || !field.visible || !field.writable || field.conditional_access) errors[prefix + key] = `${advancedNativeLabel(key, field, true)} access is required to continue.`;
    }
    work.axes.forEach(axis => { if (!sku.attributes.some(entry => entry.definition_id === axis.definition_id && entry.option_id)) errors[prefix + axis.definition_id] = `Choose ${axis.label || 'a variant option'}.`; });
    for (const [key, message] of Object.entries(advancedCustomErrors(options.sku_fields.fields, sku, sku.custom_fields))) errors[prefix + key] = message;
    for (const member of options.attribute_members ?? []) {
      if (!member.is_required || work.axes.some(axis => axis.definition_id === member.definition_id)) continue;
      const selected = sku.attributes.find(entry => entry.definition_id === member.definition_id);
      const present = !!selected && (selected.option_id != null || selected.value_text != null || selected.value_integer != null || selected.value_decimal != null || selected.value_boolean != null || selected.value_date != null);
      const path = `${prefix}attributes.${member.definition_id}`;
      if (!present) errors[path] = `Enter ${member.name} for ${sku.sku || `SKU ${index + 1}`}.`;
      if (selected && selected.value_type !== member.value_type) errors[path] = `${member.name} has the wrong value type.`;
      if (selected && [selected.option_id, selected.value_text, selected.value_integer, selected.value_decimal, selected.value_boolean, selected.value_date].filter(value => value != null).length > 1) errors[path] = `Choose one value for ${member.name}.`;
      if (selected?.option_id && selected.unit_id) errors[path] = `The published ${member.name} choice already includes its unit.`;
      if (present && !selected?.option_id) {
        const value = member.value_type === 'TEXT' ? selected?.value_text : member.value_type === 'INTEGER' ? selected?.value_integer : member.value_type === 'DECIMAL' ? selected?.value_decimal : member.value_type === 'BOOLEAN' ? selected?.value_boolean : selected?.value_date;
        if (member.value_type === 'TEXT' && (typeof value !== 'string' || !value.trim() || value.length > 200 || /[\x00-\x1f\uD800-\uDFFF]/.test(value))) errors[path] = `Enter valid text for ${member.name}.`;
        if (member.value_type === 'INTEGER' && (typeof value !== 'string' || !/^-?(?:0|[1-9]\d{0,18})$/.test(value) || BigInt(value) < -(2n ** 63n) || BigInt(value) >= 2n ** 63n)) errors[path] = `Enter a whole number for ${member.name}.`;
        if (member.value_type === 'DECIMAL' && (typeof value !== 'string' || !/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value))) errors[path] = `Enter an exact decimal for ${member.name}.`;
        if (member.value_type === 'DATE' && (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value < '1000-01-01' || Number.isNaN(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value)) errors[path] = `Enter a valid date for ${member.name}.`;
        if (member.value_type === 'BOOLEAN' && typeof value !== 'boolean') errors[path] = `Choose yes or no for ${member.name}.`;
        if (member.measurement_dimension && !selected?.unit_id) errors[path] = `Choose a unit for ${member.name}.`;
      }
    }
  });
  const canVariant = options.selected_type?.allow_variants && options.defaults.configuration.options.variants_mode !== 'DISABLED';
  if (work.axes.length && !canVariant) errors.skus = 'Variant axes are no longer allowed for this Product Type and configuration.';
  if (options.defaults.configuration.options.variants_mode === 'REQUIRED' && !work.axes.length) errors.skus = 'Add the required variant axis.';
  if (work.skus.length > 1 && !canVariant) errors.skus = 'This Product Type allows one SKU.';
  if (work.skus.length > 1 && !work.axes.length) errors.skus = 'Add a variant axis before adding SKUs.';
  if (work.axes.some(axis => !axis.definition_id)) errors.skus = 'Choose a published definition for each variant axis.';
  const members = options.attribute_members ?? [];
  if (options.selected_type?.attribute_set_revision_id && work.axes.some(axis => !members.some(member => member.definition_id === axis.definition_id && member.allow_variant_axis && member.is_variant_capable))) errors.skus = 'Variant axes must belong to the published Product Type attribute set.';
  if (new Set(work.axes.map(axis => axis.definition_id)).size !== work.axes.length) errors.skus = 'Variant axes must be distinct.';
  const signatures = new Set<string>();
  work.skus.forEach((sku, index) => { const parts = work.axes.map(axis => sku.attributes.find(entry => entry.definition_id === axis.definition_id)?.option_id ?? ''); const signature = parts.join(':'); if (parts.length && parts.every(Boolean) && signatures.has(signature)) errors[`skus.${index}.variants`] = 'This variant combination already exists.'; signatures.add(signature); });
  if (!work.skus.length || work.skus.length > (options.max_skus_per_draft ?? 64)) errors.skus = 'Create between 1 and 64 SKUs.';
  if (work.axes.length > 8) errors.skus = 'Use at most eight variant axes.';
  return errors;
}
