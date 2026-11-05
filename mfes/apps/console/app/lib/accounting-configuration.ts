'use client';
import { useEffect, useState } from 'react';
import {
  serviceCall,
  requestFailure,
  type RequestFailure,
  type ServiceRequest,
} from './service-call';
import {
  useServiceList,
  useServiceRead,
  useServiceCommand,
} from './service-resource';
import {
  accountingUUID,
  type AccountingField,
  type AccountingForm,
  type AccountingRecord,
  type AccountingResourceConfig,
} from './accounting-configuration-resources';
import { validMasterDate } from './catalog-masters';

export const accountingRequest = <T>(request: ServiceRequest) =>
  serviceCall<T>(
    '/api/product-fields',
    { service: 'accounting', ...request },
    'Accounting configuration',
  );
export const accountingBase = (
  company: string,
  config: AccountingResourceConfig,
) => `/v1/companies/${company}/${config.resource}`;
export function assertAccountingRecord<T extends AccountingRecord>(
  value: T,
  company: string,
  id?: string,
): T {
  if (
    !value ||
    value.company_id !== company ||
    !accountingUUID.test(value.id) ||
    (id && value.id !== id) ||
    !Number.isSafeInteger(value.row_version) ||
    value.row_version < 1
  )
    throw {
      status: 502,
      message: 'The Accounting record could not be verified for this company.',
    };
  return value;
}
export function assertAccountingForm(
  value: AccountingForm,
  company: string,
  config: AccountingResourceConfig,
  operation: string,
) {
  if (
    !value ||
    value.company_id !== company ||
    value.resource !== config.resource ||
    value.operation !== operation ||
    !Array.isArray(value.fields) ||
    value.fields.length > 64 ||
    new Set(value.fields.map((field) => field.key)).size !==
      value.fields.length ||
    value.fields.some((field) => !field.control)
  )
    throw {
      status: 502,
      message:
        'Accounting field settings could not be verified. Reload before editing.',
    };
  return value;
}
export function useAccountingRecord(
  company: string,
  config: AccountingResourceConfig,
  id: string | undefined,
  editing: boolean,
) {
  const [metadata, setMetadata] = useState<AccountingForm | null>(null),
    [record, setRecord] = useState<AccountingRecord | null>(null),
    [loading, setLoading] = useState(true),
    [failure, setFailure] = useState<RequestFailure | null>(null),
    [settled, setSettled] = useState(''),
    [revision, setRevision] = useState(0);
  const operation = editing ? (id ? 'update' : 'create') : 'read';
  const requestKey = [
    company,
    config.resource,
    id ?? '',
    operation,
    revision,
  ].join(':');
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setFailure(null);
    setMetadata(null);
    setRecord(null);
    const query = new URLSearchParams({ operation });
    if (id) query.set('object_id', id);
    Promise.all([
      accountingRequest<AccountingForm>({
        path: `/v1/companies/${company}/configuration/${config.resource}/field-set?${query}`,
        signal: controller.signal,
      }),
      id
        ? accountingRequest<AccountingRecord>({
            path: accountingBase(company, config) + '/' + id,
            signal: controller.signal,
          })
        : Promise.resolve(null),
    ])
      .then(([fields, row]) => {
        if (!controller.signal.aborted) {
          setMetadata(assertAccountingForm(fields, company, config, operation));
          setRecord(row ? assertAccountingRecord(row, company, id) : null);
          setLoading(false);
          setSettled(requestKey);
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setFailure(requestFailure(error, 'Accounting configuration'));
          setLoading(false);
          setSettled(requestKey);
        }
      });
    return () => controller.abort();
  }, [company, config, id, operation, revision]);
  return {
    metadata: settled === requestKey ? metadata : null,
    record: settled === requestKey ? record : null,
    setRecord,
    loading: settled !== requestKey || loading,
    failure: settled === requestKey ? failure : null,
    refresh: () => setRevision((value) => value + 1),
  };
}
export const useAccountingCommand = () =>
  useServiceCommand(accountingRequest, 'Accounting configuration');
export function useAccountingList(
  company: string,
  config: AccountingResourceConfig,
  filters = '',
  enabled = true,
) {
  return useServiceList<AccountingRecord>(
    accountingBase(company, config),
    filters,
    accountingRequest,
    (row) => assertAccountingRecord(row, company),
    enabled,
  );
}
export const useAccountingRead = <T>(
  path: string | undefined,
  verify?: (value: T) => void,
) =>
  useServiceRead<T>(
    path,
    accountingRequest,
    verify,
    'Accounting configuration',
  );
