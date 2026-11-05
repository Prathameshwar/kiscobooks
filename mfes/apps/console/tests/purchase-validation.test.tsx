import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { VoucherEntry } from '../app/components/VoucherEntry';
import { productFieldRequest } from '../app/lib/product-fields';
import { serviceCall } from '../app/lib/service-call';
import { company, metadata } from './purchase-entry-fixtures';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(productFieldRequest).mockImplementation(async (_service, _method, path) => (path.includes('/field-set') ? metadata : path.includes('/voucher-classes') ? { items: [] } : { items: [{ id: metadata.configuration.type_revision_id, company_id: company, kind: 'PURCHASE', name: 'Account purchase' }] }) as never);
});
it('associates missing supplier validation with its control and focuses correction', async () => {
  render(<VoucherEntry company={company} currency="INR" initialKind="PURCHASE" canCreate />);
  fireEvent.click(screen.getByRole('button', { name: 'Load voucher types' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Load voucher types' })).toBeEnabled());
  fireEvent.change(screen.getByRole('combobox', { name: 'Voucher type' }), { target: { value: metadata.configuration.type_revision_id } });
  fireEvent.change(screen.getByLabelText('Document date'), { target: { value: '2026-10-30' } });
  fireEvent.click(screen.getByRole('button', { name: 'Load entry fields' }));
  const save = await screen.findByRole('button', { name: 'Save draft' });
  await waitFor(() => expect(save).toBeEnabled());
  fireEvent.submit(save.closest('form')!);
  const supplier = screen.getByRole('combobox', { name: 'Supplier' });
  await waitFor(() => expect(supplier).toHaveAttribute('aria-invalid', 'true'));
  expect(supplier).toHaveAccessibleDescription('Select a verified active supplier.');
  expect(supplier).toHaveFocus();
  expect(serviceCall).not.toHaveBeenCalled();
});
