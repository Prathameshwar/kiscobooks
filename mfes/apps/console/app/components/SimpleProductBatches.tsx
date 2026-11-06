'use client';

import type { components } from '@janso/api-client/catalog';
import { Button, FieldGroup, Notice, TextField, Toggle, useFormatters } from '@janso/ui';

import { SimpleProductSerials, serialInputs, type SerialRow } from './SimpleProductSerials';

type Options = components['schemas']['SimpleCreationOptions'];
type Input = components['schemas']['SimpleBatchInput'];
export type BatchRow = { key: string; values: Record<string, string>; serials?: SerialRow[] };
export const batchRow = (): BatchRow => ({ key: crypto.randomUUID(), values: { code: '', opening_quantity: '0' } });
type Column = { key: string; label: string; required: boolean; writable: boolean; date?: boolean };
const decimal = /^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;
const positive = (value: string) => /[1-9]/.test(value);

export function batchColumns(options: Options): Column[] {
  const field = (key: string) => options.fields?.find(value => value.key === key);
  const enabled = (key: string) => !!field(key)?.visible;
  const write = (key: string) => enabled(key) && !!field(key)?.writable && !field(key)?.conditional_access;
  const columns: Column[] = [{ key: 'code', label: 'Batch', required: true, writable: write('batch_code') }];
  if (options.batch?.manufacture_date_required) columns.push({ key: 'manufactured_on', label: 'Manufacture date', date: true, required: true, writable: write('batch_manufactured_on') });
  if (options.batch?.expiry_enabled) columns.push({ key: 'expires_on', label: 'Expiry date', date: true, required: !!options.batch.expiry_required, writable: write('batch_expires_on') });
  if (enabled('opening_quantity')) columns.push({ key: 'opening_quantity', label: 'Opening quantity', required: false, writable: write('opening_quantity') });
  if (enabled('purchase_price')) columns.push({ key: 'purchase_price', label: 'Purchase price', required: options.configuration.pricing.purchase_reference_mode === 'REQUIRED', writable: write('purchase_price') });
  if (enabled('sale_price')) columns.push({ key: 'sale_price', label: 'Selling price', required: options.configuration.pricing.sale_price_mode === 'REQUIRED', writable: write('sale_price') });
  for (const level of options.sale_price_levels ?? []) if (enabled('sale_prices.' + level.price_level_id)) columns.push({ key: 'sale_prices.' + level.price_level_id, label: level.name + (level.tax_basis === 'INCLUSIVE' ? ' (incl. tax)' : ' (excl. tax)'), required: level.required, writable: write('sale_prices.' + level.price_level_id) });
  if (enabled('mrp')) columns.push({ key: 'mrp', label: 'MRP', required: options.configuration.pricing.mrp_mode === 'REQUIRED', writable: write('mrp') && write('batch_mrp_amount') });
  return columns;
}

export function batchInputs(rows: BatchRow[], options: Options): { batches: Input[]; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const columns = batchColumns(options);
  const seen = new Set<string>();
  const serialSeen = new Set<string>();
  const batches = rows.map((row, index) => {
    if (options.serial?.enabled) row = { ...row, values: { ...row.values, opening_quantity: String(row.serials?.length ?? 0) } };
    const data: Input = { code: row.values.code?.trim() ?? '', opening_quantity: '0' };
    for (const column of columns) {
      const value = row.values[column.key]?.trim() ?? '';
      const key = `batches.${index}.${column.key}`;
      const required = column.required || (column.key === 'purchase_price' && positive(row.values.opening_quantity ?? '0'));
      if (required && !value) errors[key] = `${column.label} is required.`;
      if (value && !column.writable) errors[key] = 'This field is unavailable. Review settings and field access.';
      if (!value) continue;
      if (!column.date && column.key !== 'code' && (!decimal.test(value) || (['mrp', 'purchase_price'].includes(column.key) && !positive(value)))) errors[key] = column.key === 'purchase_price' ? 'Enter a positive Purchase price with up to four decimal places.' : 'Enter a valid amount or quantity with up to four decimal places.';
      if (column.key.startsWith('sale_prices.')) (data.sale_prices ??= []).push({ price_level_id: column.key.slice(12), amount: value });
      else Object.assign(data, { [column.key]: value });
    }
    for (const [key, value] of Object.entries(row.values)) if (value && !(key === 'opening_quantity' && !positive(value)) && !columns.some(column => column.key === key)) errors[`batches.${index}.${key}`] = 'This value is no longer available under current settings. Restore the settings or remove this row.';
    if (positive(row.values.opening_quantity ?? '0') && !row.values.purchase_price) errors[`batches.${index}.purchase_price`] = 'Purchase price is required for opening stock.';
    const normalized = data.code.normalize('NFKC').toLocaleLowerCase('en-US');
    if (seen.has(normalized)) errors[`batches.${index}.code`] = 'Batch numbers must be distinct.';
    seen.add(normalized);
    if (data.manufactured_on && data.expires_on && data.expires_on < data.manufactured_on) errors[`batches.${index}.expires_on`] = 'Expiry must not precede manufacture.';
    if (options.serial?.enabled) {
      const prepared = serialInputs(row.serials ?? [], options, `batches.${index}.serials`, serialSeen);
      data.serials = prepared.serials; Object.assign(errors, prepared.errors);
    } else if (row.serials?.length) errors[`batches.${index}.serials`] = 'Serial entry is no longer enabled. Restore settings or remove this batch.';
    return data;
  });
  return { batches, errors };
}

