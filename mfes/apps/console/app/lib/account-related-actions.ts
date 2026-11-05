import type { MenuItem } from '@janso/ui';
import {
  accountingBack,
  accountingLink,
  accountingResource,
  accountingUUID,
  type AccountingField,
  type AccountingRecord,
  type AccountingResourceConfig,
} from './accounting-configuration-resources';

const resources = [
  'account-aliases',
  'account-external-keys',
  'account-bank-profiles',
  'account-tax-profiles',
  'account-tax-defaults',
  'posting-mappings',
  'charge-policies',
] as const;
const readable = (fields: readonly AccountingField[], key: string) =>
  fields.some(
    (field) =>
      field.key === key &&
      field.readable &&
      field.visible &&
      !field.conditional_access,
  );

/** UX hints mirror native creation rules. Native scope, field and domain checks remain authoritative. */
export function accountCreationReason(
  resource: string,
  row: AccountingRecord,
  fields: readonly AccountingField[],
  available: readonly string[],
): string | undefined {
  if (row.status === 'INACTIVE')
    return 'Retired accounts retain their records. Create a new account when needed.';
  if (!['DRAFT', 'ACTIVE'].includes(String(row.status)))
    return 'The account status must be readable before creating related records.';
  if (['account-aliases', 'account-external-keys'].includes(resource)) return;
  if (!readable(fields, 'kind'))
    return 'The account kind must be readable before creating this record.';
  if (
    resource === 'account-bank-profiles' ||
    resource === 'account-tax-profiles'
  ) {
    const kind = resource === 'account-bank-profiles' ? 'BANK' : 'TAX';
    if (row.kind !== kind)
      return `This profile belongs to a ${kind.toLowerCase()} account.`;
    if (row.status !== 'DRAFT' || row.used_at !== null)
      return 'Profiles require an unused draft account. Its usage must be readable.';
    return;
  }
  if (row.status !== 'ACTIVE')
    return 'Activate this account before creating dated defaults or charge policies.';
  if (resource === 'account-tax-defaults' && row.kind !== 'GENERAL')
    return 'Tax defaults require a general account under an eligible income, expense or asset head.';
  if (
    resource === 'charge-policies' &&
    ['party_id', 'party_role', 'currency', 'currency_mode'].some(
      (key) => !readable(fields, key),
    )
  )
    return 'Party account attributes must be readable before creating a charge policy.';
  if (
    resource === 'charge-policies' &&
    (row.kind !== 'PARTY' ||
      typeof row.party_id !== 'string' ||
      !accountingUUID.test(row.party_id) ||
      !['CUSTOMER', 'SUPPLIER'].includes(String(row.party_role)) ||
      !available.includes('parties'))
  )
    return 'Charge policies require an active customer or supplier party account and permission to read its party.';
}

export function accountRelatedActions(
  row: AccountingRecord,
  fields: readonly AccountingField[],
  here: string,
  available: readonly string[],
  manageable: readonly string[],
): MenuItem[] {
  if (!accountingUUID.test(row.id)) return [];
  const items: MenuItem[] = [];
  for (const resource of resources) {
    if (!available.includes(resource)) continue;
    const config = accountingResource(resource)!;
    const query = new URLSearchParams({ account_id: row.id });
    items.push({
      id: 'manage-' + resource,
      label: 'Manage ' + config.title.toLowerCase(),
      href: accountingLink('/accounting/' + resource + '?' + query, here),
    });
    if (manageable.includes(resource))
      items.push({
        id: 'create-' + resource,
        label: 'Create ' + config.singular.toLowerCase(),
        href: accountingLink('/accounting/' + resource + '/new?' + query, here),
        disabledReason: accountCreationReason(resource, row, fields, available),
      });
  }
  for (const [key, resource, label] of [
    ['group_id', 'account-groups', 'Open account group'],
    ['party_id', 'parties', 'Open linked party'],
  ]) {
    const value = row[key];
    if (
      available.includes(resource) &&
      readable(fields, key) &&
      typeof value === 'string' &&
      accountingUUID.test(value)
    )
      items.push({
        id: 'open-' + resource,
        label,
        href: accountingLink('/accounting/' + resource + '/' + value, here),
      });
  }
  return items;
}

/** Only a validated native parent detail in the return chain establishes its owner. */
export function accountingCreationContext(
  config: AccountingResourceConfig,
  back: string,
): {
  key: 'account_id' | 'party_id';
  ownerId: string;
  label: 'account' | 'party';
  href: string;
} | null {
  if (config.owner !== 'account_id' && config.owner !== 'party_id') return null;
  const parent = config.owner === 'account_id' ? 'accounts' : 'parties';
  let next = accountingBack(back);
  for (let depth = 0; depth < 8; depth++) {
    const url = new URL(next, 'https://console.invalid');
    const parts = url.pathname.split('/');
    if (
      parts.length === 4 &&
      parts[1] === 'accounting' &&
      parts[2] === parent &&
      accountingUUID.test(parts[3]!)
    )
      return {
        key: config.owner,
        ownerId: parts[3]!,
        label: parent === 'accounts' ? 'account' : 'party',
        href: next,
      };
    const ancestor = url.searchParams.get('returnTo');
    if (!ancestor) return null;
    const safe = accountingBack(ancestor);
    if (safe === next) return null;
    next = safe;
  }
  return null;
}
export function accountCreationContext(
  config: AccountingResourceConfig,
  back: string,
): { accountId: string; href: string } | null {
  const context = accountingCreationContext(config, back);
  return context?.key === 'account_id'
    ? { accountId: context.ownerId, href: context.href }
    : null;
}
