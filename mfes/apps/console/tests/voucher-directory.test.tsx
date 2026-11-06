import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { VoucherDirectory } from '../app/components/VoucherDirectory';
import { serviceCall } from '../app/lib/service-call';
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const company = '10000000-0000-7000-8000-000000000001', voucher = '10000000-0000-7000-8000-000000000002', type = '10000000-0000-7000-8000-000000000003';
const page = { items: [{ id: voucher, company_id: company, type_id: type, row_version: 4, status: 'DRAFT', kind: 'RECEIPT', type_code: 'RCP' }], page: { limit: 25, has_more: false, next_cursor: null } };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(serviceCall).mockResolvedValue(page); });
it('discovers current company drafts and offers permitted review/edit routes', async () => {
  render(<VoucherDirectory company={company} permissions={['vouchers.read', 'vouchers.edit', 'vouchers.create']} />);
  await screen.findByText('RCP');
  expect(vi.mocked(serviceCall).mock.calls[0]![1].path).toContain(`/companies/${company}/vouchers?status=DRAFT`);
  fireEvent.click(screen.getByRole('button', { name: /actions/i }));
  expect(screen.getByRole('menuitem', { name: 'Edit draft' })).toHaveAttribute('href', `/vouchers/${voucher}/edit?type_id=${type}`);
  expect(screen.getByRole('menuitem', { name: 'Review voucher' })).toHaveAttribute('href', '/vouchers/' + voucher);
});
describe('a Purchase in the list', () => {
  const purchase = (status: string) => ({ ...page, items: [{ ...page.items[0], kind: 'PURCHASE', profile: 'STANDARD', status }] });
  const revision = '10000000-0000-7000-8000-000000000004';
  it.each([['DRAFT', 'Edit draft'], ['REJECTED', 'Edit rejected bill'], ['SUBMITTED', 'Edit submitted bill'], ['APPROVED', 'Edit approved bill']])('opens a %s bill on its own entry screen', async (status, label) => {
    vi.mocked(serviceCall).mockResolvedValue(purchase(status));
    render(<VoucherDirectory company={company} permissions={['vouchers.read', 'vouchers.edit']} />);
    await screen.findByText('RCP'); fireEvent.click(screen.getByRole('button', { name: /actions/i }));
    expect(screen.getByRole('menuitem', { name: label })).toHaveAttribute('href', '/vouchers/new/purchase?voucher_id=' + voucher + '&type_id=' + type);
  });
  it.each(['POSTED', 'CANCELLED'])('offers no edit for a %s bill', async status => {
    vi.mocked(serviceCall).mockResolvedValue(purchase(status));
    render(<VoucherDirectory company={company} permissions={['vouchers.read', 'vouchers.edit']} />);
    await screen.findByText('RCP'); fireEvent.click(screen.getByRole('button', { name: /actions/i }));
    expect(screen.queryByRole('menuitem', { name: /^Edit/ })).not.toBeInTheDocument();
  });
  it.each(['DRAFT', 'POSTED', 'CANCELLED', 'REVERSED'])('offers Print / PDF for a saved %s Purchase', async status => {
    vi.mocked(serviceCall).mockResolvedValue({ ...purchase(status), items: [{ ...purchase(status).items[0], revision_id: revision }] });
    render(<VoucherDirectory company={company} permissions={['vouchers.read', 'vouchers.artifact.create', 'vouchers.artifact.read', 'accounting.account.read']} />);
    await screen.findByText('RCP'); fireEvent.click(screen.getByRole('button', { name: /actions/i }));
    expect(screen.getByRole('menuitem', { name: 'Print / PDF' })).toHaveAttribute('href', `/vouchers/${voucher}/print?revision=${revision}&version=4`);
  });
  it('hides Print / PDF without the saved revision or one required permission', async () => {
    const permissions = ['vouchers.read', 'vouchers.artifact.create', 'vouchers.artifact.read', 'accounting.account.read'];
    vi.mocked(serviceCall).mockResolvedValue(purchase('POSTED'));
    const view = render(<VoucherDirectory company={company} permissions={permissions} />);
    await screen.findByText('RCP'); fireEvent.click(screen.getByRole('button', { name: /actions/i }));
    expect(screen.queryByRole('menuitem', { name: 'Print / PDF' })).not.toBeInTheDocument();
    view.unmount();
    vi.mocked(serviceCall).mockResolvedValue({ ...purchase('POSTED'), items: [{ ...purchase('POSTED').items[0], revision_id: revision }] });
    render(<VoucherDirectory company={company} permissions={permissions.filter(key => key !== 'vouchers.artifact.read')} />);
    await screen.findByText('RCP'); fireEvent.click(screen.getByRole('button', { name: /actions/i }));
    expect(screen.queryByRole('menuitem', { name: 'Print / PDF' })).not.toBeInTheDocument();
  });
  it('leaves another kind’s rejected voucher to its review page', async () => {
    vi.mocked(serviceCall).mockResolvedValue({ ...page, items: [{ ...page.items[0], status: 'REJECTED' }] });
    render(<VoucherDirectory company={company} permissions={['vouchers.read', 'vouchers.edit']} />);
    await screen.findByText('RCP'); fireEvent.click(screen.getByRole('button', { name: /actions/i }));
    expect(screen.queryByRole('menuitem', { name: /^Edit/ })).not.toBeInTheDocument();
  });
});
it.each(['POSTED', 'SUBMITTED'])('does not offer ordinary draft editing for %s', async status => {
  vi.mocked(serviceCall).mockResolvedValue({ ...page, items: [{ ...page.items[0], status }] });
  render(<VoucherDirectory company={company} permissions={['vouchers.read', 'vouchers.edit']} />);
  await screen.findByText('RCP'); fireEvent.click(screen.getByRole('button', { name: /actions/i }));
  expect(screen.queryByRole('menuitem', { name: 'Edit draft' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Create voucher draft' })).not.toBeInTheDocument();
});
it('refuses a foreign company row and leaves a failed count unavailable', async () => {
  vi.mocked(serviceCall).mockResolvedValue({ ...page, items: [{ ...page.items[0], company_id: type }] });
  render(<VoucherDirectory company={company} permissions={['vouchers.read']} />);
  await screen.findByText('The voucher list could not be verified for this company.');
  expect(screen.queryByText('RCP')).not.toBeInTheDocument();
  expect(screen.queryByText('No vouchers')).not.toBeInTheDocument();
});
it('restarts discovery with native allowlisted status and search filters', async () => {
  render(<VoucherDirectory company={company} permissions={['vouchers.read']} />);
  await screen.findByText('RCP');
  fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'POSTED' } });
  await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.at(-1)![1].path).toContain('status=POSTED'));
});
describe('counterparty name, reference and amount columns', () => {
  const account = '10000000-0000-7000-8000-000000000004';
  const withInvoiceFields = { ...page, items: [{ ...page.items[0], party_account_id: account, ref_number: 'SUP-INV-9', amount: '1234.5600', currency: 'INR' }] };
  it('resolves the counterparty name from its own authorized account read and shows the amount in its own currency', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request: { path: string }) => {
      if (request.path.includes('/accounts/')) return { id: account, company_id: company, name: 'Acme Traders' };
      return withInvoiceFields;
    });
    render(<VoucherDirectory company={company} permissions={['vouchers.read']} />);
    await screen.findByText('SUP-INV-9');
    await screen.findByText('Acme Traders');
    expect(screen.getByText(/1,234\.56/)).toBeInTheDocument();
  });
  it('falls back to the raw account id when the name lookup fails', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request: { path: string }) => {
      if (request.path.includes('/accounts/')) throw new Error('denied');
      return withInvoiceFields;
    });
    render(<VoucherDirectory company={company} permissions={['vouchers.read']} />);
    await screen.findByText(account);
  });
  it('shows an em dash when a row has no counterparty', async () => {
    vi.mocked(serviceCall).mockResolvedValue(page);
    render(<VoucherDirectory company={company} permissions={['vouchers.read']} />);
    await screen.findByText('RCP');
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });
});
