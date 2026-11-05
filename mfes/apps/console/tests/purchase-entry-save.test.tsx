vi.mock('../app/lib/navigate', async original => ({ ...await original<typeof import('../app/lib/navigate')>(), goTo: vi.fn() }));
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { VoucherEntry } from '../app/components/VoucherEntry';
import { productFieldRequest } from '../app/lib/product-fields';
import { serviceCall } from '../app/lib/service-call';
import { company, draft, metadata } from './purchase-entry-fixtures';
import type { PurchaseDraft } from '../app/lib/purchase-entry';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<object>(), serviceCall: vi.fn() }));
vi.mock('../app/components/PurchaseInvoice', () => ({ PurchaseInvoice: ({ onChange, disabled }: { onChange: (value: PurchaseDraft) => void; disabled: boolean }) => <button type="button" disabled={disabled} onClick={() => onChange(draft)}>Prepare verified purchase</button> }));
vi.mock('../app/components/VoucherWorkflow', () => ({ VoucherWorkflow: () => <p>Saved purchase workflow</p> }));
vi.mock('@janso/ui', async original => ({ ...await original<typeof import('@janso/ui')>(), Select: ({ label, value, options, disabled, onChange }: { label: string; value: string; options: { value: string; label: string }[]; disabled?: boolean; onChange: (value: string) => void }) => <select aria-label={label} disabled={disabled} value={value} onChange={event => onChange(event.target.value)}><option value="">Choose</option>{options.map(row => <option key={row.value} value={row.value}>{row.label}</option>)}</select> }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(productFieldRequest).mockImplementation(async (_service, _method, path) => (path.includes('/field-set') ? metadata : path.includes('/voucher-classes') ? { items: [] } : { items: [{ id: metadata.configuration.type_revision_id, company_id: company, kind: 'PURCHASE', name: 'Account purchase' }] }) as never);
});
async function load() {
  render(<VoucherEntry company={company} currency="INR" initialKind="PURCHASE" canCreate />);
  fireEvent.click(screen.getByRole('button', { name: 'Load voucher types' }));
  await screen.findByRole('option', { name: 'Account purchase' });
  fireEvent.change(screen.getByLabelText('Voucher type'), { target: { value: metadata.configuration.type_revision_id } });
  fireEvent.change(screen.getByLabelText('Document date'), { target: { value: '2026-10-30' } });
  fireEvent.click(screen.getByRole('button', { name: 'Load entry fields' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Prepare verified purchase' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Prepare verified purchase' }));
}
it('saves exact account invoices with supplier versions and kind-bound discovery', async () => {
  vi.mocked(serviceCall).mockResolvedValue({ id: company, company_id: company });
  await load(); fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(await screen.findByText('Saved purchase workflow')).toBeVisible();
  expect(vi.mocked(productFieldRequest).mock.calls[0]?.[2]).toContain('kind=PURCHASE');
  expect(vi.mocked(serviceCall).mock.calls[0]?.[1].body).toMatchObject({ invoice: { supplies: [{ amount: '42.1234', account_version: 4 }] }, parties: [{ source_version: 2 }], mode: 'ACCOUNTS', posting_date: '2026-10-30' });
});
it('freezes an uncertain purchase and retries the exact body and key', async () => {
  vi.mocked(serviceCall).mockRejectedValueOnce({ status: 503, message: 'Save unconfirmed' }).mockResolvedValueOnce({ id: company, company_id: company });
  await load(); fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByRole('button', { name: 'Retry the same save' });
  expect(screen.getByLabelText('Document date')).toBeDisabled(); expect(screen.getByRole('button', { name: 'Prepare verified purchase' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Retry the same save' }));
  expect(await screen.findByText('Saved purchase workflow')).toBeVisible();
  expect(vi.mocked(serviceCall).mock.calls[1]?.[1]).toEqual(vi.mocked(serviceCall).mock.calls[0]?.[1]);
});
it('leaves a refused invoice editable and does not advance workflow', async () => {
  vi.mocked(serviceCall).mockRejectedValue({ status: 422, message: 'Supplier total differs' });
  await load(); fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(await screen.findByText('Supplier total differs')).toBeVisible();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Prepare verified purchase' })).toBeEnabled());
  expect(screen.queryByText('Saved purchase workflow')).not.toBeInTheDocument();
});
