'use client';
import type { components } from '@janso/api-client/catalog';
import { useRef } from 'react';
import { useServiceRead } from './service-resource';
import { masterRequest } from './catalog-master-api';
import type { MasterField } from './catalog-masters';
import { catalogId } from './product-classification';

export type ProductEntryConfiguration =
  components['schemas']['EffectiveConfiguration'];
export type ProductEntryDefaults = components['schemas']['AuthoringDefaults'];
export type ProductEntryOption =
  | 'variants'
  | 'barcode'
  | 'brand'
  | 'category'
  | 'manufacturer'
  | 'alternate_units'
  | 'compound_units'
  | 'measured_units';
const options: ProductEntryOption[] = [
  'variants',
  'barcode',
  'brand',
  'category',
  'manufacturer',
  'alternate_units',
  'compound_units',
  'measured_units',
];
export function verifyEntryConfiguration(
  value: ProductEntryConfiguration,
  company: string,
  date: string,
  kind?: string,
) {
  if (
    !value ||
    value.company_id !== company ||
    value.as_of !== date ||
    !['GOODS', 'SERVICE'].includes(value.kind) ||
    (kind && value.kind !== kind) ||
    !Number.isSafeInteger(value.policy_generation) ||
    value.policy_generation < 1 ||
    !Number.isSafeInteger(value.source_version) ||
    value.source_version < 1 ||
    !Array.isArray(value.sources)
  )
    throw {
      status: 502,
      message:
        'Product configuration could not be verified. Reload before changing configuration-dependent values.',
    };
  for (const option of options) {
    const mode =
      value.options?.[(option + '_mode') as keyof typeof value.options];
    const initial =
      value.options?.[(option + '_default') as keyof typeof value.options];
    if (
      !['DISABLED', 'OPTIONAL', 'REQUIRED'].includes(String(mode)) ||
      (mode === 'OPTIONAL' && typeof initial !== 'boolean') ||
      (mode !== 'OPTIONAL' && initial != null)
    )
      throw {
        status: 502,
        message:
          'Product option settings are incomplete. Reload configuration before continuing.',
      };
  }
  return value;
}
export function entryOption(
  config: ProductEntryConfiguration | null | undefined,
  key: ProductEntryOption,
) {
  const mode =
    config?.options[
      (key + '_mode') as keyof ProductEntryConfiguration['options']
    ];
  const initial =
    config?.options[
      (key + '_default') as keyof ProductEntryConfiguration['options']
    ];
  return {
    mode,
    allowed: mode === 'OPTIONAL' || mode === 'REQUIRED',
    required: mode === 'REQUIRED',
    enabled: mode === 'REQUIRED' || (mode === 'OPTIONAL' && initial === true),
    reason: !config
      ? 'Product configuration must be available before adding this record.'
      : mode === 'DISABLED'
        ? 'Disabled by the effective product configuration. Existing records remain readable.'
        : undefined,
  };
}
export function useProductEntryConfiguration(
  company: string,
  date: string,
  owner: { itemId?: string; familyId?: string; kind?: unknown },
  enabled: boolean,
) {
  const validItem = !!owner.itemId && catalogId.test(owner.itemId);
  const validFamily =
    !!owner.familyId &&
    catalogId.test(owner.familyId) &&
    ['GOODS', 'SERVICE'].includes(String(owner.kind));
  const params = new URLSearchParams({ as_of: date });
  if (!validItem && validFamily) {
    params.set('kind', String(owner.kind));
    params.set('family_id', owner.familyId!);
  }
  const context = `${enabled}:${company}:${date}:${owner.itemId ?? owner.familyId}:${String(owner.kind)}`;
  const verifiedContext = useRef('');
  const read = useServiceRead<ProductEntryConfiguration>(
    enabled && (validItem || validFamily)
      ? `/v1/companies/${company}/` +
          (validItem
            ? `items/${owner.itemId}/configuration`
            : 'product-configuration/effective') +
          '?' +
          params
      : undefined,
    masterRequest,
    (value) => {
      verifyEntryConfiguration(
        value,
        company,
        date,
        validItem ? undefined : String(owner.kind),
      );
      verifiedContext.current = context;
    },
    'product configuration',
  );
  return {
    ...read,
    data: verifiedContext.current === context ? read.data : null,
  };
}
export function useProductEntryDefaults(
  company: string,
  date: string,
  selection: {
    kind: unknown;
    familyId?: string;
    itemId?: string;
    typeId?: string;
    unitId?: string;
    groupId?: string;
  },
  enabled: boolean,
) {
  const params = new URLSearchParams({
    as_of: date,
    kind: String(selection.kind),
    include_price: 'false',
  });
  for (const [key, value] of [
    ['family_id', selection.familyId],
    ['item_id', selection.itemId],
    ['product_type_revision_id', selection.typeId],
    ['unit_id', selection.unitId],
    ['group_id', selection.groupId],
  ] as const)
    if (value && catalogId.test(value)) params.set(key, value);
  const context = `${enabled}:${company}:${params}`;
  const verifiedContext = useRef('');
  const read = useServiceRead<ProductEntryDefaults>(
    enabled && ['GOODS', 'SERVICE'].includes(String(selection.kind))
      ? `/v1/companies/${company}/product-configuration/authoring-defaults?${params}`
      : undefined,
    masterRequest,
    (value) => {
      verifyEntryConfiguration(
        value?.configuration,
        company,
        date,
        String(selection.kind),
      );
      if (
        !value.acceptance ||
        value.acceptance.as_of !== date ||
        value.acceptance.expected_generation !==
          value.configuration.policy_generation ||
        value.acceptance.expected_source_version !==
          value.configuration.source_version ||
        (value.product_type_revision_id != null &&
          !catalogId.test(value.product_type_revision_id)) ||
        (value.quantity &&
          (value.quantity.unit_id !== selection.unitId ||
            !Number.isInteger(value.quantity.quantity_decimal_places) ||
            value.quantity.quantity_decimal_places < 0 ||
            value.quantity.quantity_decimal_places > 4 ||
            !/^\d+(?:\.\d{1,4})?$/.test(value.quantity.quantity_increment) ||
            typeof value.quantity.fractional_entry !== 'boolean'))
      )
        throw {
          status: 502,
          message:
            'Product defaults did not match the selected context. Reload the defaults.',
        };
      verifiedContext.current = context;
    },
    'product defaults',
  );
  return {
    ...read,
    data: verifiedContext.current === context ? read.data : null,
  };
}
/** Apply native suggestions only to a new form; never overwrite an existing record or a dirty draft. */
export function nativeProductInitial(
  fields: readonly MasterField[],
  initial: Record<string, unknown>,
) {
  const next = { ...initial };
  for (const field of fields) {
    const hint = field.control;
    if (!hint || !field.visible || !field.writable || field.conditional_access)
      continue;
    if (field.suggested_value != null) {
      const value = field.suggested_value;
      if (hint.kind === 'boolean' && ['true', 'false'].includes(value))
        next[field.key] = value === 'true';
      else if (
        hint.kind === 'integer' &&
        /^\d+$/.test(value) &&
        Number.isSafeInteger(Number(value))
      )
        next[field.key] = Number(value);
      else if (
        ['text', 'decimal', 'date'].includes(hint.kind) ||
        (hint.kind === 'reference' && catalogId.test(value))
      )
        next[field.key] = value;
    }
    if (hint.kind === 'select' && Array.isArray(next[field.key])) {
      const selected = (next[field.key] as unknown[]).filter((value) =>
        (hint.choices ?? []).some((choice) => choice.value === value),
      );
      next[field.key] = selected.length
        ? selected
        : (hint.choices ?? []).slice(0, 1).map((choice) => choice.value);
    }
  }
  return next;
}
export function productEntryFields(
  fields: readonly MasterField[],
  configuration?: ProductEntryConfiguration | null,
) {
  return fields.map((field) => {
    if (!field.control || !['brand_id', 'series_id'].includes(field.key))
      return field;
    const policy = entryOption(configuration, 'brand');
    return {
      ...field,
      required: field.required || (field.key === 'brand_id' && policy.required),
      control: {
        ...field.control,
        nullable:
          field.key === 'brand_id' && policy.required
            ? false
            : field.control.nullable,
        disabled_reason: policy.reason ?? field.control.disabled_reason,
      },
    };
  });
}

/** Dependent controls retain native field grants; options never grant write access. */
export function productUnitEntryFields(
  fields: readonly MasterField[],
  configuration: ProductEntryConfiguration | null,
) {
  const alternate = entryOption(configuration, 'alternate_units'),
    measured = entryOption(configuration, 'measured_units');
  return fields.map((field) => {
    if (!field.control) return field;
    const control = field.control,
      choices = control.choices ?? [];
    return {
      ...field,
      control: {
        ...control,
        choices:
          field.key === 'usage_role'
            ? choices.filter(
                (choice) =>
                  (alternate.allowed || choice.value === 'BASE') &&
                  (measured.allowed || choice.value !== 'MEASURED'),
              )
            : field.key === 'conversion_mode'
              ? choices.filter(
                  (choice) => measured.allowed || choice.value !== 'MEASURED',
                )
              : choices,
        disabled_reason:
          field.key === 'unit_id' && !alternate.allowed
            ? 'Alternate units are disabled; the existing base unit is used.'
            : control.disabled_reason,
      },
    };
  });
}
