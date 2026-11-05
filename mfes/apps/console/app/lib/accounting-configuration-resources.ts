import { masterReturnQuery } from './master-navigation';
import type { components } from '@janso/api-client/accounting';
import {
  configurationLink,
  configurationReturn,
} from './configuration-navigation';

export type AccountingResource =
  components['schemas']['ConfigurationForm']['resource'];
export type AccountingForm = components['schemas']['ConfigurationForm'];
export type AccountingField = AccountingForm['fields'][number];
export type AccountingRecord = {
  id: string;
  company_id: string;
  row_version: number;
  [key: string]: unknown;
};
export type AccountingResourceConfig = {
  resource: AccountingResource;
  title: string;
  singular: string;
  family: string;
  owner?: 'party_id' | 'account_id' | 'group_id' | 'payment_term_id';
  readonly?: boolean;
  workflow?: 'charge';
};
const resource = (
  name: AccountingResource,
  title: string,
  singular: string,
  family: string,
  owner?: AccountingResourceConfig['owner'],
  readonly = false,
): AccountingResourceConfig => ({
  resource: name,
  title,
  singular,
  family,
  owner,
  readonly,
});
export const accountingResources = [
  {
    ...resource(
      'charge-policies',
      'Charge policies',
      'Charge policy',
      'charges',
      'account_id',
    ),
    workflow: 'charge',
  },
  resource('accounts', 'Accounts', 'Account', 'account'),
  resource(
    'account-heads',
    'Account heads',
    'Account head',
    'head',
    undefined,
    true,
  ),
  resource('account-groups', 'Account groups', 'Account group', 'group'),
  resource(
    'account-group-aliases',
    'Group aliases',
    'Group alias',
    'group',
    'group_id',
  ),
  resource(
    'account-aliases',
    'Account aliases',
    'Account alias',
    'account',
    'account_id',
  ),
  resource(
    'account-external-keys',
    'External account references',
    'External account reference',
    'account',
    'account_id',
  ),
  resource(
    'account-tax-profiles',
    'Account tax profiles',
    'Tax profile',
    'tax',
    'account_id',
  ),
  resource(
    'account-bank-profiles',
    'Account bank profiles',
    'Bank profile',
    'bank',
    'account_id',
  ),
  resource(
    'account-tax-defaults',
    'Account tax defaults',
    'Tax default',
    'tax',
    'account_id',
  ),
  resource(
    'posting-mappings',
    'Posting defaults',
    'Posting default',
    'mapping',
    'account_id',
  ),
  resource('parties', 'Parties', 'Party', 'party'),
  resource('party-roles', 'Party roles', 'Party role', 'party', 'party_id'),
  resource(
    'party-addresses',
    'Party addresses',
    'Address',
    'party',
    'party_id',
  ),
  resource(
    'party-address-uses',
    'Address defaults',
    'Address default',
    'party',
    'party_id',
  ),
  resource('party-contacts', 'Party contacts', 'Contact', 'party', 'party_id'),
  resource(
    'party-contact-uses',
    'Contact defaults',
    'Contact default',
    'party',
    'party_id',
  ),
  resource(
    'party-identifiers',
    'Business identifiers',
    'Business identifier',
    'tax',
    'party_id',
  ),
  resource(
    'party-tax-registrations',
    'Party tax registrations',
    'Tax registration',
    'tax',
    'party_id',
  ),
  resource(
    'party-registration-addresses',
    'Registration addresses',
    'Registration address',
    'tax',
    'party_id',
  ),
  resource(
    'party-bank-accounts',
    'Party beneficiaries',
    'Beneficiary',
    'bank',
    'party_id',
  ),
  resource(
    'party-commercial-types',
    'Commercial types',
    'Commercial type',
    'party',
  ),
  resource(
    'party-commercial-type-memberships',
    'Commercial classifications',
    'Commercial classification',
    'party',
    'party_id',
  ),
  resource(
    'party-accounting-policies',
    'Accounting policies',
    'Accounting policy',
    'policy',
    'party_id',
  ),
  resource(
    'party-credit-policies',
    'Credit policies',
    'Credit policy',
    'policy',
    'party_id',
  ),
  resource(
    'party-withholding-profiles',
    'Withholding profiles',
    'Withholding profile',
    'withholding',
    'party_id',
  ),
  resource(
    'withholding-sections',
    'Withholding sections',
    'Withholding section',
    'withholding',
  ),
  resource(
    'withholding-rates',
    'Withholding rates',
    'Withholding rate',
    'withholding',
  ),
  resource(
    'withholding-certificates',
    'Withholding certificates',
    'Withholding certificate',
    'withholding',
    'party_id',
  ),
  resource('payment-terms', 'Payment terms', 'Payment term', 'policy'),
  resource(
    'payment-term-lines',
    'Payment instalments',
    'Payment instalment',
    'policy',
    'payment_term_id',
  ),
  resource(
    'accounting-setup',
    'Accounting setup',
    'Accounting setup',
    'setup',
    undefined,
    true,
  ),
  resource(
    'template-installations',
    'Installed charts',
    'Chart installation',
    'setup',
    undefined,
    true,
  ),
  resource(
    'template-bindings',
    'Chart bindings',
    'Chart binding',
    'setup',
    undefined,
    true,
  ),
] as const;
export const accountingResource = (name: string) =>
  accountingResources.find((config) => config.resource === name);
