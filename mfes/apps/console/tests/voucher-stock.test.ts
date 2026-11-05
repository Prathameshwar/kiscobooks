import { describe, expect, it } from 'vitest';
import type { components } from '@janso/api-client/vouchers';
import type { FieldSet } from '../app/lib/voucher-fields';
import { buildStockCapture, initialStockDraft, stockAction, type StockDraft } from '../app/lib/voucher-stock';

const id = (index: number) => '10000000-0000-7000-8000-' + String(index).padStart(12, '0');
const line: components['schemas']['LineInput'] = { line_key: id(1), line_kind: 'ITEM', item: { item_id: id(2), item_version: 1, unit_id: id(3), actual_quantity: '2.0000', billed_quantity: '0.0000' } };
const metadata = { native: { properties: { stock: {} } }, custom: [], configuration: { kind: 'RECEIPT_NOTE', profile: 'STANDARD', type_revision_id: id(4), policy: { stock: {} } } } as FieldSet;
function draft(): StockDraft {
  return { ...initialStockDraft(metadata, '2026-10-28')!, reason: 'Receive purchased goods', dimensions: { [line.line_key]: { item_id: id(2), warehouse_id: id(5), received_value: '123456789012345.1234', profile: { id: id(6), base_unit_id: id(3), lot_tracking: false, serial_tracking: false } } } };
}
it('recognizes only the eight native stock profiles and requires writable configured stock', () => {
  expect(stockAction('STOCK_JOURNAL', 'REQUISITION')).toBeUndefined();
  expect(stockAction('STOCK_JOURNAL', 'TRANSFER_RECEIPT')).toBe('TRANSFER_RECEIPT');
  expect(initialStockDraft({ ...metadata, native: { properties: { stock: { readOnly: true } } } }, '2026-10-28')).toBeNull();
  expect(initialStockDraft({ ...metadata, configuration: { ...metadata.configuration, policy: {} } }, '2026-10-28')).toBeNull();
});
it('retains exact decimal strings and common line quantities while removing UI evidence', () => {
  const result = buildStockCapture(draft(), [line], 'INR', metadata);
  expect(result.lines[0]).toEqual({ warehouse_id: id(5), received_value: '123456789012345.1234', line_id: id(1), item_id: id(2), quantity: '2.0000' });
  expect(result.lines[0]).not.toHaveProperty('profile');
  expect(result).not.toHaveProperty('opening_mode');
});
describe('validation', () => {
  it.each(['0', '-1', '1e3', '1.00001', 'NaN'])('rejects quantity %s', quantity => {
    expect(() => buildStockCapture(draft(), [{ ...line, item: { ...line.item, actual_quantity: quantity } }], 'INR', metadata)).toThrow(/positive base-unit quantity/);
  });
  it('requires the current item and base unit', () => {
    const value = draft(); value.dimensions[line.line_key]!.item_id = id(99);
    expect(() => buildStockCapture(value, [line], 'INR', metadata)).toThrow(/current product/);
    expect(() => buildStockCapture(draft(), [{ ...line, item: { ...line.item, unit_id: id(99) } }], 'INR', metadata)).toThrow(/base unit/);
  });
  it('requires explicit zero-cost policy and evidence', () => {
    const value = draft(); value.dimensions[line.line_key]!.received_value = '0';
    expect(() => buildStockCapture(value, [line], 'INR', metadata)).toThrow(/zero-cost stock/);
    value.dimensions[line.line_key]!.zero_value_reason = 'Donated goods';
    const allowed = { ...metadata, configuration: { ...metadata.configuration, policy: { stock: { allow_zero_value_receipts: true } } } } as FieldSet;
    expect(buildStockCapture(value, [line], 'INR', allowed).lines[0]!.received_value).toBe('0');
  });
  it('requires distinct serials with an exact physical unit count', () => {
    const value = draft(), selected = value.dimensions[line.line_key]!;
    selected.profile!.serial_tracking = true; selected.unit_ids = [id(10), id(10)];
    expect(() => buildStockCapture(value, [line], 'INR', metadata)).toThrow(/distinct/);
    selected.unit_ids = [id(10)];
    expect(() => buildStockCapture(value, [line], 'INR', metadata)).toThrow(/one serial/);
    selected.unit_ids = [id(10), id(11)];
    expect(buildStockCapture(value, [line], 'INR', metadata).lines[0]!.unit_ids).toHaveLength(2);
  });
  it('requires source claims, transfer destinations and linked opening evidence', () => {
    const value = draft(); delete value.dimensions[line.line_key]!.received_value;
    value.action = 'CUSTOMER_RETURN';
    expect(() => buildStockCapture(value, [line], 'INR', metadata)).toThrow(/original stock movement/);
    value.action = 'TRANSFER';
    expect(() => buildStockCapture(value, [line], 'INR', metadata)).toThrow(/destination warehouse/);
    value.action = 'OPENING'; value.openingMode = 'LINKED_GL'; value.dimensions[line.line_key]!.received_value = '10';
    expect(() => buildStockCapture(value, [line], 'INR', metadata)).toThrow(/posted inventory opening/);
  });
});
