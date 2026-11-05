import { beforeAll, afterAll } from 'vitest';
import { configure, getConfig } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { DayBookWorkspace } from '../app/components/DayBookWorkspace';
import { productFieldRequest } from '../app/lib/product-fields';
import { DAY_BOOK_CODE, defaultDayBookFilters, filterError, preferencesKey, readDayBookFilters, reportParameters } from '../app/lib/day-book';
import { DEFAULT_DISPLAY_CONFIG, DisplayConfigProvider } from '@janso/ui';
import { allowedVoucherRequest } from '../app/lib/voucher-request-policy';

// Allow asynchronous UI effects to settle while local services share the runner's CPU.
const previousAsyncTimeout = getConfig().asyncUtilTimeout;
beforeAll(() => configure({ asyncUtilTimeout: 10000 }));
afterAll(() => configure({ asyncUtilTimeout: previousAsyncTimeout }));

vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
const company = '01990000-0000-7000-8000-000000000001', generation = '01990000-0000-7000-8000-000000000002', runId = '01990000-0000-7000-8000-000000000003';
const voucher = '01990000-0000-7000-8000-000000000004', exportId = '01990000-0000-7000-8000-000000000005';
const filters = defaultDayBookFilters(DEFAULT_DISPLAY_CONFIG);
const entry = { line_id: 'line1', journal_id: 'journal1', date: filters.date_from, number: 'PUR-0042', account_code: 'PUR', account_name: 'Purchase account', debit: '100.0000', credit: '0.0000', currency: 'INR' };
const row = { id: voucher, voucher_id: voucher, journal_id: 'journal1', date: filters.date_from, number: 'PUR-0042', kind: 'PURCHASE', particulars: 'ABC Traders', narration: 'Equipment purchase', currency: 'INR', debit: '100.0000', credit: '100.0000', status: 'POSTED', journal_count: 1, line_count: 2,
  journals: [{ journal_id: 'journal1', date: filters.date_from, number: 'PUR-0042', currency: 'INR', debit: '100.0000', credit: '100.0000', entries: [entry, { ...entry, line_id: 'line2', account_name: 'ABC Traders', account_code: 'ABC', debit: '0.0000', credit: '100.0000' }] }] };
const summary = { voucher_count: 75, journal_count: 76, line_count: 152, debit: '7500.0000', credit: '7500.0000', currency: 'INR', by_kind: { PURCHASE: { count: 75, debit: '7500.0000', credit: '7500.0000' } }, groups: {} };
const definition = { run_enabled: true, export_limits: ['CSV', 'XLSX', 'PDF'].map(format => ({ format, max_rows: 5000, max_cells: 200000 })) };
const job = (parameters: unknown) => ({ id: runId, generation_id: generation, kind: 'RUN', code: DAY_BOOK_CODE, status: 'COMPLETE', completed_rows: 75, views: [{ key: 'default', columns: [{ key: 'number', kind: 'TEXT' }] }, { key: 'accounting', columns: [{ key: 'account_name', kind: 'TEXT' }] }], created_at: '2026-11-01T10:00:00Z', result: { evidence: { day_book: summary } }, display: null, parameters });
let failure = '', ready = true, empty = false;
beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); window.history.replaceState(null, '', '/books/day-book');
  failure = ''; ready = true; empty = false;
  vi.mocked(productFieldRequest).mockReset();
  vi.mocked(productFieldRequest).mockImplementation(async (_service, method, path, body) => {
    if (failure && method === 'POST' && path.endsWith('/report-runs')) throw new Error(failure);
    if (path.includes('/report-definitions/')) return definition;
    if (path.includes('/report-generations?')) return { items: ready ? [{ id: generation, status: 'READY' }] : [], page: { next_cursor: null } };
    if (path.endsWith('/report-runs')) return job((body as { parameters: unknown }).parameters);
    if (path.includes('/rows?')) return { items: empty ? [] : [{ ordinal: path.includes('cursor=') ? 51 : 1, data: row }], page: { next_cursor: path.includes('cursor=') ? null : 'next-page' } };
    if (path.endsWith('/exports')) return { id: exportId, status: 'COMPLETE' };
    if (path.endsWith('/day-book/query')) return { items: [row], summary: { voucher_count: 1, by_status: { DRAFT: 1 }, by_kind: { PURCHASE: 1 } }, observed_at: '2026-11-01T11:00:00Z', page: { next_cursor: null } };
    throw new Error('Unexpected test request: ' + path);
  });
});
function mount(permissions = ['report.read', 'report.export', 'vouchers.read', 'vouchers.create']) {
  return render(<DisplayConfigProvider config={{ ...DEFAULT_DISPLAY_CONFIG, currency: 'INR', currencySymbol: '₹', amountPrecision: 2 }}><DayBookWorkspace company={company} companyName="Example Traders" actor="actor1" permissions={permissions} /></DisplayConfigProvider>);
}
async function loaded() {
  await waitFor(() => expect(screen.getByLabelText('Report totals')).toHaveTextContent('75'));
  await act(async () => {});
}