export const accountingRoot = '/accounting';
export const accountingUUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const accountingLabel = (row: AccountingRecord) =>
  String(
    row.name ??
      row.label ??
      row.code ??
      row.alias ??
      row.role ??
      row.deductee_type ??
      row.purpose ??
      row.scheme ??
      row.kind ??
      (typeof row.method === 'string'
        ? row.method.charAt(0) +
          row.method.slice(1).toLowerCase() +
          ' charge policy' +
          (row.currency ? ' / ' + row.currency : '') +
          (row.valid_from ? ' / ' + row.valid_from : '')
        : 'Record'),
  );
export const accountingReadPermissions = [...new Set(accountingResources.map(config => `accounting.${config.family}.read`)), 'accounting.finance.read'];

export const accountingPermission = (
  config: AccountingResourceConfig,
  action: 'read' | 'manage',
) => `accounting.${config.family}.${action}`;
export function accountingBack(
  value: string | undefined,
  fallback = accountingRoot,
): string {
  return configurationReturn(value, fallback, (url) => {
    if (url.pathname.startsWith('/masters/')) return masterReturnQuery(url);
    const parts = url.pathname.split('/').filter(Boolean);
    if (parts[0] !== 'accounting') return null;
    const config = accountingResource(
      parts[1] === 'suppliers' ? 'parties' : parts[1],
    );
    const record = parts.length >= 3 && accountingUUID.test(parts[2] ?? '');
    const supported =
      url.pathname === accountingRoot ||
      (parts.length === 2 &&
        (config || ['setup', 'exchange-rates'].includes(parts[1]!))) ||
      (parts.length === 3 && ['parties','suppliers'].includes(parts[1]!) && parts[2] === 'import') ||
      (record &&
        ((parts.length === 3 && (config || parts[1] === 'exchange-rates')) ||
          (parts.length === 4 &&
            parts[3] === 'history' &&
            config &&
            !config.workflow)));
    if (!supported) return null;
    return new URLSearchParams(
      [...url.searchParams].filter(
        ([key]) => url.searchParams.getAll(key).length === 1,
      ),
    );
  });
}
export const accountingLink = (path: string, back: string) =>
  configurationLink(path, accountingBack(back));

export function accountingBackLabel(back: string) {
  if (back === '/masters') return 'masters';
  const parts = new URL(back, 'https://console.invalid').pathname
    .split('/')
    .filter(Boolean);
  if (parts[0] === 'masters') {
    const title = (parts[1] ?? '').replaceAll('-', ' ');
    const singular = title.replace(/ies$/, 'y').replace(/s$/, '');
    return parts[3] === 'revisions'
      ? singular + ' revision'
      : parts[2]
        ? singular + ' details'
        : title;
  }
  if (parts.length === 1) return 'accounting configuration';
  if (parts[1] === 'setup') return 'company accounting setup';
  if (parts[1] === 'exchange-rates')
    return parts[2] ? 'exchange rate details' : 'exchange rates';
  const config = accountingResource(
    parts[1] === 'suppliers' ? 'parties' : parts[1],
  );
  if (!config) return 'accounting configuration';
  if (parts[3] === 'history')
    return (config.singular + ' history').toLowerCase();
  return (
    parts[2]
      ? config.singular + ' details'
      : parts[1] === 'suppliers'
        ? 'Suppliers'
        : config.title
  ).toLowerCase();
}
