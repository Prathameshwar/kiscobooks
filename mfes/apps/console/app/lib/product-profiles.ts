'use client';
import { masterReturn } from './master-navigation';
import {
  assertMaster,
  assertMasterFields,
  masterRequest,
} from './catalog-master-api';
import type { MasterField, MasterFieldSet, MasterRow } from './catalog-masters';
import { useServiceRead, type ServicePage } from './service-resource';
import {
  identifierBase,
  identifierId,
  identifierVisible,
  identifierWritable,
} from './units-identifiers';
import {
  profileDefinitions,
  conditionCodes,
  profileDefaults,
  revisionedDefinitionResources,
  type ProductProfileResource,
} from './product-profile-resources';
import { allowedProductProfileRequest } from './product-profile-request-policy';
export const profileBase = identifierBase,
  profileId = identifierId,
  profileVisible = identifierVisible,
  profileWritable = identifierWritable;
export { conditionCodes, profileDefaults } from './product-profile-resources';
export const profileKeys = (resource: ProductProfileResource) =>
  Object.keys(profileDefaults[resource]).filter(
    (key) => key !== 'condition_codes' && key !== 'steps',
  );
export function useProfileFields(
  company: string,
  entity: string,
  operation?: 'create' | 'update' | 'publish',
  enabled = true,
) {
  return useServiceRead<MasterFieldSet>(
    enabled
      ? profileBase(company, 'entities/' + entity + '/field-set') +
          (operation ? '?operation=' + operation : '')
      : undefined,
    masterRequest,
    (data) => assertMasterFields(data, company, entity),
  );
}
export function profileReturn(
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
    const url = new URL(value, 'https://console.invalid');
    if (
      url.origin !== 'https://console.invalid' ||
      url.hash ||
      !new RegExp(
        '^/masters/(?:' +
          revisionedDefinitionResources.join('|') +
          ')(?:/(?:new|' +
          profileId.source.slice(1, -1) +
          '(?:/edit|/revisions/(?:new|' +
          profileId.source.slice(1, -1) +
          '))?))?$',
        'i',
      ).test(url.pathname)
    )
      return masterReturn(value, fallback, depth);
    const params = new URLSearchParams();
    for (const [key, item] of url.searchParams) {
      if (key === 'returnTo' && depth < 3)
        params.set(key, profileReturn(item, fallback, depth + 1));
      else if (
        allowedProductProfileRequest(
          'GET',
          '/v1/companies/00000000-0000-7000-8000-000000000001/' +
            url.pathname.split('/')[2] +
            '?' +
            new URLSearchParams({ [key]: item }),
        ) === true
      )
        params.set(key, item);
    }
    return url.pathname + (params.size ? '?' + params : '');
  } catch {
    return fallback;
  }
}
export const profileLink = (href: string, back: string) =>
  href +
  (href.includes('?') ? '&' : '?') +
  new URLSearchParams({ returnTo: profileReturn(back) });
