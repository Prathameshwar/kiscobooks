import { act, fireEvent, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CompanyReadiness } from '../app/components/CompanyReadiness';
import { renderWithProviders } from './helpers';
import { reload } from '../app/lib/navigate';
const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/company-api', async original => ({ ...await original<object>(), companyCall: call }));
vi.mock('../app/lib/navigate', () => ({ reload: vi.fn() }));
const company = '01990000-0000-7000-8000-000000000001', yearId = '01990000-0000-7000-8000-000000000002';
const year = { id: yearId, code: '2026-27', startDate: '2026-04-01', endDate: '2027-03-31', current: true, open: true };
const permissions = ['company.read', 'period.read', 'accounting.finance.read', 'ledger.read'];
beforeEach(() => {
  vi.mocked(reload).mockClear();
  call.mockReset(); call.mockImplementation(async (_service, path) => {
    if (path.endsWith('/setup-readiness')) return { company_id: company, company_status: 'active', first_posted_at: null, frozen_company_fields: [], features: [] };
    if (path.endsWith('/financial-setup')) return { id: 'books', company_id: company, base_currency: 'INR', books_begin_date: '2026-04-01', first_posted_at: null };
    if (path.endsWith('/readiness')) return { fiscal_year_id: yearId, ready_for_posting: false, blockers: ['OPENING_NOT_FINALIZED'], periods: [{ id: 'period', code: 'Apr', status: 'FUTURE' }] };
    return { id: company, display_name: 'Company A', base_currency: 'INR', books_begin_date: '2026-04-01', default_tax_system: 'gst_in', status: 'active' };
  });
});
async function mount(overrides: Partial<React.ComponentProps<typeof CompanyReadiness>> = {}) {
  await act(async () => { await renderWithProviders(<CompanyReadiness company={company} name="Company A" permissions={permissions} year={year} fiscalNote={null} {...overrides} />); });
}
it('refreshes the server financial-year context when resumed setup completes', async () => {
  let resumed = false;
  call.mockImplementation(async (_service, path) => {
    if (path.endsWith('/setup/retry')) { resumed = true; return {}; }
    if (path.endsWith('/setup')) return { company_id: company, status: resumed ? 'COMPLETE' : 'NEEDS_ACTION', steps: [] };
    throw { status: 404 };
  });
  await mount({ permissions: ['company.read', 'company.update'], year: null });
  expect(reload).not.toHaveBeenCalled();
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Complete remaining setup' })));
  expect(reload).toHaveBeenCalledOnce();
});
it('shows authoritative setup facts and opening/period blockers without claiming global readiness', async () => {
  await mount();
  expect(screen.getByText('Opening balances have not been finalised.')).toBeVisible();
  expect(screen.getByText('No period in this year is open.')).toBeVisible();
  expect(screen.getByText(/do not authorise posting/)).toBeVisible();
  expect(screen.queryByText('Year prerequisites satisfied')).not.toBeInTheDocument();
  expect(call.mock.calls.every(args => args[1].startsWith('/v1/companies/' + company))).toBe(true);
  expect(call.mock.calls.every(args => !args[2]?.method || args[2].method === 'GET')).toBe(true);
});
it('does not fetch setup facts without their read permissions', async () => {
  await mount({ permissions: [], year: null });
  expect(call).not.toHaveBeenCalled();
  expect(screen.getAllByText(/additional read access/)).toHaveLength(3);
});
it('does not borrow finance/ledger authority from a calendar read grant', async () => {
  await mount({ permissions: ['period.read'] }); expect(call).not.toHaveBeenCalled();
});
it('marks missing financial setup as incomplete and retains a manual retry', async () => {
  call.mockRejectedValue({ status: 404, message: 'not found' });
  await mount({ permissions: ['accounting.finance.read'], year: null });
  expect(screen.getByText(/Accounting books have not been initialised/)).toBeVisible();
  const count = call.mock.calls.length;
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Refresh accounting books' })));
  expect(call.mock.calls.length).toBe(count + 1);
});
it.each([401, 403, 500])('does not interpret error %s as complete setup', async status => {
  call.mockRejectedValue({ status, message: 'Unavailable' });
  await mount(); expect(screen.queryByText('Year prerequisites satisfied')).not.toBeInTheDocument();
  expect(screen.getAllByText(status === 401 ? /session needs to be refreshed/ : status === 403 ? /field policy does not permit/ : /check is unavailable/).length).toBeGreaterThan(0);
});
it('rejects identity facts for a different company', async () => {
  call.mockResolvedValue({ id: yearId }); await mount({ permissions: ['company.read'], year: null });
  expect(screen.getByText('The company response does not match the current workspace.')).toBeVisible();
});
it('does not display accounting facts returned for a different company', async () => {
  call.mockResolvedValue({ id: 'books', company_id: yearId, base_currency: 'SECRET' });
  await mount({ permissions: ['accounting.finance.read'], year: null });
  expect(screen.queryByText('SECRET')).not.toBeInTheDocument();
  expect(screen.getByText('The accounting response does not match the current workspace.')).toBeVisible();
});
it('keeps redacted accounting fields unknown instead of reporting no first posting', async () => {
  call.mockResolvedValue({ id: 'books' });
  await mount({ permissions: ['accounting.finance.read'], year: null });
  expect(screen.queryByText('None recorded')).not.toBeInTheDocument();
  expect(screen.getAllByText('Not available to this check')).toHaveLength(3);
});
it('rejects a readiness result for a different financial year', async () => {
  call.mockResolvedValue({ fiscal_year_id: company, ready_for_posting: true, blockers: [], periods: [] });
  await mount({ permissions: ['period.read', 'accounting.finance.read', 'ledger.read'] });
  expect(screen.getByText('The readiness response does not match the selected financial year.')).toBeVisible();
  expect(screen.queryByText('Year prerequisites satisfied')).not.toBeInTheDocument();
});
it('aborts and ignores a late setup response after the company changes', async () => {
  let resolve!: (data: unknown) => void; let previous: AbortSignal | undefined;
  call.mockImplementation((_service, path, options) => {
    if (path === '/v1/companies/' + company) { previous = options.signal; return new Promise(done => { resolve = done; }); }
    if (path.endsWith('/setup-readiness')) return Promise.resolve({ company_id: path.includes(yearId) ? yearId : company, company_status: 'active', first_posted_at: null, frozen_company_fields: [], features: [] });
    return Promise.resolve({ id: yearId, display_name: 'Company B' });
  });
  let view!: Awaited<ReturnType<typeof renderWithProviders>>;
  await act(async () => { view = await renderWithProviders(<CompanyReadiness company={company} name="Company A" permissions={['company.read']} year={null} fiscalNote={null} />); });
  await act(async () => { view.rerender(<CompanyReadiness company={yearId} name="Company B" permissions={['company.read']} year={null} fiscalNote={null} />); });
  expect(previous?.aborted).toBe(true);
  await act(async () => resolve({ id: company, display_name: 'Late company A' }));
  expect(screen.queryByText('Late company A')).not.toBeInTheDocument(); expect(screen.getByText('Company B', { selector: 'dd' })).toBeVisible();
});
it('shows frozen settings and feature prerequisites without offering a mutation', async () => {
  call.mockResolvedValue({ company_id: company, company_status: 'active', first_posted_at: '2026-04-01T00:00:00Z', frozen_company_fields: ['base_currency'],
    features: [{ feature_key: 'expiry_tracking', state: 'INCONSISTENT', missing_prerequisites: ['batch_tracking'], tax_system_supported: false }] });
  await mount({ permissions: ['company.read'], year: null });
  expect(screen.getByText(/Protected settings are frozen/)).toBeVisible();
  expect(screen.getByText(/expiry tracking: inconsistent.*missing batch_tracking.*incompatible tax system/)).toBeVisible();
  expect(call.mock.calls.every(args => !args[2]?.method || args[2].method === 'GET')).toBe(true);
});
it('distinguishes a satisfied year check from authority to post a transaction', async () => {
  call.mockImplementation(async (_service, path) => path.endsWith('/readiness')
    ? { fiscal_year_id: yearId, ready_for_posting: true, blockers: [], periods: [{ code: 'Apr', status: 'OPEN' }] }
    : { company_id: company, id: 'books' });
  await mount({ permissions: ['period.read', 'accounting.finance.read', 'ledger.read'] });
  expect(screen.getByText('Year prerequisites satisfied')).toBeVisible();
  expect(screen.getByText(/do not authorise posting/)).toBeVisible();
  expect(screen.queryByRole('button', { name: /^(post|initialise|close period)\b/i })).not.toBeInTheDocument();
});

