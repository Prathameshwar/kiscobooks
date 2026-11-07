import { customCondition, customPatch } from '@janso/ui';
import { masterCustomFields } from './catalog-masters';
import type { MasterField } from './catalog-masters';
import type { AdvancedOptions, ProductProfileValues } from './advanced-product-draft';

export function unavailableProfileFields(profile: ProductProfileValues, options: AdvancedOptions) {
  const modes = options.defaults.configuration.options;
  const fields: (keyof ProductProfileValues)[] = [];
  if (modes.brand_mode === 'DISABLED') { if (profile.brand_id) fields.push('brand_id'); if (profile.series_id) fields.push('series_id'); }
  if (modes.model_mode === 'DISABLED' && profile.model_code) fields.push('model_code');
  if (modes.category_mode === 'DISABLED' && profile.categories.length) fields.push('categories');
  if (profile.kind === 'SERVICE' || modes.manufacturer_mode === 'DISABLED') { if (profile.manufacturer_id) fields.push('manufacturer_id'); if (profile.manufacturer_site_id) fields.push('manufacturer_site_id'); }
  return fields;
}

export function clearUnavailableProfile(profile: ProductProfileValues, options: AdvancedOptions): ProductProfileValues {
  const next = { ...profile };
  for (const field of unavailableProfileFields(profile, options)) {
    if (field === 'categories') next.categories = [];
    else Object.assign(next, { [field]: '' });
  }
  return next;
}

/** Match rendered custom defaults and conditions; the API enforces the full definition. */
export function advancedCustomErrors(fields: readonly MasterField[], native: Record<string, unknown>, supplied: Record<string, unknown>) {
  const errors: Record<string, string> = {};
  const definitions = masterCustomFields(fields);
  const values = { ...Object.fromEntries(definitions.filter(field => field.custom?.is_active).map(field => [field.key, field.custom?.default_value])), ...supplied };
  const numeric = new Set(definitions.filter(field => ['decimal', 'integer'].includes(field.custom?.data_type ?? '')).map(field => field.key));
  for (const field of definitions) {
    if (!field.custom?.is_active || field.custom.data_type === 'auto_number' || !customCondition(field.custom.visibility, { ...native, ...values }, numeric)) continue;
    const value = values[field.key];
    const missing = value == null || typeof value === 'string' && !value.trim() || Array.isArray(value) && !value.length;
    if (field.required && missing) errors['custom_fields.' + field.key] = `${field.label} is required.`;
    if (field.required && (!field.visible || !field.writable || fields.find(row => row.key === field.key)?.conditional_access)) errors['custom_fields.' + field.key] = `${field.label} access is required to continue.`;
    if (!field.visible || !field.writable || missing) continue;
    try { customPatch([field], values, {}); }
    catch (error) { errors['custom_fields.' + field.key] = error instanceof Error ? error.message : 'Check this custom field.'; }
  }
  return errors;
}
