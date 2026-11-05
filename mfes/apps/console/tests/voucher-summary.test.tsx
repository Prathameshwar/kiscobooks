import { act, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { VoucherSummary } from '../app/components/VoucherSummary';
import { productFieldRequest } from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
const id = '10000000-0000-7000-8000-000000000001';
const voucher = { id, company_id: id, row_version: 4, revision_id: id, revision_number: 2, type_revision_id: id, status: 'DRAFT', currency: 'INR', document_date: '2026-10-30', narration: 'Supplier services', financial: { accounts: [{ line_key: id, source_version: 1, account_id: id, amount: '900.1250', currency: 'INR', side: 'DEBIT' as const }] }, parties: [], references: [], lines: [] };
it.each([0,2,4])('uses configured precision %s without changing the captured amount', precision => {
  vi.mocked(productFieldRequest).mockRejectedValue(new Error('Protected current master'));
  render(<DisplayConfigProvider config={{ amountPrecision: precision }}><VoucherSummary company={id} voucher={voucher} /></DisplayConfigProvider>);
  const amount = precision === 0 ? '900' : precision === 2 ? '900.13' : '900.1250';
  expect(screen.getByRole('list', { name: 'Account entries' })).toHaveTextContent(amount + ' INR');
  expect(voucher.financial.accounts[0].amount).toBe('900.1250');
});
it('omits unreadable capture details and never accepts a foreign current-master name', async () => {
  vi.mocked(productFieldRequest).mockResolvedValue({ id, company_id: 'other', name: 'Foreign account' });
  render(<VoucherSummary company={id} voucher={{ ...voucher, invoice: null, lines: null }} />);
  await act(async () => {});
  const summary = screen.getByRole('region', { name: 'Saved voucher summary' });
  expect(within(summary).getByText(/unavailable with your current field access/)).toBeVisible();
  expect(within(summary).queryByText('Foreign account')).not.toBeInTheDocument();
});
it('shows the received and billed quantities of a product line with configured quantity precision', () => {
  vi.mocked(productFieldRequest).mockRejectedValue(new Error('Protected current master'));
  const lines = [{ line_key: id, description: 'Steel rod', item: { item_id: id, actual_quantity: '12.5000', billed_quantity: '10.0000' } }];
  render(<DisplayConfigProvider config={{ quantityPrecision: 2 }}><VoucherSummary company={id} voucher={{ ...voucher, lines }} /></DisplayConfigProvider>);
  const list = screen.getByRole('list', { name: 'Item lines' });
  expect(list).toHaveTextContent('Steel rod');
  expect(list).toHaveTextContent('Quantity 12.50');
  expect(list).toHaveTextContent('Billed 10.00');
});
it('omits a billed quantity the line does not carry', () => {
  vi.mocked(productFieldRequest).mockRejectedValue(new Error('Protected current master'));
  const lines = [{ line_key: id, description: 'Received only', item: { item_id: id, actual_quantity: '3.0000' } }];
  render(<VoucherSummary company={id} voucher={{ ...voucher, lines }} />);
  expect(screen.getByRole('list', { name: 'Item lines' })).not.toHaveTextContent('Billed');
});
