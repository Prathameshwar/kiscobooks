import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { PurchaseInvoice } from '../app/components/PurchaseInvoice';
import { productFieldRequest } from '../app/lib/product-fields';
import { buildPurchase, type PurchaseDraft } from '../app/lib/purchase-entry';
import { company, draft, metadata } from './purchase-entry-fixtures';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<object>(), serviceCall: vi.fn() }));
vi.mock('../app/components/VoucherWorkflow', () => ({ VoucherWorkflow: () => <p>Saved purchase workflow</p> }));
vi.mock('@janso/ui', async original => ({ ...await original<typeof import('@janso/ui')>(), SearchSelect: ({ label, disabled, value, onChange }: { label: string; disabled?: boolean; value: string | null; onChange: (value: string | null) => void }) => <input aria-label={label} disabled={disabled} value={value ?? ''} onChange={event => onChange(event.target.value || null)} />, Select: ({ label, value, options, disabled, onChange }: { label: string; value: string; options: { value: string; label: string }[]; disabled?: boolean; onChange: (value: string) => void }) => <select aria-label={label} disabled={disabled} value={value} onChange={event => onChange(event.target.value)}><option value="">Choose</option>{options.map(row => <option key={row.value} value={row.value}>{row.label}</option>)}</select> }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
beforeEach(() => { vi.clearAllMocks(); vi.mocked(productFieldRequest).mockReset(); });
function Form({ disabled = false }: { disabled?: boolean }) {
  const [value, setValue] = useState<PurchaseDraft>(draft), [pending, setPending] = useState(false);
  return <><PurchaseInvoice company={company} currency="INR" metadata={metadata} value={value} onChange={setValue} onPendingChange={setPending} disabled={disabled || pending} /><output data-testid="capture">{JSON.stringify(value)}</output><button disabled={pending} onClick={() => buildPurchase(company, value, '2026-10-30', metadata)}>Review capture</button></>;
}
it('captures exact inputs and supports add/remove while respecting disabled access', () => {
  render(<Form />);
  fireEvent.change(screen.getByLabelText('Purchase amount 1 (INR)'), { target: { value: '999999999999999.1234' } });
  expect(screen.getByTestId('capture')).toHaveTextContent('999999999999999.1234');
  fireEvent.click(screen.getByRole('button', { name: 'Add purchase line' })); expect(screen.getByLabelText('Purchase amount 2 (INR)')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Remove purchase line 2' })); expect(screen.queryByLabelText('Purchase amount 2 (INR)')).not.toBeInTheDocument();
});
/** What Accounting answers when a supplier is chosen: the party, its supplier role, its party accounts in the supplier role, and each account. */
function supplierReads(payables: string[], gate?: Promise<void>) {
  vi.mocked(productFieldRequest).mockImplementation((async (_service: string, _method: string, path: string) => {
    if (path.includes('/party-roles?')) return { items: [{ id: id(12), company_id: company, party_id: id(10), role: 'SUPPLIER' }], page: { next_cursor: null } };
    if (path.includes('/parties/' + id(10))) { await gate; return { id: id(10), company_id: company, row_version: 5, name: 'New supplier', status: 'ACTIVE' }; }
    if (path.includes('/accounts?')) return { items: payables.map(account => ({ id: account, company_id: company, party_id: id(10), party_role: 'SUPPLIER' })), page: { next_cursor: null } };
    if (payables.some(account => path.endsWith('/accounts/' + account))) return { id: path.split('/').at(-1), company_id: company, row_version: 6, name: 'Supplier payable', status: 'ACTIVE', kind: 'PARTY', party_id: id(10), party_role: 'SUPPLIER' };
    throw Error('Unexpected read ' + path);
  }) as never);
}
it('locks capture during supplier verification, clears its prior payable, then takes the one payable account of the supplier without asking for it', async () => {
  let finish!: () => void; supplierReads([id(14)], new Promise<void>(resolve => { finish = resolve; }));
  render(<Form />);
  fireEvent.change(screen.getByLabelText('Supplier'), { target: { value: id(10) } });
  expect(screen.getByRole('button', { name: 'Review capture' })).toBeDisabled(); expect(screen.getByTestId('capture')).toHaveTextContent('"payable":null');
  expect(screen.queryByLabelText(/payable account/i)).not.toBeInTheDocument();
  finish();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Review capture' })).toBeEnabled());
  expect(screen.getByTestId('capture')).toHaveTextContent('New supplier'); expect(screen.getByTestId('capture')).toHaveTextContent('"payable":{"id":"' + id(14) + '"');
  expect(screen.queryByLabelText(/payable account/i)).not.toBeInTheDocument();
  expect(vi.mocked(productFieldRequest).mock.calls.some(call => call[2] === '/v1/companies/' + company + '/accounts?kind=PARTY&party_id=' + id(10) + '&role=SUPPLIER&status=ACTIVE&limit=200')).toBe(true);
});
it('shows a refused reference without accepting stale source facts', async () => {
  vi.mocked(productFieldRequest).mockRejectedValue(new Error('Account access refused'));
  render(<Form />); fireEvent.change(screen.getByLabelText('Expense account 1'), { target: { value: id(11) } });
  expect(await screen.findByText('Account access refused')).toBeVisible(); expect(screen.getByLabelText('Expense account 1')).toHaveValue('');
});
it('requires configuration/field authority and exposes an actionable setup link', () => {
  render(<PurchaseInvoice company={company} currency="INR" metadata={{ ...metadata, native: { properties: { invoice: { readOnly: true } } } }} value={draft} onChange={vi.fn()} onPendingChange={vi.fn()} disabled={false} />);
  expect(screen.getByText(/Missing write access for .*invoice.*Ask a company administrator/)).toBeVisible(); expect(screen.queryByLabelText('Supplier')).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Review voucher types' })).toHaveAttribute('href', '/masters/voucher-types');
});
it('keeps every purchase field disabled for a reader', () => {
  render(<Form disabled />); expect(screen.getByLabelText('Supplier invoice reference')).toBeDisabled(); expect(screen.getByRole('button', { name: 'Add purchase line' })).toBeDisabled();
});
