'use client';
import { masterReturnQuery } from './master-navigation';
import type { components } from '@janso/api-client/catalog';
import { businessToday, type PageMeta } from '@janso/ui';
import { masterRequest } from './catalog-master-api';
import { validMasterDate } from './catalog-masters';
import { useServiceRead, useServiceList, useServiceCommand, useServiceDestination } from './service-resource';
import { configurationLink, configurationReturn } from './configuration-navigation';

export type ConfigField = Omit<components['schemas']['FieldMetadata'], 'control'> & { control?: (Omit<components['schemas']['ConfigurationControl'], 'choices'> & { choices: components['schemas']['ConfigurationChoice'][] }) | null };
export type ConfigFieldSet = components['schemas']['FieldSet'];
export type ConfigScope = components['schemas']['ScopeDetail'];
export type ConfigDraft = components['schemas']['DraftDetail'];
export type ConfigRevision = components['schemas']['RevisionDetail'];
export type ConfigPreview = components['schemas']['ConfigurationPreview'];
export type ConfigEffective = Omit<components['schemas']['EffectiveConfiguration'], 'settings'> & { settings: components['schemas']['ConfigurationSetting'][] };
export type ConfigPage<T> = { items: T[]; page: PageMeta };
export type ConfigValues = Record<string, unknown>;
export type ConfigSections = 'details' | 'options' | 'profiles' | 'pricing' | 'numeric_defaults';
export type ConfigMetadata = Record<ConfigSections, ConfigField[]>;
export const configRoot = '/products/configuration';
export const configEntities = { details: 'catalog.product_configuration_draft', options: 'catalog.product_entry_option_policy', profiles: 'catalog.catalog_default_profile', pricing: 'catalog.product_pricing_policy', numeric_defaults: 'catalog.product_numeric_default' } as const;
export const scopeLabels = { COMPANY: 'Company', TYPE: 'Product type', GROUP: 'Item group', FAMILY: 'Product family', SKU: 'Product / SKU' } as const;
const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export function configListRecord(value: { id: string }) {
  if (!value || !uuid.test(value.id)) throw { status: 502, message: 'The configuration list response could not be verified.' };
}
export function configLabel(field: ConfigField) { return field.label && field.label !== field.key ? field.label : field.control?.label ?? field.key.replaceAll('_', ' '); }
export function configRecord<T extends { id: string; company_id: string }>(value: T, company: string, id?: string): T {
  if (!value || value.company_id !== company || !uuid.test(value.id) || id && value.id !== id) throw { status: 502, message: 'The configuration response did not match this company. Reload before continuing.' };
  return value;
}
export function configFields(value: ConfigFieldSet, company: string, entity: string): ConfigField[] {
  if (value.company_id !== company || value.entity_type !== entity || !Array.isArray(value.fields) || new Set(value.fields.map(field => field.key)).size !== value.fields.length) throw { status: 502, message: 'Configuration field settings could not be verified. Reload before continuing.' };
  return value.fields.filter(field => field.source === 'native').map(field => ({ ...field, control: field.control ? { ...field.control, choices: field.control.choices ?? [] } : null })).sort((a, b) => a.order - b.order);
}
export function configBack(value: string | undefined, fallback = configRoot): string {
  return configurationReturn(value, fallback, url => {
    if (url.pathname.startsWith('/masters/') || url.pathname.startsWith('/inventory')) return masterReturnQuery(url);
    if (url.pathname === '/products/custom-fields') return url.search ? null : new URLSearchParams();
    const route = new RegExp('^' + configRoot + '(?:/(?:effective|adopt|scopes/[0-9a-f-]{36}|drafts/[0-9a-f-]{36}|revisions/[0-9a-f-]{36}))?$','i');
    if (!route.test(url.pathname)) return null;
    const query = new URLSearchParams();
    return query;
  });
}
export const configLink = (path: string, back: string) => configurationLink(path, configBack(back));
export async function configMetadata(company: string, operation: 'create' | 'update', signal?: AbortSignal): Promise<ConfigMetadata> {
  const keys = Object.keys(configEntities) as ConfigSections[];
  const rows = await Promise.all(keys.map(async key => {
    const value = await masterRequest<ConfigFieldSet>({ path: `/v1/companies/${company}/entities/${configEntities[key]}/field-set?operation=${operation}`, signal });
    return [key, configFields(value, company, configEntities[key])] as const;
  }));
  return Object.fromEntries(rows) as ConfigMetadata;
}
export function companyToday(timezone: string): string {
  return businessToday(timezone);
}
export function useConfigRead<T>(path: string | undefined, verify?: (value: T) => void) {
  return useServiceRead(path, masterRequest, verify, 'product configuration service');
}
export function useConfigList<T>(base: string, filters = '') {
  return useServiceList<T>(base, filters, masterRequest);
}
/** Keep an uncertain command's exact body/key; edits cannot become a different retry. */
export function useConfigCommand() {
  return useServiceCommand(masterRequest, 'product configuration service');
}
export function useConfigDestination(pending: boolean) {
  return useServiceDestination(pending);
}
export function configInitial(fields: ConfigField[]): ConfigValues {
  return Object.fromEntries(fields.filter(field => field.control).map(field => [field.key, field.control!.kind === 'select' ? field.control!.choices.some(choice => choice.value === 'INHERIT') ? 'INHERIT' : field.control!.choices[0]?.value ?? '' : field.control!.nullable ? null : '']));
}
const exact = (value: unknown, places = 4) => {
  if (typeof value !== 'string' || !/^\d{1,15}(?:\.\d{1,4})?$/.test(value)) return null;
  const [whole, tail = ''] = value.split('.'); if (tail.slice(places).replaceAll('0', '')) return null;
  return BigInt(whole!) * 10000n + BigInt(tail.padEnd(4, '0'));
};
export function configBody(fields: ConfigMetadata, values: Record<ConfigSections, ConfigValues | ConfigValues[]>, before?: ConfigDraft) {
  const body: Record<string, unknown> = before ? { expected_version: before.row_version } : {}, errors: Record<string, string> = {};
  if (before && (!Number.isSafeInteger(before.row_version) || Number(before.row_version) < 1)) errors.version = 'The draft version is unavailable. Reload before saving.';
  for (const section of ['details', 'options', 'profiles', 'pricing'] as const) {
    const output: ConfigValues = {}, current = values[section] as ConfigValues, previous = section === 'details' ? before : before?.[section];
    for (const field of fields[section]) {
      if (!field.control || !field.writable || !field.visible || field.conditional_access || !(field.key in current)) continue;
      const hint = field.control; let value = current[field.key];
      if (typeof value === 'string' && hint.kind === 'text') value = value.trim();
      if (hint.nullable && value === '') value = null;
      if (hint.kind === 'integer' && value !== null) value = typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : value;
      if (before && JSON.stringify(value) === JSON.stringify((previous as ConfigValues | undefined)?.[field.key])) continue;
      const errorKey = section === 'details' ? field.key : section + '.' + field.key;
      if (value === null && !hint.nullable || hint.kind === 'text' && (typeof value !== 'string' || !value || value.length > (hint.max_length ?? 250) || /[\x00-\x1f\x7f]/.test(value))) errors[errorKey] = 'Enter printable text with up to ' + (hint.max_length ?? 250) + ' characters.';
      else if (hint.kind === 'date' && !validMasterDate(value)) errors[errorKey] = 'Enter a valid effective date.';
      else if (hint.kind === 'select' && !hint.choices.some(choice => choice.value === value)) errors[errorKey] = 'Choose an available option.';
      else if (hint.kind === 'integer' && value !== null && (!Number.isSafeInteger(value) || Number(value) < (hint.minimum ?? 0) || Number(value) > (hint.maximum ?? 4))) errors[errorKey] = 'Enter a whole number from ' + hint.minimum + ' to ' + hint.maximum + '.';
      else if (hint.kind === 'reference' && value !== null && (typeof value !== 'string' || !uuid.test(value))) errors[errorKey] = 'Choose an available reference.';
      else if (hint.kind === 'boolean' && value !== null && typeof value !== 'boolean') errors[errorKey] = 'Choose whether this option is enabled by default.';
      else output[field.key] = value;
    }
    if (section === 'details') Object.assign(body, output); else if (Object.keys(output).length) body[section] = output;
    if (section === 'options' || section === 'profiles') for (const field of fields[section].filter(field => field.key.endsWith('_mode') && field.control)) {
      const mode = current[field.key], pair = field.key.slice(0, -5) + (section === 'options' ? '_default' : '_id');
      if (mode === 'OPTIONAL' && typeof current[pair] !== 'boolean') errors[section + '.' + pair] = 'Choose whether this option is enabled by default.';
      if (mode === 'VALUE' && (typeof current[pair] !== 'string' || !uuid.test(String(current[pair])))) errors[section + '.' + pair] = 'Choose an available published reference.';
      if (!['OPTIONAL', 'VALUE'].includes(String(mode)) && current[pair] != null) errors[section + '.' + field.key] = 'Clear the obsolete default or reference when changing its mode.';
    }
  }
  const rows = values.numeric_defaults as ConfigValues[];
  if (!before || JSON.stringify(rows) !== JSON.stringify(before.numeric_defaults.map(({ id: _id, draft_id: _draft, revision_id: _revision, ...row }) => row))) {
    const numeric: ConfigValues[] = [], dimensions = new Set<string>();
    for (const [index, row] of rows.entries()) {
      const key = 'numeric_defaults.' + index, dimension = String(row.dimension ?? '');
      if (!['COUNT', 'MASS', 'VOLUME', 'LENGTH', 'AREA', 'TIME', 'JOB'].includes(dimension) || dimensions.has(dimension) || rows.length > 7) errors[key + '.dimension'] = 'Choose each supported dimension only once.';
      dimensions.add(dimension);
      const clean: ConfigValues = {};
      for (const field of fields.numeric_defaults.filter(field => field.control)) {
        let value = row[field.key] ?? null;
        if (!field.writable || !field.visible || field.conditional_access) { errors[key] = 'Numeric defaults contain protected fields. Reload or ask an administrator.'; continue; }
        if (value === '') value = null;
        if (field.control!.kind === 'integer' && typeof value === 'string' && /^\d+$/.test(value)) value = Number(value);
        clean[field.key] = value;
      }
      for (const prefix of ['quantity', 'price']) {
        const precision = clean[prefix + '_decimal_places'], increment = clean[prefix + '_increment'];
        if (precision != null && (!Number.isInteger(precision) || Number(precision) < 0 || Number(precision) > 4)) errors[key + '.' + prefix + '_decimal_places'] = 'Choose 0 to 4 decimal places.';
        if (increment != null && (exact(increment, precision == null ? 4 : Number(precision)) ?? 0n) <= 0n) errors[key + '.' + prefix + '_increment'] = 'Enter a positive exact decimal that fits its precision.';
        if (prefix === 'quantity' && (precision == null) !== (increment == null)) errors[key + '.quantity_increment'] = 'Quantity precision and increment must be set together.';
        if (prefix === 'price' && (precision == null) !== (clean.currency == null)) errors[key + '.currency'] = 'Price precision and currency must be set together.';
        if (prefix === 'price' && precision == null && increment != null) errors[key + '.price_decimal_places'] = 'Price increments require price precision and currency.';
      }
      if (clean.currency != null && !/^[A-Z]{3}$/.test(String(clean.currency))) errors[key + '.currency'] = 'Choose a supported price currency.';
      if (clean.price_basis_quantity != null && (exact(clean.price_basis_quantity) ?? 0n) <= 0n) errors[key + '.price_basis_quantity'] = 'Enter a positive exact price basis quantity.';
      if (Object.entries(clean).every(([name, value]) => name === 'dimension' || value == null)) errors[key] = 'Enter a numeric default or remove this dimension to inherit.';
      numeric.push(clean);
    }
    body.numeric_defaults = numeric;
  }
  return { body, errors };
}
