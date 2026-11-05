import type { components } from '@janso/api-client/identity';
import { customPatch, type CustomField } from '@janso/ui';
import { validFiscalAnchor } from './company-defaults';

export type CompanyField = components['schemas']['FieldDescriptor'];
export function companyFieldLabel(field: CompanyField): string {
  const label = field.label && field.label !== field.key ? field.label : field.key.replaceAll('_', ' ');
  return label.charAt(0).toUpperCase() + label.slice(1);
}
export function companyCustomFields(fields: readonly CompanyField[]): CustomField[] {
  return fields.filter(field => field.source === 'custom' && field.custom).map(field => ({
    key: field.key.replace(/^custom_field:/, ''), source: 'custom', label: companyFieldLabel(field),
    visible: field.is_visible ?? true, writable: field.writable ?? false, required: field.required,
    help_text: field.help_text, placeholder: field.placeholder, custom: field.custom ? {
      ...field.custom, is_active: field.custom.is_active ?? true,
      is_immutable_after_create: field.custom.is_immutable_after_create ?? false,
      validation: { ...field.custom.validation, required: field.custom.validation?.required ?? false, max_length: field.custom.validation?.max_length ?? 4096 },
      choices: (field.custom.choices ?? []).map(choice => ({ ...choice, is_active: choice.is_active ?? true })),
      sequence_config: field.custom.sequence_config ? { prefix: field.custom.sequence_config.prefix ?? '',
        padding: field.custom.sequence_config.padding ?? 1, start: field.custom.sequence_config.start ?? 1,
        reset: field.custom.sequence_config.reset ?? 'never' } : null,
    } : null,
  }));
}
export function companyPatch(fields: readonly CompanyField[], draft: Record<string, unknown>, previous: Record<string, unknown>) {
  const patch: Record<string, unknown> = {}, errors: Record<string, string> = {};
  for (const field of fields) {
    if (field.source === 'custom' || !field.writable || !field.is_visible || !(field.key in draft)) continue;
    const key = field.key, value = draft[key], before = previous[key];
    if (JSON.stringify(value) === JSON.stringify(before)) continue;
    const label = companyFieldLabel(field), bounds = field.validation ?? {};
    if (field.required && (value == null || (typeof value === 'string' && !value.trim()) || (Array.isArray(value) && !value.length))) {
      errors[key] = `${label} is required.`; continue;
    }
    if (field.data_type === 'integer' && value != null && value !== '') {
      if (!/^-?\d+$/.test(String(value)) || !Number.isSafeInteger(Number(value))) { errors[key] = 'Enter a whole number.'; continue; }
      const number = Number(value);
      if ((bounds.min != null && number < Number(bounds.min)) || (bounds.max != null && number > Number(bounds.max))) {
        errors[key] = `Enter a value between ${bounds.min ?? 'the minimum'} and ${bounds.max ?? 'the maximum'}.`; continue;
      }
      patch[key] = number;
    } else if (field.data_type === 'decimal' && value != null && value !== '') {
      if (!/^-?\d{1,15}(?:\.\d{1,4})?$/.test(String(value))) { errors[key] = 'Enter an amount with at most four decimal places.'; continue; }
      patch[key] = String(value);
    } else {
      if (typeof value === 'string' && value && bounds.min_length != null && value.length < Number(bounds.min_length)) {
        errors[key] = `Use at least ${bounds.min_length} characters.`; continue;
      }
      if (typeof value === 'string' && bounds.max_length != null && value.length > Number(bounds.max_length)) {
        errors[key] = `Use at most ${bounds.max_length} characters.`; continue;
      }
      if (typeof value === 'string' && value && typeof bounds.pattern === 'string') {
        try { if (!new RegExp(bounds.pattern).test(value)) { errors[key] = `Enter a valid ${label.toLowerCase()}.`; continue; } }
        catch { errors[key] = 'Field validation is unavailable. Reload the form.'; continue; }
      }
      if (value != null && value !== '' && field.choices?.length && !field.choices.some(choice => choice.value === value)) {
        errors[key] = 'Choose an available option.'; continue;
      }
      patch[key] = value === '' && bounds.nullable ? null : value;
    }
  }
  try {
    const custom = companyCustomFields(fields);
    const changed = customPatch(custom.filter(field => field.visible), (draft.custom_fields ?? {}) as Record<string, unknown>, (previous.custom_fields ?? {}) as Record<string, unknown>);
    if (Object.keys(changed).length) patch.custom_fields = changed;
  } catch (error) { errors.custom_fields = error instanceof Error ? error.message : 'Check the custom field values.'; }
  if (('fiscal_year_start_month' in patch || 'fiscal_year_start_day' in patch)
    && !validFiscalAnchor(Number(draft.fiscal_year_start_month), Number(draft.fiscal_year_start_day))) {
    errors.fiscal_year_start_day = 'Choose a valid fiscal start month and day.';
  }
  return { patch, errors };
}
