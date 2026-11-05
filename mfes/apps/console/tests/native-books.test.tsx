import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { DEFAULT_DISPLAY_CONFIG, DisplayConfigProvider } from '@janso/ui';
import { NativeBookWorkspace } from '../app/components/NativeBookWorkspace';
import { bookParameterLabel, bookPreferencesKey, nativeBooks } from '../app/lib/book-workspace';
import { productFieldRequest } from '../app/lib/product-fields';

vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));

const company = '01990000-0000-7000-8000-000000000001';
const generation = '01990000-0000-7000-8000-000000000002';
const runId = '01990000-0000-7000-8000-000000000003';
const exportId = '01990000-0000-7000-8000-000000000004';
const columns = [
  { key: 'date', title: 'Posting date', kind: 'DATE' },
  { key: 'number', title: 'Voucher number', kind: 'TEXT' },
  { key: 'account_id', title: 'Account Id', kind: 'IDENTIFIER' },
  { key: 'debit', title: 'Debit', kind: 'MONEY', currency_key: 'currency' },
  { key: 'credit', title: 'Credit', kind: 'MONEY', currency_key: 'currency' },
  { key: 'balance', title: 'Balance', kind: 'MONEY', currency_key: 'currency' },
];
const compactColumns = [{ key: 'number', title: 'Voucher number', kind: 'TEXT' }];
let extraView = false;
const definition = (code: string) => ({
  definition: { code, version: 2, title: nativeBooks['cash-book'].title, description: 'Verified book', datasets: ['journal_line'], views: [{ key: 'default', title: 'Cash Book', columns }, ...(extraView ? [{ key: 'compact', title: 'Compact', columns: compactColumns }] : [])] },
  parameter_schema: { required: ['date_from', 'date_to'], properties: {
    date_from: { type: 'string', format: 'date', title: 'From date' },
    date_to: { type: 'string', format: 'date', title: 'To date' },
    basis: { type: 'string', enum: ['BASE', 'TRANSACTION'], default: 'BASE', title: 'Currency basis' },
    currency: { anyOf: [{ type: 'string' }, { type: 'null' }], title: 'Currency' },
    account_id: { anyOf: [{ type: 'string', format: 'uuid' }, { type: 'null' }], title: 'Account Id' },
    group_id: { anyOf: [{ type: 'string', format: 'uuid' }, { type: 'null' }], title: 'Group Id' },
  } },
  run_enabled: true, export_limits: ['CSV', 'XLSX', 'PDF'].map(format => ({ format, max_rows: 1000, max_cells: 10000 })), package_limits: { max_rows: 5000, max_parts: 10 },
});
const cashSummary = { code: 'CASH_BOOK', record_count: 75, entry_count: 73, amounts: { INR: { debit: '12500.0000', credit: '8000.0000', closing: '9500.0000' } } };
const job = { id: runId, generation_id: generation, kind: 'RUN', code: 'CASH_BOOK', version: 2, status: 'COMPLETE', attempt: 1, completed_rows: 75, created_at: '2026-11-01T10:00:00Z', failure_code: null, result: { evidence: { book_summary: cashSummary } }, origin: null, display: null, title: 'Cash Book', views: [{ key: 'default', title: 'Cash Book', columns }], parameters: {}, view: 'default', execution: 'STANDARD', delivery: 'SINGLE' };
let completedRows = 75;
let coverage = '2026-04-01';

beforeEach(() => {
  localStorage.clear();
  completedRows = 75;
  extraView = false;
  coverage = '2026-04-01';
  vi.mocked(productFieldRequest).mockReset();
  vi.mocked(productFieldRequest).mockImplementation(async (_service, method, path, body) => {
    if (path.includes('/report-definitions/')) return definition(path.split('/').at(-1)!);
    if (path.includes('/report-generations?')) return { items: [{ id: generation, status: 'READY' }], page: { next_cursor: null } };
    if (path.endsWith('/report-generations/' + generation)) return { id: generation, status: 'READY', manifest: { control: { coverage_start: coverage } } };
    if (path.endsWith('/report-runs')) {
      const requestBody = body as { code: string; parameters: object; view: string };
      return { ...job, completed_rows: completedRows, code: requestBody.code, parameters: requestBody.parameters, view: requestBody.view, views: definition(requestBody.code).definition.views, result: { evidence: { book_summary: { ...cashSummary, record_count: completedRows } } } };
    }
    if (path.includes('/rows?')) return { items: [{ ordinal: path.includes('cursor=') ? 51 : 1, data: { date: '2026-11-01', number: 'RCP-1', account_id: '01990000-0000-7000-8000-000000000099', debit: '1250.0000', credit: '0.0000', balance: '5250.0000', currency: 'INR' }, drilldowns: [] }], page: { next_cursor: path.includes('cursor=') ? null : 'next' } };
    if (path.endsWith('/exports')) return { ...job, completed_rows: completedRows, id: exportId, kind: 'EXPORT', parameters: { format: (body as { format: string }).format }, delivery: (body as { delivery: string }).delivery };
    throw new Error('Unexpected request: ' + method + ' ' + path);
  });
});

