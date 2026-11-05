vi.mock('../app/lib/navigate', async original => ({ ...await original<typeof import('../app/lib/navigate')>(), goTo: vi.fn() }));
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { VoucherEntry } from '../app/components/VoucherEntry';
import { productFieldRequest } from '../app/lib/product-fields';
import { serviceCall } from '../app/lib/service-call';
import type { FieldSet } from '../app/lib/voucher-fields';

vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('@janso/ui', async original => ({ ...await original<typeof import('@janso/ui')>(), Select: ({ label, value, options, onChange, disabled }: { label: string; value: string; options: { value: string; label: string }[]; onChange: (value: string) => void; disabled?: boolean }) => <label>{label}<select aria-label={label} value={value} disabled={disabled} onChange={event => onChange(event.target.value)}><option value="">Choose</option>{options.map(row => <option key={row.value} value={row.value}>{row.label}</option>)}</select></label> }));
vi.mock('../app/components/VoucherItems', () => ({ VoucherItems: () => <button type="button">Add item</button> }));
vi.mock('../app/components/VoucherRelated', () => ({ VoucherRelated: () => null }));
vi.mock('../app/components/VoucherWorkflow', () => ({ VoucherWorkflow: () => <p>Saved workflow</p> }));
vi.mock('../app/components/VoucherMoney', () => ({ VoucherMoney: ({ onChange, disabled }: { onChange: (value: unknown) => void; disabled: boolean }) => <button type="button" disabled={disabled} onClick={() => onChange({ purpose: 'GENERAL', accounts: [{ line_key: '10000000-0000-7000-8000-000000000005', account_id: '10000000-0000-7000-8000-000000000006', source_version: 2, side: 'DEBIT', currency: 'INR', amount: '42.1234', exchange_rate: '1', tracking: 'NONE' }], tenders: [], allocations: [] })}>Prepare exact money capture</button> }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), type = id(2);
const metadata: FieldSet = { native: { properties: { financial: {}, posting_date: {}, narration: {} } }, custom: [], configuration: { type_revision_id: id(3), kind: 'RECEIPT', profile: 'STANDARD', policy: { schema_version: 2, allowed_modes: ['ACCOUNTS'] } } };
const api = vi.mocked(productFieldRequest);
beforeEach(() => {
  vi.clearAllMocks();
  api.mockImplementation(async (_service, _method, path) => (path.includes('/field-set') ? metadata : path.includes('/voucher-classes') ? { items: [] } : { items: [{ id: type, company_id: company, kind: 'RECEIPT', name: 'Ordinary receipt' }] }) as never);
});
async function load() {
  render(<VoucherEntry company={company} currency="INR" initialKind="RECEIPT" canCreate />);
  fireEvent.click(screen.getByRole('button', { name: 'Load voucher types' }));
  await screen.findByRole('option', { name: 'Ordinary receipt' });
  fireEvent.change(screen.getByLabelText('Voucher type'), { target: { value: type } });
  fireEvent.change(screen.getByLabelText('Document date'), { target: { value: '2026-10-30' } });
  fireEvent.click(screen.getByRole('button', { name: 'Load entry fields' }));
}
it('does not offer item entry for an account-only money type', async () => {
  await load(); await screen.findByRole('button', { name: 'Save draft' });
  expect(screen.queryByRole('button', { name: 'Add item' })).not.toBeInTheDocument();
});
it('queries only active Receipt types and explains empty company setup', async () => {
  api.mockResolvedValue({ items: [] });
  render(<VoucherEntry company={company} currency="INR" initialKind="RECEIPT" canCreate />);
  fireEvent.click(screen.getByRole('button', { name: 'Load voucher types' }));
  await screen.findByText(/No active receipt voucher types/);
  expect(api.mock.calls[0]?.[2]).toContain('status=ACTIVE&limit=200&kind=RECEIPT');
  expect(screen.getByRole('link', { name: 'Review voucher types' })).toHaveAttribute('href', '/masters/voucher-types');
});
it.each([{ company_id: id(9), kind: 'RECEIPT' }, { company_id: company, kind: 'PAYMENT' }])('refuses a foreign company or wrong kind in discovery', async row => {
  api.mockResolvedValue({ items: [{ id: type, name: 'Wrong type', ...row }] });
  render(<VoucherEntry company={company} currency="INR" initialKind="RECEIPT" canCreate />);
  fireEvent.click(screen.getByRole('button', { name: 'Load voucher types' }));
  await screen.findByText('Voucher type ownership and kind could not be verified.');
  expect(screen.queryByRole('option', { name: 'Wrong type' })).not.toBeInTheDocument();
});
it.each([{}, { ...metadata, configuration: { ...metadata.configuration, kind: 'PAYMENT' } }])('refuses incomplete or wrong-kind entry metadata safely', async bad => {
  api.mockImplementation(async (_service, _method, path) => (path.includes('/field-set') ? bad : { items: [{ id: type, company_id: company, kind: 'RECEIPT', name: 'Ordinary receipt' }] }) as never);
  await load();
  await screen.findByText('The selected type does not match this voucher entry.');
  expect(screen.queryByRole('button', { name: 'Save draft' })).not.toBeInTheDocument();
});
it('freezes an uncertain money save and recovers the same body and idempotency key', async () => {
  vi.mocked(serviceCall).mockRejectedValueOnce({ status: 503, message: 'Connection interrupted' }).mockResolvedValueOnce({ id: id(8), company_id: company });
  await load();
  fireEvent.click(await screen.findByRole('button', { name: 'Prepare exact money capture' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByRole('button', { name: 'Retry the same save' });
  expect(screen.getByLabelText('Document date')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Prepare exact money capture' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Retry the same save' }));
  await screen.findByText('Saved workflow');
  const calls = vi.mocked(serviceCall).mock.calls;
  expect(calls[1]?.[1]).toEqual(calls[0]?.[1]);
  expect(calls[0]?.[1].body).toMatchObject({ financial: { accounts: [{ amount: '42.1234', source_version: 2 }] }, posting_date: '2026-10-30' });
  expect(calls[0]?.[1].key).toBeTruthy();
});
it('keeps a refused save editable', async () => {
  vi.mocked(serviceCall).mockRejectedValueOnce({ status: 422, message: 'Account entries must balance' });
  await load();
  fireEvent.click(await screen.findByRole('button', { name: 'Prepare exact money capture' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByText('Account entries must balance');
  await waitFor(() => expect(screen.getByLabelText('Document date')).toBeEnabled());
});
