import type { components } from '@janso/api-client/vouchers';
import type { FieldSet } from './voucher-fields';
import { trackingId } from './stock-tracking-resources';
import { validMasterDate } from './catalog-masters';

export type StockCapture = components['schemas']['StockInput-Input'];
export type StockDimension = Omit<components['schemas']['StockLine-Input'], 'line_id' | 'item_id' | 'quantity'> & { item_id: string; quantity_pending?: boolean; profile?: { id: string; base_unit_id: string; lot_tracking: boolean; serial_tracking: boolean } };
export type StockDraft = { action: StockCapture['action']; date: string; reason: string; openingMode: 'COMBINED' | 'LINKED_GL'; dimensions: Record<string, StockDimension> };
const profiles: Record<string, StockCapture['action']> = {
  'STOCK_JOURNAL:OPENING': 'OPENING', 'RECEIPT_NOTE:STANDARD': 'RECEIPT',
  'DELIVERY_NOTE:STANDARD': 'DISPATCH', 'STOCK_JOURNAL:TRANSFER': 'TRANSFER',
  'STOCK_JOURNAL:TRANSFER_DISPATCH': 'TRANSFER_DISPATCH',
  'STOCK_JOURNAL:TRANSFER_RECEIPT': 'TRANSFER_RECEIPT',
  'REJECTIONS_IN:STANDARD': 'CUSTOMER_RETURN', 'REJECTIONS_OUT:STANDARD': 'SUPPLIER_RETURN',
  'PHYSICAL_STOCK:STANDARD': 'COUNT',
};
export const stockAction = (kind?: string | null, profile?: string | null) => profiles[kind + ':' + profile];
export const stockKind = (kind?: string | null) => Object.keys(profiles).some(key => key.startsWith(kind + ':'));
export function initialStockDraft(metadata: FieldSet, date: string): StockDraft | null {
  const action = stockAction(metadata.configuration.kind, metadata.configuration.profile);
  if (!action || !metadata.configuration.policy.stock || !metadata.native.properties?.stock || metadata.native.properties.stock.readOnly) return null;
  return { action, date, reason: '', openingMode: metadata.configuration.policy.stock.opening_gl_mode === 'LINKED_GL' ? 'LINKED_GL' : 'COMBINED', dimensions: {} };
}
export const inwardStock = (action: StockCapture['action']) => action === 'RECEIPT' || action === 'OPENING';
export const transferStock = (action: StockCapture['action']) => action === 'TRANSFER' || action === 'TRANSFER_DISPATCH';
export const linkedStock = (action: StockCapture['action']) => ['CUSTOMER_RETURN', 'SUPPLIER_RETURN', 'TRANSFER_RECEIPT'].includes(action);
const decimal = /^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;
export function buildStockCapture(draft: StockDraft, lines: components['schemas']['LineInput'][], currency: string, metadata: FieldSet): StockCapture {
  if (!validMasterDate(draft.date)) throw new Error('Enter a valid stock movement date.');
  if (draft.reason.trim().length < 3) throw new Error('Explain the physical stock movement.');
  if (!lines.length || lines.length > 100) throw new Error('Add between one and 100 stock item lines.');
  const seen = new Set<string>();
  const capture: StockCapture = { action: draft.action, stock_date: draft.date, currency, reason: draft.reason.trim(), lines: lines.map((line, index) => {
    const selected = draft.dimensions[line.line_key], prefix = 'Item ' + (index + 1) + ': ';
    if (selected?.quantity_pending) throw new Error(prefix + 'validate and apply the entered product quantity, or use base quantity.');
    if (!selected || selected.item_id !== line.item.item_id || !trackingId.test(selected.warehouse_id)) throw new Error(prefix + 'select a warehouse for the current product.');
    if (!selected.profile || selected.profile.base_unit_id !== line.item.unit_id) throw new Error(prefix + 'load the current inventory profile and use its base unit.');
    if (selected.profile.lot_tracking && !trackingId.test(selected.lot_id ?? '')) throw new Error(prefix + 'select a prepared batch.');
    if (!decimal.test(line.item.actual_quantity) || (draft.action !== 'COUNT' && /^0(?:\.0+)?$/.test(line.item.actual_quantity))) throw new Error(prefix + (draft.action==='COUNT'?'enter a nonnegative counted quantity with at most four decimal places.':'enter a positive base-unit quantity with at most four decimal places.'));
    if (draft.action === 'COUNT' && (selected.profile.serial_tracking || !trackingId.test(selected.count?.observation_id??'') || !Number.isSafeInteger(selected.count?.expected_revision) || (selected.count?.expected_revision??0)<2)) throw new Error(prefix + 'record a native non-serial count observation before saving.');
    const units = selected.unit_ids ?? [];
    if (!selected.profile.lot_tracking && selected.lot_id) throw new Error(prefix + 'this product does not use batches.');
    if (!selected.profile.serial_tracking && units.length) throw new Error(prefix + 'this product does not use serials.');
    for (const key of ['bin_id', 'lot_id', 'destination_warehouse_id', 'destination_bin_id', 'source_movement_id', 'opening_journal_line_id'] as const) if (selected[key] && !trackingId.test(selected[key]!)) throw new Error(prefix + 'select a valid stock reference.');
    if (units.length > 200 || new Set(units).size !== units.length || units.some(id => !trackingId.test(id) || seen.has(id))) throw new Error(prefix + 'serial selections must be distinct and limited to 200 units.');
    if (selected.profile.serial_tracking && (!/^[1-9]\d*(?:\.0{1,4})?$/.test(line.item.actual_quantity) || BigInt(line.item.actual_quantity.split('.')[0]!) !== BigInt(units.length))) throw new Error(prefix + 'select one serial for each physical unit.');
    units.forEach(id => seen.add(id));
    const { item_id: _item, profile: _profile, quantity_pending: _pending, ...dimensions } = selected;
    if (inwardStock(draft.action)) {
      if (typeof selected.received_value !== 'string' || !decimal.test(selected.received_value)) throw new Error(prefix + 'enter the reviewed total carrying value.');
      if (/^0(?:\.0+)?$/.test(selected.received_value) && (!metadata.configuration.policy.stock?.allow_zero_value_receipts || (selected.zero_value_reason?.trim().length ?? 0) < 3)) throw new Error(prefix + 'zero-cost stock requires an enabled policy and a reason.');
    }
    if (transferStock(draft.action) && !trackingId.test(selected.destination_warehouse_id ?? '')) throw new Error(prefix + 'select the destination warehouse.');
    if (linkedStock(draft.action) && !trackingId.test(selected.source_movement_id ?? '')) throw new Error(prefix + 'select the original stock movement.');
    if (draft.action === 'OPENING' && draft.openingMode === 'LINKED_GL' && !trackingId.test(selected.opening_journal_line_id ?? '')) throw new Error(prefix + 'select the posted inventory opening line.');
    return { ...dimensions, line_id: line.line_key, item_id: line.item.item_id, quantity: line.item.actual_quantity };
  }) };
  if (draft.action === 'OPENING') capture.opening_mode = draft.openingMode;
  if (seen.size > 1000) throw new Error('A stock voucher supports at most 1,000 serials.');
  return capture;
}
