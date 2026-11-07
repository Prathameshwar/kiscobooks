'use client';
import { masterReturn } from './master-navigation';
import {
  assertMaster,
  assertMasterFields,
  masterRequest,
} from './catalog-master-api';
import type {
  MasterConfig,
  MasterField,
  MasterFieldSet,
  MasterRow,
} from './catalog-masters';
import { useServiceRead } from './service-resource';
import { identifierResources } from './units-identifiers-resources';
export { identifierResources, isUnitsIdentifier } from './units-identifiers-resources';

export const identifierId = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const identifierBase = (company: string, resource: string) =>
  '/v1/companies/' + company + '/' + resource;
export const identifierVisible = (
  fields: readonly MasterField[],
  key: string,
) =>
  fields.some(
    (field) =>
      field.key === key &&
      field.source === 'native' &&
      field.visible &&
      !field.conditional_access,
  );
export const identifierWritable = (
  fields: readonly MasterField[],
  keys: readonly string[],
) =>
  keys.every((key) =>
    fields.some(
      (field) =>
        field.key === key &&
        field.source === 'native' &&
        field.visible &&
        field.writable &&
        !field.conditional_access,
    ),
  );
export const identifierTitle = (row: MasterRow) =>
  row.name ?? row.code ?? 'Protected record';
export const identifierCodeSearch = (resource: string) =>
  ['identifier-types', 'identifier-namespaces'].includes(resource);