it('loads the report directly and shows full-result counts and totals independent of displayed rows', async () => {
  mount(); await loaded();
  expect(screen.getByRole('heading', { name: 'Day Book', level: 1 })).toBeVisible();
  expect(screen.getByLabelText('Report totals')).toHaveTextContent('75');
  expect(screen.getByLabelText('Report totals')).toHaveTextContent('152 accounting lines');
  expect(screen.getByLabelText('Report totals')).toHaveTextContent('7,500.00');
  expect(screen.getByRole('searchbox', { name: 'Search transactions' })).toBeVisible();
  expect(productFieldRequest).toHaveBeenCalledWith('reports', 'POST', expect.stringContaining('/report-runs'), expect.objectContaining({ code: DAY_BOOK_CODE }), expect.any(String), expect.any(AbortSignal));
});
it('expands a voucher into complete balanced entries and preserves the report in its drill-through URL', async () => {
  mount(); await loaded();
  fireEvent.click(screen.getByRole('button', { name: 'Expand PUR-0042' }));
  expect(screen.getByRole('button', { name: 'Collapse PUR-0042' })).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getAllByText('Purchase account').length).toBeGreaterThan(0);
  expect(screen.getAllByText('Journal total · INR').length).toBeGreaterThan(0);
  expect(screen.getAllByRole('link', { name: 'Open voucher →' })[0]).toHaveAttribute('href', expect.stringContaining('returnTo='));
});
it('keeps edited filters pending until Apply and retains rows while a retryable request fails', async () => {
  mount(); await loaded();
  const before = vi.mocked(productFieldRequest).mock.calls.filter(call => call[2].endsWith('/report-runs')).length;
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search transactions' }), { target: { value: 'equipment' } });
  expect(screen.getByText(/Filters changed/)).toBeVisible();
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[2].endsWith('/report-runs'))).toHaveLength(before);
  failure = 'Reports service unavailable';
  fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
  expect(await screen.findByText('Reports service unavailable')).toBeVisible();
  expect(screen.getAllByRole('link', { name: 'PUR-0042' }).length).toBeGreaterThan(0);
  const failed = vi.mocked(productFieldRequest).mock.calls.findLast(call => call[2].endsWith('/report-runs'));
  failure = ''; fireEvent.click(screen.getByRole('button', { name: 'Retry report' }));
  await waitFor(() => expect(screen.queryByText(/Filters changed/)).not.toBeInTheDocument());
  const retried = vi.mocked(productFieldRequest).mock.calls.findLast(call => call[2].endsWith('/report-runs'));
  expect(retried?.[4]).toBe(failed?.[4]);
});
it('validates date and amount ranges before issuing another report', async () => {
  mount(); await loaded();
  fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2027-12-01' } });
  fireEvent.change(screen.getByLabelText('To date'), { target: { value: '2026-01-01' } });
  fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
  expect(await screen.findByText('The start date must be on or before the end date.')).toBeVisible();
});

