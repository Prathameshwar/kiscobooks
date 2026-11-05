'use client';
import { masterLink, masterReturn } from './master-navigation';
import {
  assertMasterFields,
  assertMaster,
  masterRequest,
} from './catalog-master-api';
import type {
  MasterConfig,
  MasterField,
  MasterFieldSet,
  MasterRow,
} from './catalog-masters';
import { masterBody, validMasterDate } from './catalog-masters';
import { useServiceRead } from './service-resource';
import {
  identifierId,
  identifierVisible,
  identifierWritable,
} from './units-identifiers';
import {
  classificationDefinitions,
  type ClassificationResource,
  typeSets,
} from './product-classification-resources';
export const catalogId = identifierId,
  catalogVisible = identifierVisible,
  catalogWritable = identifierWritable;
export const catalogBase = (company: string, resource: string) =>
  `/v1/companies/${company}/${resource}`;
export const catalogBack = masterReturn;
export const catalogLink = masterLink;
export function useCatalogFields(
  company: string,
  entity: string,
  operation?: 'create' | 'update' | 'publish',
  objectId?: string,
  enabled = true,
) {
  const params = new URLSearchParams();
  if (operation) params.set('operation', operation);
  if (
    objectId &&
    operation === 'update' &&
    ['catalog.item', 'catalog.product_family'].includes(entity)
  )
    params.set('object_id', objectId);
  return useServiceRead<MasterFieldSet>(
    enabled
      ? catalogBase(company, 'entities/' + entity + '/field-set') +
          (params.size ? '?' + params : '')
      : undefined,
    masterRequest,
    (data) => assertMasterFields(data, company, entity),
    'product field settings',
  );
}
export function catalogReceipt(
  row: MasterRow,
  company: string,
  id?: string,
  parent?: { key: string; id: string },
) {
  assertMaster(row, company, id);
  if (
    !catalogId.test(row.id) ||
    !Number.isSafeInteger(row.row_version) ||
    Number(row.row_version) < 1 ||
    (parent && row[parent.key] !== parent.id)
  )
    throw {
      status: 502,
      message:
        'The saved record could not be verified. Retry the same save to recover its result.',
    };
  return row;
}
export function classificationBody(
  config: MasterConfig,
  fields: readonly MasterField[],
  values: Record<string, unknown>,
  previous?: MasterRow,
) {
  const resource = config.resource as ClassificationResource,
    definition = classificationDefinitions[resource];
  const result = nativeCatalogBody(
    fields,
    previous ? definition.update : definition.create,
    values,
    previous,
  );
  // Reuse custom-field defaults, conditional validation and exact patching.
  const custom = masterBody(
    { ...config, inputs: {} },
    fields,
    values,
    previous,
  );
  if ('custom_fields' in custom.body)
    result.body.custom_fields = custom.body.custom_fields;
  Object.assign(result.errors, custom.errors);
  if (
    resource === 'product-families' &&
    ('series_id' in result.body || 'brand_id' in result.body) &&
    values.series_id &&
    !values.brand_id
  )
    result.errors.series_id = 'Choose a brand before its series.';
  if (
    resource === 'manufacturer-sites' &&
    ('state_code' in result.body || 'country_code' in result.body) &&
    values.state_code &&
    (!values.country_code ||
      !String(values.state_code).startsWith(String(values.country_code) + '-'))
  )
    result.errors.state_code = 'Choose a state in the selected country.';
  return result;
}
export function nativeCatalogBody(
  fields: readonly MasterField[],
  keys: readonly string[],
  values: Record<string, unknown>,
  previous?: MasterRow,
) {
  const body: Record<string, unknown> = previous
      ? { expected_version: previous.row_version }
      : {},
    errors: Record<string, string> = {};
  if (
    previous &&
    (!catalogVisible(fields, 'row_version') ||
      !Number.isSafeInteger(previous.row_version) ||
      Number(previous.row_version) < 1)
  )
    errors.row_version = 'Reload the record to obtain its current version.';
  for (const key of keys) {
    const field = fields.find(
        (entry) => entry.source === 'native' && entry.key === key,
      ),
      control = field?.control;
    if (!field || !catalogWritable(fields, [key]) || !control) {
      if (!previous && values[key] != null && values[key] !== '')
        errors[key] =
          'This value requires field access before the record can be created.';
      continue;
    }
    let value = values[key];
    if (typeof value === 'string') value = value.trim();
    if ((value == null || value === '') && control.nullable) value = null;
    if (previous && JSON.stringify(value) === JSON.stringify(previous[key]))
      continue;
    if (
      (field.required || !control.nullable) &&
      (value == null || value === '' || (Array.isArray(value) && !value.length))
    ) {
      errors[key] = `${control.label} is required.`;
      continue;
    }
    if (value === null) {
      body[key] = null;
      continue;
    }
    if (typeSets.includes(key)) {
      if (
        !Array.isArray(value) ||
        !value.length ||
        new Set(value).size !== value.length ||
        value.some(
          (entry) =>
            !(control.choices ?? []).some((choice) => choice.value === entry),
        )
      )
        errors[key] =
          'Select at least one available option without duplicates.';
      else body[key] = [...value].sort();
      continue;
    }
    if (control.kind === 'boolean' && typeof value !== 'boolean')
      errors[key] = 'Choose yes or no.';
    else if (
      control.kind === 'select' &&
      !(control.choices ?? []).some((choice) => choice.value === value)
    )
      errors[key] = 'Choose an available option.';
    else if (
      control.kind === 'reference' &&
      (typeof value !== 'string' || !catalogId.test(value))
    )
      errors[key] = 'Choose an available record.';
    else if (control.kind === 'date' && !validMasterDate(value))
      errors[key] = 'Choose a valid date.';
    else if (control.kind === 'integer') {
      if (
        !/^\d+$/.test(String(value)) ||
        !Number.isSafeInteger(Number(value)) ||
        Number(value) < (control.minimum ?? 0) ||
        Number(value) > (control.maximum ?? Number.MAX_SAFE_INTEGER)
      )
        errors[key] = 'Enter a whole number within the allowed range.';
      else body[key] = Number(value);
      continue;
    } else if (
      control.kind === 'decimal' &&
      (typeof value !== 'string' ||
        !/^\d{1,15}(?:\.\d{1,4})?$/.test(value) ||
        !/[1-9]/.test(value))
    )
      errors[key] =
        'Enter a positive exact quantity with up to four decimal places.';
    else if (
      control.kind === 'text' &&
      (typeof value !== 'string' ||
        value.length > (control.max_length ?? 2000) ||
        (key === 'description'
          ? /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/
          : /[\x00-\x1f\x7f]/
        ).test(value))
    )
      errors[key] = 'Enter printable text within the displayed limit.';
    else if (
      ['code', 'sku'].includes(key) &&
      !/^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(String(value))
    )
      errors[key] =
        'Use uppercase letters, numbers, dots, hyphens or underscores.';
    else if (key === 'country_code' && !/^[A-Z]{2}$/.test(String(value)))
      errors[key] = 'Choose a country.';
    else if (
      ['numerator', 'denominator'].includes(key) &&
      (!/^[1-9]\d{0,18}$/.test(String(value)) ||
        BigInt(String(value)) >= 2n ** 63n)
    )
      errors[key] = 'Enter a positive whole number below 9223372036854775808.';
    body[key] = value;
  }
  return { body, errors };
}
export function validateTypeRequirements(
  values: Record<string, unknown>,
  kind: unknown,
) {
  const errors: Record<string, string> = {},
    inventory = values.inventory_modes as string[] | undefined,
    tracking = values.tracking_modes as string[] | undefined,
    units = values.unit_dimensions as string[] | undefined;
  if (
    !Array.isArray(inventory) ||
    !Array.isArray(tracking) ||
    !Array.isArray(units)
  )
    return errors;
  if (
    kind === 'SERVICE' &&
    (inventory.join() !== 'NON_STOCK' || tracking.join() !== 'NONE')
  )
    errors.inventory_modes =
      'Services require non-stock inventory and no physical tracking.';
  if (
    kind !== 'GOODS' &&
    (values.require_manufacturer ||
      values.require_expiry ||
      values.inventory_template_revision_id ||
      values.handling_revision_id)
  )
    errors.require_expiry =
      'Physical requirements and profiles require a goods-only type.';
  if (
    kind === 'BOTH' &&
    (!inventory.includes('NON_STOCK') || !tracking.includes('NONE'))
  )
    errors.inventory_modes =
      'A mixed type must also allow non-stock, untracked services.';
  if (
    (inventory.includes('NON_STOCK') && !tracking.includes('NONE')) ||
    (inventory.length === 1 &&
      inventory[0] === 'NON_STOCK' &&
      tracking.some((value) => value !== 'NONE'))
  )
    errors.tracking_modes =
      'Physical tracking requires stock; non-stock requires no tracking.';
  if (
    (tracking.some((value) => ['SERIAL', 'BATCH_SERIAL'].includes(value)) &&
      !units.includes('COUNT')) ||
    (tracking.length > 0 &&
      tracking.every((value) => ['SERIAL', 'BATCH_SERIAL'].includes(value)) &&
      (units.length !== 1 || units[0] !== 'COUNT'))
  )
    errors.unit_dimensions =
      'Serial tracking requires count units; exclusively serial tracking allows only count.';
  if (
    values.require_expiry &&
    (inventory.join() !== 'STOCK' ||
      tracking.some((value) => !['BATCH', 'BATCH_SERIAL'].includes(value)))
  )
    errors.require_expiry = 'Expiry requires stock with batch tracking.';
  return errors;
}
