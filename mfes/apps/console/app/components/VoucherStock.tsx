'use client';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, CardBody, Notice, SearchSelect, SectionHeader, Select, TextField, useFormatters, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import type { components } from '@janso/api-client/vouchers';
import type { components as Accounting } from '@janso/api-client/accounting';
import { productFieldRequest as request } from '../lib/product-fields';
import type { FieldSet, Native } from '../lib/voucher-fields';
import { inwardStock, linkedStock, transferStock, type StockDimension, type StockDraft } from '../lib/voucher-stock';
import { trackingId, trackingTitle } from '../lib/stock-tracking-resources';
import {VoucherStockQuantity} from './VoucherStockQuantity';
import {VoucherStockCount} from './VoucherStockCount';

type Line = components['schemas']['LineInput'];
type Reference = { id: string; company_id?: string; code?: string; name?: string; stock_date?: string; quantity?: string; is_active?: boolean; status?: string; kind?: string };
type Page<T> = { items: T[]; page: { has_more: boolean; next_cursor: string | null } };
const properties = (value?: Native) => value?.properties ?? value?.anyOf?.find(branch => branch.properties)?.properties ?? {};

/** Native field-set controls govern both the visible controls and their write access. */
export function VoucherStock({ company, currency, metadata, lines, value, onChange, onQuantity, disabled, canReviewCount=false }: {
  company: string; currency: string; metadata: FieldSet; lines: Line[]; value: StockDraft;
  onChange: (value: StockDraft) => void; disabled: boolean;
  onQuantity?: (lineKey:string,quantity:string)=>void;
  canReviewCount?:boolean;
}) {
  const native = properties(metadata.native.properties?.stock);
  const writable = (key: string) => !!native[key] && !native[key].readOnly;
  return <Card><CardBody><div className="janso-flow">
    <SectionHeader title="Physical stock" description="Quantities use the product's base unit. Saving prepares a draft; approved posting changes stock and carrying value." />
    <div className="janso-form-grid">
      {native.stock_date && <TextField label="Stock movement date" type="date" value={value.date} required disabled={disabled || !writable('stock_date')} onChange={event => onChange({ ...value, date: event.target.value, dimensions: {} })} />}
      {value.action === 'OPENING' && native.opening_mode && <Select label="Opening accounting" value={value.openingMode} disabled={disabled || !writable('opening_mode')} options={(metadata.configuration.policy.stock?.opening_gl_mode === 'EITHER' ? ['COMBINED', 'LINKED_GL'] : [metadata.configuration.policy.stock?.opening_gl_mode ?? 'COMBINED']).map(mode => ({ value: mode, label: mode === 'COMBINED' ? 'Post stock and opening value together' : 'Link a previously recorded opening balance' }))} onChange={mode => onChange({ ...value, openingMode: mode as StockDraft['openingMode'], dimensions: {} })} />}
      {native.reason && <TextField label="Stock movement reason" value={value.reason} required minLength={3} maxLength={500} disabled={disabled || !writable('reason')} onChange={event => onChange({ ...value, reason: event.target.value })} />}
    </div>
    {!writable('stock_date') || !writable('lines') ? <Notice tone="warning">Stock date and stock line write access are required to prepare this movement.</Notice> : lines.map((line, index) => <StockLine key={line.line_key + ':' + line.item.item_id + ':' + value.date} company={company} currency={currency} index={index} line={line} draft={value} native={properties(native.lines?.items)} disabled={disabled} onQuantity={onQuantity} canReviewCount={canReviewCount} onChange={dimension => onChange({ ...value, dimensions: { ...value.dimensions, [line.line_key]: dimension } })} />)}
  </div></CardBody></Card>;
}

