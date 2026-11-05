import type { components } from '@janso/api-client/identity';
export const catalogs = ['countries', 'states', 'languages', 'currencies'] as const;
export type Catalog = typeof catalogs[number];
export type ReferenceDetail = components['schemas']['ReferenceDetail'];
export type ReferenceItem = components['schemas']['ReferenceItem'];
export type ReferencePage = components['schemas']['Page_ReferenceItem_'];
export type ReferenceOptions = components['schemas']['ReferenceOptions'];
export type Field = { key: string; label: string; max: number; pattern?: string; optional?: boolean; options?: 'countries' | 'currencies'; numeric?: boolean; hint?: string };
const code = (max: number, pattern: string, hint: string): Field => ({ key: 'code', label: 'Code', max, pattern, hint });
const name: Field = { key: 'name', label: 'Name', max: 100 };
const numeric: Field = { key: 'numeric_code', label: 'ISO numeric code', max: 3, pattern: '[0-9]{3}', hint: 'Three digits, including leading zeros.' };
export const catalogConfig: Record<Catalog, { title: string; singular: string; kind: string; description: string; fields: readonly Field[] }> = {
  countries: { title: 'Countries', singular: 'country', kind: 'country', description: 'Manage country references and regional defaults for new workspaces.', fields: [code(2, '[A-Z]{2}', 'Two uppercase ISO letters, for example IN.'), { key: 'iso3', label: 'ISO alpha-3 code', max: 3, pattern: '[A-Z]{3}' }, numeric, name, { key: 'official_name', label: 'Official name', max: 200 }, { key: 'default_currency_code', label: 'Default currency', max: 3, options: 'currencies' }, { key: 'phone_prefix', label: 'Phone prefix', max: 8, pattern: '\\+[0-9]{1,7}', hint: 'Include the plus sign, for example +91.' }, { key: 'subdivision_label', label: 'Subdivision label', max: 60, hint: 'For example State, Province or Emirate.' }] },
  states: { title: 'States', singular: 'state', kind: 'state', description: 'Manage states, provinces and other subdivisions within each country.', fields: [{ key: 'country_code', label: 'Country', max: 2, options: 'countries' }, code(6, '[A-Z]{2}-[A-Z0-9]{1,3}', 'Country prefix and subdivision code, for example IN-MH.'), name, { key: 'subdivision_type', label: 'Subdivision type', max: 60 }, { key: 'tax_jurisdiction_code', label: 'GST jurisdiction code', max: 2, pattern: '[0-9]{2}', optional: true, hint: 'India only. Enter an assigned GST state code; leave blank otherwise.' }] },
  languages: { title: 'Languages', singular: 'language', kind: 'language', description: 'Manage language references used by workspace regional defaults.', fields: [code(2, '[a-z]{2}', 'Two lowercase ISO letters, for example en.'), { key: 'iso3', label: 'ISO alpha-3 code', max: 3, pattern: '[a-z]{3}' }, { ...name, max: 128 }, { key: 'native_name', label: 'Native name', max: 128, optional: true }] },
  currencies: { title: 'Currencies', singular: 'currency', kind: 'currency', description: 'Manage currency references and their display metadata.', fields: [code(3, '[A-Z]{3}', 'Three uppercase ISO letters, for example INR.'), numeric, name, { key: 'symbol', label: 'Symbol', max: 8 }, { key: 'minor_unit', label: 'Decimal places', max: 1, numeric: true, pattern: '[0-4]', hint: 'Display scale from 0 to 4; stored amounts always retain four decimals.' }, { key: 'major_unit_name', label: 'Major unit name', max: 40 }, { key: 'minor_unit_name', label: 'Minor unit name', max: 40, optional: true }, { key: 'minor_unit_name_plural', label: 'Minor unit plural', max: 40, optional: true }] },
};
export function catalogReturnTo(kind: Catalog, value?: string | null): string {
  const base = '/platform/references/' + kind;
  if (!value || value.length > 3000 || /[\\\r\n]/.test(value)) return base;
  try { const url = new URL(value, 'https://console.invalid');
    return url.origin === 'https://console.invalid' && url.pathname === base && !url.hash && [...url.searchParams.keys()].every(key => ['q', 'status', 'country_code', 'sort', 'limit', 'cursor'].includes(key)) ? url.pathname + url.search : base;
  } catch { return base; }
}