function mount(permissions = ['report.read', 'report.export'], book: keyof typeof nativeBooks = 'cash-book') {
  return render(<DisplayConfigProvider config={{ ...DEFAULT_DISPLAY_CONFIG, currency: 'INR', amountPrecision: 2 }}><NativeBookWorkspace book={book} company={company} companyName="Example Traders" actor="actor-1" permissions={permissions} year={{ id: 'year', code: 'FY26', startDate: '2026-04-01', endDate: '2027-03-31', current: true, open: true }} /></DisplayConfigProvider>);
}

it.each(Object.keys(nativeBooks))('prepares %s automatically inside the snapshot history and enables print', async book => {
  coverage = '2026-10-31';
  mount(['report.read', 'report.export'], book as keyof typeof nativeBooks);
  expect(await screen.findByText('RCP-1')).toBeVisible();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Print / PDF' })).toBeEnabled());
  expect(screen.getByLabelText('From date')).toHaveValue(coverage);
  expect(productFieldRequest).toHaveBeenCalledWith('reports', 'POST', expect.stringContaining('/report-runs'), expect.objectContaining({ parameters: expect.objectContaining({ date_from: coverage }) }), expect.any(String), expect.any(AbortSignal));
});

it('explains the required stock item and prepares its printable ledger after verified selection', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  const item = { id: '01990000-0000-7000-8000-000000000005', company_id: company, name: 'Copper cable' };
  let verifyItem!: (value: typeof item) => void;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => {
    if (args[2].endsWith('/report-definitions/ITEM_LEDGER')) {
      const found = definition('ITEM_LEDGER');
      found.parameter_schema.required.push('item_id');
      Object.assign(found.parameter_schema.properties, { item_id: { type: 'string', format: 'uuid', title: 'Item Id' } });
      return found;
    }
    if (args[2].includes('/items?')) return { items: [item], page: { next_cursor: null } };
    if (args[2].endsWith('/items/' + item.id)) return new Promise(resolve => { verifyItem = resolve; });
    return original(...args);
  });
  mount(['report.read', 'report.export'], 'stock-ledger');
  const selector = await screen.findByRole('combobox', { name: 'Stock item' });
  expect(screen.getByRole('button', { name: 'Print / PDF' })).toHaveAttribute('title', 'Choose Stock item to prepare this book for print and export.');
  expect(screen.getByText('Choose Stock item to prepare this book for print and export.')).toBeVisible();
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[1] === 'POST')).toHaveLength(0);
  fireEvent.focus(selector);
  fireEvent.click(await screen.findByRole('option', { name: 'Copper cable' }));
  await waitFor(() => expect(verifyItem).toEqual(expect.any(Function)));
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[2].endsWith('/report-runs'))).toHaveLength(0);
  await act(async () => verifyItem(item));
  await screen.findByText('RCP-1');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Print / PDF' })).toBeEnabled());
  expect(productFieldRequest).toHaveBeenCalledWith('reports', 'POST', expect.stringContaining('/report-runs'), expect.objectContaining({ parameters: expect.objectContaining({ item_id: item.id }) }), expect.any(String), expect.any(AbortSignal));
});