it('keeps the selected period preset visible and identifies a custom date range', async () => {
  mount(); await loaded();
  expect(screen.getByLabelText('Period preset')).toHaveValue('today');
  fireEvent.change(screen.getByLabelText('Period preset'), { target: { value: 'yesterday' } });
  expect(screen.getByLabelText('Period preset')).toHaveValue('yesterday');
  fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2025-04-01' } });
  expect(screen.getByLabelText('Period preset')).toHaveValue('');
});
it('switches to live document activity with status counts and no invented accounting totals', async () => {
  mount(); await loaded();
  fireEvent.click(screen.getByRole('button', { name: 'All vouchers' }));
  expect(await screen.findByText(/No accounting totals/)).toBeVisible();
  expect(screen.getByLabelText('Report totals')).toHaveTextContent('Draft');
  expect(screen.getByLabelText('Report totals')).not.toHaveTextContent('Total debit');
  expect(screen.getByLabelText('Document status')).toBeVisible();
});
it('hides create, export and live-document navigation without the required permissions', async () => {
  mount(['report.read']); await loaded();
  expect(screen.queryByRole('button', { name: '+ New voucher' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Export' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'All vouchers' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'PUR-0042' })).not.toBeInTheDocument();
});
it('pages through frozen rows without recalculating totals and returns to the previous page', async () => {
  mount(); await loaded();
  fireEvent.click(screen.getByRole('button', { name: 'Next' }));
  await screen.findByText('51–51 of 75 vouchers');
  expect(screen.getByLabelText('Report totals')).toHaveTextContent('7,500.00');
  fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
  await screen.findByText('1–1 of 75 vouchers');
});
it('saves company-and-actor scoped preferences and exports the complete report through the private pipeline', async () => {
  mount(); await loaded();
  fireEvent.click(screen.getByRole('button', { name: 'Save view' }));
  const dialog = screen.getByRole('dialog', { name: 'Save this view' });
  fireEvent.change(within(dialog).getByLabelText('View name'), { target: { value: 'Daily purchases' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Save view' }));
  expect(await screen.findByLabelText('Saved view')).toBeVisible();
  const stored = JSON.parse(localStorage.getItem(preferencesKey('actor1', company))!);
  expect(stored.views[0].name).toBe('Daily purchases');
  expect(JSON.stringify(stored)).not.toContain('ABC Traders');
  fireEvent.click(screen.getByRole('button', { name: 'Export' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'CSV spreadsheet' }));
  expect(await screen.findByRole('link', { name: 'Download report' })).toHaveAttribute('href', '/api/report-download?company=' + company + '&export=' + exportId);
});
it('offers recovery when no accounting snapshot exists and still allows live documents', async () => {
  ready = false; mount(['report.read', 'vouchers.read', 'report.definition.manage']);
  expect(await screen.findByRole('button', { name: 'Prepare report data' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'All vouchers' }));
  await screen.findByText(/No accounting totals/);
});
it('opens accessible advanced filtering and retains explicit AND/OR conditions', async () => {
  mount(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'More filters' }));
  const drawer = screen.getByRole('dialog', { name: 'More filters' });
  fireEvent.click(within(drawer).getByRole('button', { name: '+ Add condition' }));
  fireEvent.change(within(drawer).getByLabelText('Condition 1 value'), { target: { value: 'equipment' } });
  fireEvent.change(within(drawer).getByLabelText('Match conditions'), { target: { value: 'ANY' } });
  fireEvent.click(within(drawer).getByRole('button', { name: 'Apply filters' }));
  await waitFor(() => expect(vi.mocked(productFieldRequest).mock.calls.some(call => (call[3] as { parameters?: { match?: string } })?.parameters?.match === 'ANY')).toBe(true));
});
it('rejects malformed URL filters and uses exact decimals for range validation', () => {
  expect(readDayBookFilters({ ...filters, scope: 'ADMIN' }, filters)).toBeNull();
  expect(readDayBookFilters({ ...filters, conditions: [{ field: 'secret', operator: 'equals', value: 'x' }] }, filters)).toBeNull();
  expect(filterError({ ...filters, amount_min: '999999999999999.0002', amount_max: '999999999999999.0001' })).toMatch(/Minimum/);
  expect(reportParameters({ ...filters, basis: 'BASE', currency: 'USD' })).not.toHaveProperty('currency');
  expect(filterError({ ...filters, status: 'DRAFT' })).toMatch(/All vouchers/);
  expect(filterError({ ...filters, scope: 'ALL', mode: 'ACCOUNTING' })).toMatch(/voucher view/);
  expect(filterError({ ...filters, type_revision_ids: [voucher] })).toMatch(/configured voucher type/);
});

it('labels grouped daily activity separately when one voucher posts on several days', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].endsWith('/report-runs') ? { ...job(reportParameters(filters)), result: { evidence: { day_book: { ...summary, activity_count: 76, groups: { [filters.date_from]: { count: 76, debit: '7500.0000', credit: '7500.0000' } } } } } } : original(...args));
  mount(); await loaded();
  expect(screen.getByText(/^76 voucher entries \u00b7 Debit/)).toBeVisible();
});
it('only permits the exact read-only Day Book proxy routes', () => {
  expect(allowedVoucherRequest('POST', '/v1/companies/' + company + '/day-book/query')).toBe(true);
  expect(allowedVoucherRequest('DELETE', '/v1/companies/' + company + '/day-book/query')).toBe(false);
  expect(allowedVoucherRequest('POST', '/v1/companies/' + company + '/day-book/query?unexpected=true')).toBe(false);
});


it('rejects a retained run whose parameters differ from the URL filters', async () => {
  window.history.replaceState(null, '', '/books/day-book?' + new URLSearchParams({ company, filters: JSON.stringify({ ...filters, q: 'different' }), run: runId }));
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].endsWith('/report-runs/' + runId) ? job(reportParameters(filters)) : original(...args));
  mount();
  expect(await screen.findByText(/saved Day Book report does not match/)).toBeVisible();
  expect(screen.queryByText('7,500.00')).not.toBeInTheDocument();
});


