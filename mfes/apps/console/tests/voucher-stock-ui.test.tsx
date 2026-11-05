import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { components } from '@janso/api-client/vouchers';
import { VoucherStock } from '../app/components/VoucherStock';
import type { FieldSet } from '../app/lib/voucher-fields';
import type { StockDraft } from '../app/lib/voucher-stock';
import { productFieldRequest as request } from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('@janso/ui', async original => ({ ...await original<typeof import('@janso/ui')>(), SearchSelect: ({ label, disabled, value, onChange, multiple }: { label: string; disabled: boolean; value: string | string[]; onChange: (value: string | string[]) => void; multiple?: boolean }) => <input aria-label={label} disabled={disabled} value={Array.isArray(value) ? value.join(',') : value ?? ''} onChange={event => onChange(multiple ? event.target.value.split(',') : event.target.value)} /> }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const line: components['schemas']['LineInput'] = { line_key: id(1), line_kind: 'ITEM', item: { item_id: id(2), item_version: 1, unit_id: id(3), actual_quantity: '2', billed_quantity: '0' } };
const dimensions = Object.fromEntries(['warehouse_id', 'bin_id', 'lot_id', 'unit_ids', 'destination_warehouse_id', 'destination_bin_id', 'source_movement_id', 'opening_journal_line_id', 'received_value', 'zero_value_reason'].map(key => [key, {}]));
const metadata = { native: { properties: { stock: { anyOf: [{ properties: { stock_date: {}, opening_mode: {}, reason: {}, lines: { items: { properties: dimensions } } } }] } } }, custom: [], configuration: { kind: 'RECEIPT_NOTE', profile: 'STANDARD', type_revision_id: id(4), policy: { stock: { opening_gl_mode: 'EITHER' } } } } as unknown as FieldSet;
const initial: StockDraft = { action: 'RECEIPT', date: '2026-10-28', reason: '', openingMode: 'COMBINED', dimensions: {} };
function Form({ draft = initial, fields = metadata, disabled = false }: { draft?: StockDraft; fields?: FieldSet; disabled?: boolean }) {
  const [value, setValue] = useState(draft);
  return <><VoucherStock company={id(10)} currency="INR" metadata={fields} lines={[line]} value={value} onChange={setValue} disabled={disabled} /><output data-testid="stock">{JSON.stringify(value)}</output></>;
}
const current = () => JSON.parse(screen.getByTestId('stock').textContent!);
beforeEach(() => { vi.mocked(request).mockReset().mockRejectedValue(new Error('Reference unavailable')); });
it('captures exact inward value and meaningful evidence using shared controls', () => {
  render(<Form />);
  fireEvent.change(screen.getByLabelText('Stock movement reason'), { target: { value: 'Receive delivered goods' } });
  fireEvent.change(screen.getByLabelText('Total carrying value 1 (INR)'), { target: { value: '123456789012345.1234' } });
  expect(current().reason).toBe('Receive delivered goods');
  expect(current().dimensions[id(1)].received_value).toBe('123456789012345.1234');
  fireEvent.change(screen.getByLabelText('Total carrying value 1 (INR)'), { target: { value: '0.0000' } });
  expect(screen.getByLabelText('Zero-cost reason 1')).toBeRequired();
});
it('verifies current company/product ownership before enabling batch and serial capture', async () => {
  vi.mocked(request).mockResolvedValueOnce({ id: id(2), company_id: id(10), base_unit_id: id(3) } as never).mockResolvedValueOnce({ company_id: id(10), item_id: id(2), profile_revision_id: id(20), lot_tracking: true, serial_tracking: true } as never);
  render(<Form />);
  fireEvent.click(screen.getByRole('button', { name: 'Verify product requirements 1' }));
  await waitFor(() => expect(screen.getByLabelText('Batch 1')).toBeEnabled());
  expect(screen.getByLabelText('Serials 1')).toBeEnabled();
  fireEvent.change(screen.getByLabelText('Serials 1'), { target: { value: id(30) + ',' + id(31) } });
  expect(current().dimensions[id(1)].unit_ids).toEqual([id(30), id(31)]);
});
it('shows verification failures and never adopts a different company profile', async () => {
  vi.mocked(request).mockResolvedValueOnce({ id: id(2), company_id: id(99), base_unit_id: id(3) } as never).mockResolvedValueOnce({ company_id: id(10), item_id: id(2), profile_revision_id: id(20), lot_tracking: true, serial_tracking: true } as never);
  render(<Form />);
  fireEvent.click(screen.getByRole('button', { name: 'Verify product requirements 1' }));
  await screen.findByText('The current product tracking profile could not be verified.');
  expect(screen.queryByLabelText('Serials 1')).not.toBeInTheDocument();
});
it('clears dimensions when movement date changes', () => {
  render(<Form draft={{ ...initial, dimensions: { [id(1)]: { item_id: id(2), warehouse_id: id(5), unit_ids: [id(30)] } } }} />);
  fireEvent.change(screen.getByLabelText('Stock movement date'), { target: { value: '2026-10-29' } });
  expect(current().dimensions).toEqual({});
});
it('renders transfer destinations and linked claim controls only for applicable actions', () => {
  const { unmount } = render(<Form draft={{ ...initial, action: 'TRANSFER' }} />);
  expect(screen.getByLabelText('Destination warehouse 1')).toBeEnabled();
  expect(screen.queryByLabelText('Total carrying value 1 (INR)')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Original stock movement 1')).not.toBeInTheDocument();
  unmount();
  render(<Form draft={{ ...initial, action: 'CUSTOMER_RETURN' }} />);
  expect(screen.getByLabelText('Original stock movement 1')).toBeEnabled();
  expect(screen.queryByLabelText('Destination warehouse 1')).not.toBeInTheDocument();
});
it('offers explicit opening GL handling and displays linked evidence', () => {
  render(<Form draft={{ ...initial, action: 'OPENING', openingMode: 'LINKED_GL' }} />);
  expect(screen.getByLabelText('Posted inventory opening line 1')).toBeEnabled();
});
it('obeys field denies and locks all controls during save', () => {
  const fields = { ...metadata, native: { properties: { stock: { properties: { stock_date: {}, reason: { readOnly: true }, lines: { items: { properties: { warehouse_id: { readOnly: true } } } } } } } } };
  const { unmount } = render(<Form fields={fields} />);
  expect(screen.getByLabelText('Warehouse 1')).toBeDisabled();
  expect(screen.getByLabelText('Stock movement reason')).toBeDisabled();
  expect(screen.queryByLabelText('Total carrying value 1 (INR)')).not.toBeInTheDocument();
  unmount(); render(<Form disabled />);
  expect(screen.getByLabelText('Stock movement date')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Verify product requirements 1' })).toBeDisabled();
});