it('preserves a manually chosen earlier period for owner-side historical verification', async () => {
  coverage = '2026-10-31'; mount(); await screen.findByText('RCP-1');
  fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-04-01' } });
  expect(screen.getByRole('button', { name: 'Print / PDF' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
  await waitFor(() => expect(vi.mocked(productFieldRequest).mock.calls.findLast(call => call[2].endsWith('/report-runs'))?.[3]).toMatchObject({ parameters: { date_from: '2026-04-01' } }));
  expect(screen.getByLabelText('From date')).toHaveValue('2026-04-01');
});

it('explains the missing inventory snapshot and blocks preparation without inventing empty stock', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].endsWith('/report-generations/' + generation)
    ? { id: generation, status: 'READY', manifest: { control: { coverage_start: coverage, counts: { inventory_report_record: 0 } } } }
    : original(...args));
  mount(['report.read', 'report.export', 'report.definition.manage'], 'stock-ledger');
  const explanation = 'Stock Ledger needs a complete inventory snapshot before print or export. Update accounting data after the stock source is prepared.';
  expect(await screen.findByText(explanation)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Print / PDF' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Print / PDF' })).toHaveAttribute('title', explanation);
  expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Update accounting data' })).toBeEnabled();
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[1] === 'POST')).toHaveLength(0);
});

it('does not repeat a failed automatic run and aborts its request when leaving the book', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => {
    if (args[2].endsWith('/report-runs')) throw new Error('Access changed');
    return original(...args);
  });
  const rendered = mount();
  expect(await screen.findByText('Access changed')).toBeVisible();
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call => call[2].endsWith('/report-runs'))).toHaveLength(1);
  const signal = vi.mocked(productFieldRequest).mock.calls.find(call => call[2].endsWith('/report-runs'))?.[5];
  rendered.unmount(); expect(signal?.aborted).toBe(true);
});

it('updates the history hint when refreshing to a newer verified snapshot', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  const latest = '01990000-0000-7000-8000-000000000006';
  let generationReads = 0;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => {
    if (args[2].includes('/report-generations?') && ++generationReads > 1) return { items: [{ id: latest, status: 'READY' }], page: { next_cursor: null } };
    if (args[2].endsWith('/report-generations/' + latest)) return { id: latest, status: 'READY', manifest: { control: { coverage_start: '2026-05-01' } } };
    return original(...args);
  });
  mount(); await screen.findByText('RCP-1');
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await waitFor(() => expect(screen.getByText(/This snapshot covers activity from/)).toHaveTextContent('01 May 2026'));
  expect(screen.getByLabelText('From date')).toHaveValue('2026-04-01');
});

it('defines a dedicated implementation profile for every remaining Books route', () => {
  expect(Object.keys(nativeBooks)).toEqual(['cash-book', 'bank-book', 'sales-book', 'purchase-book', 'payment-book', 'receipt-book', 'account-ledger', 'party-ledger', 'stock-ledger']);
  expect(new Set(Object.values(nativeBooks).map(item => item.code)).size).toBe(9);
  expect(bookParameterLabel('cash-book', 'account_id', 'Account Id')).toBe('Cash account');
  expect(bookParameterLabel('bank-book', 'account_id', 'Account Id')).toBe('Bank account');
  expect(bookParameterLabel('sales-book', 'party_id', 'Party Id')).toBe('Customer');
  expect(bookParameterLabel('purchase-book', 'party_id', 'Party Id')).toBe('Supplier');
  expect(bookParameterLabel('stock-ledger', 'group_id', 'Group Id')).toBe('Item group');
});

it('recovers an unavailable initial book load without showing a false missing-snapshot state', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  let refuse = true;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => {
    if (args[2].includes('/report-definitions/') && refuse) { refuse = false; throw new Error('Report service unavailable'); }
    return original(...args);
  });
  mount();
  expect(await screen.findByText('Report service unavailable')).toBeVisible();
  expect(screen.queryByText(/There is no prepared snapshot/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Retry loading book' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled());
  expect(screen.queryByText('Report service unavailable')).not.toBeInTheDocument();
});