it('restores the exact frozen page after returning from a voucher', async () => {
  const query = new URLSearchParams({ company, filters: JSON.stringify(filters), run: runId, page: '1' });
  window.history.replaceState(null, '', '/books/day-book?' + query);
  sessionStorage.setItem(preferencesKey('actor1', company) + ':position', JSON.stringify({ run: runId, filters: JSON.stringify(filters), position: { index: 1, cursors: [null, 'next-page'] } }));
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].endsWith('/report-runs/' + runId) ? job(reportParameters(filters)) : original(...args));
  mount();
  expect(await screen.findByText('51\u201351 of 75 vouchers')).toBeVisible();
  expect(vi.mocked(productFieldRequest).mock.calls.some(call => call[2].includes('/rows?limit=50&cursor=next-page'))).toBe(true);
  expect(screen.getAllByRole('link', { name: 'PUR-0042' })[0].getAttribute('href')).toContain('page%3D1');
});

it('offers a private PDF preview after preparing a printable report', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].endsWith('/exports') ? { id: exportId, status: 'COMPLETE', parameters: { format: 'PDF' } } : original(...args));
  mount(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }));
  expect(await screen.findByRole('link', { name: 'Open print preview' })).toHaveAttribute('href', '/api/report-download?company=' + company + '&export=' + exportId + '&preview=1');
});

it('removes the previous download when a new export fails', async () => {
  mount(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }));
  await screen.findByRole('link', { name: 'Download report' });
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => { if (args[2].endsWith('/exports')) throw new Error('Export service unavailable'); return original(...args); });
  fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }));
  expect(await screen.findByText('Export service unavailable')).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Download report' })).not.toBeInTheDocument();
});

it('polls a pending run and renders its verified result', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].endsWith('/report-runs') ? { ...job(reportParameters(filters)), status: 'QUEUED' } : args[2].endsWith('/report-runs/' + runId) ? job(reportParameters(filters)) : original(...args));
  mount(); expect(await screen.findByText(/Preparing your Day Book/)).toBeVisible();
  await waitFor(() => expect(screen.getByLabelText('Report totals')).toHaveTextContent('75'), { timeout: 4000 });
});

