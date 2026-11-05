'use client';
import { masterReturn } from './master-navigation';
import { masterRequest, assertMasterFields, assertMaster } from './catalog-master-api';
import { dimensions, validMasterDate, type MasterConfig, type MasterField, type MasterFieldSet, type MasterRow } from './catalog-masters';
import { useServiceRead } from './service-resource';
import { identifierId, identifierVisible, identifierWritable } from './units-identifiers';
import { attributeResources } from './attribute-resources';
export const attributeId = identifierId,
  attributeVisible = identifierVisible,
  attributeWritable = identifierWritable;
export const attributeBase = (company: string, resource: string) =>
  '/v1/companies/' + company + '/' + resource;
export const valueTypes = [
  'TEXT',
  'INTEGER',
  'DECIMAL',
  'BOOLEAN',
  'DATE',
] as const;
export const attributeLabel = (row: MasterRow) =>
  row.name ?? row.code ?? 'Protected record';
export function attributeEditKeys(resource: string, row?: MasterRow | null) {
  const numeric = ['INTEGER', 'DECIMAL'].includes(String(row?.value_type));
  return [
    'code',
    'name',
    ...(resource === 'attribute-definitions'
      ? [
          'value_type',
          'is_variant_capable',
          ...(numeric ? ['measurement_dimension'] : []),
        ]
      : resource === 'attribute-options'
        ? [
            ...((valueTypes as readonly unknown[]).includes(row?.value_type)
              ? ['value_' + String(row?.value_type).toLowerCase()]
              : []),
            ...(numeric && typeof row?.unit_id === 'string' ? ['unit_id'] : []),
          ]
        : []),
  ];
}
export const attributeReceipt = (
  row: MasterRow,
  company: string,
  id?: string,
  previous?: number,
) => {
  assertMaster(row, company, id);
  // Canonically equivalent typed edits can be native no-ops with the same version.
  if (
    !attributeId.test(row.id) ||
    !Number.isSafeInteger(row.row_version) ||
    Number(row.row_version) < 1 ||
    (previous != null && Number(row.row_version) < previous)
  )
    throw {
      status: 502,
      message: 'The save receipt could not be verified. Retry the same save.',
    };
};
export function useAttributeFields(
  company: string,
  entity: string,
  operation?: 'create' | 'update' | 'publish',
  enabled = true,
) {
  return useServiceRead<MasterFieldSet>(
    enabled
      ? attributeBase(company, 'entities/' + entity + '/field-set') +
          (operation ? '?operation=' + operation : '')
      : undefined,
    masterRequest,
    (data) => assertMasterFields(data, company, entity),
  );
}
export function attributeReturn(
  value?: string,
  fallback = '/settings',
  depth = 0,
): string {
  if (
    value === '/settings' ||
    value === '/' ||
    value === '/masters/items'
  )
    return value;
  if (
    !value ||
    value.length > 8192 ||
    value.startsWith('//') ||
    /[%\\#]/.test(value.split('?')[0]!) ||
    value.split('?').length > 2
  )
    return fallback;
  try {
    const url = new URL(value, 'https://console.invalid'),
      id = attributeId.source.slice(1, -1);
    if (
      url.origin !== 'https://console.invalid' ||
      url.hash ||
      !new RegExp(
        '^/masters/(?:' +
          attributeResources.join('|') +
          ')(?:/(?:new|' +
          id +
          '(?:/edit|/revisions/(?:new|' +
          id +
          '))?))?$',
        'i',
      ).test(url.pathname)
    )
      return masterReturn(value, fallback, depth);
    const params = new URLSearchParams();
    for (const [key, item] of url.searchParams) {
      if (key === 'returnTo' && depth < 3)
        params.set(key, attributeReturn(item, fallback, depth + 1));
      else if (
        (key === 'q' && item.trim().length >= 2 && item.length <= 200) ||
        (['is_active', 'is_variant_capable', 'published'].includes(key) &&
          ['true', 'false'].includes(item)) ||
        (key === 'definition_id' && attributeId.test(item)) ||
        (key === 'value_type' &&
          valueTypes.includes(item as (typeof valueTypes)[number])) ||
        (key === 'measurement_dimension' &&
          (dimensions as readonly string[]).includes(item)) ||
        (key === 'sort' &&
          [
            'id',
            '-id',
            'code',
            '-code',
            'name',
            '-name',
            'revision',
            '-revision',
          ].includes(item)) ||
        (key === 'limit' && /^\d+$/.test(item) && +item >= 1 && +item <= 200)
      )
        params.set(key, item);
    }
    return url.pathname + (params.size ? '?' + params : '');
  } catch {
    return fallback;
  }
}
export const attributeLink = (path: string, back: string) =>
  path +
  (path.includes('?') ? '&' : '?') +
  new URLSearchParams({ returnTo: attributeReturn(back) });
export function exactAttributeInteger(value: unknown) {
  return (
    typeof value === 'string' &&
    /^-?(0|[1-9]\d{0,18})$/.test(value) &&
    BigInt(value) >= -9223372036854775808n &&
    BigInt(value) <= 9223372036854775807n
  );
}
export function exactAttributeDecimal(value: unknown) {
  return typeof value === 'string' && /^-?\d{1,15}(?:\.\d{1,4})?$/.test(value);
}
export function attributeBody(
  config: MasterConfig,
  fields: readonly MasterField[],
  values: Record<string, unknown>,
  previous?: MasterRow,
  definition?: MasterRow | null,
) {
  const body: Record<string, unknown> = previous
      ? { expected_version: previous.row_version }
      : {},
    errors: Record<string, string> = {};
  const option = config.resource === 'attribute-options',
    definitionResource = config.resource === 'attribute-definitions';
  const type = option
    ? (previous?.value_type ?? definition?.value_type)
    : values.value_type;
  const typedKey = 'value_' + String(type).toLowerCase();
  const keys = [
    'code',
    'name',
    ...(definitionResource
      ? ['value_type', 'measurement_dimension', 'is_variant_capable']
      : option
        ? [
            ...(!previous ? ['definition_id', 'value_type'] : []),
            typedKey,
            ...(definition?.measurement_dimension || previous?.unit_id
              ? ['unit_id']
              : []),
          ]
        : []),
  ];
  for (const key of keys) {
    if (!attributeWritable(fields, [key])) continue;
    let value = key === 'value_type' && option ? type : values[key];
    if (typeof value === 'string') value = value.trim();
    if (key === 'measurement_dimension') value = value || null;
    if (
      previous &&
      JSON.stringify(value) ===
        JSON.stringify(
          previous[key] ?? (key === 'measurement_dimension' ? null : undefined),
        )
    )
      continue;
    if (
      key === 'code' &&
      (typeof value !== 'string' || !/^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(value))
    )
      errors[key] =
        'Use an uppercase code with up to 30 letters, numbers, dots, hyphens or underscores.';
    if (
      ['name', 'value_text'].includes(key) &&
      (typeof value !== 'string' ||
        !value ||
        value.length > (key === 'name' ? 100 : 200) ||
        /[\x00-\x1f\x7f]/.test(value))
    )
      errors[key] = 'Enter printable text within the field length limit.';
    if (key === 'value_integer' && !exactAttributeInteger(value))
      errors[key] =
        'Enter a whole number from -9223372036854775808 to 9223372036854775807.';
    if (key === 'value_decimal' && !exactAttributeDecimal(value))
      errors[key] =
        'Enter an exact decimal with up to 15 whole digits and four decimal places.';
    if (key === 'value_date' && !validMasterDate(value))
      errors[key] = 'Choose a valid date from 1000-01-01 to 9999-12-31.';
    if (
      ['value_boolean', 'is_variant_capable'].includes(key) &&
      typeof value !== 'boolean'
    )
      errors[key] = 'Choose yes or no.';
    if (
      ['definition_id', 'unit_id'].includes(key) &&
      !attributeId.test(String(value))
    )
      errors[key] =
        'Choose an available ' +
        (key === 'unit_id' ? 'measurement unit.' : 'definition.');
    if (
      key === 'value_type' &&
      !(valueTypes as readonly unknown[]).includes(value)
    )
      errors[key] = 'Choose a supported value type.';
    if (
      key === 'measurement_dimension' &&
      value !== null &&
      (!(dimensions as readonly unknown[]).includes(value) ||
        !['INTEGER', 'DECIMAL'].includes(String(type)))
    )
      errors[key] =
        'Measurements require a numeric value type and a supported dimension.';
    body[key] = value;
  }
  if (
    previous &&
    (!Number.isSafeInteger(previous.row_version) ||
      Number(previous.row_version) < 1)
  )
    errors.row_version = 'Reload to obtain the current version.';
  return { body, errors };
}
export type AttributeMember = {
  definition_id: string;
  position: number;
  is_required: boolean;
  allow_variant_axis: boolean;
};
export function attributeMemberErrors(
  members: readonly AttributeMember[],
  definitions: Record<string, MasterRow>,
  publishing = false,
) {
  const errors: Record<string, string> = {},
    seen = new Set<string>();
  if (members.length > 128 || (publishing && !members.length))
    errors.members = publishing
      ? 'Add at least one definition before publishing (maximum 128).'
      : 'A template supports up to 128 definitions.';
  members.forEach((member, index) => {
    const key = 'members.' + index + '.definition_id',
      definition = definitions[member.definition_id];
    if (
      !attributeId.test(member.definition_id) ||
      seen.has(member.definition_id)
    )
      errors[key] = 'Choose a distinct definition.';
    else if (!definition || definition.is_active !== true)
      errors[key] = 'Choose an active, readable definition.';
    if (member.allow_variant_axis && definition?.is_variant_capable !== true)
      errors['members.' + index + '.allow_variant_axis'] =
        'This definition cannot distinguish variants.';
    seen.add(member.definition_id);
  });
  return errors;
}
export function verifyAttributeRevision(
  row: MasterRow,
  company: string,
  setId: string,
  id?: string,
  previous?: number,
) {
  attributeReceipt(row, company, id, previous);
  if (
    row.attribute_set_id !== setId ||
    !Number.isSafeInteger(row.revision) ||
    Number(row.revision) < 1 ||
    !('published_at' in row)
  )
    throw {
      status: 502,
      message:
        'The template revision could not be verified. Retry the same action.',
    };
}
