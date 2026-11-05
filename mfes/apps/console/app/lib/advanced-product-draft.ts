import type { components } from '@janso/api-client/catalog';

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
  sellable: boolean; purchasable: boolean; min_sale_quantity: string;
  custom_fields: Record<string, unknown>;
  attributes: components['schemas']['AttributeSelection-Input'][];
  units: { key: string; code: string; unit_id: string; role: 'SALE' | 'PURCHASE' | 'BOTH' | 'PACK'; pack_type_id: string; numerator: string; denominator: string; quantity_decimal_places: string; quantity_increment: string }[];
};
export type ProductAxis = { key: string; definition_id: string; label: string; value_type: ProductSkuValues['attributes'][number]['value_type']; options: { id: string; label: string }[] };
export type AdvancedWork = { profile: ProductProfileValues; axes: ProductAxis[]; skus: ProductSkuValues[]; business: Record<string, unknown>; opening: Record<string, unknown> };
export const newSku = (): ProductSkuValues => ({ key: crypto.randomUUID(), sku: '', name: '', base_unit_id: '', sellable: true, purchasable: true, min_sale_quantity: '', custom_fields: {}, attributes: [], units: [] });
export const newWork = (): AdvancedWork => ({ profile: { kind: 'GOODS', name: '', code: '', group_id: '', product_type_id: '', product_type_revision_id: '', brand_id: '', series_id: '', model_code: '', description: '', manufacturer_id: '', manufacturer_site_id: '', categories: [], custom_fields: {} }, axes: [], skus: [newSku()], business: {}, opening: {} });
export function readWork(content: components['schemas']['AdvancedDraftContent']): AdvancedWork {
  const fresh = newWork();
  const profile = content.profile ?? {};
  const skus = Array.isArray(content.skus) ? content.skus : [];
  const string = (value: unknown) => typeof value === 'string' ? value : '';
  const categories = Array.isArray(profile.categories) ? profile.categories : [];
  const values: ProductProfileValues = { ...fresh.profile, kind: profile.kind === 'SERVICE' ? 'SERVICE' : 'GOODS', name: string(profile.name), code: string(profile.code), group_id: string(profile.group_id), product_type_id: string(profile.product_type_id), product_type_revision_id: string(profile.product_type_revision_id), brand_id: string(profile.brand_id), series_id: string(profile.series_id), model_code: string(profile.model_code), description: string(profile.description), manufacturer_id: string(profile.manufacturer_id), manufacturer_site_id: string(profile.manufacturer_site_id), categories: categories.map(row => ({ key: string(row.key) || crypto.randomUUID(), scheme_id: string(row.scheme_id), category_id: string(row.category_id), is_primary: row.is_primary === true })), custom_fields: typeof profile.custom_fields === 'object' && profile.custom_fields && !Array.isArray(profile.custom_fields) ? profile.custom_fields as Record<string, unknown> : {} };
  const axes = Array.isArray(profile.axes) ? profile.axes : [];
  return { profile: values, axes: axes.filter(row => row && typeof row === 'object' && typeof row.definition_id === 'string').map(row => ({ key: string(row.key) || crypto.randomUUID(), definition_id: string(row.definition_id), label: string(row.label), value_type: ['TEXT', 'INTEGER', 'DECIMAL', 'BOOLEAN', 'DATE'].includes(row.value_type) ? row.value_type as ProductAxis['value_type'] : 'TEXT', options: Array.isArray(row.options) ? row.options.filter((option: { id?: unknown }) => option && typeof option.id === 'string').map((option: { id: string; label: string }) => ({ id: string(option.id), label: string(option.label) })) : [] })), skus: skus.length ? skus.map((row) => ({ ...newSku(), key: string(row.key) || crypto.randomUUID(), sku: string(row.sku), name: string(row.name), base_unit_id: string(row.base_unit_id), sellable: row.sellable !== false, purchasable: row.purchasable !== false, min_sale_quantity: string(row.min_sale_quantity), custom_fields: typeof row.custom_fields === 'object' && row.custom_fields && !Array.isArray(row.custom_fields) ? row.custom_fields as Record<string, unknown> : {}, attributes: Array.isArray(row.attributes) ? row.attributes as ProductSkuValues['attributes'] : [], units: Array.isArray(row.units) ? row.units.map(unit => ({ key: string(unit.key) || crypto.randomUUID(), code: string(unit.code), unit_id: string(unit.unit_id), role: ['SALE', 'PURCHASE', 'BOTH', 'PACK'].includes(unit.role) ? unit.role : 'BOTH', pack_type_id: string(unit.pack_type_id), numerator: string(unit.numerator), denominator: string(unit.denominator), quantity_decimal_places: string(unit.quantity_decimal_places), quantity_increment: string(unit.quantity_increment) })) : [] })) : fresh.skus, business: content.business ?? {}, opening: content.opening ?? {} };
}
export function profileErrors(work: AdvancedWork, options: AdvancedOptions): Record<string, string> {
  const fields = options.family_fields.fields;
  const permitted = (key: string) => fields.find(field => field.key === key);
  const required = (key: string) => { const field = permitted(key); return !field || (field.required && (!field.visible || !field.writable || field.conditional_access)); };
  const errors: Record<string, string> = {};
  if (!work.profile.name.trim()) errors.name = 'Enter a Profile name.';
  if (!/^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(work.profile.code)) errors.code = 'Use 1–30 uppercase letters, digits, dots, dashes or underscores.';
  if (!work.profile.product_type_revision_id || options.selected_type?.id !== work.profile.product_type_revision_id) errors.product_type_revision_id = 'Choose a published Product Type revision.';
  if (!work.profile.group_id) errors.group_id = 'Choose a product group.';
  for (const key of ['name', 'code', 'product_type_revision_id', 'brand_id', 'series_id', 'model_code', 'description'] as const) {
    const field = permitted(key);
    if (field?.required && !String(work.profile[key] ?? '').trim()) errors[key] = `${field.label} is required.`;
    if (required(key) && field?.required) errors[key] = `${field.label} access is required to continue.`;
  }
  if (options.selected_type?.require_brand && !work.profile.brand_id) errors.brand_id = 'This Product Type requires a brand.';
  if (work.profile.series_id && !work.profile.brand_id) errors.series_id = 'Choose a brand first.';
  if (work.profile.kind === 'GOODS' && (options.selected_type?.require_manufacturer || options.defaults.configuration.options.manufacturer_mode === 'REQUIRED') && !work.profile.manufacturer_id) errors.manufacturer_id = 'Choose a manufacturer.';
  if (work.profile.manufacturer_site_id && !work.profile.manufacturer_id) errors.manufacturer_site_id = 'Choose a manufacturer first.';
  for (const scheme of options.required_category_schemes ?? []) if (!work.profile.categories.some(row => row.scheme_id === scheme.id && row.category_id)) errors['categories.' + scheme.id] = `Choose a category in ${scheme.name}.`;
  for (const row of work.profile.categories) if (row.scheme_id && !row.category_id) errors['categories.' + row.key] = 'Choose a category for the selected scheme.';
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
    if (!sku.sellable && !sku.purchasable) errors[prefix + 'sellable'] = 'Choose at least one trade direction.';
    if (sku.min_sale_quantity && !/^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/.test(sku.min_sale_quantity)) errors[prefix + 'min_sale_quantity'] = 'Enter a positive quantity with up to four decimals.';
    if (sku.min_sale_quantity && !/[1-9]/.test(sku.min_sale_quantity)) errors[prefix + 'min_sale_quantity'] = 'Minimum sale quantity must be greater than zero.';
    const alternate = options.defaults.configuration.options.alternate_units_mode;
    if (alternate === 'REQUIRED' && !sku.units.length) errors[prefix + 'units'] = 'Add the required alternate unit.';
    if (alternate === 'DISABLED' && sku.units.length) errors[prefix + 'units'] = 'Alternate units are disabled for this product.';
    if (sku.units.length > 8) errors[prefix + 'units'] = 'Use at most eight alternate units.';
    sku.units.forEach((unit, unitIndex) => {
      const path = `${prefix}units.${unitIndex}.`;
      if (!/^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(unit.code)) errors[path + 'code'] = 'Enter an uppercase unit binding code.';
      if (!unit.unit_id) errors[path + 'unit_id'] = 'Choose an alternate unit.';
      if (!/^[1-9]\d{0,17}$/.test(unit.numerator) || !/^[1-9]\d{0,17}$/.test(unit.denominator)) errors[path + 'ratio'] = 'Enter positive whole-number numerator and denominator.';
      if (!/^[0-4]$/.test(unit.quantity_decimal_places) || !/^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/.test(unit.quantity_increment) || !/[1-9]/.test(unit.quantity_increment)) errors[path + 'grid'] = 'Enter a valid quantity precision and positive increment.';
      if (unit.role === 'PACK' && !unit.pack_type_id) errors[path + 'pack_type_id'] = 'Choose a pack type.';
    });
    for (const key of ['sku', 'name', 'base_unit_id', 'sellable', 'purchasable'] as const) {
      const field = options.sku_fields.fields.find(row => row.key === key);
      if (!field || !field.visible || !field.writable || field.conditional_access) errors[prefix + key] = `${field?.label ?? key} access is required to continue.`;
    }
    work.axes.forEach(axis => { if (!sku.attributes.some(entry => entry.definition_id === axis.definition_id && entry.option_id)) errors[prefix + axis.definition_id] = `Choose ${axis.label || 'a variant option'}.`; });
  });
  const canVariant = options.selected_type?.allow_variants && options.defaults.configuration.options.variants_mode !== 'DISABLED';
  if (work.skus.length > 1 && !canVariant) errors.skus = 'This Product Type allows one SKU.';
  if (work.skus.length > 1 && !work.axes.length) errors.skus = 'Add a variant axis before adding SKUs.';
  if (work.axes.some(axis => !axis.definition_id)) errors.skus = 'Choose a published definition for each variant axis.';
  if (new Set(work.axes.map(axis => axis.definition_id)).size !== work.axes.length) errors.skus = 'Variant axes must be distinct.';
  const signatures = new Set<string>();
  work.skus.forEach((sku, index) => { const parts = work.axes.map(axis => sku.attributes.find(entry => entry.definition_id === axis.definition_id)?.option_id ?? ''); const signature = parts.join(':'); if (parts.length && parts.every(Boolean) && signatures.has(signature)) errors[`skus.${index}.variants`] = 'This variant combination already exists.'; signatures.add(signature); });
  return errors;
}