it('verifies URL-selected voucher types before requesting a posted report', async () => {
  const selected = { ...filters, type_id: voucher, type_label: 'Purchase product bill' };
  window.history.replaceState(null, '', '/books/day-book?' + new URLSearchParams({ company, filters: JSON.stringify(selected) }));
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].endsWith('/revisions') ? { type_id: voucher, revision_ids: [exportId] } : original(...args));
  mount(); await loaded();
  expect(vi.mocked(productFieldRequest).mock.calls.find(call => call[2].endsWith('/report-runs'))?.[3]).toMatchObject({ parameters: { type_revision_ids: [exportId] } });
});

it('exposes the filter disclosure state and stops polling quarantined sources', async () => {
  ready = false;
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].endsWith('/report-generations') ? { id: generation } : args[2].endsWith('/report-generations/' + generation) ? { status: 'QUARANTINED' } : original(...args));
  mount(['report.read', 'report.definition.manage']);
  const disclosure = screen.getByRole('button', { name: 'Filters' });
  expect(disclosure).toHaveAttribute('aria-expanded', 'false'); fireEvent.click(disclosure);
  expect(screen.getByRole('button', { name: 'Hide filters' })).toHaveAttribute('aria-expanded', 'true');
  fireEvent.click(await screen.findByRole('button', { name: 'Prepare report data' }));
  expect(await screen.findByText(/Report data could not be prepared/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Retry report data' })).toBeEnabled();
});

it.each(['Sign in required', 'Access denied', 'Invalid report filters', 'Service unavailable'])('keeps a useful report screen for %s', async message => {
  failure = message; mount();
  expect(await screen.findByText(message)).toBeVisible();
  expect(screen.getByRole('heading', { name: 'Day Book' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Retry report' })).toBeEnabled();
});

it('shows source discovery as loading without claiming the report is ready', () => {
  vi.mocked(productFieldRequest).mockImplementation(() => new Promise(() => {}));
  mount();
  expect(screen.getByRole('status', { name: 'Day Book progress' })).toHaveTextContent('Loading report data');
  expect(screen.getByRole('region', { name: 'Day Book report' })).toHaveAttribute('aria-busy', 'true');
  expect(screen.queryByText('Your Day Book is ready to explore')).not.toBeInTheDocument();
  expect(screen.queryByText('0 vouchers')).not.toBeInTheDocument();
});

it('shows an initial report failure as unavailable instead of an empty or ready report', async () => {
  failure = 'Report request failed'; mount();
  await screen.findByText(failure);
  expect(screen.getByRole('heading', { name: 'Report unavailable' })).toBeVisible();
  expect(screen.queryByText('Your Day Book is ready to explore')).not.toBeInTheDocument();
  expect(screen.queryByText('No transactions found')).not.toBeInTheDocument();
});

it('announces export preparation without marking an empty report as loading again', async () => {
  empty = true;
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  let finish!: (value: unknown) => void;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].endsWith('/exports') ? new Promise(resolve => { finish = resolve; }) : original(...args));
  mount(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }));
  expect(screen.getByRole('status', { name: 'Day Book progress' })).toHaveTextContent('Preparing PDF report');
  expect(screen.getByRole('region', { name: 'Day Book report' })).toHaveAttribute('aria-busy', 'false');
  expect(screen.getByText('No transactions found')).toBeVisible();
  expect(screen.queryByText(/Preparing your Day Book/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Apply' })).toHaveAttribute('aria-busy', 'false');
  await act(async () => finish({ id: exportId, status: 'COMPLETE' }));
  expect(await screen.findByRole('link', { name: 'Download report' })).toBeVisible();
});

it('keeps existing rows visible while paging and retries the failed page without rerunning the report', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  let reject!: (failure: Error) => void;
  let refused = true;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].includes('cursor=next-page') && refused ? new Promise((_resolve, fail) => { reject = fail; }) : original(...args));
  mount(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByRole('status', { name: 'Day Book progress' })).toHaveTextContent('Loading page 2');
  expect(screen.getByRole('status', { name: 'Day Book progress' })).toHaveTextContent('current results remain visible');
  expect(screen.getAllByRole('link', { name: 'PUR-0042' }).length).toBeGreaterThan(0);
  await act(async () => reject(new Error('Page request failed')));
  expect(await screen.findByRole('button', { name: 'Retry page' })).toBeEnabled();
  refused = false; fireEvent.click(screen.getByRole('button', { name: 'Retry page' }));
  await screen.findByText('51\u201351 of 75 vouchers');
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[2].endsWith('/report-runs'))).toHaveLength(1);
});

