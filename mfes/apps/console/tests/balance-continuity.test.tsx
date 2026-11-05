import { beforeAll, afterAll } from 'vitest';
import { configure, getConfig } from '@testing-library/react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { BalanceContinuityWorkspace, CompanyBalanceContinuity } from '../app/components/CompanyBalanceContinuity';
import { productFieldRequest } from '../app/lib/product-fields';
import { companyCall, openCompany } from '../app/lib/company-api';

// Allow asynchronous UI effects to settle while local services share the runner's CPU.
const previousAsyncTimeout = getConfig().asyncUtilTimeout;
beforeAll(() => configure({ asyncUtilTimeout: 10000 }));
afterAll(() => configure({ asyncUtilTimeout: previousAsyncTimeout }));

vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn(), openCompany: vi.fn(), companyFailure: (value: { message?: string }) => ({ message: value?.message ?? 'Unavailable' }) }));
const COMPANY = '01990000-0000-7000-8000-000000000001', YEAR = '01990000-0000-7000-8000-000000000002';
const year = { id: YEAR, company_id: COMPANY, row_version: 1, code: 'FY2027-2028', start_date: '2027-04-01', end_date: '2028-03-31', created_at: '2026-10-26T00:00:00Z', updated_at: '2026-10-26T00:00:00Z' };
const display = { base_currency: 'EUR', amount_precision: 2, quantity_precision: 3, rounding_mode: 'half_even', date_format: 'dd.MM.yyyy', datetime_format: 'dd.MM.yyyy HH:mm', digit_grouping: 'western', currency_display: 'code', currency_symbol_position: 'suffix', decimal_separator: ',', thousands_separator: '.', negative_format: 'parentheses', timezone: 'Europe/Berlin', locale: 'de-DE' };
const definition = { definition: { code: 'BALANCE_CONTINUITY', version: 4, title: 'Balance continuity', views: [{ key: 'default', title: 'Balances', columns: [{ key: 'account_code', title: 'Account code', kind: 'TEXT' }] }] }, run_enabled: true, export_limits: [{ format: 'CSV', max_rows: 5000, max_cells: 200000 }] };
const job = { id: 'review', code: 'BALANCE_CONTINUITY', generation_id: 'snapshot', title: 'Balance continuity', status: 'COMPLETE', display, completed_rows: 3, views: definition.definition.views, parameters: { date_from: year.start_date, date_to: year.end_date } };
const control = { ordinal: 1, data: { row_kind: 'CONTINUITY_CONTROL', next_year_id: YEAR, next_opening_date: year.start_date, previous_closing_date: '2027-03-31', previous_year_code: 'FY2026-2027', next_year_code: year.code, reconciled: true, difference: '0.0000', account_count: 1, bill_count: 1, advance_count: 0 }, drilldowns: [] };
const account = { ordinal: 2, data: { row_kind: 'ACCOUNT_CONTINUITY', account_code: 'CASH', account_name: 'Cash account', currency: 'EUR', previous_closing: '1234.5000', next_opening: '1234.5000', difference: '0.0000', reconciled: true }, drilldowns: [{ key: 'account_entries', title: 'View account entries', token: 'signed-account', method: 'POST' }, { key: 'row_detail', title: 'View retained row detail', token: 'signed-detail', method: 'GET' }] };
const api = vi.mocked(productFieldRequest);
beforeEach(() => {
  vi.clearAllMocks(); api.mockImplementation(async (_service, method, path) => {
    if (path.endsWith('/report-definitions')) return { items: [definition] };
    if (path.includes('/report-generations')) return { items: [{ id: 'snapshot', status: 'READY', applied_sequence: 20 }] };
    if (path.endsWith('/queries')) return { ...job, id: 'filtered', status: 'QUEUED' };
    if (path.endsWith('/drilldowns')) return { ...job, id: 'child', code: 'ACCOUNT_LEDGER', status: 'QUEUED', title: 'Cash ledger', views: [{ key: 'default', columns: [{ key: 'number', title: 'Number', kind: 'TEXT' }] }] };
    if (path.endsWith('/exports')) return { ...job, kind: 'EXPORT', id: 'export', status: 'QUEUED' };
    if (path.includes('/report-exports/')) return { ...job, kind: 'EXPORT', id: 'export', status: 'COMPLETE' };
    if (path.includes('/rows/2?')) return account;
    if (path.includes('/rows')) return { items: path.includes('filtered') ? [account] : path.includes('cursor') ? [{ ...account, ordinal: 52 }] : [control, account], page: { next_cursor: path.includes('cursor') ? null : 'next' } };
    if (path.includes('/child')) return { ...job, id: 'child', code: 'ACCOUNT_LEDGER', title: 'Cash ledger', views: [{ key: 'default', columns: [{ key: 'number', title: 'Number', kind: 'TEXT' }] }] };
    if (path.includes('/filtered')) return { ...job, id: 'filtered' };
    return method === 'POST' ? { ...job, status: 'QUEUED' } : job;
  });
  vi.mocked(openCompany).mockResolvedValue(null);
});
function view(permissions = ['report.read', 'report.export']) { return render(<BalanceContinuityWorkspace company={COMPANY} name="Acme" year={year} permissions={permissions} />); }
async function review() { view(); await screen.findByText('Review balances'); fireEvent.click(screen.getByText('Review balances')); await screen.findByText('Review: queued'); fireEvent.click(screen.getByText('Refresh review')); await screen.findByText(/Previous closing and next opening match/); }
it('requests the exact year, renders verified differences using frozen formatting, and explicitly selects the year', async () => {
  await review(); expect(screen.getAllByText('1.234,50')).toHaveLength(2);
  expect(api.mock.calls.find(call => call[1] === 'POST')?.[3]).toMatchObject({ code: 'BALANCE_CONTINUITY', generation_id: 'snapshot', parameters: { date_from: '2027-04-01', date_to: '2028-03-31' } });
  expect(openCompany).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('Use this year'));
  await waitFor(() => expect(openCompany).toHaveBeenCalledWith(COMPANY, YEAR));
  expect(screen.getByRole('link', { name: /Back to financial year/i })).toHaveAttribute('href', `/companies/${COMPANY}/years/${YEAR}`);
});
it('searches the retained result without changing its source snapshot', async () => {
  await review(); fireEvent.change(screen.getByRole('searchbox', { name: 'Search accounts or references' }), { target: { value: 'CASH' } });
  fireEvent.click(screen.getByText('Apply filters')); await screen.findByText('Review: queued');
  expect(api.mock.calls.find(call => call[2].endsWith('/queries'))?.[3]).toMatchObject({ q: 'CASH', sort: 'ordinal' });
  fireEvent.click(screen.getByText('Refresh review')); await screen.findByText(/Filtered rows are shown/);
  fireEvent.click(screen.getByText('Back to complete review')); await screen.findByText(/Previous closing and next opening match/);
});
it('uses signed kebab actions for record detail and ledger drilldowns', async () => {
  await review(); fireEvent.click(screen.getByRole('button', { name: 'Actions for Cash account' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'View retained row detail' })); await screen.findByText('Record details');
  expect(api.mock.calls.some(call => call[1] === 'GET' && call[2].includes('token=signed-detail'))).toBe(true);
  fireEvent.click(screen.getByText('Close details')); fireEvent.click(screen.getByRole('button', { name: 'Actions for Cash account' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'View account entries' })); await screen.findByText('Cash ledger');
  expect(api.mock.calls.find(call => call[2].endsWith('/drilldowns'))?.[3]).toEqual({ token: 'signed-account' });
});
it('exports a verified review and provides its scoped download link', async () => {
  await review(); fireEvent.click(screen.getByText('Export CSV')); await screen.findByText('Export: queued');
  fireEvent.click(screen.getByText('Refresh export')); expect(await screen.findByRole('link', { name: 'Download export' })).toHaveAttribute('href', `/api/report-download?company=${COMPANY}&export=export`);
});
it('retains the same request identity after a network failure', async () => {
  const original = api.getMockImplementation()!; let attempts = 0;
  api.mockImplementation((...args) => args[1] === 'POST' && args[2].endsWith('/report-runs') && attempts++ === 0 ? Promise.reject(new Error('Connection unavailable')) : original(...args));
  view(); await screen.findByText('Review balances'); fireEvent.click(screen.getByText('Review balances')); await screen.findByRole('alert');
  fireEvent.click(screen.getByText('Review balances')); await screen.findByText('Review: queued');
  const calls = api.mock.calls.filter(call => call[1] === 'POST'); expect(calls[0][4]).toBe(calls[1][4]);
});
it('shows differences and never claims that they reconcile', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation((...args) => args[2].includes('/rows') ? Promise.resolve({ items: [{ ...control, data: { ...control.data, reconciled: false, difference: '100.0000' } }, { ...account, data: { ...account.data, reconciled: false, difference: '100.0000' } }], page: { next_cursor: null } }) : original(...args));
  view(); await screen.findByText('Review balances'); fireEvent.click(screen.getByText('Review balances')); await screen.findByText('Review: queued');
  fireEvent.click(screen.getByText('Refresh review')); expect(await screen.findByText(/Differences require accounting review/)).toBeVisible();
  expect(screen.queryByText(/Previous closing and next opening match/)).not.toBeInTheDocument();
});
it('hides exports without permission and respects disabled report admission', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation((...args) => args[2].endsWith('/report-definitions') ? Promise.resolve({ items: [{ ...definition, run_enabled: false }] }) : original(...args));
  view(['report.read']); await screen.findByText(/New report runs are not enabled/);
  expect(screen.getByText('Review balances')).toBeDisabled(); expect(screen.queryByText('Export CSV')).not.toBeInTheDocument();
});
it('refuses a foreign year response before loading report data', async () => {
  vi.mocked(companyCall).mockResolvedValue({ ...year, company_id: 'foreign' } as never);
  render(<CompanyBalanceContinuity company={COMPANY} yearId={YEAR} name="Acme" permissions={['report.read']} />);
  expect(await screen.findByText(/financial year is unavailable for this company/)).toBeVisible(); expect(api).not.toHaveBeenCalled();
});
it('keeps the completed review labelled with its original source after changing the next source', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation((...args) => args[2].includes('/report-generations') ? Promise.resolve({ items: [{ id: 'snapshot', status: 'READY', applied_sequence: 20 }, { id: 'later', status: 'READY', applied_sequence: 30 }], page: { next_cursor: null } }) : original(...args));
  await review(); fireEvent.change(screen.getByLabelText('Source snapshot'), { target: { value: 'later' } });
  expect(screen.getByText(/Result source: verified snapshot · sequence 20/)).toBeVisible();
});
it('uses an informational message for a requested source refresh', async () => {
  view(['report.read', 'report.definition.manage']); await screen.findByText('Request source refresh');
  fireEvent.click(screen.getByText('Request source refresh')); await screen.findByText(/Source refresh requested/);
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
it('disables exports when their cell bound is exceeded', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation((...args) => args[2].endsWith('/report-definitions') ? Promise.resolve({ items: [{ ...definition, export_limits: [{ format: 'CSV', max_rows: 5000, max_cells: 1 }] }] }) : args[2].includes('/report-runs/') && !args[2].includes('/rows') ? Promise.resolve({ ...job, views: [{ key: 'default', columns: [{ key: 'amount', kind: 'MONEY' }] }] }) : original(...args));
  await review(); expect(screen.getByText('Export CSV')).toBeDisabled();
});
it('can reach an older verified snapshot through bounded source pagination', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation((...args) => args[2].includes('/report-generations') ? Promise.resolve(args[2].includes('cursor=older') ? { items: [{ id: 'older-source', status: 'READY', applied_sequence: 10 }], page: { next_cursor: null } } : { items: [{ id: 'snapshot', status: 'READY', applied_sequence: 20 }], page: { next_cursor: 'older' } }) : original(...args));
  view(); fireEvent.click(await screen.findByText('Load older snapshots'));
  expect(await screen.findByRole('option', { name: 'Verified snapshot · sequence 10' })).toBeVisible();
  expect(api.mock.calls.some(call => call[2].includes('limit=50&cursor=older'))).toBe(true);
});
it('guards a delayed page refresh and clears old rows when a new review is selected', async () => {
  await review(); const original = api.getMockImplementation()!;
  let resolveRows!: (value: unknown) => void;
  api.mockImplementation((...args) => args[2].includes('/review/rows') ? new Promise(resolve => { resolveRows = resolve; }) : args[1] === 'POST' && args[2].endsWith('/report-runs') ? Promise.resolve({ ...job, id: 'new-review', status: 'QUEUED' }) : original(...args));
  fireEvent.click(screen.getByText('Refresh review'));
  await waitFor(() => expect(resolveRows).toBeTypeOf('function'));
  // The action guard lets the first refresh finish before another command starts.
  resolveRows({ items: [control, account], page: { next_cursor: null } });
  await waitFor(() => expect(screen.getByText('Create new review')).toBeEnabled());
  fireEvent.click(screen.getByText('Create new review')); await screen.findByText('Review: queued');
  expect(screen.queryByText('Cash account')).not.toBeInTheDocument();
});
