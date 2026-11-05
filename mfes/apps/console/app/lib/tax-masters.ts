import type { components } from '@janso/api-client/catalog';
import { customCondition, customPatch } from '@janso/ui';
import { masterCustomFields, validMasterDate } from './catalog-masters';
import { accountingBack } from './accounting-configuration-resources';

export type TaxField = components['schemas']['FieldMetadata'];
export type TaxContext = components['schemas']['TaxAdministrationContext'];
export type TaxResource = 'categories' | 'classifications' | 'rules' | 'rates';
export type TaxRow = Record<string, unknown> & { id: string; company_id?: string; row_version?: number; code?: string; name?: string; is_active?: boolean; custom_fields?: Record<string, unknown> };
export type TaxConfig = { key: TaxResource; resource: string; entity: string; title: string; singular: string; dated: boolean; description: string };
export const taxRoot = '/tax';
export const taxSupplyLabel = (value: unknown) => ({ INTRA_STATE: 'Within a state (CGST + SGST)', INTRA_UT: 'Within a union territory (CGST + UTGST)', INTER_STATE: 'Between states / territories (IGST)' }[String(value)] ?? 'Supply context protected');
export const taxUuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const taxConfigs: TaxConfig[] = [
  { key: 'categories', resource: 'tax-categories', entity: 'catalog.tax_category', title: 'Tax categories', singular: 'tax category', dated: false, description: 'Organize the categories used by tax rules.' },
  { key: 'classifications', resource: 'tax-classifications', entity: 'catalog.tax_classification', title: 'Tax classifications', singular: 'tax classification', dated: true, description: 'Maintain dated HSN goods and SAC service classifications with official evidence.' },
  { key: 'rules', resource: 'tax-rules', entity: 'catalog.tax_rule', title: 'Tax rules', singular: 'tax rule', dated: false, description: 'Define the tax category, product kind, treatment and HSN/SAC applicability.' },
  { key: 'rates', resource: 'tax-rates', entity: 'catalog.tax_rate', title: 'Tax rates', singular: 'tax rate', dated: true, description: 'Publish dated GST and cess components for each rule and supply context.' },
];
export const taxConfig = (key: string) => taxConfigs.find(config => config.key === key);
export const taxTitle = (row: TaxRow, fallback = 'Tax record') => row.name ?? row.code ?? (row.valid_from ? 'Effective ' + row.valid_from : fallback);

