import {
  accountingResource,
  accountingUUID,
} from './accounting-configuration-resources';

/** Native master administration only. Financial posting stays under its existing boundary. */
export function allowedAccountingConfigurationRequest(
  method: string,
  path: string,
): boolean | undefined {
  if (
    !path.includes('/configuration/') &&
    !path.includes('/history/') &&
    !path.includes('/accounting-setup/') &&
    !/^\/v1\/companies\/[^/]+\/(?:account-|party-|parties|accounts|payment-|withholding-|posting-mappings|accounting-setup|template-|charge-policies|exchange-rates)/.test(
      path,
    )
  )
    return undefined;
  if (
    !path.startsWith('/v1/') ||
    path.length > 3000 ||
    /[\\#\x00-\x1f\x7f]/.test(path) ||
    /%2f|%5c|%2e/i.test(path) ||
    path.includes('..')
  )
    return false;
  let url: URL;
  try {
    url = new URL(path, 'https://accounting.invalid');
  } catch {
    return false;
  }
  if (url.origin !== 'https://accounting.invalid' || url.pathname.includes('%'))
    return false;
  const parts = url.pathname.split('/').filter(Boolean);
  if (
    parts[0] !== 'v1' ||
    parts[1] !== 'companies' ||
    !accountingUUID.test(parts[2] ?? '')
  )
    return false;
  const route = parts.slice(3),
    params = url.searchParams;
  const only = (keys: string[]) =>
    [...params].every(
      ([key, value]) =>
        keys.includes(key) &&
        params.getAll(key).length === 1 &&
        !/[\x00-\x1f\x7f]/.test(value),
    );
  if (route[0] === 'exchange-rates') {
    if (route.length === 1)
      return (
        method === 'GET' &&
        only([
          'limit',
          'cursor',
          'sort',
          'from_currency',
          'purpose',
          'status',
          'effective_date',
        ])
      );
    if (url.search) return false;
    if (route.length === 2)
      return (
        (route[1] === 'context' && method === 'GET') ||
        (route[1] === 'candidates' && method === 'POST')
      );
    if (route.length === 3 && route[1] === 'quotes')
      return method === 'GET' && accountingUUID.test(route[2]);
    return (
      route.length === 3 &&
      accountingUUID.test(route[1]) &&
      ['approve', 'withdraw'].includes(route[2]) &&
      method === 'POST'
    );
  }
  if (route[0] === 'configuration') {
    if (route.length !== 3 || method !== 'GET') return false;
    if (route[1] === 'options')
      return (
        [
          'accounts',
          'account-heads',
          'account-groups',
          'parties',
          'party-addresses',
          'party-contacts',
          'party-identifiers',
          'party-tax-registrations',
          'party-commercial-types',
          'payment-terms',
          'withholding-sections',
          'withholding-rates',
          'countries',
          'states',
          'currencies',
        ].includes(route[2]) &&
        only([
          'q',
          'limit',
          'cursor',
          'sort',
          'value',
          'party_id',
          'account_id',
          'country_code',
          'kind',
          'role',
          'status',
          ...(route[2] === 'accounts' ? ['currency_mode'] : []),
          ...(route[2] === 'currencies' ? ['company_currency', 'base_only'] : []),
        ]) &&
        ['company_currency', 'base_only'].every(
          (key) => !params.has(key) || ['true', 'false'].includes(params.get(key)!),
        )
      );
    return (
      !!accountingResource(route[1]) &&
      route[2] === 'field-set' &&
      only(['operation', 'object_id'])
    );
  }
  if (route[0] === 'history')
    return (
      route.length === 3 &&
      !!accountingResource(route[1]) &&
      !accountingResource(route[1])?.workflow &&
      accountingUUID.test(route[2]) &&
      method === 'GET' &&
      only(['limit', 'cursor', 'sort'])
    );
  if (
    route[0] === 'accounting-setup' &&
    route.length === 2 &&
    ['initialize', 'preview', 'install'].includes(route[1])
  )
    return method === 'POST' && !url.search;
  const config = accountingResource(route[0]);
  if (!config) return false;
  if (route[0] === 'parties' && route[1] === 'create-with-details')
    return route.length === 2 && method === 'POST' && !url.search;
  // A party is only ever created with its role and ledger account (`create-with-details`): the
  // plain identity-only create no longer exists.
  if (route[0] === 'parties' && route.length === 1 && method === 'POST') return false;
  // One command that creates an account and activates it, for the purchase bill's expense accounts.
  if (route[0] === 'accounts' && route[1] === 'create-active')
    return route.length === 2 && method === 'POST' && !url.search;
  if (config.workflow === 'charge') {
    if (route.length === 1)
      return (
        (method === 'GET' &&
          only(['limit', 'cursor', 'sort', 'account_id', 'as_of'])) ||
        (method === 'POST' && !url.search)
      );
    if (route.length === 2)
      return method === 'GET' && accountingUUID.test(route[1]) && !url.search;
    return (
      route.length === 3 &&
      accountingUUID.test(route[1]) &&
      route[2] === 'close' &&
      method === 'POST' &&
      !url.search
    );
  }
  if (route.length === 1)
    return (
      (method === 'GET' &&
        only([
          'q',
          'limit',
          'cursor',
          'sort',
          'code',
          'status',
          'role',
          'kind',
          'party_id',
          'account_id',
          'group_id',
          'head_id',
          'parent_id',
          'payment_term_id',
          'address_id',
          'registration_id',
          'as_of',
          'alias',
          'purpose',
          'direction',
          'section_id',
          'deductee_type',
          ...(route[0] === 'accounts' ? ['currency', 'currency_mode'] : []),
        ])) ||
      (method === 'POST' && !config.readonly && !url.search)
    );
  if (route.length === 2 && route[1] === 'field-set')
    return method === 'GET' && !url.search;
  if (!accountingUUID.test(route[1] ?? '')) return false;
  if (route.length === 2)
    return (
      (method === 'GET' || (method === 'PATCH' && !config.readonly)) &&
      !url.search
    );
  return (
    route.length === 3 &&
    ['activate', 'deactivate'].includes(route[2]) &&
    !config.readonly &&
    method === 'POST' &&
    !url.search
  );
}
export function allowedAccountingIdentityLookup(
  method: string,
  path: string,
): boolean {
  if (
    method !== 'GET' ||
    /[\\#\x00-\x1f\x7f]/.test(path) ||
    /%2f|%5c|%2e/i.test(path) ||
    path.includes('..')
  )
    return false;
  let url: URL;
  try {
    url = new URL(path, 'https://identity.invalid');
  } catch {
    return false;
  }
  const parts = url.pathname.split('/').filter(Boolean);
  return (
    path.startsWith('/v1/') &&
    url.origin === 'https://identity.invalid' &&
    parts[1] === 'companies' &&
    accountingUUID.test(parts[2] ?? '') &&
    ['bank-accounts', 'tax-registrations'].includes(parts[3]) &&
    (parts.length === 4 ||
      (parts.length === 5 && accountingUUID.test(parts[4]))) &&
    [...url.searchParams].every(
      ([key, value]) =>
        ['limit', 'cursor', 'sort', 'status'].includes(key) &&
        url.searchParams.getAll(key).length === 1 &&
        !/[\x00-\x1f\x7f]/.test(value) &&
        (key !== 'limit' ||
          (/^\d+$/.test(value) &&
            Number(value) >= 1 &&
            Number(value) <= 200)) &&
        (key !== 'cursor' || (value.length > 0 && value.length <= 3000)) &&
        (key !== 'sort' || ['id', '-id'].includes(value)) &&
        (key !== 'status' || ['DRAFT', 'ACTIVE', 'INACTIVE'].includes(value)),
    )
  );
}
export function allowedAccountingCatalogLookup(
  method: string,
  path: string,
): boolean {
  if (
    method !== 'GET' ||
    path.includes('?') ||
    /[\\#\x00-\x1f\x7f]/.test(path) ||
    /%2f|%5c|%2e/i.test(path)
  )
    return false;
  const parts = path.split('/').filter(Boolean);
  return (
    path.startsWith('/v1/companies/') &&
    parts.length === 5 &&
    accountingUUID.test(parts[2] ?? '') &&
    parts[3] === 'tax-rules' &&
    accountingUUID.test(parts[4] ?? '')
  );
}
