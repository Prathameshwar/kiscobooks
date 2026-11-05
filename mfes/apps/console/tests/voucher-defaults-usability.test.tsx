import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { initialFulfillmentTerms, VoucherFulfillment } from '../app/components/VoucherFulfillment';
import { VoucherTypeDirectory } from '../app/components/VoucherTypeDirectory';
import { loadSalesTypes } from '../app/lib/sales-entry-lookups';
import { salesCall } from '../app/lib/sales-entry-api';
import { serviceCall } from '../app/lib/service-call';
import { allowedVoucherRequest } from '../app/lib/voucher-request-policy';
import type { FieldSet } from '../app/lib/voucher-fields';
import { COMPANY, OTHER, service } from './voucher-type-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...(await original<typeof import('../app/lib/service-call')>()), serviceCall: vi.fn() }));
vi.mock('../app/lib/sales-entry-api', () => ({ salesCall: vi.fn(), companyPath: (company: string, path: string) => `/v1/companies/${company}${path}` }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

const requisition = (purposes: string[]) => ({ configuration: { kind: 'STOCK_JOURNAL', profile: 'REQUISITION', policy: { order: { allowed_purposes: purposes } } }, native: { properties: { fulfillment_terms: {} } } }) as unknown as FieldSet;
const prepared = (company = COMPANY) => ({ company_id: company, catalogue_version: 'company-voucher-defaults-v2', status: 'READY', created_count: 20, updated_count: 0, preserved_count: 0, review_count: 0, features: [] });
beforeEach(() => vi.clearAllMocks());

it('starts Material Requisition with its permitted internal-issue purpose', () => {
  expect(initialFulfillmentTerms(requisition(['INTERNAL_ISSUE']))?.purpose).toBe('INTERNAL_ISSUE');
});

it.each([['PROCURE'], ['INTERNAL_ISSUE'], ['PROCURE', 'INTERNAL_ISSUE']])('shows only permitted requisition purposes: %j', (...purposes) => {
  const metadata = requisition(purposes);
  render(<VoucherFulfillment metadata={metadata} value={initialFulfillmentTerms(metadata)} onChange={vi.fn()} disabled={false} />);
  const select = screen.getByRole('combobox', { name: 'Requisition purpose' });
  expect(within(select).getAllByRole('option').map(option => (option as HTMLOptionElement).value)).toEqual(purposes);
});

it('keeps pro forma types out of the standard Sales invoice workflow', async () => {
  vi.mocked(salesCall).mockResolvedValue({ items: [
    { id: 'account', kind: 'SALES', profile: 'STANDARD' },
    { id: 'product', kind: 'SALES', profile: 'STANDARD' },
    { id: 'mixed', kind: 'SALES', profile: 'STANDARD' },
    { id: 'proforma', kind: 'SALES', profile: 'PRO_FORMA' },
  ] } as never);
  expect((await loadSalesTypes(COMPANY)).map(row => row.id)).toEqual(['account', 'product', 'mixed']);
});

it.each(['GET', 'POST-query', 'POST-extra'])('does not broaden the defaults proxy: %s', variant => {
  const suffix = variant === 'POST-query' ? '?override=1' : variant === 'POST-extra' ? '/extra' : '';
  expect(allowedVoucherRequest(variant === 'GET' ? 'GET' : 'POST', `/v1/companies/${COMPANY}/voucher-type-defaults/bootstrap${suffix}`)).toBe(false);
});
it('allows the scoped defaults command through the normal voucher proxy', () => {
  expect(allowedVoucherRequest('POST', `/v1/companies/${COMPANY}/voucher-type-defaults/bootstrap`)).toBe(true);
});

it('lets an administrator prepare defaults and refreshes the directory', async () => {
  const existing = service();
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.endsWith('/voucher-type-defaults/bootstrap') ? prepared() as never : existing(args[0], args[1]));
  render(<VoucherTypeDirectory company={COMPANY} canManage />);
  await screen.findByRole('row', { name: /Retail sales/ });
  fireEvent.click(screen.getByRole('button', { name: 'Prepare default voucher types' }));
  await screen.findByText(/20 created/);
  const call = vi.mocked(serviceCall).mock.calls.find(([, request]) => request.path.endsWith('/voucher-type-defaults/bootstrap'))!;
  expect(call[1]).toMatchObject({ service: 'vouchers', method: 'POST', body: {} });
  await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.filter(([, request]) => (request.method ?? 'GET') === 'GET').length).toBeGreaterThan(1));
});

it('hides default provisioning from readers', async () => {
  vi.mocked(serviceCall).mockImplementation(service());
  render(<VoucherTypeDirectory company={COMPANY} canManage={false} />);
  await screen.findByRole('row', { name: /Retail sales/ });
  expect(screen.queryByRole('button', { name: 'Prepare default voucher types' })).not.toBeInTheDocument();
});

it('rejects another company result and retries uncertain provisioning with the same key', async () => {
  const existing = service(); let calls = 0;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.endsWith('/voucher-type-defaults/bootstrap') ? prepared(++calls === 1 ? OTHER : COMPANY) as never : existing(args[0], args[1]));
  render(<VoucherTypeDirectory company={COMPANY} canManage />);
  await screen.findByRole('row', { name: /Retail sales/ });
  fireEvent.click(screen.getByRole('button', { name: 'Prepare default voucher types' }));
  await screen.findByText(/could not be verified/);
  fireEvent.click(screen.getByRole('button', { name: 'Retry preparing default types' }));
  await screen.findByText(/20 created/);
  const requests = vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.path.endsWith('/voucher-type-defaults/bootstrap'));
  expect(requests).toHaveLength(2);
  expect(requests[0][1]).toEqual(requests[1][1]);
});