it('updates deferred setup evidence after zero opening is explicitly confirmed', async () => {
  let finalized = false;
  const original = call.getMockImplementation()!;
  call.mockImplementation(async (service, path, request) => {
    if (path.endsWith('/setup')) return { company_id: company, status: 'COMPLETE', steps: [{ key: 'opening', status: 'AWAITING_OPENING' }] };
    if (path.endsWith('/confirm-zero-opening')) { finalized = true; return { id: yearId, company_id: company, status: 'FINALIZED', journal_id: null }; }
    if (path.endsWith('/zero-opening-review')) return { company_id: company, expected_setup_version: 1, books_begin_date: '2026-04-01', eligible: !finalized, blocker: finalized ? 'OPENING_ALREADY_FINALIZED' : null };
    if (path.endsWith('/readiness')) return { fiscal_year_id: yearId, ready_for_posting: finalized, blockers: finalized ? [] : ['OPENING_NOT_FINALIZED'], periods: [{ code: 'Apr', status: 'OPEN' }] };
    return original(service, path, request);
  });
  await mount({ permissions: [...permissions, 'opening_balance.initialize_zero'] });
  expect(screen.getByText(/Opening balances still need your decision/)).toBeVisible();
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Review zero opening' })));
  expect(finalized).toBe(false);
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Confirm zero opening' })));
  expect(screen.getByText('Opening balances: Finalised')).toBeVisible();
  expect(screen.getByText('Year prerequisites satisfied')).toBeVisible();
  expect(screen.queryByText(/Opening balances still need your decision/)).toBeNull();
});

it.each(['Refresh accounting books', 'Complete remaining setup'])('preserves an opening draft when %s would refresh it', async action => {
  const original = call.getMockImplementation()!; let resumed = false;
  call.mockImplementation(async (service, path, request) => {
    if (path.endsWith('/setup/retry')) { resumed = true; return {}; }
    if (path.endsWith('/setup')) return { company_id: company, status: resumed ? 'COMPLETE' : 'NEEDS_ACTION', steps: [] };
    if (path.endsWith('/zero-opening-review')) return { company_id: company, expected_setup_version: 1, books_begin_date: '2026-04-01', eligible: true, blocker: null };
    return original(service, path, request);
  });
  await mount({ permissions: [...permissions, 'company.update', 'opening_balance.initialize_zero'] });
  fireEvent.change(screen.getByLabelText('Reason for zero opening'), { target: { value: 'Draft explanation to keep' } });
  await act(async () => fireEvent.click(screen.getByRole('button', { name: action })));
  expect(reload).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Reason for zero opening')).toHaveValue('Draft explanation to keep');
  expect(screen.getByText('Finish the opening-balance review before refreshing setup checks.')).toBeVisible();
});