it('runs a frozen Cash Book with definition-owned filters, formatted balances and cursor paging', async () => {
  mount();
  expect(await screen.findByRole('heading', { level: 1, name: 'Cash Book' })).toBeVisible();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
  expect(await screen.findByText('RCP-1')).toBeVisible();
  expect(screen.getByLabelText('Cash Book summary')).toHaveTextContent('73');
  expect(screen.getByLabelText('Cash Book summary')).toHaveTextContent('12,500.00');
  expect(screen.getByLabelText('Cash Book summary')).toHaveTextContent('9,500.00');
  expect(screen.getByLabelText('Cash account')).toBeVisible();
  expect(within(screen.getByRole('form', { name: 'Cash Book filters' })).queryByLabelText('Cash ledger group')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'More filters' }));
  expect(within(screen.getByRole('dialog', { name: 'Cash Book filters' })).getByLabelText('Cash ledger group')).toBeVisible();
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Cash Book filters' })).getByRole('button', { name: 'Close' }));
  expect(screen.queryByRole('columnheader', { name: 'Account Id' })).not.toBeInTheDocument();
  expect(screen.getByText('5,250.00')).toBeVisible();
  expect(productFieldRequest).toHaveBeenCalledWith('reports', 'POST', expect.stringContaining('/report-runs'), expect.objectContaining({ code: 'CASH_BOOK', generation_id: generation }), expect.any(String), expect.any(AbortSignal));
  fireEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(await screen.findByText('51–51 of 75')).toBeVisible();
});

it('keeps retained columns aligned with the applied view until the next view is prepared', async () => {
  extraView = true; mount();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
  expect(await screen.findByRole('columnheader', { name: 'Debit' })).toBeVisible();
  fireEvent.change(screen.getByLabelText('Book view'), { target: { value: 'compact' } });
  expect(screen.getByRole('columnheader', { name: 'Debit' })).toBeVisible();
  expect(screen.getByText('Filters changed. Select Apply to update this book.')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
  await waitFor(() => expect(screen.queryByRole('columnheader', { name: 'Debit' })).not.toBeInTheDocument());
  expect(screen.getByRole('columnheader', { name: 'Voucher number' })).toBeVisible();
});

it('locks conflicting actions while refreshing the latest snapshot and then prepares it', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  let generationReads = 0, finish!: (value: { items: { id: string; status: string }[]; page: { next_cursor: null } }) => void;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => {
    if (args[2].includes('/report-generations?') && ++generationReads === 2) return new Promise(resolve => { finish = resolve; });
    return original(...args);
  });
  mount(); await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
  expect(screen.getByRole('status', { name: 'Cash Book progress' })).toHaveTextContent('Loading book');
  await act(async () => finish({ items: [{ id: generation, status: 'READY' }], page: { next_cursor: null } }));
  expect(await screen.findByText('RCP-1')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled();
});

it('keeps saved filters actor/company/book scoped and uses the private export pipeline', async () => {
  mount(); await waitFor(() => expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled());
  expect(screen.queryByLabelText('New view name')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Saved views' }));
  fireEvent.change(screen.getByLabelText('New view name'), { target: { value: 'Month close' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save current view' }));
  const stored = JSON.parse(localStorage.getItem(bookPreferencesKey('actor-1', company, 'cash-book'))!);
  expect(stored.views[0].name).toBe('Month close');
  fireEvent.click(screen.getByRole('button', { name: 'Done' }));
  fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-05-01' } });
  fireEvent.click(screen.getByRole('button', { name: 'Saved views' }));
  fireEvent.change(screen.getByLabelText('Choose saved view'), { target: { value: '' } });
  fireEvent.change(screen.getByLabelText('Choose saved view'), { target: { value: stored.views[0].id } });
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Saved views' })).not.toBeInTheDocument());
  expect(screen.getByLabelText('From date')).toHaveValue('2026-04-01'); await screen.findByText('RCP-1');
  fireEvent.click(screen.getByRole('button', { name: 'Export' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'CSV spreadsheet' }));
  expect(await screen.findByRole('link', { name: 'Download report' })).toHaveAttribute('href', '/api/report-download?company=' + company + '&export=' + exportId);
});

it('keeps the completed book visible while preparing its printable PDF', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  let finish!: (value: typeof job) => void;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => args[2].endsWith('/exports')
    ? new Promise(resolve => { finish = resolve; }) : original(...args));
  mount(); await waitFor(() => expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Apply' })); await screen.findByText('RCP-1');
  fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }));
  expect(screen.getByRole('status', { name: 'Cash Book progress' })).toHaveTextContent('Preparing PDF report');
  expect(screen.getByText('RCP-1')).toBeVisible();
  expect(screen.getByLabelText('Cash Book report')).toHaveAttribute('aria-busy', 'false');
  await act(async () => finish({ ...job, id: exportId, kind: 'EXPORT', parameters: { format: 'PDF' } }));
  expect(await screen.findByRole('link', { name: 'Open print preview' })).toBeVisible();
});

