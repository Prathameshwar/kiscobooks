'use client';

import { useId } from 'react';
import { FieldLabel } from './FieldLabel';
import { SearchSelect, type SearchSelectLoader } from './SearchSelect';
import { Select } from './Select';
import { TextField } from './TextField';
import { customCondition, type CustomField } from '../lib/custom-fields';

export type CustomFieldsProps = {
  fields: readonly CustomField[]; values: Record<string, unknown>;
  nativeValues?: Record<string, unknown>; creating?: boolean; disabled?: boolean;
  errors?: Record<string, string>; currencies?: readonly string[];
  onChange: (values: Record<string, unknown>) => void;
  loadOptions?: (source: string, parent: string | null) => SearchSelectLoader;
};

export function CustomFields({ fields, values, nativeValues = {}, creating = false, disabled = false,
  errors = {}, currencies = [], onChange, loadOptions }: CustomFieldsProps) {
  const prefix = useId();
  if (creating) values = { ...Object.fromEntries(fields.filter(f => f.custom?.is_active).map(f => [f.key, f.custom?.default_value])), ...values };
  const numeric = new Set(fields.filter(field => ['decimal', 'integer'].includes(field.custom?.data_type ?? '')).map(field => field.key));
  // Native decimal values are transported as text by the owner API.
  for (const key of Object.keys(nativeValues)) if (typeof nativeValues[key] === 'number' || key === 'min_sale_quantity') numeric.add(key);
  function change(key: string, value: unknown) {
    const next = { ...values, [key]: value };
    const changed = new Set([key]);
    for (let i = 0; i < fields.length; i++) for (const field of fields) {
      if (field.custom?.depends_on_key && changed.has(field.custom.depends_on_key) && !changed.has(field.key)) {
        next[field.key] = null; changed.add(field.key);
      }
    }
    onChange(next);
  }
  return <div className="janso-custom-fields">{fields.map(field => {
    const definition = field.custom;
    if (!definition) return null;
    const value = field.key in values ? values[field.key] : creating ? definition.default_value : null;
    const historical = !definition.is_active && value != null;
    if (!historical && (!field.visible || !customCondition(definition.visibility, { ...nativeValues, ...values }, numeric))) return null;
    const locked = disabled || !field.writable || historical || (!creating && definition.is_immutable_after_create) || definition.data_type === 'auto_number';
    const common = { label: field.label, disabled: locked, required: field.required && !locked,
      hint: historical ? 'Retired field. Its saved value is retained.' : field.help_text ?? undefined,
      error: errors[`custom_fields.${field.key}`] ?? errors[field.key] };
    const choices = definition.choices.map(choice => ({ id: choice.value, label: choice.label, disabled: !choice.is_active }));
    if (definition.data_type === 'multi_select') return <SearchSelect key={field.key} {...common} multiple options={choices}
      value={Array.isArray(value) ? value as string[] : []} selected={choices.filter(c => Array.isArray(value) && value.includes(c.id))}
      onChange={selected => change(field.key, [...selected].sort())} />;
    if (definition.data_type === 'dynamic_select') {
      const parent = definition.depends_on_key ? String(values[definition.depends_on_key] ?? nativeValues[definition.depends_on_key] ?? '') : null;
      return <SearchSelect key={`${field.key}:${parent}`} {...common} disabled={locked || !loadOptions || (!!definition.depends_on_key && !parent)}
        value={value == null ? null : String(value)} scopeKey={JSON.stringify([definition.option_source_key, parent])}
        loadOptions={loadOptions && definition.option_source_key ? loadOptions(definition.option_source_key, parent) : undefined}
        onChange={selected => change(field.key, selected)} />;
    }
    if (definition.data_type === 'select') return <Select key={field.key} {...common} value={value == null ? '' : String(value)}
      options={choices.map(c => ({ value: c.id, label: c.label, disabled: c.disabled }))} placeholder="Choose an option"
      onChange={selected => change(field.key, selected || null)} />;
    if (definition.data_type === 'boolean') return <Select key={field.key} {...common}
      value={value === true ? 'true' : value === false ? 'false' : ''} placeholder="Not set"
      options={[{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }]}
      onChange={selected => change(field.key, selected === '' ? null : selected === 'true')} />;
    if (definition.data_type === 'currency_amount') {
      const amount = value && typeof value === 'object' ? value as { amount: string; currency: string } : { amount: '', currency: currencies[0] ?? '' };
      return <fieldset key={field.key} className="janso-custom-fields__amount"><legend>{field.label}</legend>
        <TextField {...common} label={`${field.label} amount`} inputMode="decimal" value={amount.amount}
          onChange={event => change(field.key, event.target.value === '' ? null : { ...amount, amount: event.target.value })} />
        <Select label={`${field.label} currency`} disabled={locked} value={amount.currency} options={currencies.map(currency => ({ value: currency, label: currency }))}
          onChange={currency => change(field.key, { ...amount, currency })} />
      </fieldset>;
    }
    if (definition.data_type === 'long_text') return <div className="janso-field" key={field.key}>
      <FieldLabel htmlFor={`${prefix}-${field.key}`} required={field.required}>{field.label}</FieldLabel>
      <textarea id={`${prefix}-${field.key}`} className="janso-input" disabled={locked} required={common.required}
        maxLength={definition.validation.max_length} value={String(value ?? '')} onChange={event => change(field.key, event.target.value)}
        aria-describedby={common.error ? `${prefix}-${field.key}-error` : undefined} />
      {common.error && <p role="alert" id={`${prefix}-${field.key}-error`}>{common.error}</p>}
    </div>;
    return <TextField key={field.key} {...common} placeholder={field.placeholder ?? undefined} value={String(value ?? '')}
      type={definition.data_type === 'date' ? 'date' : 'text'} inputMode={['integer', 'decimal'].includes(definition.data_type) ? 'decimal' : 'text'}
      maxLength={definition.validation.max_length} onChange={event => change(field.key, event.target.value)} />;
  })}</div>;
}