export function accountingInitial(
  fields: AccountingField[],
  record?: AccountingRecord | null,
  prefills: Record<string, string> = {},
) {
  const values = Object.fromEntries(
    fields.map((field) => [
      field.key,
      field.control.write_only
        ? ''
        : record
          ? record[field.key]
          : field.editable && prefills[field.key] !== undefined
            ? prefills[field.key]
            : (field.initial ?? (field.control.nullable ? null : '')),
    ]),
  );
  if (!record) {
    for (const field of fields) {
      if (
        field.editable &&
        field.control.nullable &&
        !accountingFieldActive(field, values)
      )
        values[field.key] = null;
    }
  }
  return values;
}
export function accountingFieldActive(
  field: AccountingField,
  values: Record<string, unknown>,
) {
  return Object.entries(field.control.depends_on ?? {}).every(
    ([key, choices]) => choices.includes(String(values[key])),
  );
}
export function accountingChoices(
  field: AccountingField,
  values: Record<string, unknown>,
) {
  return (field.control.choices ?? []).filter((choice) =>
    Object.entries(field.control.choice_dependencies?.[choice] ?? {}).every(
      ([key, choices]) => choices.includes(String(values[key])),
    ),
  );
}
export function accountingChange(
  fields: AccountingField[],
  values: Record<string, unknown>,
  key: string,
  value: unknown,
) {
  const next = { ...values, [key]: value };
  const writable = (field: AccountingField) =>
    field.editable &&
    field.visible &&
    (field.readable || field.control.write_only) &&
    !field.conditional_access &&
    !field.control.disabled_reason;
  for (const field of fields) {
    if (!writable(field)) continue;
    if (field.control.depends_on?.[key]) {
      const wasActive = accountingFieldActive(field, values),
        active = accountingFieldActive(field, next);
      if (!active && field.control.nullable) next[field.key] = null;
      else if (
        active &&
        !wasActive &&
        (next[field.key] == null || next[field.key] === '') &&
        field.initial != null
      )
        next[field.key] = field.initial;
    }
    if (
      field.control.choice_dependencies &&
      !accountingChoices(field, next).includes(String(next[field.key])) &&
      Object.values(field.control.choice_dependencies).some(
        (condition) => key in condition,
      )
    ) {
      next[field.key] = accountingChoices(field, next)[0] ?? next[field.key];
    }
    if (
      (key === 'country_code' && field.key === 'state_code') ||
      (key === 'scheme' && field.key === 'company_registration_id') ||
      (key === 'party_id' &&
        [
          'address_id',
          'contact_id',
          'registration_id',
          'pan_identifier_id',
        ].includes(field.key)) ||
      (key === 'kind' && field.control.reference === 'withholding-sections')
    )
      next[field.key] = null;
  }
  return next;
}
function decimalUnits(value: unknown): bigint | null {
  if (typeof value !== 'string' || !/^-?\d{1,15}(?:\.\d{1,4})?$/.test(value))
    return null;
  const negative = value.startsWith('-'),
    [whole, fraction = ''] = value.replace(/^-/, '').split('.');
  const units = BigInt(whole) * 10000n + BigInt(fraction.padEnd(4, '0'));
  return negative ? -units : units;
}
export function accountingConstraints(field: AccountingField) {
  const value = field.definition as Record<string, unknown>,
    parts = value.anyOf as Record<string, unknown>[] | undefined;
  return { ...value, ...(parts?.find((part) => part.type !== 'null') ?? {}) };
}
export function accountingBody(
  fields: AccountingField[],
  values: Record<string, unknown>,
  record?: AccountingRecord | null,
) {
  const body: Record<string, unknown> = record
      ? { expected_version: record.row_version }
      : {},
    errors: Record<string, string> = {};
  for (const field of fields) {
    if (
      !field.editable ||
      !field.visible ||
      (!field.readable && !field.control.write_only) ||
      field.conditional_access ||
      field.control.disabled_reason
    )
      continue;
    let value = values[field.key],
      constraints = accountingConstraints(field);
    if (typeof value === 'string') value = value.trim();
    if (field.control.write_only && record && value === '') continue;
    if (value === '' && field.control.nullable) value = null;
    if (
      (field.control.kind === 'integer' ||
        (field.control.kind === 'select' && constraints.type === 'integer')) &&
      typeof value === 'string' &&
      /^\d+$/.test(value)
    )
      value = Number(value);
    if (
      record &&
      !field.control.write_only &&
      JSON.stringify(value) === JSON.stringify(record[field.key])
    )
      continue;
    let error = '';
    if (value == null || value === '') {
      if (
        ((field.required || field.control.required_when_active) &&
          accountingFieldActive(field, values)) ||
        (!field.control.nullable && record)
      )
        error = 'Enter ' + field.label.toLowerCase() + '.';
      else if (!field.control.nullable) continue;
    } else if (field.control.kind === 'boolean' && typeof value !== 'boolean')
      error = 'Choose yes or no.';
    else if (
      field.control.kind === 'select' &&
      !accountingChoices(field, values).includes(String(value))
    )
      error = 'Choose an available option.';
    else if (
      field.control.kind === 'integer' &&
      (!Number.isSafeInteger(value) ||
        Number(value) < Number(constraints.minimum ?? 0) ||
        Number(value) > Number(constraints.maximum ?? 1000000))
    )
      error = 'Enter a whole number within the allowed range.';
    else if (
      field.control.kind === 'decimal' &&
      (typeof value !== 'string' || !/^-?\d{1,15}(?:\.\d{1,4})?$/.test(value))
    )
      error = 'Enter an exact decimal with up to four decimal places.';
    else if (field.control.kind === 'date' && !validMasterDate(value))
      error = 'Enter a valid date.';
    else if (
      field.control.kind === 'datetime' &&
      (typeof value !== 'string' ||
        !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value) ||
        !Number.isFinite(Date.parse(value)))
    )
      error = 'Enter a valid UTC date and time.';
    else if (
      field.control.kind === 'reference' &&
      (typeof value !== 'string' ||
        !(['countries', 'states', 'currencies'].includes(
          field.control.reference ?? '',
        )
          ? /^[A-Z0-9-]{2,8}$/.test(value)
          : accountingUUID.test(value)))
    )
      error = 'Choose an available reference.';
    else if (
      typeof value === 'string' &&
      (value.length < Number(constraints.minLength ?? 0) ||
        value.length > Number(constraints.maxLength ?? 4000) ||
        (field.control.kind === 'text' &&
        ['notes', 'description'].includes(field.key)
          ? /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/
          : /[\x00-\x1f\x7f]/
        ).test(value))
    )
      error = 'Enter printable text within the allowed length.';
    if (!error && field.control.kind === 'decimal' && value != null) {
      const units = decimalUnits(value);
      for (const [key, bound] of Object.entries(
        field.control.decimal_bounds ?? {},
      )) {
        const limit = decimalUnits(bound);
        if (
          units === null ||
          limit === null ||
          ![
            'minimum',
            'maximum',
            'exclusiveMinimum',
            'exclusiveMaximum',
          ].includes(key)
        ) {
          error = 'The allowed decimal range is unavailable. Reload the form.';
          break;
        }
        if (
          (key === 'minimum' && units < limit) ||
          (key === 'maximum' && units > limit) ||
          (key === 'exclusiveMinimum' && units <= limit) ||
          (key === 'exclusiveMaximum' && units >= limit)
        ) {
          error = 'Enter an exact decimal within the allowed range.';
          break;
        }
      }
    }
    if (
      !error &&
      constraints.pattern &&
      value !== null &&
      typeof value === 'string'
    ) {
      try {
        if (!new RegExp(String(constraints.pattern)).test(value))
          error = 'Use the required format.';
      } catch {
        error = 'The field format is unavailable. Reload the form.';
      }
    }
    if (
      !error &&
      !accountingFieldActive(field, values) &&
      value != null &&
      value !== ''
    )
      error = 'Clear this value or enable its controlling option.';
    if (error) errors[field.key] = error;
    else body[field.key] = value;
  }
  if (
    values.valid_from &&
    values.valid_to &&
    String(values.valid_to) < String(values.valid_from)
  )
    errors.valid_to = 'End date must be on or after the start date.';
  if (
    values.rounding_method === 'NONE' &&
    values.rounding_limit != null &&
    values.rounding_limit !== ''
  )
    errors.rounding_limit = 'Clear the limit when rounding is disabled.';
  if (
    values.rounding_method &&
    values.rounding_method !== 'NONE' &&
    (typeof values.rounding_limit !== 'string' ||
      !/^\d{1,15}(?:\.\d{1,4})?$/.test(values.rounding_limit) ||
      !/[1-9]/.test(values.rounding_limit))
  )
    errors.rounding_limit = 'Enabled rounding requires a positive exact limit.';
  if (
    values.currency_mode === 'MULTI' &&
    values.rounding_method &&
    values.rounding_method !== 'NONE'
  )
    errors.rounding_method = 'Disable rounding for a multi-currency account.';
  if (values.kind === 'PARTY' && (!values.party_id || !values.party_role))
    errors.party_id = 'Choose the party and its active role.';
  if (
    values.kind &&
    values.kind !== 'PARTY' &&
    (values.party_id || values.party_role)
  )
    errors.kind = 'Party and role apply only to party accounts.';
  if ('tax_treatment' in values && 'offset_account_id' in values) {
    for (const key of ['rate', 'minimum', 'cap'])
      if (
        (typeof values[key] === 'string' && /^-/.test(values[key] as string)) ||
        (key === 'rate' &&
          typeof values[key] === 'string' &&
          !/[1-9]/.test(values[key] as string))
      )
        errors[key] =
          key === 'rate'
            ? 'Enter a positive exact rate.'
            : 'Enter a nonnegative exact amount.';
    const exact = (value: unknown) =>
      typeof value === 'string' && /^\d{1,15}(?:\.\d{1,4})?$/.test(value)
        ? BigInt(value.split('.')[0]) * 10000n +
          BigInt((value.split('.')[1] ?? '').padEnd(4, '0'))
        : null;
    const minimum = exact(values.minimum),
      cap = exact(values.cap);
    if (minimum !== null && cap !== null && cap < minimum)
      errors.cap = 'Cap must be at least the minimum charge.';
    if (values.method === 'FIXED' && values.compound !== 'SIMPLE')
      errors.compound = 'Fixed charges require simple calculation.';
  }
  return { body, errors };
}