function StockLine({ company, currency, index, line, draft, native, disabled, onChange, onQuantity, canReviewCount }: {
  company: string; currency: string; index: number; line: Line; draft: StockDraft;
  native: Record<string, Native>; disabled: boolean; onChange: (value: StockDimension) => void;
  onQuantity?: (lineKey:string,quantity:string)=>void;
  canReviewCount:boolean;
}) {
  const dimension = draft.dimensions[line.line_key]?.item_id === line.item.item_id ? draft.dimensions[line.line_key]! : { item_id: line.item.item_id, warehouse_id: '' };
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState('');
  const [selection, setSelection] = useState<Accounting['schemas']['StockSelection'] | null>(null);
  const format = useFormatters();
  const base = '/v1/companies/' + company;
  const write = (key: string) => !!native[key] && !native[key].readOnly;
  const update = (next: Partial<StockDimension>) => {
    const moved=draft.action==='COUNT'&&(['warehouse_id','bin_id','lot_id'] as const).some(key=>key in next&&next[key]!==dimension[key]);
    onChange({ ...dimension, ...next,...(moved?{count:null,quantity_pending:true}:{}) });
  };
  useEffect(() => { setSelection(null); }, [dimension.warehouse_id, draft.date]);
  async function profile() {
    setBusy(true); setFailure('');
    try {
      const [product, context] = await Promise.all([
        request<{ id: string; company_id: string; base_unit_id?: string }>('catalog', 'GET', base + '/items/' + line.item.item_id),
        request<Accounting['schemas']['TrackingSource']>('accounting', 'GET', base + '/stock-tracking/context/' + line.item.item_id + '?resource=stock'),
      ]);
      if (product.id !== line.item.item_id || product.company_id !== company || !product.base_unit_id || context.item_id !== product.id || context.company_id !== company || !trackingId.test(context.profile_revision_id)) throw new Error('The current product tracking profile could not be verified.');
      update({ profile: { id: context.profile_revision_id, base_unit_id: product.base_unit_id, lot_tracking: context.lot_tracking, serial_tracking: context.serial_tracking }, lot_id: null, unit_ids: [] });
    } catch (error) { setFailure(error instanceof Error ? error.message : 'Unable to verify product requirements.'); }
    finally { setBusy(false); }
  }
  async function availability() {
    setBusy(true); setFailure('');
    try {
      const result = await request<Accounting['schemas']['StockSelection']>('accounting', 'POST', base + '/stock/selection', { item_id: line.item.item_id, warehouse_id: dimension.warehouse_id, stock_date: draft.date, operation: transferStock(draft.action) ? 'TRANSFER_OUT' : 'SALE_ISSUE' });
      if (result.company_id !== company || result.item_id !== line.item.item_id || result.warehouse_id !== dimension.warehouse_id || result.stock_date !== draft.date) throw new Error('Stock availability could not be verified.');
      setSelection(result);
    } catch (error) { setFailure(error instanceof Error ? error.message : 'Unable to check available stock.'); }
    finally { setBusy(false); }
  }
  const selectedPosition = selection?.items.find(row => row.bin_id === (dimension.bin_id ?? null) && row.lot_id === (dimension.lot_id ?? null));
  const serials = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ limit: '50' });
    let path: string;
    if (inwardStock(draft.action)) {
      path = base + '/stock-tracking/serials'; params.set('item_id', line.item.item_id); params.set('status', 'ACTIVE'); params.set('is_held', 'false'); params.set('receipt_eligible', 'true');
      if (dimension.lot_id) params.set('lot_id', dimension.lot_id);
    } else if (linkedStock(draft.action)) {
      if (!dimension.source_movement_id) throw new Error('Select the original movement first.');
      path = base + '/stock-tracking/serials'; params.set('item_id', line.item.item_id); params.set('source_movement_id', dimension.source_movement_id);
      if (dimension.lot_id) params.set('lot_id', dimension.lot_id);
    } else {
      if (!selectedPosition) throw new Error('Check eligible stock and select its bin and batch first.');
      path = base + '/stock/available-units'; params.set('position_id', selectedPosition.position_id); params.set('stock_date', draft.date); params.set('operation', transferStock(draft.action) ? 'TRANSFER_OUT' : 'SALE_ISSUE');
    }
    if (q) params.set('q', q); if (cursor) params.set('cursor', cursor);
    const page = await request<Page<Accounting['schemas']['SerialListItem']>>('accounting', 'GET', path + '?' + params, undefined, undefined, signal);
    return { items: page.items.map(row => ({ id: row.id, label: trackingTitle(row) })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [base, line.item.item_id, draft.action, draft.date, dimension.lot_id, dimension.source_movement_id, selectedPosition]);
  return <fieldset className="janso-fieldgroup janso-flow" disabled={disabled || busy}><legend>Stock item {index + 1}</legend>
    <Button type="button" variant="ghost" disabled={!line.item.item_id || disabled || busy} loading={busy} onClick={() => void profile()}>Verify product requirements {index + 1}</Button>
    {failure && <Notice tone="danger">{failure}</Notice>}
    {dimension.profile && <Notice>{dimension.profile.lot_tracking ? 'Batch tracked. ' : ''}{dimension.profile.serial_tracking ? 'One serial must be selected for each physical unit. ' : ''}Use the product base unit for quantity.{dimension.profile.base_unit_id !== line.item.unit_id ? ' The selected unit differs from the base unit; correct it before saving.' : ''}</Notice>}
    {dimension.profile&&native.quantity_entry&&onQuantity&&<VoucherStockQuantity company={company} item={line.item.item_id} baseUnit={dimension.profile.base_unit_id} date={draft.date} index={index} value={dimension.quantity_entry} disabled={disabled||busy||!write('quantity_entry')} onPending={()=>update({quantity_pending:true,...(draft.action==='COUNT'?{count:null}:{})})} onApply={(capture,quantity)=>{update({quantity_entry:capture,quantity_pending:draft.action==='COUNT',...(draft.action==='COUNT'?{count:null}:{})});if(quantity)onQuantity(line.line_key,quantity);}}/>}
    <div className="janso-form-grid">
      {native.warehouse_id && <StockReference company={company} resource="warehouses" label={'Warehouse ' + (index + 1)} value={dimension.warehouse_id} disabled={!write('warehouse_id')} onChange={warehouse => update({ warehouse_id: warehouse ?? '', bin_id: null, unit_ids: [] })} />}
      {native.bin_id && <StockReference company={company} resource="warehouse-bins" parent={dimension.warehouse_id} label={'Bin ' + (index + 1)} value={dimension.bin_id} disabled={!write('bin_id') || !dimension.warehouse_id} onChange={bin => update({ bin_id: bin, unit_ids: [] })} />}
      {dimension.profile?.lot_tracking && native.lot_id && <StockReference company={company} resource="batches" parent={line.item.item_id} label={'Batch ' + (index + 1)} value={dimension.lot_id} disabled={!write('lot_id')} onChange={batch => update({ lot_id: batch, unit_ids: [] })} />}
      {inwardStock(draft.action) && native.received_value && <TextField label={'Total carrying value ' + (index + 1) + ' (' + currency + ')'} value={dimension.received_value ?? ''} inputMode="decimal" required disabled={!write('received_value')} onChange={event => update({ received_value: event.target.value, zero_value_reason: undefined })} hint="Total value for this physical line, excluding recoverable tax. Enter zero only for an authorised zero-cost receipt." />}
      {inwardStock(draft.action) && /^0(?:\.0+)?$/.test(dimension.received_value ?? '') && native.zero_value_reason && <TextField label={'Zero-cost reason ' + (index + 1)} value={dimension.zero_value_reason ?? ''} required minLength={3} maxLength={500} disabled={!write('zero_value_reason')} onChange={event => update({ zero_value_reason: event.target.value })} />}
      {transferStock(draft.action) && native.destination_warehouse_id && <StockReference company={company} resource="warehouses" label={'Destination warehouse ' + (index + 1)} value={dimension.destination_warehouse_id} disabled={!write('destination_warehouse_id')} onChange={warehouse => update({ destination_warehouse_id: warehouse, destination_bin_id: null })} />}
      {transferStock(draft.action) && native.destination_bin_id && <StockReference company={company} resource="warehouse-bins" parent={dimension.destination_warehouse_id ?? ''} label={'Destination bin ' + (index + 1)} value={dimension.destination_bin_id} disabled={!write('destination_bin_id') || !dimension.destination_warehouse_id} onChange={bin => update({ destination_bin_id: bin })} />}
      {linkedStock(draft.action) && native.source_movement_id && <StockReference company={company} resource="movements" parent={line.item.item_id} label={'Original stock movement ' + (index + 1)} value={dimension.source_movement_id} disabled={!write('source_movement_id')} onChange={movement => update({ source_movement_id: movement, unit_ids: [] })} />}
      {draft.action === 'OPENING' && draft.openingMode === 'LINKED_GL' && native.opening_journal_line_id && <OpeningReference company={company} date={draft.date} label={'Posted inventory opening line ' + (index + 1)} value={dimension.opening_journal_line_id ?? null} disabled={!write('opening_journal_line_id')} onChange={id => update({ opening_journal_line_id: id })} />}
    </div>
    {draft.action==='COUNT'&&dimension.profile&&native.count&&(dimension.profile.serial_tracking?<Notice tone="warning">Serial counts require identity reconciliation and are unavailable in this count workflow.</Notice>:<VoucherStockCount key={[company,line.item.item_id,dimension.warehouse_id,dimension.bin_id,dimension.lot_id,draft.date].join(':')} company={company} item={line.item.item_id} warehouse={dimension.warehouse_id} bin={dimension.bin_id} lot={dimension.lot_id} date={draft.date} reason={draft.reason} quantity={line.item.actual_quantity} entry={dimension.quantity_entry} value={dimension.count} index={index} canReview={canReviewCount} disabled={disabled||busy||!write('count')} onPending={()=>update({count:null,quantity_pending:true})} onApply={count=>update({count,quantity_pending:!count})}/>)}
    {!inwardStock(draft.action) && !linkedStock(draft.action) && <Button type="button" variant="ghost" disabled={!dimension.warehouse_id || !dimension.profile || disabled || busy} onClick={() => void availability()}>Check eligible stock {index + 1}</Button>}
    {selection && <Notice>{selection.items.length ? 'Eligible cohorts are available in ' + selection.issue_strategy + ' order. Select their bin and batch; posting rechecks availability.' : 'No eligible stock is available for this product, warehouse and movement date.'}{selection.has_more ? ' More than 200 cohorts exist; split the movement.' : ''}</Notice>}
    {selection?.items.length ? <Select label={'Eligible stock cohort ' + (index + 1)} value={selection.items.find(row => row.bin_id === (dimension.bin_id ?? null) && row.lot_id === (dimension.lot_id ?? null))?.position_id ?? ''} options={[{ value: '', label: 'Select eligible stock' }, ...selection.items.filter((row, at, rows) => rows.findIndex(other => other.position_id === row.position_id) === at).map((row, at) => ({ value: row.position_id, label: (at + 1) + '. Received ' + format.date(row.received_on) + (row.expires_on ? ' · Expires ' + format.date(row.expires_on) : '') + ' · Available ' + format.quantity(row.quantity) }))]} disabled={!write('bin_id') || !!dimension.profile?.lot_tracking && !write('lot_id')} onChange={position => { const row = selection.items.find(entry => entry.position_id === position); if (row) onChange({ ...dimension, bin_id: row.bin_id, lot_id: row.lot_id, unit_ids: [] }); }} /> : null}
    {dimension.profile?.serial_tracking && native.unit_ids && <SearchSelect multiple label={'Serials ' + (index + 1)} value={dimension.unit_ids ?? []} loadOptions={serials} scopeKey={[company, line.item.item_id, dimension.lot_id, dimension.bin_id, dimension.warehouse_id, dimension.source_movement_id, draft.date, draft.action].join(':')} minQueryLength={0} maxOptions={200} disabled={!write('unit_ids') || disabled || busy || (linkedStock(draft.action) ? !dimension.source_movement_id : !inwardStock(draft.action) && !selectedPosition)} onChange={ids => onChange({ ...dimension, unit_ids: ids })} hint="Select one distinct serial per base unit. Original movement choices retain historical units; remaining claims and availability are checked again before posting." />}
  </fieldset>;
}

