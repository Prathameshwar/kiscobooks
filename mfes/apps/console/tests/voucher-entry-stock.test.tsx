vi.mock('../app/lib/navigate', async original => ({ ...await original<typeof import('../app/lib/navigate')>(), goTo: vi.fn() }));
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { VoucherEntry } from '../app/components/VoucherEntry';
import { productFieldRequest } from '../app/lib/product-fields';
import { serviceCall } from '../app/lib/service-call';
import type { StockDraft } from '../app/lib/voucher-stock';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('@janso/ui', async original => ({ ...await original<typeof import('@janso/ui')>(), Select: ({ label, value, options, onChange, disabled }: { label: string; value: string; options: { value: string; label: string }[]; onChange: (value: string) => void; disabled?: boolean }) => <label>{label}<select aria-label={label} value={value} disabled={disabled} onChange={event => onChange(event.target.value)}><option value="">Choose</option>{options.map(row => <option key={row.value} value={row.value}>{row.label}</option>)}</select></label> }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
vi.mock('../app/components/VoucherItems', () => ({ VoucherItems: ({ onChange }: { onChange: (value: unknown[]) => void }) => <button type="button" onClick={() => onChange([{ line_key: '10000000-0000-7000-8000-000000000001', line_kind: 'ITEM', item: { item_id: '10000000-0000-7000-8000-000000000002', item_version: 1, unit_id: '10000000-0000-7000-8000-000000000003', actual_quantity: '2.0000', billed_quantity: '0' } }])}>Choose stock product</button> }));
vi.mock('../app/components/VoucherStock', () => ({ VoucherStock: ({ value, onChange }: { value: StockDraft; onChange: (value: StockDraft) => void }) => <button type="button" onClick={() => onChange({ ...value, reason: 'Receive purchased goods', dimensions: { '10000000-0000-7000-8000-000000000001': { item_id: '10000000-0000-7000-8000-000000000002', warehouse_id: '10000000-0000-7000-8000-000000000005', received_value: '12.50', profile: { id: '10000000-0000-7000-8000-000000000006', base_unit_id: '10000000-0000-7000-8000-000000000003', lot_tracking: false, serial_tracking: false } } } })}>Choose stock dimensions</button> }));
vi.mock('../app/components/VoucherWorkflow', () => ({ VoucherWorkflow: () => <p>Saved workflow</p> }));
vi.mock('../app/components/VoucherMoney', () => ({ VoucherMoney: () => null }));
vi.mock('../app/components/VoucherRelated', () => ({ VoucherRelated: () => null }));
const metadata = { native: { properties: { mode: {}, narration: {}, posting_date: {}, stock_date: {}, stock: {} } }, custom: [], configuration: { type_revision_id: id(7), kind: 'RECEIPT_NOTE', profile: 'STANDARD', policy: { stock: {}, allowed_modes: ['ITEMS'] } } };
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(productFieldRequest).mockImplementation(async (_service, _method, path) => path.includes('/field-set') ? metadata as never : path.includes('/voucher-classes') ? { items: [] } as never : { items: [{ id: id(7), name: 'Goods receipt' }] } as never);
});
async function prepared() {
  render(<VoucherEntry company={id(10)} currency="INR" canCreate />);
  fireEvent.click(screen.getByRole('button', { name: 'Load voucher types' }));
  await screen.findByRole('option', { name: 'Goods receipt' });
  fireEvent.change(screen.getByLabelText('Voucher type'), { target: { value: id(7) } });
  fireEvent.change(screen.getByLabelText('Document date'), { target: { value: '2026-10-28' } });
  fireEvent.click(screen.getByRole('button', { name: 'Load entry fields' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Choose stock product' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Choose stock product' }));
  fireEvent.click(screen.getByRole('button', { name: 'Choose stock dimensions' }));
}
it.each([
  ['PHYSICAL_STOCK', id(10), true],
  ['PURCHASE', id(10), false],
  ['PHYSICAL_STOCK', id(11), false],
] as const)('verifies the kind and company of stock-adjustment types: %s / %s', async (kind, company, accepted) => {
  vi.mocked(productFieldRequest).mockResolvedValueOnce({ items: [{ id: id(7), name: 'Stock adjustment', kind, company_id: company }] } as never);
  render(<VoucherEntry company={id(10)} currency="INR" canCreate initialKind="PHYSICAL_STOCK" />);
  fireEvent.click(screen.getByRole('button', { name: 'Load voucher types' }));
  if (accepted) await screen.findByRole('option', { name: 'Stock adjustment' });
  else {
    await screen.findByText('Voucher type ownership and kind could not be verified.');
    expect(screen.queryByRole('option', { name: 'Stock adjustment' })).not.toBeInTheDocument();
  }
  expect(productFieldRequest).toHaveBeenCalledWith('vouchers', 'GET', expect.stringContaining('&kind=PHYSICAL_STOCK'));
});
it('saves physical capture and retries an uncertain response with exactly the same body and key', async () => {
  vi.mocked(serviceCall).mockRejectedValueOnce({ status: 503, message: 'Connection interrupted' }).mockResolvedValueOnce({ id: id(20), company_id: id(10) });
  await prepared();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByRole('button', { name: 'Retry the same save' });
  expect(screen.getByLabelText('Document date')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Choose stock dimensions' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Retry the same save' }));
  await screen.findByText('Saved workflow');
  const first = vi.mocked(serviceCall).mock.calls[0]![1], second = vi.mocked(serviceCall).mock.calls[1]![1];
  expect(second).toEqual(first);
  expect(first.key).toBeTruthy();
  expect(first.body).toMatchObject({ mode: 'ITEMS', stock_date: '2026-10-28', stock: { action: 'RECEIPT', stock_date: '2026-10-28', lines: [{ quantity: '2.0000', received_value: '12.50' }] } });
});
it('keeps a rejected draft editable and displays the validation failure', async () => {
  vi.mocked(serviceCall).mockRejectedValueOnce({ status: 422, message: 'The chosen warehouse is unavailable' });
  await prepared();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByText('The chosen warehouse is unavailable');
  expect(screen.getByLabelText('Document date')).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Choose stock dimensions' })).toBeEnabled();
});