export function useIdentifierFields(
  company: string,
  entity: string,
  operation?: 'create' | 'update',
  enabled = true,
) {
  return useServiceRead<MasterFieldSet>(
    enabled
      ? identifierBase(company, 'entities/' + entity + '/field-set') +
          (operation ? '?operation=' + operation : '')
      : undefined,
    masterRequest,
    (data) => assertMasterFields(data, company, entity),
  );
}
export function identifierReturn(
  value?: string,
  fallback = '/masters/units',
  depth = 0,
): string {
  if (value === '/settings' || value === '/') return value;
  if (
    !value ||
    value.length > 8192 ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
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
        '^/masters/(?:units|' +
          identifierResources.join('|') +
          ')(?:/(?:new|' +
          identifierId.source.slice(1, -1) +
          '(?:/edit)?))?$',
        'i',
      ).test(url.pathname)
    )
      return masterReturn(value, fallback, depth);
    const params = new URLSearchParams();
    for (const [key, item] of url.searchParams) {
      if (key === 'returnTo' && depth < 3)
        params.set(key, identifierReturn(item, fallback, depth + 1));
      if (
        (key === 'q' && item.trim().length >= 2 && item.length <= 200) ||
        (['is_active', 'is_barcode'].includes(key) &&
          ['true', 'false'].includes(item)) ||
        (key === 'sort' &&
          ['id', '-id', 'code', '-code', 'name', '-name'].includes(item)) ||
        (key === 'limit' && /^\d+$/.test(item) && +item >= 1 && +item <= 200) ||
        (['from_unit_id', 'canonical_unit_id'].includes(key) &&
          identifierId.test(item))
      )
        params.set(key, item);
    }
    return url.pathname + (params.size ? '?' + params : '');
  } catch {
    return fallback;
  }
}
export function identifierLink(path: string, back: string) {
  return (
    path +
    (path.includes('?') ? '&' : '?') +
    new URLSearchParams({ returnTo: identifierReturn(back) })
  );
}
export function identifierReceipt(
  row: MasterRow,
  company: string,
  conversion: boolean,
  id?: string,
  previous?: number,
) {
  assertMaster(row, company, id);
  if (
    !identifierId.test(row.id) ||
    (!conversion &&
      (!Number.isSafeInteger(row.row_version) ||
        Number(row.row_version) < 1 ||
        (previous != null && Number(row.row_version) <= previous)))
  )
    throw {
      status: 502,
      message: 'The save receipt could not be verified. Retry the same save.',
    };
}
export function ratioPart(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^[1-9]\d{0,18}$/.test(value) &&
    BigInt(value) <= 9223372036854775807n
  );
}
export function reducedRatio(numerator: unknown, denominator: unknown) {
  if (!ratioPart(numerator) || !ratioPart(denominator)) return null;
  let a = BigInt(numerator),
    b = BigInt(denominator);
  while (b) {
    const next = a % b;
    a = b;
    b = next;
  }
  return {
    numerator: (BigInt(numerator) / a).toString(),
    denominator: (BigInt(denominator) / a).toString(),
  };
}
export const initialRequirement = () => ({
  identifier_type: 'SERIAL',
  namespace_rule: 'COMPANY',
  min_count: '1',
  max_count: '1',
  requires_slot: false,
});
export function identifierBody(
  config: MasterConfig,
  fields: readonly MasterField[],
  draft: Record<string, unknown>,
  requirements: Record<string, unknown>[] = [],
  child: readonly MasterField[] = [],
  previous?: MasterRow,
) {
  const errors: Record<string, string> = {},
    body: Record<string, unknown> = previous
      ? { expected_version: previous.row_version }
      : {};
  const keys =
    previous &&
    ['identifier-types', 'identifier-namespaces', 'identifier-profiles'].includes(config.resource)
      ? ['name']
      : config.resource === 'unit-conversions'
        ? ['from_unit_id', 'canonical_unit_id', 'numerator', 'denominator']
        : [
            'code',
            'name',
            ...(config.resource === 'identifier-types' ? ['is_barcode'] : []),
          ];
  if (
    previous &&
    (!Number.isSafeInteger(previous.row_version) ||
      Number(previous.row_version) < 1)
  )
    errors.row_version = 'Reload to obtain the current record version.';
  for (const key of keys) {
    const field = fields.find(
      (row) => row.key === key && row.source === 'native',
    );
    if (
      !field?.visible ||
      !field.writable ||
      field.conditional_access ||
      !field.control
    )
      continue;
    const value =
        typeof draft[key] === 'string'
          ? (draft[key] as string).trim()
          : draft[key],
      label = field.control.label;
    if (previous && value === previous[key]) continue;
    if (key === 'is_barcode') {
      if (typeof value !== 'boolean')
        errors[key] = 'Choose the identifier classification.';
    } else if (key.endsWith('_unit_id')) {
      if (!identifierId.test(String(value)))
        errors[key] = 'Choose an available unit.';
    } else if (['numerator', 'denominator'].includes(key)) {
      if (!ratioPart(value))
        errors[key] =
          'Enter a positive whole number up to 9223372036854775807.';
    } else if (
      typeof value !== 'string' ||
      !value ||
      value.length > (field.control.max_length ?? 100) ||
      /[\x00-\x1f\x7f]/.test(value)
    )
      errors[key] =
        `${label} is required and must contain printable text within its length limit.`;
    else if (key === 'code' && !/^[A-Z0-9][A-Z0-9_.-]*$/.test(value))
      errors[key] =
        'Use uppercase letters, numbers, dots, hyphens or underscores.';
    body[key] = value;
  }
  if (
    !previous &&
    config.resource === 'unit-conversions' &&
    draft.from_unit_id &&
    draft.from_unit_id === draft.canonical_unit_id &&
    draft.numerator !== draft.denominator
  )
    errors.numerator =
      'A canonical root must convert to itself with a 1 to 1 ratio.';
  if (!previous && config.resource === 'identifier-profiles') {
    if (
      !identifierWritable(child, [
        'identifier_type',
        'namespace_rule',
        'min_count',
        'max_count',
        'requires_slot',
      ])
    )
      errors.requirements =
        'Your field access does not allow the required profile rules.';
    if (!requirements.length || requirements.length > 2)
      errors.requirements = 'Add one or two distinct identifier requirements.';
    const seen = new Set<string>();
    body.requirements = requirements.map((row, index) => {
      const out: Record<string, unknown> = {};
      for (const field of child.filter((field) =>
        [
          'identifier_type',
          'namespace_rule',
          'min_count',
          'max_count',
          'requires_slot',
        ].includes(field.key),
      )) {
        const c = field.control,
          value = row[field.key];
        if (!c || !field.visible || !field.writable || field.conditional_access)
          continue;
        out[field.key] =
          c.kind === 'integer' && /^\d$/.test(String(value))
            ? Number(value)
            : value;
        if (
          (c.kind === 'select' &&
            !c.choices?.some((choice) => choice.value === value)) ||
          (c.kind === 'boolean' && typeof value !== 'boolean') ||
          (c.kind === 'integer' &&
            (!/^\d$/.test(String(value)) ||
              Number(value) < (c.minimum ?? 0) ||
              Number(value) > (c.maximum ?? 8)))
        )
          errors[`requirements.${index}.${field.key}`] =
            'Choose a supported value within the allowed bounds.';
      }
      if (seen.has(String(row.identifier_type)))
        errors[`requirements.${index}.identifier_type`] =
          'Each identifier type can appear only once.';
      seen.add(String(row.identifier_type));
      if (Number(row.min_count) > Number(row.max_count))
        errors[`requirements.${index}.min_count`] =
          'Minimum count cannot exceed maximum count.';
      if (Number(row.max_count) > 1 && row.requires_slot !== true)
        errors[`requirements.${index}.requires_slot`] =
          'Multiple identifiers require explicit slots.';
      if (row.identifier_type === 'IMEI' && row.namespace_rule !== 'COMPANY')
        errors[`requirements.${index}.namespace_rule`] =
          'IMEI uses the company namespace.';
      return out;
    });
  }
  return { body, errors };
}
