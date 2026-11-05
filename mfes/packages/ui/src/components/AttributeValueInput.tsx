'use client';
import { Select } from './Select';
import { TextField } from './TextField';
import { FieldGroup } from './FieldGroup';
import { SearchSelect, type SearchSelectLoader } from './SearchSelect';
import { useState } from 'react';
export type NativeAttributeValue = {
  definition_id: string;
  value_type: string;
  option_id?: string | null;
  unit_id?: string | null;
  value_text?: string | null;
  value_integer?: string | null;
  value_decimal?: string | null;
  value_boolean?: boolean | null;
  value_date?: string | null;
};
export type NativeAttributeField = {
  definition_id: string;
  label: string;
  value_type: string;
  measurement_dimension: string | null;
  is_axis: boolean;
  is_required: boolean;
  writable: boolean;
  allowed_options: { id: string; label: string; is_active: boolean }[];
  option_label?: string | null;
  unit_label?: string | null;
  unit_visible?: boolean;
  value?: NativeAttributeValue | null;
};
export function attributeValue(value: NativeAttributeValue): NativeAttributeValue {
  const fields = [
    'value_text',
    'value_integer',
    'value_decimal',
    'value_boolean',
    'value_date',
  ] as const;
  const present = fields.filter((key) => value[key] != null && value[key] !== '');
  const expected = 'value_' + value.value_type.toLowerCase();
  if (
    value.option_id
      ? present.length > 0 || !!value.unit_id
      : present.length !== 1 || present[0] !== expected
  )
    throw new Error('Choose an option or enter one value of the declared type.');
  if (value.value_integer != null) {
    if (!/^-?(0|[1-9][0-9]{0,18})$/.test(value.value_integer))
      throw new Error('Enter an exact whole number.');
    const integer = BigInt(value.value_integer);
    if (integer < -(2n ** 63n) || integer >= 2n ** 63n)
      throw new Error('Whole number exceeds the supported range.');
  }
  if (value.value_decimal != null && !/^-?\d{1,15}(?:\.\d{1,4})?$/.test(value.value_decimal))
    throw new Error('Enter a decimal with at most four decimal places.');
  return value;
}
export function AttributeValueInput({
  field,
  value,
  onChange,
  loadOptions,
  loadUnits,
  disabled = false,
}: {
  field: NativeAttributeField;
  value: NativeAttributeValue | null;
  onChange: (value: NativeAttributeValue | null) => void;
  loadOptions?: SearchSelectLoader;
  loadUnits?: SearchSelectLoader;
  disabled?: boolean;
}) {
  const restricted = field.is_axis || field.allowed_options.length > 0;
  const [mode, setMode] = useState(value?.option_id || restricted ? 'option' : 'scalar');
  const locked = disabled || !field.writable;
  const base = { definition_id: field.definition_id, value_type: field.value_type };
  const valueKeys = {
    TEXT: 'value_text',
    INTEGER: 'value_integer',
    DECIMAL: 'value_decimal',
    BOOLEAN: 'value_boolean',
    DATE: 'value_date',
  } as const;
  const key = valueKeys[field.value_type as keyof typeof valueKeys];
  const common = { label: field.label, disabled: locked };
  const optionLabel =
    field.allowed_options.find((o) => o.id === value?.option_id)?.label ??
    (field.value?.option_id === value?.option_id ? field.option_label : undefined);
  const unitLabel = field.value?.unit_id === value?.unit_id ? field.unit_label : undefined;
  return (
    <FieldGroup
      title={
        field.label +
        (field.is_axis
          ? ' (variant axis)'
          : field.is_required
            ? ' (required before activation)'
            : '')
      }
    >
      {!restricted && loadOptions && (
        <Select
          label={field.label + ' entry'}
          value={mode}
          options={[
            { value: 'scalar', label: 'Enter a value' },
            { value: 'option', label: 'Choose an option' },
          ]}
          disabled={locked}
          onChange={(v) => {
            setMode(v);
            onChange(null);
          }}
        />
      )}
      {mode === 'option' || restricted ? (
        <SearchSelect
          {...common}
          scopeKey={JSON.stringify([field.definition_id, restricted])}
          value={value?.option_id ?? null}
          selected={
            value?.option_id && optionLabel
              ? { id: value.option_id, label: optionLabel }
              : undefined
          }
          options={
            restricted
              ? field.allowed_options.map((o) => ({
                  id: o.id,
                  label: o.label,
                  disabled: !o.is_active,
                }))
              : undefined
          }
          loadOptions={restricted ? undefined : loadOptions}
          onChange={(id) => onChange(id ? { ...base, option_id: id } : null)}
        />
      ) : (
        <>
          {field.value_type === 'BOOLEAN' ? (
            <Select
              {...common}
              value={
                value?.value_boolean === true
                  ? 'true'
                  : value?.value_boolean === false
                    ? 'false'
                    : ''
              }
              placeholder="Not set"
              options={[
                { value: 'true', label: 'Yes' },
                { value: 'false', label: 'No' },
              ]}
              onChange={(v) => onChange(v ? { ...base, value_boolean: v === 'true' } : null)}
            />
          ) : (
            <TextField
              {...common}
              value={String(value?.[key] ?? '')}
              type={field.value_type === 'DATE' ? 'date' : 'text'}
              inputMode={['INTEGER', 'DECIMAL'].includes(field.value_type) ? 'decimal' : 'text'}
              maxLength={field.value_type === 'TEXT' ? 200 : undefined}
              onChange={(e) =>
                onChange(
                  e.target.value === ''
                    ? null
                    : { ...base, [key]: e.target.value, unit_id: value?.unit_id ?? null },
                )
              }
            />
          )}
          {field.measurement_dimension && field.unit_visible !== false && (
            <SearchSelect
              label={field.label + ' unit'}
              scopeKey={JSON.stringify([field.definition_id, field.measurement_dimension])}
              disabled={locked}
              value={value?.unit_id ?? null}
              selected={
                value?.unit_id && unitLabel ? { id: value.unit_id, label: unitLabel } : undefined
              }
              loadOptions={loadUnits}
              onChange={(id) => onChange({ ...base, ...value, unit_id: id })}
            />
          )}
        </>
      )}
    </FieldGroup>
  );
}
