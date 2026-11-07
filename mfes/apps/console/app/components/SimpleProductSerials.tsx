'use client';

import type { components } from '@janso/api-client/catalog';
import { Button, FieldGroup, Notice, TextField } from '@janso/ui';
import { trimSerialIdentifier, validateSerialIdentifiers } from '../lib/serial-identity';

type Options = components['schemas']['SimpleCreationOptions'];
type Input = components['schemas']['SimpleSerialInput'];
export type SerialRow = { key: string; values: Record<string, string> };
export const serialRow = (): SerialRow => ({ key: crypto.randomUUID(), values: {} });

function columns(options: Options) {
  return (options.serial?.requirements ?? []).flatMap(rule => Array.from({ length: rule.max_count }, (_, index) => ({
    key: `${rule.identifier_type}.${index + 1}`, type: rule.identifier_type, slot: index + 1,
    label: (rule.identifier_type === 'SERIAL' ? 'Serial number' : 'IMEI') + (rule.max_count > 1 ? ` ${index + 1}` : ''),
    required: rule.min_count === rule.max_count,
  })));
}

export function serialInputs(rows: SerialRow[], options: Options, prefix = 'serials', seen = new Set<string>()): { serials: Input[]; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  if (rows.length > 200) errors[prefix] = 'Enter no more than 200 serial units.';
  const fields = columns(options);
  const serials = rows.map((row, index) => {
    const identifiers: Input['identifiers'] = [];
    for (const field of fields) {
      const value = trimSerialIdentifier(row.values[field.key] ?? '');
      const path = `${prefix}.${index}.${field.key}`;
      if (!value) { if (field.required) errors[path] = `${field.label} is required.`; continue; }
      identifiers.push({ identifier_type: field.type, slot: field.slot, value });
    }
    const validated = validateSerialIdentifiers(identifiers, options.serial?.requirements ?? [], { prefix: `${prefix}.${index}.identifiers`, seen });
    Object.assign(errors, validated.errors);
    if (Object.entries(row.values).some(([key, value]) => value && !fields.some(field => field.key === key))) errors[`${prefix}.${index}.identifiers`] = 'An entered identifier is no longer configured. Restore the settings or remove the row.';
    return { identifiers };
  });
  return { serials, errors };
}

export function SimpleProductSerials({ options, rows, onRows, locked, errors, prefix = 'serials', title = 'Serial opening units', maximum = 200 }: {
  options: Options; rows: SerialRow[]; onRows: (rows: SerialRow[]) => void; locked: boolean;
  errors: Record<string, string>; prefix?: string; title?: string; maximum?: number;
}) {
  const fields = columns(options);
  const requirements = options.serial?.requirements ?? [];
  const access = options.fields?.find(field => field.key === 'serial_identifiers');
  const writable = !!access?.visible && access.writable && !access.conditional_access;
  const prepared = serialInputs(rows, options, prefix).serials;
  return <FieldGroup title={title} hint="Required by Product Configuration. Each row is one physical unit; opening quantity follows the row count.">
    <p>Opening quantity: {rows.length}</p>
    {requirements.some(rule => rule.min_count !== rule.max_count) && <p>Identifiers per unit: {requirements.map(rule => `${rule.identifier_type === 'SERIAL' ? 'Serial number' : 'IMEI'}: ${rule.min_count === rule.max_count ? rule.min_count : `${rule.min_count}–${rule.max_count}`}`).join('; ')}.</p>}
    {!writable && <Notice tone="warning">Your field access does not allow serial entry.</Notice>}
    {access?.visible && rows.length > 0 && <div className="janso-product-batch-scroll" role="region" aria-label={title} tabIndex={0}>
      <table className="janso-product-batch-grid"><caption className="janso-visually-hidden">{title}</caption><thead><tr><th scope="col">Unit</th>{fields.map(field => <th scope="col" key={field.key}>{field.label}{field.required ? ' *' : ''}</th>)}<th scope="col">Action</th></tr></thead><tbody>
        {rows.map((row, index) => <tr key={row.key}><th scope="row">{index + 1}</th>{fields.map(field => {
          const nativeIndex = prepared[index].identifiers.findIndex(value => value.identifier_type === field.type && value.slot === field.slot);
          return <td key={field.key}><TextField hideLabel label={`${field.label}, unit ${index + 1}`} value={row.values[field.key] ?? ''} maxLength={240} required={field.required} disabled={locked || !writable}
            error={errors[`${prefix}.${index}.${field.key}`] ?? errors[`${prefix}.${index}.identifiers.${nativeIndex}.value`]}
            onChange={event => onRows(rows.map(entry => entry.key === row.key ? { ...entry, values: { ...entry.values, [field.key]: event.target.value } } : entry))} /></td>;
        })}<td><Button type="button" variant="ghost" disabled={locked} onClick={() => onRows(rows.filter(entry => entry.key !== row.key))}>Remove unit {index + 1}</Button></td></tr>)}
      </tbody></table>
    </div>}
    {Object.entries(errors).filter(([key]) => key.startsWith(prefix) && !fields.some(field => key.endsWith('.' + field.key)) && !/\.identifiers\.\d+\.value$/.test(key)).map(([key, message]) => <Notice key={key} tone="danger">{message}</Notice>)}
    {!rows.length && <p>No opening units. Add a row for each unit on hand, or save without opening stock.</p>}
    <Button type="button" variant="ghost" disabled={locked || !writable || rows.length >= maximum} onClick={() => onRows([...rows, serialRow()])}>Add serial unit</Button>
  </FieldGroup>;
}
