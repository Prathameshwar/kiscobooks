import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { VoucherEntry } from '../app/components/VoucherEntry';
import { VoucherImport } from '../app/components/VoucherImport';
import { VoucherImportLanding } from '../app/components/VoucherImportLanding';
import { productFieldRequest } from '../app/lib/product-fields';
import { IMPORT_KINDS } from '../app/lib/operate-navigation';

vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
const company = '10000000-0000-7000-8000-000000000001', typeId = '10000000-0000-7000-8000-000000000002';
const permissions = ['vouchers.read', 'vouchers.create', 'vouchers.import.read', 'vouchers.import.manage'];
const type = { id: typeId, company_id: company, status: 'ACTIVE', kind: 'PURCHASE', name: 'Local supplier bills' };
beforeEach(() => { vi.mocked(productFieldRequest).mockReset(); vi.mocked(productFieldRequest).mockResolvedValue(type); });
it.each(['entry', 'import'])('loads and selects the exact type for %s', async target => {
  render(target === 'entry' ? <VoucherEntry company={company} currency="INR" canCreate initialKind="PURCHASE" initialTypeId={typeId} /> : <VoucherImport company={company} permissions={permissions} initialKind="PURCHASE" initialTypeId={typeId} />);
  fireEvent.click(screen.getByRole('button', { name: 'Load voucher types' }));
  await screen.findByRole('option', { name: target === 'entry' ? 'Local supplier bills' : 'Local supplier bills (Purchase)' });
  expect(screen.getByLabelText('Voucher type')).toHaveValue(typeId);
  expect(vi.mocked(productFieldRequest)).toHaveBeenCalledWith('vouchers', 'GET', '/v1/companies/' + company + '/voucher-types/' + typeId);
});
it.each(['entry', 'import'])('refuses a foreign exact type for %s', async target => {
  vi.mocked(productFieldRequest).mockResolvedValue({ ...type, company_id: typeId });
  render(target === 'entry' ? <VoucherEntry company={company} currency="INR" canCreate initialKind="PURCHASE" initialTypeId={typeId} /> : <VoucherImport company={company} permissions={permissions} initialKind="PURCHASE" initialTypeId={typeId} />);
  fireEvent.click(screen.getByRole('button', { name: 'Load voucher types' }));
  await screen.findByText('Voucher type ownership and kind could not be verified.');
  expect(screen.queryByRole('option', { name: /Local supplier bills/ })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: target === 'entry' ? 'Load entry fields' : 'Download template' })).toBeDisabled();
});
it('scopes the import type query to its requested kind', async () => {
  vi.mocked(productFieldRequest).mockResolvedValue({ items: [type] });
  render(<VoucherImport company={company} permissions={permissions} initialKind="PURCHASE" />);
  fireEvent.click(screen.getByRole('button', { name: 'Load voucher types' }));
  await screen.findByRole('option', { name: 'Local supplier bills (Purchase)' });
  expect(vi.mocked(productFieldRequest).mock.calls[0][2]).toContain('&kind=PURCHASE');
});
it('explains unsupported import kinds and links to every supported importer', () => {
  render(<VoucherImportLanding company={company} permissions={permissions} kind="PHYSICAL_STOCK" returnTo="/operate/inventory/stock/physical-stock" />);
  expect(screen.getByText(/File import is currently available/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Upload file' })).not.toBeInTheDocument();
  for (const label of Object.values(IMPORT_KINDS)) expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Back to voucher list/ })).toHaveAttribute('href', '/operate/inventory/stock/physical-stock');
});
it('starts the existing importer for a supported kind', () => {
  render(<VoucherImportLanding company={company} permissions={permissions} kind="PURCHASE" />);
  expect(screen.getByRole('heading', { name: 'Import purchase vouchers' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Load voucher types' })).toBeInTheDocument();
});
it('opens general import without preselecting a kind and rejects external back links', () => {
  render(<VoucherImportLanding company={company} permissions={permissions} returnTo="https://evil.invalid" />);
  expect(screen.getByRole('heading', { name: 'Import vouchers', level: 1 })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Back to voucher drafts/ })).toHaveAttribute('href', '/vouchers');
});
it('keeps unsupported import navigation read-only without create access', () => {
  render(<VoucherImportLanding company={company} permissions={['vouchers.import.read']} kind="MEMORANDUM" />);
  expect(screen.queryByRole('link', { name: 'New voucher' })).not.toBeInTheDocument();
});