export function profileReceipt(
  row: MasterRow,
  company: string,
  id?: string,
  version?: number,
) {
  assertMaster(row, company, id);
  if (
    !profileId.test(row.id) ||
    !Number.isSafeInteger(row.row_version) ||
    Number(row.row_version) < 1 ||
    (version != null && Number(row.row_version) < version)
  )
    throw {
      status: 502,
      message: 'The save receipt could not be verified. Retry the same action.',
    };
}
export function verifyProfileRevision(
  row: MasterRow,
  company: string,
  resource: ProductProfileResource,
  parent: string,
  id?: string,
  receipt = false,
  version?: number,
  published = false,
) {
  assertMaster(row, company, id);
  const key = profileDefinitions[resource].parent;
  if (
    resource === 'manufacturing-routes' &&
    receipt &&
    (!Number.isSafeInteger(row.step_count) ||
      Number(row.step_count) < 0 ||
      Number(row.step_count) > 50 ||
      (published && Number(row.step_count) === 0))
  )
    throw {
      status: 502,
      message: 'The complete route revision receipt could not be verified.',
    };
  if (
    ['manufacturing-operations', 'manufacturing-routes'].includes(resource) &&
    receipt &&
    (!['DRAFT', 'PUBLISHED', 'RETIRED'].includes(String(row.status)) ||
      (row.status === 'DRAFT') !== (row.published_at === null))
  )
    throw {
      status: 502,
      message: 'The definition revision status could not be verified.',
    };
  if (!profileId.test(row.id) || (key in row && row[key] !== parent))
    throw {
      status: 502,
      message: 'This revision does not belong to the selected profile.',
    };
  if (receipt) {
    profileReceipt(row, company, id, version);
    if (
      row[key] !== parent ||
      !Number.isSafeInteger(row.revision) ||
      Number(row.revision) < 1 ||
      !('published_at' in row) ||
      (row.published_at !== null &&
        (typeof row.published_at !== 'string' ||
          !Number.isFinite(Date.parse(row.published_at)))) ||
      (published && row.published_at === null)
    )
      throw {
        status: 502,
        message:
          'The revision receipt could not be verified. Retry the same action.',
      };
  }
}
export function verifyProfileConditions(
  page: ServicePage<MasterRow>,
  revision: string,
  count: unknown,
): string[] {
  if (
    !Array.isArray(page.items) ||
    !page.page ||
    page.page.has_more !== false ||
    !Number.isSafeInteger(count) ||
    Number(count) < 0 ||
    Number(count) > 5 ||
    page.items.length !== count ||
    page.items.some(
      (row) =>
        !profileId.test(row.id) ||
        row.revision_id !== revision ||
        !conditionCodes.includes(
          row.condition_code as (typeof conditionCodes)[number],
        ),
    ) ||
    new Set(page.items.map((row) => row.condition_code)).size !==
      page.items.length ||
    new Set(page.items.map((row) => row.id)).size !== page.items.length
  )
    throw {
      status: 502,
      message:
        'The complete return condition set could not be verified. Reload before changing or publishing it.',
    };
  return page.items.map((row) => String(row.condition_code));
}
// Temperatures retain their exact decimal representation; compare fixed-point integers.
export function profileTemperature(value: unknown): bigint | null {
  if (typeof value !== 'string' || !/^-?\d{1,15}(?:\.\d{1,4})?$/.test(value))
    return null;
  const negative = value.startsWith('-'),
    [whole, fraction = ''] = value.replace(/^-/, '').split('.');
  return BigInt(whole! + fraction.padEnd(4, '0')) * (negative ? -1n : 1n);
}
export function profileBody(
  resource: ProductProfileResource,
  fields: readonly MasterField[],
  values: Record<string, unknown>,
  previous?: MasterRow,
  conditionsWritable = false,
) {
  const body: Record<string, unknown> = previous
      ? { expected_version: previous.row_version }
      : {},
    errors: Record<string, string> = {};
  if (
    previous &&
    (!Number.isSafeInteger(previous.row_version) ||
      Number(previous.row_version) < 1)
  )
    errors.row_version = 'Reload the saved version before saving.';
  for (const key of profileKeys(resource)) {
    const field = fields.find((field) => field.key === key),
      control = field?.control;
    if (
      !field ||
      !control ||
      !profileWritable(fields, [key]) ||
      !(key in values)
    )
      continue;
    let value = values[key];
    if (typeof value === 'string') value = value.trim();
    if (control.nullable && (value === '' || value == null)) value = null;
    if (
      control.kind === 'integer' &&
      value != null &&
      value !== '' &&
      /^\d+$/.test(String(value))
    )
      value = Number(value);
    if (previous && JSON.stringify(value) === JSON.stringify(previous[key]))
      continue;
    if (value === null && control.nullable) {
      body[key] = null;
      continue;
    }
    if (control.kind === 'boolean' && typeof value !== 'boolean')
      errors[key] = 'Choose a valid option.';
    else if (
      control.kind === 'integer' &&
      (!Number.isSafeInteger(value) ||
        Number(value) < (control.minimum ?? 0) ||
        Number(value) > (control.maximum ?? 36500))
    )
      errors[key] = 'Enter a whole number within the allowed range.';
    else if (
      control.kind === 'select' &&
      !control.choices?.some((choice) => choice.value === value)
    )
      errors[key] = 'Choose an available option.';
    else if (
      key.startsWith('temperature_') &&
      key !== 'temperature_unit' &&
      profileTemperature(value) === null
    )
      errors[key] =
        'Enter an exact temperature with up to 15 whole digits and 4 decimal places.';
    else if (
      control.kind === 'text' &&
      (typeof value !== 'string' ||
        !value ||
        value.length > (control.max_length ?? 2000) ||
        /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(value))
    )
      errors[key] = 'Enter readable text within the allowed length.';
    else if (control.kind === 'reference' && !profileId.test(String(value)))
      errors[key] = 'Choose an available reference.';
    else body[key] = value;
  }
  const effective = { ...previous, ...values, ...body },
    changed = (keys: string[]) => !previous || keys.some((key) => key in body);
  const rule = (keys: string[], invalid: boolean, message: string) => {
    if (changed(keys) && invalid)
      errors[keys.find((key) => key in body) ?? keys[0]!] = message;
  };
  if (resource === 'inventory-templates') {
    const trackingKeys = [
      'expiry_required',
      'manufacture_date_required',
      'shelf_life_days',
      'minimum_remaining_life_days',
    ];
    rule(
      ['lot_tracking', ...trackingKeys],
      effective.lot_tracking === false &&
        (effective.expiry_required === true ||
          effective.manufacture_date_required === true ||
          effective.shelf_life_days != null ||
          effective.minimum_remaining_life_days != null),
      'Enable batch / lot tracking for date and shelf-life rules.',
    );
    rule(
      ['issue_strategy', 'minimum_remaining_life_days', 'expiry_required'],
      effective.expiry_required === false &&
        (effective.issue_strategy === 'FEFO' ||
          effective.minimum_remaining_life_days != null),
      'Require expiry dates for FEFO or minimum remaining life.',
    );
    rule(
      ['shelf_life_days', 'minimum_remaining_life_days'],
      effective.shelf_life_days != null &&
        effective.minimum_remaining_life_days != null &&
        Number(effective.minimum_remaining_life_days) >
          Number(effective.shelf_life_days),
      'Minimum remaining life cannot exceed shelf life.',
    );
    rule(
      ['serial_tracking', 'identifier_profile_id', 'valuation_method'],
      effective.serial_tracking === false &&
        (effective.identifier_profile_id != null ||
          effective.valuation_method === 'SPECIFIC'),
      'Enable serial tracking for identifier profiles or specific valuation.',
    );
  }
  if (resource === 'warranty-policies') {
    const maximum = { DAYS: 36500, MONTHS: 1200, YEARS: 100 }[
      String(effective.duration_unit) as 'DAYS'
    ];
    rule(
      ['duration', 'duration_unit'],
      maximum !== undefined && Number(effective.duration) > maximum,
      `Duration exceeds the ${maximum ?? ''} limit for the selected calendar unit.`,
    );
  }
  if (resource === 'return-policies') {
    const codes = values.condition_codes;
    if (
      conditionsWritable &&
      Array.isArray(codes) &&
      (!previous ||
        JSON.stringify([...codes].sort()) !==
          JSON.stringify(
            [...((previous.condition_codes as string[]) ?? [])].sort(),
          ))
    ) {
      if (
        codes.length > 5 ||
        new Set(codes).size !== codes.length ||
        codes.some(
          (code) =>
            !conditionCodes.includes(code as (typeof conditionCodes)[number]),
        )
      )
        errors.condition_codes = 'Choose distinct supported return conditions.';
      else body.condition_codes = codes;
    }
    rule(
      ['returns_allowed', 'window_days', 'condition_codes'],
      effective.returns_allowed === true && effective.window_days === null,
      'Enter a return window; zero days is allowed.',
    );
    rule(
      ['returns_allowed', 'window_days', 'condition_codes'],
      effective.returns_allowed === false &&
        (effective.window_days != null ||
          (Array.isArray(codes) && codes.length > 0)),
      'Clear the window and conditions before disabling returns.',
    );
  }
  if (resource === 'handling-profiles') {
    const min = profileTemperature(effective.temperature_min),
      max = profileTemperature(effective.temperature_max),
      bound =
        effective.temperature_min != null || effective.temperature_max != null;
    rule(
      ['temperature_min'],
      min !== null && min < -2731500n,
      'Temperature cannot be below absolute zero (-273.15 °C).',
    );
    rule(
      ['temperature_max'],
      max !== null && max < -2731500n,
      'Temperature cannot be below absolute zero (-273.15 °C).',
    );
    rule(
      ['temperature_min', 'temperature_max'],
      min !== null && max !== null && min > max,
      'Minimum temperature cannot exceed maximum temperature.',
    );
    rule(
      ['temperature_min', 'temperature_max', 'temperature_unit'],
      (bound && effective.temperature_unit === null) ||
        (!bound &&
          'temperature_min' in effective &&
          'temperature_max' in effective &&
          effective.temperature_unit === 'CELSIUS'),
      'Select Celsius when a bound is set; clear the unit when both bounds are empty.',
    );
  }
  return { body, errors };
}
