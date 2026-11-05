'use client';
import { masterReturn } from './master-navigation';
import { assertMaster, masterRequest } from './catalog-master-api';
import {
  masterCustomDraft,
  masterBody,
  type MasterConfig,
  type MasterField,
  type MasterRow,
} from './catalog-masters';
import {
  identifierId,
  identifierVisible,
  identifierWritable,
  useIdentifierFields,
} from './units-identifiers';
import { allowedPricingRequest } from './pricing-request-policy';
import type { ServiceRequest } from './service-call';
import type { PricingAccess } from './pricing-resources';
export const pricingId = identifierId,
  pricingVisible = identifierVisible,
  pricingWritable = identifierWritable,
  usePricingFields = useIdentifierFields;
export const pricingBase = (company: string, resource: string) =>
  '/v1/companies/' + company + '/' + resource;
export const pricingPurposes = [
  { value: 'SALE', label: 'Sale' },
  { value: 'PURCHASE', label: 'Purchase' },
  { value: 'REFERENCE_RETAIL', label: 'Reference retail' },
];
export function pricingReturn(
  value?: string,
  fallback = '/settings',
  depth = 0,
): string {
  if (value === '/settings' || value === '/') return value;
  if (
    !value ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    value.length > 8192 ||
    /[%\\#]/.test(value.split('?')[0]!) ||
    value.split('?').length > 2
  )
    return fallback;
  try {
    const url = new URL(value, 'https://console.invalid'),
      id = pricingId.source.slice(1, -1);
    if (
      url.origin !== 'https://console.invalid' ||
      url.hash ||
      !new RegExp(
        '^/masters/(sales-channels|price-levels|price-plans)(?:/(?:new|' +
          id +
          '(?:/edit)?))?$',
        'i',
      ).test(url.pathname)
    )
      return masterReturn(value, fallback, depth);
    const params = new URLSearchParams(),
      resource = url.pathname.split('/')[2]!;
    for (const [key, item] of url.searchParams) {
      if (key === 'returnTo' && depth < 3)
        params.set(key, pricingReturn(item, fallback, depth + 1));
      else if (
        allowedPricingRequest(
          'GET',
          pricingBase('01990000-0000-7000-8000-000000000001', resource) +
            '?' +
            new URLSearchParams({ [key]: item }),
        )
      )
        params.set(key, item);
    }
    return url.pathname + (params.size ? '?' + params : '');
  } catch {
    return fallback;
  }
}
export const pricingLink = (path: string, back: string) =>
  path +
  (path.includes('?') ? '&' : '?') +
  new URLSearchParams({ returnTo: pricingReturn(back) });
export function pricingReceipt(
  row: MasterRow,
  company: string,
  id?: string,
  previous?: number,
) {
  assertMaster(row, company, id);
  if (
    !pricingId.test(row.id) ||
    !Number.isSafeInteger(row.row_version) ||
    Number(row.row_version) < Math.max(1, previous ?? 1)
  )
    throw {
      status: 502,
      message: 'The save result could not be verified. Retry the same save.',
    };
}
/** Pricing commands return a receipt, not a master. Verify it and read the scoped record before confirming success. */
export const pricingCommand = async <T>(
  request: ServiceRequest,
): Promise<T> => {
  const result = await masterRequest<Record<string, unknown>>(request);
  if (request.path.includes('/sales-channels')) return result as T;
  const id = result.id,
    existing = /\/(price-levels|price-plans)\/([^/]+)$/.exec(request.path)?.[2];
  if (
    typeof id !== 'string' ||
    !pricingId.test(id) ||
    (existing && id !== existing) ||
    !['row_version', 'policy_generation', 'source_version'].every(
      (key) => Number.isSafeInteger(result[key]) && Number(result[key]) >= 1,
    )
  )
    throw {
      status: 502,
      message:
        'The pricing receipt could not be verified. Retry the same save.',
    };
  const path = request.path.endsWith('/pricing/bootstrap')
    ? request.path.replace(/pricing\/bootstrap$/, 'price-levels/' + id)
    : request.path.replace(
        /\/(price-levels|price-plans)(?:\/[^/]+)?$/,
        '/$1/' + id,
      );
  try {
    const record = await masterRequest<MasterRow>({
      path,
      signal: request.signal,
    });
    pricingReceipt(
      record,
      request.path.split('/')[3]!,
      id,
      Number(result.row_version),
    );
    return record as T;
  } catch {
    throw {
      status: 502,
      message:
        'The save was received, but its current record could not be verified. Retry the same save to recover its receipt.',
    };
  }
};
export function canEditPricing(
  config: MasterConfig,
  fields: readonly MasterField[],
  row: MasterRow | null | undefined,
  access: PricingAccess,
) {
  if (
    !row ||
    !pricingVisible(fields, 'row_version') ||
    !Number.isSafeInteger(row.row_version)
  )
    return false;
  if (config.resource === 'price-plans')
    return (
      pricingVisible(fields, 'purpose') &&
      pricingPurposes.some((purpose) => purpose.value === row.purpose) &&
      pricingVisible(fields, 'name') &&
      typeof row.name === 'string' &&
      (row.purpose !== 'PURCHASE' ||
        (access.purchaseRead && access.purchaseManage)) &&
      (pricingWritable(fields, ['name']) ||
        fields.some(
          (field) =>
            field.source === 'custom' &&
            field.visible &&
            field.writable &&
            !field.conditional_access,
        ))
    );
  if (config.resource === 'price-levels')
    return (
      typeof row.name === 'string' &&
      typeof row.is_active === 'boolean' &&
      pricingVisible(fields, 'name') &&
      pricingVisible(fields, 'is_active') &&
      pricingWritable(fields, ['name'])
    );
  return ['code', 'name'].some((key) => pricingWritable(fields, [key]));
}
export function pricingBody(
  config: MasterConfig,
  fields: readonly MasterField[],
  values: Record<string, unknown>,
  previous?: MasterRow,
) {
  const draft = masterBody(config, fields, values, previous),
    errors = draft.errors,
    body = draft.body;
  if (config.resource === 'price-levels') {
    if (previous) {
      body.name = String(values.name ?? previous.name).trim();
      body.is_active = previous.is_active;
    } else if (!/^(?:[4-9]|[1-5]\d|6[0-4])$/.test(String(values.ordinal)))
      errors.ordinal = 'Choose a level number from 4 to 64.';
    if (
      !previous &&
      ['PRICE1', 'PRICE2', 'PRICE3'].includes(String(values.code))
    )
      errors.code =
        'Baseline codes are reserved. Set up baseline levels, then edit their names.';
  }
  if (config.resource === 'price-plans') {
    if (previous) body.name = String(values.name ?? previous.name).trim();
    else {
      if (
        values.purpose === 'SALE' &&
        !pricingId.test(String(values.price_level_id))
      )
        errors.price_level_id = 'Choose an active sales price level.';
      body.price_level_id =
        values.purpose === 'SALE' ? values.price_level_id : null;
      if (!/^[A-Z]{3}$/.test(String(values.currency)))
        errors.currency = 'Choose an available currency.';
    }
  }
  return draft;
}
export const pricingCustomWritable = (
  config: MasterConfig,
  fields: readonly MasterField[],
  values: Record<string, unknown>,
  creating: boolean,
) => masterCustomDraft(config, fields, values, creating);