/** Keep only implemented tax destinations and their bounded, validated query context. */
export function taxReturn(value?: string, fallback = taxRoot, depth = 0): string {
  if (value === '/masters') return value;
  try {
    if (!value || value.length > 4096 || depth > 3 || !value.startsWith('/') || /[%\\#\x00-\x1f]/.test(value.split('?')[0]!)) return fallback;
    const url = new URL(value, 'https://console.invalid');
    if (url.pathname === '/accounting' || url.pathname.startsWith('/accounting/')) return accountingBack(value, fallback);
    if (url.origin !== 'https://console.invalid' || url.hash || !/^\/tax(?:\/(categories|classifications|rules|rates)(?:\/[0-9a-f-]{36})?)?$/.test(url.pathname) || url.pathname.split('/').length > 3 && !taxUuid.test(url.pathname.split('/')[3]!)) return fallback;
    const params = new URLSearchParams();
    for (const [key, item] of url.searchParams) {
      if (url.searchParams.getAll(key).length !== 1 || /[\x00-\x1f]/.test(item)) continue;
      if (key === 'returnTo') { const back = taxReturn(item, '', depth + 1); if (back && new URL(back, url).pathname !== url.pathname) params.set(key, back); }
      else if (key === 'q' && item.trim().length >= 2 && item.length <= 200) params.set(key, item.trim());
      else if (key === 'limit' && /^\d+$/.test(item) && +item >= 1 && +item <= 200) params.set(key, item);
      else if (key === 'sort' && ['id', '-id', 'code', '-code'].includes(item)) params.set(key, item);
      else if (key === 'is_active' && ['true', 'false'].includes(item) || key === 'code_system' && ['HSN', 'SAC'].includes(item)) params.set(key, item);
      else if (['rule_id', 'series_id'].includes(key) && taxUuid.test(item)) params.set(key, item);
      else if (key === 'as_of' && validMasterDate(item)) params.set(key, item);
    }
    return url.pathname + (params.size ? '?' + params : '');
  } catch { return fallback; }
}
export function taxLink(path: string, back: string) {
  const url = new URL(path, 'https://console.invalid'), target = taxReturn(back, '');
  if (target && new URL(target, url).pathname !== url.pathname) url.searchParams.set('returnTo', target);
  return url.pathname + url.search;
}
export function taxLabel(field: TaxField) { return field.label !== field.key ? field.label : field.control?.label ?? field.key.replaceAll('_', ' ').replace(/^./, value => value.toUpperCase()); }
export function taxInitial(config: TaxConfig, today: string) {
  return { code: '', name: '', description: '', code_system: 'HSN', item_kind: 'GOODS', treatment: 'TAXABLE', classification_scope: 'SPECIFIC', tax_category_id: null, series_id: null, valid_from: today, valid_to: null, source_reference: '', source_url: '', source_sha256: '', is_active: true, custom_fields: {}, ...(config.key === 'classifications' ? { jurisdiction: 'IN' } : {}) } as Record<string, unknown>;
}
export function taxBody(config: TaxConfig, fields: TaxField[], values: Record<string, unknown>, context: TaxContext, previous?: TaxRow, superseding = false) {
  const body: Record<string, unknown> = {}, errors: Record<string, string> = {};
  const creating = !previous || superseding, mutable = creating ? null : new Set(['name', 'is_active']);
  for (const field of fields) {
    if (field.source !== 'native' || !field.control || !field.visible || !field.writable || field.conditional_access || mutable && !mutable.has(field.key)) continue;
    let value = values[field.key]; const c = field.control;
    if (typeof value === 'string') value = value.trim();
    if (value === '' || value == null) {
      if (!c.nullable) errors[field.key] = taxLabel(field) + ' is required.';
      else body[field.key] = null;
      continue;
    }
    if (c.kind === 'select' && !(c.choices ?? []).some(choice => choice.value === value)) errors[field.key] = 'Choose an available option.';
    if (c.kind === 'reference' && (typeof value !== 'string' || !taxUuid.test(value))) errors[field.key] = 'Choose an available reference.';
    if (c.kind === 'boolean' && typeof value !== 'boolean') errors[field.key] = 'Choose Active or Inactive.';
    if (c.kind === 'date' && !validMasterDate(value)) errors[field.key] = 'Choose a valid effective date.';
    if (c.kind === 'text' && (typeof value !== 'string' || value.length > (c.max_length ?? 1000) || /[\x00-\x1f\x7f]/.test(value))) errors[field.key] = 'Enter printable text within the field limit.';
    body[field.key] = value;
  }
  if (!creating) {
    // MasterPatch requires both fields. Retain a readable, protected value;
    // never take its replacement from the form. The API checks changed fields.
    for (const key of ['name', 'is_active']) if (!(key in body)) body[key] = previous?.[key];
    body.expected_version = previous?.row_version;
    if (!Number.isSafeInteger(previous?.row_version) || Number(previous?.row_version) < 1) errors.row_version = 'Reload the latest record before saving.';
  } else {
    delete body.is_active;
    if (['categories', 'rules'].includes(config.key) && body.code && !/^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(String(body.code))) errors.code = 'Use up to 30 uppercase letters, numbers, dots, hyphens or underscores.';
    if (config.dated) {
      body.expected_generation = context.policy_generation; body.expected_source_version = context.source_version;
      if (body.valid_from && String(body.valid_from) < context.business_date || superseding && String(body.valid_from) <= context.business_date) errors.valid_from = superseding ? 'A replacement must start on a future date.' : 'A new definition cannot start in the past.';
      if (body.valid_to && String(body.valid_to) < String(body.valid_from)) errors.valid_to = 'The end date must be on or after the start date.';
      if (superseding) { body.supersedes_id = previous?.id; body.expected_previous_version = previous?.row_version; }
    }
    if (config.key === 'classifications') {
      body.jurisdiction = 'IN'; body.item_kind = values.code_system === 'SAC' ? 'SERVICE' : 'GOODS';
      const pattern = values.code_system === 'SAC' ? /^99\d{4}$/ : /^(?!99)\d{4}(?:\d{2}){0,2}$/;
      if (body.code && !pattern.test(String(body.code))) errors.code = values.code_system === 'SAC' ? 'SAC requires six digits starting with 99.' : 'HSN requires 4, 6 or 8 digits outside chapter 99.';
    }
    if (config.key === 'rules') { body.tax_system = 'gst_in'; body.jurisdiction = 'IN'; }
    if (config.key !== 'categories') {
      try { const url = new URL(String(body.source_url)); if (url.protocol !== 'https:' || !/\.(gov|nic)\.in$/.test(url.hostname) || url.username || url.password || url.port && url.port !== '443') throw new Error(); }
      catch { errors.source_url = 'Use an official Indian government HTTPS document URL (.gov.in or .nic.in).'; }
      if (!/^[0-9a-f]{64}$/.test(String(body.source_sha256 ?? ''))) errors.source_sha256 = 'Enter the document SHA-256 as 64 lowercase hexadecimal characters.';
    }
  }
  if (config.key === 'rules') {
    const custom = masterCustomFields(fields.filter(field => !field.conditional_access)), incoming = { ...(creating ? Object.fromEntries(custom.map(field => [field.key, field.custom?.default_value])) : {}), ...values.custom_fields as Record<string, unknown> };
    const numeric = new Set(custom.filter(field => ['decimal', 'integer'].includes(field.custom?.data_type ?? '')).map(field => field.key));
    const allowed = custom.filter(field => field.visible && field.writable && field.custom?.is_active && field.custom.data_type !== 'auto_number' && (creating || !field.custom.is_immutable_after_create) && customCondition(field.custom.visibility, { ...values, ...incoming }, numeric));
    for (const field of allowed) {
      if (field.required && (incoming[field.key] == null || incoming[field.key] === '')) errors['custom_fields.' + field.key] = field.label + ' is required.';
      try { const patch = customPatch([field], incoming, previous?.custom_fields ?? {}); if (Object.keys(patch).length) body.custom_fields = { ...body.custom_fields as object, ...patch }; }
      catch (error) { errors['custom_fields.' + field.key] = error instanceof Error ? error.message : 'Check this value.'; }
    }
  }
  return { body, errors };
}