it('clears a stale download and retries an uncertain export with the same command identity', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  let refuse = false;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) => {
    if (args[2].endsWith('/exports') && refuse) { refuse = false; throw new Error('Export temporarily unavailable'); }
    return original(...args);
  });
  mount(); await waitFor(() => expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Apply' })); await screen.findByText('RCP-1');
  fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }));
  await screen.findByRole('link', { name: 'Download report' });
  refuse = true; fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }));
  expect(await screen.findByText('Export temporarily unavailable')).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Download report' })).not.toBeInTheDocument();
  const failed = vi.mocked(productFieldRequest).mock.calls.findLast(call => call[2].endsWith('/exports'))!;
  fireEvent.click(screen.getByRole('button', { name: 'Retry export' }));
  await screen.findByRole('link', { name: 'Download report' });
  const retried = vi.mocked(productFieldRequest).mock.calls.findLast(call => call[2].endsWith('/exports'))!;
  expect(retried[4]).toBe(failed[4]);
});

it.each(Object.entries(nativeBooks))('runs, exports and prints %s through its authoritative report code', async (book, profile) => {
  mount(['report.read', 'report.export'], book as keyof typeof nativeBooks);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Apply' })); await screen.findByText('RCP-1');
  expect(productFieldRequest).toHaveBeenCalledWith('reports', 'POST', expect.stringContaining('/report-runs'), expect.objectContaining({ code: profile.code }), expect.any(String), expect.any(AbortSignal));
  fireEvent.click(screen.getByRole('button', { name: 'Export' })); fireEvent.click(screen.getByRole('menuitem', { name: 'CSV spreadsheet' }));
  expect(await screen.findByRole('link', { name: 'Download report' })).toHaveAttribute('href', '/api/report-download?company=' + company + '&export=' + exportId);
  expect(productFieldRequest).toHaveBeenCalledWith('reports', 'POST', expect.stringContaining('/exports'), expect.objectContaining({ format: 'CSV', delivery: 'SINGLE' }), expect.any(String), expect.any(AbortSignal));
  fireEvent.click(screen.getByRole('button', { name: 'Export' })); fireEvent.click(screen.getByRole('menuitem', { name: 'Excel workbook' }));
  await waitFor(() => expect(productFieldRequest).toHaveBeenCalledWith('reports', 'POST', expect.stringContaining('/exports'), expect.objectContaining({ format: 'XLSX', delivery: 'SINGLE' }), expect.any(String), expect.any(AbortSignal)));
  fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }));
  expect(await screen.findByRole('link', { name: 'Open print preview' })).toHaveAttribute('href', '/api/report-download?company=' + company + '&export=' + exportId + '&preview=1');
  expect(productFieldRequest).toHaveBeenCalledWith('reports', 'POST', expect.stringContaining('/exports'), expect.objectContaining({ format: 'PDF', delivery: 'SINGLE' }), expect.any(String), expect.any(AbortSignal));
});

it('explains single-file capacity and enables packaged PDF delivery within package limits', async () => {
  completedRows = 1500; mount(); await waitFor(() => expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Apply' })); await screen.findByText('RCP-1');
  fireEvent.click(screen.getByRole('button', { name: 'Export' }));
  expect(screen.getByRole('menuitem', { name: /CSV spreadsheet/ })).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByRole('button', { name: 'Print / PDF' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Print / PDF' }).getAttribute('title')).toMatch(/1,000 rows/i);
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' });
  fireEvent.change(screen.getByLabelText('PDF delivery'), { target: { value: 'PACKAGE' } });
  expect(screen.getByRole('button', { name: 'Print / PDF' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Export' })); fireEvent.click(screen.getByRole('menuitem', { name: 'PDF report' }));
  expect(await screen.findByRole('link', { name: 'Download report' })).toBeVisible();
  expect(productFieldRequest).toHaveBeenCalledWith('reports', 'POST', expect.stringContaining('/exports'), expect.objectContaining({ format: 'PDF', delivery: 'PACKAGE' }), expect.any(String), expect.any(AbortSignal));
});

it('permission-gates export and source management without hiding the readable book', async () => {
  mount(['report.read']);
  expect(await screen.findByRole('heading', { name: 'Cash Book' })).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Export' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Update accounting data' })).not.toBeInTheDocument();
});
