import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PurchaseSupplierHistory } from '../app/components/PurchaseSupplierHistory';
import { serviceCall } from '../app/lib/service-call';

vi.mock('../app/lib/service-call', () => ({ serviceCall: vi.fn() }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), supplier = id(2), voucher = id(3), line = id(4);
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/vouchers?')
    ? { items: [{ id: voucher, company_id: company, kind: 'PURCHASE', status: 'POSTED', document_date: '2026-11-01', ref_number: 'SUP-42', amount: '700.0000', currency: 'INR' }], page: { next_cursor: null } } as never
    : { id: voucher, company_id: company, kind: 'PURCHASE', parties: [{ role: 'SUPPLIER', party_id: supplier }],
      lines: [{ line_key: line, item: { item_id: id(5), billed_quantity: '3.5000' } }],
      invoice: { supplies: [{ line_key: line, item_line_key: line, supply_kind: 'GOODS', description: 'Paper boxes', amount: '700.0000', unit_price: '200.0000' }] } } as never);
});

it('opens a focused supplier history, drills into products, and returns to the list', async () => {
  const user = userEvent.setup();
  render(<PurchaseSupplierHistory company={company} supplier={supplier} name="Paper Supplier" />);
  expect(serviceCall).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Purchase history for Paper Supplier' }));
  const dialog = await screen.findByRole('dialog', { name: 'Purchases from Paper Supplier' });
  expect(dialog.querySelector('.janso-supplier-purchases')).toBeInTheDocument();
  expect(dialog.querySelector('.janso-purchase-history')).toBeNull();
  expect(await screen.findByRole('button', { name: /Open invoice SUP-42/ })).toBeInTheDocument();
  expect(serviceCall).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole('button', { name: /Open invoice SUP-42/ }));
  expect(await screen.findByRole('heading', { name: 'Products' })).toBeInTheDocument();
  expect(screen.getByText('Supplier invoice')).toBeInTheDocument();
  expect(screen.getByText('Purchase amount')).toBeInTheDocument();
  expect(screen.getByText('Paper boxes')).toBeInTheDocument();
  expect(screen.getByText(/3\.5/)).toBeInTheDocument();
  expect(serviceCall).toHaveBeenCalledTimes(2);
  await user.click(screen.getByRole('button', { name: '← All purchases' }));
  expect(screen.getByRole('button', { name: /Open invoice SUP-42/ })).toBeInTheDocument();
  await user.click(screen.getAllByRole('button', { name: 'Close' }).at(-1)!);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});