export function SimpleProductBatches({ options, enabled, onToggle, rows, onRows, locked, errors }: {
  options: Options; enabled: boolean; onToggle: (value: boolean) => void; rows: BatchRow[]; onRows: (rows: BatchRow[]) => void; locked: boolean; errors: Record<string, string>;
}) {
  const format = useFormatters();
  const columns = batchColumns(options);
  const displayErrors = { ...errors };
  rows.forEach((row, index) => {
    const entered = (options.sale_price_levels ?? []).filter(level => row.values['sale_prices.' + level.price_level_id]?.trim());
    entered.forEach((level, priceIndex) => {
      const native = `batches.${index}.sale_prices.${priceIndex}.amount`;
      if (errors[native]) { displayErrors[`batches.${index}.sale_prices.${level.price_level_id}`] = errors[native]; delete displayErrors[native]; }
    });
  });
  const choice = options.fields?.find(field => field.key === 'batch_enabled');
  const blocked = !choice?.visible || !choice.writable || choice.conditional_access;
  return <FieldGroup title="Batches" hint="Each batch keeps its own opening quantity and prices."
    headerEnd={<label className="janso-check"><Toggle label="Allow batch" checked={enabled} disabled={locked || blocked || !!options.batch?.required} onChange={onToggle} /><span>Allow batch</span></label>}>
    {options.batch?.required && <p>Batch tracking is required by Product Configuration.</p>}
    {blocked && <Notice tone="warning">Your field access does not allow a batch choice.</Notice>}
    {errors.batch_enabled && <Notice tone="danger">{errors.batch_enabled}</Notice>}
    {enabled && <div className="janso-flow">
      <p>Opening date: {format.date(options.opening_date)}. Prices are per base unit in {options.currency}. Opening value is Purchase price × Opening quantity.</p>
      {rows.length > 0 && <div className="janso-product-batch-scroll" role="region" aria-label="Batch opening quantities and prices" tabIndex={0}><table className="janso-product-batch-grid"><caption className="janso-visually-hidden">Batch opening quantities and prices</caption><thead><tr><th scope="col">Row</th>{columns.map(column => <th key={column.key} scope="col">{column.label}{column.required ? ' *' : ''}</th>)}<th scope="col">Action</th></tr></thead><tbody>
        {rows.map((row, index) => <tr key={row.key}><th scope="row">{index + 1}</th>{columns.map(column => <td key={column.key}><TextField hideLabel label={`${column.label} ${index + 1}`} type={column.date ? 'date' : 'text'} inputMode={column.date || column.key === 'code' ? undefined : 'decimal'} required={column.required} disabled={locked || !column.writable} readOnly={!!options.serial?.enabled && column.key === 'opening_quantity'} value={options.serial?.enabled && column.key === 'opening_quantity' ? String(row.serials?.length ?? 0) : row.values[column.key] ?? ''} error={displayErrors[`batches.${index}.${column.key}`]} onChange={value => onRows(rows.map(entry => entry.key === row.key ? { ...entry, values: { ...entry.values, [column.key]: value.target.value } } : entry))} /></td>)}<td><Button type="button" variant="ghost" disabled={locked} onClick={() => onRows(rows.filter(entry => entry.key !== row.key))}>Remove batch {index + 1}</Button></td></tr>)}
      </tbody></table></div>}
      {options.serial?.enabled && rows.map((row, index) => <SimpleProductSerials key={row.key} options={options} rows={row.serials ?? []} prefix={`batches.${index}.serials`} title={`Serials for batch ${row.values.code || index + 1}`} locked={locked} errors={errors} maximum={200 - rows.reduce((count, other) => count + (other.key === row.key ? 0 : other.serials?.length ?? 0), 0)} onRows={serials => onRows(rows.map(entry => entry.key === row.key ? { ...entry, serials, values: { ...entry.values, opening_quantity: String(serials.length) } } : entry))} />)}
      {!rows.length && <p>No batches entered. Add a row to enter stock or prices, or save with no opening stock.</p>}
      {Object.entries(displayErrors).filter(([key]) => key.startsWith('batches') && !rows.some((_, index) =>
        columns.some(column => key === `batches.${index}.${column.key}`) || (options.serial?.enabled && (key === `batches.${index}.serials` || key.startsWith(`batches.${index}.serials.`)))
      )).map(([key, message]) => <Notice key={key} tone="danger">{message}</Notice>)}
      <Button type="button" variant="ghost" disabled={locked || rows.length >= 64} onClick={() => onRows([...rows, batchRow()])}>Add batch</Button>
    </div>}
  </FieldGroup>;
}