export function OpeningReference({ company, date, label, value, disabled, onChange }: { company: string; date: string; label: string; value: string | null; disabled: boolean; onChange: (id: string | null) => void }) {
  const format = useFormatters();
  const load = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ stock_date: date, limit: '50' });
    if (q.trim().length >= 2) params.set('q', q.trim()); if (cursor) params.set('cursor', cursor);
    const page = await request<Page<{ id: string; number: string; currency: string; remaining_value: string }>>('accounting', 'GET', '/v1/companies/' + company + '/stock/opening-lines?' + params, undefined, undefined, signal);
    if (!page.page || !Array.isArray(page.items) || page.items.some(row => !trackingId.test(row.id))) throw new Error('Opening lines could not be verified.');
    return { items: page.items.map(row => ({ id: row.id, label: row.number, meta: 'Unclaimed ' + format.money(row.remaining_value, { display: 'none' }) + ' ' + row.currency })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [company, date, format]);
  return <SearchSelect label={label} value={value} loadOptions={load} scopeKey={company + ':' + date} minQueryLength={0} disabled={disabled} onChange={onChange} hint="Choose a posted inventory opening with unclaimed value. The amount is checked again before posting." />;
}

export function StockReference({ company, resource, parent, label, value, onChange, disabled, physicalOnly = false, required = false }: {
  company: string; resource: 'warehouses' | 'warehouse-bins' | 'batches' | 'movements'; parent?: string; label: string; value?: string | null; onChange: (id: string | null) => void; disabled: boolean; physicalOnly?: boolean; required?: boolean;
}) {
  const format = useFormatters(), [selected, setSelected] = useState<SearchSelectOption | null>(null), [failure, setFailure] = useState('');
  const service = resource === 'batches' || resource === 'movements' ? 'accounting' : 'catalog';
  const path = '/v1/companies/' + company + '/' + (resource === 'batches' ? 'stock-tracking/batches' : resource === 'movements' ? 'stock/movements' : resource);
  const option = useCallback((row: Reference): SearchSelectOption => ({ id: row.id, label: row.name ?? row.code ?? (row.stock_date ? 'Movement on ' + format.date(row.stock_date) : 'Protected record'), meta: row.name && row.code ? row.code : row.quantity != null ? format.quantity(row.quantity) + ' · Reference ' + row.id.slice(-8) : undefined }), [format]);
  useEffect(() => {
    const abort = new AbortController(); setSelected(null); setFailure('');
    if (value && trackingId.test(value)) request<Reference>(service, 'GET', path + '/' + value, undefined, undefined, abort.signal).then(row => {
      if (row.id !== value || row.company_id !== company) throw new Error('Stock reference ownership could not be verified.');
      if (!abort.signal.aborted) setSelected(option(row));
    }).catch(error => { if (!abort.signal.aborted) setFailure(error instanceof Error ? error.message : 'Unable to load the stock reference.'); });
    return () => abort.abort();
  }, [value, company, path, service, option]);
  const load = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ limit: '50' });
    if (cursor) params.set('cursor', cursor);
    if (resource === 'movements') params.set('item_id', parent ?? '');
    else { params.set(resource === 'batches' ? 'status' : 'is_active', resource === 'batches' ? 'ACTIVE' : 'true'); if (q.trim().length >= 2) params.set('q', q.trim()); }
    if (resource === 'warehouse-bins') params.set('warehouse_id', parent ?? '');
    if (resource === 'batches') { params.set('item_id', parent ?? ''); params.set('is_held', 'false'); }
    const page = await request<Page<Reference>>(service, 'GET', path + '?' + params, undefined, undefined, signal);
    if (!Array.isArray(page.items) || !page.page || page.items.some(row => !trackingId.test(row.id))) throw new Error('Stock options could not be verified.');
    return { items: page.items.filter(row => !physicalOnly || ['STORE', 'GODOWN'].includes(row.kind ?? '')).map(option), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [resource, parent, path, service, option, physicalOnly]);
  return <SearchSelect required={required} label={label} value={value ?? null} selected={selected} error={failure} loadOptions={load} scopeKey={[company, resource, parent].join(':')} minQueryLength={0} disabled={disabled} onChange={onChange} hint={resource === 'movements' ? 'Browse this product’s original movements. The remaining claim and matching dimensions are verified before posting.' : undefined} />;
}