it('retries the failed export with the same command identity and keeps the report intact', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  let refused = true;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => { if (args[2].endsWith('/exports') && refused) throw new Error('Export temporarily unavailable'); return original(...args); });
  mount(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }));
  const retry = await screen.findByRole('button', { name: 'Retry export' });
  const first = vi.mocked(productFieldRequest).mock.calls.findLast(call => call[2].endsWith('/exports'));
  refused = false; fireEvent.click(retry); await screen.findByRole('link', { name: 'Download report' });
  const second = vi.mocked(productFieldRequest).mock.calls.findLast(call => call[2].endsWith('/exports'));
  expect(second?.[4]).toBe(first?.[4]);
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[2].endsWith('/report-runs'))).toHaveLength(1);
  expect(screen.getByLabelText('Report totals')).toHaveTextContent('7,500.00');
});

it('clears and applies filters from the empty-state recovery action', async () => {
  empty = true;
  window.history.replaceState(null, '', '/books/day-book?' + new URLSearchParams({ company, filters: JSON.stringify({ ...filters, q: 'unmatched' }) }));
  mount(); await loaded();
  fireEvent.click(within(screen.getByRole('region', { name: 'Day Book report' })).getByRole('button', { name: 'Reset filters' }));
  await waitFor(() => expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[2].endsWith('/report-runs'))).toHaveLength(2));
  expect(vi.mocked(productFieldRequest).mock.calls.findLast(call => call[2].endsWith('/report-runs'))?.[3]).toMatchObject({ parameters: { q: '' } });
});

it('keeps unavailable report generation clear and does not submit a disabled run', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].includes('/report-definitions/') ? { ...definition, run_enabled: false } : original(...args));
  mount();
  expect(await screen.findByRole('heading', { name: 'Report unavailable' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[2].endsWith('/report-runs'))).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: 'All vouchers' }));
  await screen.findByText(/No accounting totals/);
  await waitFor(() => expect(screen.getByRole('button', { name: 'All vouchers' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Posted book' }));
  expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[2].endsWith('/report-runs'))).toHaveLength(0);
});

it('keeps active status and currency filters visible when mobile filters are collapsed', async () => {
  window.history.replaceState(null, '', '/books/day-book?' + new URLSearchParams({ company, filters: JSON.stringify({ ...filters, scope: 'ALL', status: 'DRAFT', basis: 'TRANSACTION', currency: 'INR' }) }));
  mount(); await screen.findByText(/No accounting totals/);
  expect(screen.getByRole('button', { name: 'Remove filter Status: Draft' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Remove filter Currency: INR' }));
  await waitFor(() => expect(vi.mocked(productFieldRequest).mock.calls.findLast(call => call[2].endsWith('/day-book/query'))?.[3]).not.toHaveProperty('currency'));
});

it('focuses each added condition and keeps Escape available at the eight-condition limit', async () => {
  mount(); await loaded();
  const opener = screen.getByRole('button', { name: 'More filters' });
  opener.focus(); fireEvent.click(opener);
  const drawer = screen.getByRole('dialog', { name: 'More filters' });
  for (let index = 1; index <= 8; index++) {
    fireEvent.click(within(drawer).getByRole('button', { name: '+ Add condition' }));
    expect(within(drawer).getByLabelText('Condition ' + index + ' value')).toHaveFocus();
  }
  expect(within(drawer).getByRole('button', { name: '+ Add condition' })).toBeDisabled();
  for (let index = 8; index >= 1; index--) {
    fireEvent.click(within(drawer).getByRole('button', { name: 'Remove condition ' + index }));
    expect(index > 1 ? within(drawer).getByLabelText('Condition ' + (index - 1) + ' value') : within(drawer).getByRole('button', { name: '+ Add condition' })).toHaveFocus();
  }
  fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
  expect(screen.queryByRole('dialog', { name: 'More filters' })).not.toBeInTheDocument();
  expect(opener).toHaveFocus();
});

it('keeps PDF, Excel and CSV discoverable when a renderer is not enabled', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].includes('/report-definitions/') ? { ...definition, export_limits: definition.export_limits.filter(item => item.format === 'CSV') } : original(...args));
  mount(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'Export' }));
  expect(screen.getByRole('menuitem', { name: /PDF report/ })).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByRole('menuitem', { name: /Excel workbook/ })).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByRole('menuitem', { name: 'CSV spreadsheet' })).not.toHaveAttribute('aria-disabled', 'true');
  expect(screen.getAllByText(/not enabled/i)).toHaveLength(2);
  expect(screen.getByRole('button', { name: 'Print / PDF' })).toBeDisabled();
});

