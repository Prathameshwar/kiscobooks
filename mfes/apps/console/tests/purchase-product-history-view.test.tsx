import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PurchaseProductHistory } from '../app/components/PurchaseProductHistory';
import { serviceCall } from '../app/lib/service-call';

vi.mock('../app/lib/service-call', () => ({ serviceCall: vi.fn() }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), supplier = id(2), product = id(3), voucher = id(4), line = id(5), discount = id(6), otherSupplier = id(8), otherVoucher = id(9);
const accepted = 'a'.repeat(64);

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/vouchers?')
    ? { items: [
      ...(request.path.includes('party_id=') ? [] : [{ id: otherVoucher, company_id: company, kind: 'PURCHASE', status: 'POSTED', document_date: '2026-11-05', ref_number: 'SUP-29', currency: 'INR', amount: '210.0000' }]),
      { id: voucher, company_id: company, kind: 'PURCHASE', status: 'POSTED', document_date: '2026-11-04', ref_number: 'SUP-28', currency: 'INR', amount: '210.0000' },
    ], page: { next_cursor: null } } as never
    : request.service === 'accounting'
      ? { id: otherSupplier, company_id: company, name: 'Other Supplier' } as never
    : request.path.endsWith('/invoice-preview')
      ? { calculation_hash: accepted, currency: 'INR', lines: [{ key: line, payable: '210.0000', taxes: [{ amount: '20.0000', supplier_charged: true }] }], allocations: [{ component_key: discount, line_key: line, purpose: 'COMMERCIAL', amount: '-10.0000' }] } as never
      : { id: request.path.includes(otherVoucher) ? otherVoucher : voucher, company_id: company, kind: 'PURCHASE', document_date: request.path.includes(otherVoucher) ? '2026-11-05' : '2026-11-04', currency: 'INR', row_version: 2,
        parties: [{ role: 'SUPPLIER', party_id: request.path.includes(otherVoucher) ? otherSupplier : supplier }], lines: [{ line_key: line, item: { item_id: product, billed_quantity: '2.0000' } }],
        invoice: { accepted_calculation_hash: accepted, components: [{ component_key: discount, purpose: 'DISCOUNT' }], supplies: [{ line_key: line, item_line_key: line, supply_kind: 'GOODS', unit_price: '100.0000' }] } } as never);
});

it('reads only after opening and presents the invoice and product figures in aligned fields', async () => {
  const user = userEvent.setup();
  render(<PurchaseProductHistory company={company} supplier={supplier} product={product} name="Paper boxes" />);
  expect(serviceCall).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Purchase history for Paper boxes' }));
  const dialog = await screen.findByRole('dialog', { name: 'Paper boxes · purchase history' });
  expect(within(dialog).getByRole('tab', { name: 'Current supplier' })).toHaveAttribute('aria-selected', 'true');
  expect(within(dialog).getByRole('tab', { name: 'All suppliers' })).toHaveAttribute('aria-selected', 'false');
  expect(await within(dialog).findByText('SUP-28')).toBeInTheDocument();
  await waitFor(() => expect(within(dialog).getByText(/210\.00/)).toBeInTheDocument());
  expect(within(dialog).getByText('2.0000')).toBeInTheDocument();
  expect(within(dialog).getByText(/100\.0000 INR/)).toBeInTheDocument();
  for (const label of ['Invoice date', 'Quantity', 'Price', 'Discount', 'Tax', 'Amount']) expect(within(dialog).getByText(label)).toBeInTheDocument();
  expect(serviceCall).toHaveBeenCalledTimes(3);
  await user.click(within(dialog).getByRole('tab', { name: 'All suppliers' }));
  expect(within(dialog).getByRole('tab', { name: 'All suppliers' })).toHaveAttribute('aria-selected', 'true');
  await waitFor(() => expect(within(dialog).getByText('Other Supplier')).toBeInTheDocument());
  expect(within(dialog).getAllByText(/SUP-2[89]/).map(node => node.textContent)).toEqual(['SUP-29', 'SUP-28']);
  const allQuery = vi.mocked(serviceCall).mock.calls.find(([, request]) => request.path.includes('/vouchers?') && !request.path.includes('party_id='));
  expect(allQuery?.[1].path).toContain(`item_id=${product}`);
  expect(vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.service === 'accounting')).toHaveLength(1);
  await user.click(within(dialog).getAllByRole('button', { name: 'Close' }).at(-1)!);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});

it('opens all suppliers when the product is selected before a supplier', async () => {
  const user = userEvent.setup();
  render(<PurchaseProductHistory company={company} supplier="" product={product} name="Paper boxes" />);
  await user.click(screen.getByRole('button', { name: 'Purchase history for Paper boxes' }));
  const dialog = await screen.findByRole('dialog', { name: 'Paper boxes · purchase history' });
  expect(within(dialog).getByRole('tab', { name: 'All suppliers' })).toHaveAttribute('aria-selected', 'true');
  await user.click(within(dialog).getByRole('tab', { name: 'Current supplier' }));
  expect(await within(dialog).findByText('Choose a supplier')).toBeInTheDocument();
  expect(vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.path.includes('party_id='))).toHaveLength(0);
});