it('blocks an oversized PDF before submission while retaining Excel and CSV', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].includes('/report-definitions/') ? { ...definition, export_limits: definition.export_limits.map(item => item.format === 'PDF' ? { ...item, max_rows: 74 } : item) } : original(...args));
  mount(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'Export' }));
  expect(screen.getByRole('menuitem', { name: /PDF report/ })).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByText(/supports up to 74 rows/)).toBeVisible();
  expect(screen.getByRole('menuitem', { name: 'Excel workbook' })).not.toHaveAttribute('aria-disabled', 'true');
  fireEvent.click(screen.getByRole('menuitem', { name: /PDF report/ }));
  expect(vi.mocked(productFieldRequest).mock.calls.some(call => call[2].endsWith('/exports'))).toBe(false);
});

it.each(['VOUCHERS', 'ACCOUNTING'] as const)('exports the full %s result in PDF, Excel and CSV through the existing API', async mode => {
  window.history.replaceState(null, '', '/books/day-book?' + new URLSearchParams({ company, filters: JSON.stringify({ ...filters, mode }) }));
  mount(); await loaded();
  for (const [label, format] of [['PDF report', 'PDF'], ['Excel workbook', 'XLSX'], ['CSV spreadsheet', 'CSV']]) {
    fireEvent.click(screen.getByRole('button', { name: 'Export' })); fireEvent.click(screen.getByRole('menuitem', { name: label }));
    expect(await screen.findByRole('link', { name: 'Download report' })).toBeVisible();
    expect(vi.mocked(productFieldRequest).mock.calls.findLast(call => call[2].endsWith('/exports'))?.[3]).toEqual({ format, view: mode === 'ACCOUNTING' ? 'accounting' : 'default', delivery: 'SINGLE' });
    expect(screen.getByLabelText('Report totals')).toHaveTextContent('7,500.00');
  }
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[2].endsWith('/report-runs'))).toHaveLength(1);
});

it('explains how live document activity users can reach PDF, Excel and CSV exports', async () => {
  mount(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'All vouchers' }));
  expect(await screen.findByText(/To export PDF, Excel or CSV, switch to Posted book/)).toBeVisible();
});

it('removes a completed download when export permission is removed', async () => {
  const props = { company, companyName: 'Example Traders', actor: 'actor1' };
  const result = render(<DayBookWorkspace {...props} permissions={['report.read', 'report.export']} />);
  await loaded(); fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }));
  await screen.findByRole('link', { name: 'Download report' });
  result.rerender(<DayBookWorkspace {...props} permissions={['report.read']} />);
  expect(screen.queryByRole('link', { name: 'Download report' })).not.toBeInTheDocument();
});

it('resumes the known export after a status-read failure without creating another file job', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  let refused = true;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => {
    if (args[2].endsWith('/exports')) return { id: exportId, kind: 'EXPORT', status: 'QUEUED', parameters: { format: 'PDF' } };
    if (args[2].includes('/report-exports/')) {
      if (refused) throw new Error('Export status temporarily unavailable');
      return { id: exportId, kind: 'EXPORT', status: 'COMPLETE', parameters: { format: 'PDF' } };
    }
    return original(...args);
  });
  mount(); await loaded(); fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }));
  await screen.findByText('Export status temporarily unavailable');
  refused = false; fireEvent.click(screen.getByRole('button', { name: 'Retry export' }));
  await screen.findByRole('link', { name: 'Download report' });
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[2].endsWith('/exports'))).toHaveLength(1);
});
