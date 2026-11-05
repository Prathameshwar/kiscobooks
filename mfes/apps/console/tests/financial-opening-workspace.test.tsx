import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DEFAULT_DISPLAY_CONFIG, DisplayConfigProvider } from '@janso/ui';
import { FinancialOpeningWorkspace } from '../app/components/FinancialOpeningWorkspace';
import { FinancialOpeningEntry } from '../app/components/FinancialOpeningEntry';
import { FinancialOpeningPosting } from '../app/components/FinancialOpeningPosting';
import { OpeningJournal } from '../app/components/FinancialOpeningJournal';
import { serviceCall } from '../app/lib/service-call';
import { ACCOUNT, BATCH, COMPANY, JOURNAL, access, declaration, line, metadata, page, readiness, workspace } from './financial-opening-fixtures';
import { heldEntry } from '../app/lib/party-opening';
import { held, heldInvoice, heldPage } from './party-opening-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...(await original<typeof import('../app/lib/service-call')>()), serviceCall: vi.fn() }));
vi.mock('../app/lib/product-fields', async original => ({ ...(await original<typeof import('../app/lib/product-fields')>()), productFieldRequest: vi.fn(async () => ({ items: [{ id: ACCOUNT, name: 'Test ledger', status: 'ACTIVE' }], page })) }));
const api = vi.mocked(serviceCall);
let deny = false, uncertain = false, posted = false, newCompany = false, legacyOpening = false, accountKind = 'PARTY';
beforeEach(() => {
  deny = false; uncertain = false; posted = false; newCompany = false; legacyOpening = false; accountKind = 'PARTY'; api.mockReset();
  api.mockImplementation(async (_endpoint, req) => {
    if (legacyOpening && req.path.includes('/workspaces/' + BATCH)) throw { status: 409, message: 'use the legacy opening workflow for this batch' };
    if (req.path.endsWith('/readiness')) return (newCompany ? { ...readiness, batch_id: null, status: 'NOT_STARTED', can_prepare: true } : readiness) as never;
    if (req.path.endsWith('/workspaces/field-set')) return metadata as never;
    if (req.path.includes('/finance/field-sets/')) return (metadata.native.find(set => req.path.endsWith('/' + set.resource)) ?? { resource: req.path.split('/').at(-1), fields: [] }) as never;
    if (req.path.endsWith('/declaration') || req.path.includes('/revisions/' + workspace.revision_id)) { if (deny) throw { status: 403, message: 'Opening amounts are protected.' }; return declaration() as never; }
    if (req.path.endsWith('/workspaces/preview')) return { company_id: COMPANY, manifest_hash: 'b'.repeat(64), posting_date: readiness.books_begin_date, entry_count: 2, document_count: 0, journal_count: 1, currency: 'INR', total_debit: '100', total_credit: '100', informational_only: true } as never;
    if (req.path.endsWith('/replace') || req.path.endsWith('/prepare-drafts') || req.path.endsWith('/finalize')) {
      if (uncertain) { uncertain = false; throw { status: 503, message: 'Confirmation connection unavailable.' }; }
      return { ...workspace, expected_version: 2, ...(req.path.endsWith('/finalize') ? { status: 'FINALIZED' } : {}) } as never;
    }
    if (req.path.endsWith('/reconciliation')) return { batch_id: BATCH, revision_id: workspace.revision_id, posting_date: readiness.books_begin_date, covered_through: '2026-03-31', coverage_mode: 'POST_CUTOVER_ONLY', currency: 'INR', expected_debit: '100', expected_credit: '100', posted_debit: '100', posted_credit: '100', declared_documents: 0, posted_documents: 0, gl_matches: true, party_items_match: true, confirmation_pending: false, ready_to_finalize: true, blockers: [], clearing_balance: '0' } as never;
    if (req.path.includes('/accounts?')) return { items: [{ id: ACCOUNT, name: 'Test ledger', status: 'ACTIVE' }], page } as never;
    if (req.path.includes('/accounts/')) return { id: ACCOUNT, company_id: COMPANY, name: 'Test ledger', kind: accountKind, party_role: 'CUSTOMER', status: 'ACTIVE' } as never;
    if (req.path.endsWith('/journals/' + JOURNAL) || req.path.endsWith('/journals/' + JOURNAL + '/post')) {
      if (req.path.endsWith('/post')) posted = true;
      return { id: JOURNAL, company_id: COMPANY, kind: 'OPENING', source_type: 'financial_opening_chunk', row_version: posted ? 2 : 1, status: posted ? 'POSTED' : 'DRAFT', total_debit: '100', total_credit: '100' } as never;
    }
    if (req.path.includes('/journal-lines?')) return { items: [{ id: ACCOUNT, company_id: COMPANY, journal_id: JOURNAL, sequence: 1, account_id: ACCOUNT, amount: '100', base_amount: '100', currency: 'INR', base_currency: 'INR', side: 'DEBIT', row_version: 1 }], page } as never;
    if (req.path.includes('?')) return { items: [], page } as never;
    return workspace as never;
  });
});
async function openSource() {
  await screen.findByRole('button', { name: /^Review and post/ });
  await userEvent.click(screen.getByRole('button', { name: /^Review and post/ }));
  const toggle = await screen.findByRole('switch', { name: 'Prepare and post automatically' });
  if (toggle.getAttribute('aria-checked') === 'true' && !toggle.hasAttribute('disabled')) await userEvent.click(toggle);
  await screen.findByLabelText('Source system');
}
async function openEntries() {
  await screen.findByRole('button', { name: /^Enter openings/ });
  await userEvent.click(screen.getByRole('button', { name: /^Enter openings/ }));
  await userEvent.click(await screen.findByText(/^Entered lines and bill details/));
}
it('formats the opening review summary while keeping native date input values', async () => {
  render(<DisplayConfigProvider config={{ ...DEFAULT_DISPLAY_CONFIG, dateFormat: 'dd/MM/yyyy', timezone: 'America/Los_Angeles' }}><FinancialOpeningWorkspace company={COMPANY} access={access} /></DisplayConfigProvider>);
  await openSource();
  expect(await screen.findByLabelText('Opening date')).toHaveValue('2026-04-01');
  expect(screen.getByLabelText('Source covered through')).toHaveValue('2026-03-31');
  expect(screen.getByText('01/04/2026')).toBeVisible();
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getByRole('button', { name: /^Review/ }));
  expect(await screen.findByText('31/03/2026')).toBeVisible();
});
it('formats the native opening journal posting date', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    const result = await original(...args);
    return args[1].path.endsWith('/journals/' + JOURNAL) ? { ...(result as object), posting_date: '2026-04-01' } as never : result;
  });
  render(<DisplayConfigProvider config={{ ...DEFAULT_DISPLAY_CONFIG, dateFormat: 'dd/MM/yyyy' }}><OpeningJournal company={COMPANY} id={JOURNAL} access={access} onDirty={vi.fn()} onChanged={vi.fn()} /></DisplayConfigProvider>);
  expect(await screen.findByText('01/04/2026')).toBeVisible();
});
it('formats the legacy opening cutover message', async () => {
  legacyOpening = true;
  render(<DisplayConfigProvider config={{ ...DEFAULT_DISPLAY_CONFIG, dateFormat: 'dd/MM/yyyy' }}><FinancialOpeningWorkspace company={COMPANY} access={access} /></DisplayConfigProvider>);
  expect(await screen.findByText(/retained with status .* at 01\/04\/2026/)).toBeVisible();
});
it('formats outstanding due dates and keeps document editor dates in native ISO form', async () => {
  const initial = { ...line(), documents: [{ reference: 'Historical bill', document_kind: 'INVOICE' as const, amount: '100', base_amount: '100', document_date: '2026-03-01', due_date: '2026-03-20' }] };
  render(<DisplayConfigProvider config={{ ...DEFAULT_DISPLAY_CONFIG, dateFormat: 'dd/MM/yyyy' }}><FinancialOpeningEntry company={COMPANY} declaration={declaration()} initial={initial} metadata={metadata} native={metadata.native} disabled={false} onSave={vi.fn()} onCancel={vi.fn()} onDirty={vi.fn()} /></DisplayConfigProvider>);
  expect(await screen.findByText('20/03/2026')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Edit Historical bill' }));
  expect(screen.getByLabelText('Document date')).toHaveValue('2026-03-01');
  expect(screen.getByLabelText('Due date')).toHaveValue('2026-03-20');
});
it('reviews a company-wide worksheet, validates changes and saves an explicit revision', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await openSource();
  fireEvent.change(screen.getByLabelText('Opening source and reason'), { target: { value: 'Reviewed and checked migration' } });
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getByRole('button', { name: /^Review/ }));
  expect(screen.getByRole('button', { name: 'Save reviewed revision' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
  await screen.findByText(/Preview passed: 2 account lines/);
  await userEvent.click(screen.getByRole('button', { name: 'Save reviewed revision' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save opening' }));
  await screen.findByText('Opening worksheet saved. No balances have been posted.');
  const saved = api.mock.calls.find(([, req]) => req.path.endsWith('/replace'))![1];
  expect(saved.key).toBeTruthy();
  expect(saved.body).toMatchObject({ expected_version: 1, manifest_hash: workspace.manifest_hash, declaration: { reason: 'Reviewed and checked migration' } });
});

it('loads the immutable declaration revision named by its versioned workspace', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await openSource();
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/revisions/' + workspace.revision_id))).toBe(true);
});

it.each([false, true])('pins the original worksheet baseline after conflict and reload (new=%s)', async (initiallyNew) => {
  newCompany = initiallyNew;
  const original = api.getMockImplementation()!;
  let conflict = false;
  const writes: unknown[] = [];
  api.mockImplementation(async (...args) => {
    const req = args[1];
    if (req.method === 'POST' && (req.path.endsWith('/replace') || req.path.endsWith('/workspaces'))) {
      writes.push(req); conflict = true; newCompany = false;
      throw { status: 409, message: 'Opening declaration changed.' };
    }
    if (conflict && req.path.endsWith('/workspaces/' + BATCH))
      return { ...workspace, expected_version: 2, manifest_hash: 'c'.repeat(64) } as never;
    return original(...args);
  });
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  // A new worksheet needs its local account lines, supplied here through the same editor state seed.
  if (initiallyNew) {
    accountKind = 'GENERAL';
    await openEntries();
    for (const side of ['DEBIT', 'CREDIT']) {
      await userEvent.click(screen.getByRole('button', { name: 'Add account balance' }));
      const picker = await screen.findByRole('combobox', { name: 'Ledger account' });
      await userEvent.type(picker, 'Test');
      await userEvent.click(await screen.findByRole('option', { name: 'Test ledger' }));
      fireEvent.change(screen.getByLabelText('Opening amount'), { target: { value: '100' } });
      fireEvent.change(screen.getByLabelText('Balance side'), { target: { value: side } });
      await waitFor(() => expect(screen.getByRole('button', { name: 'Keep account line' })).toBeEnabled());
      await userEvent.click(screen.getByRole('button', { name: 'Keep account line' }));
    }
  }
  await openSource();
  fireEvent.change(screen.getByLabelText('Opening source and reason'), { target: { value: 'My reviewed local change' } });
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getByRole('button', { name: /^Review/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
  await screen.findByText(/Preview passed/);
  await userEvent.click(screen.getByRole('button', { name: initiallyNew ? 'Save reviewed opening' : 'Save reviewed revision' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save opening' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Reload and review' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save reviewed revision' })).toBeEnabled());
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save opening' }));
  await screen.findByText(/worksheet changed while you were editing/i);
  expect(writes).toHaveLength(1);
});

it.each(['BOOKS_BEGIN_PERIOD_NOT_OPEN', 'LATER_BOOKS_CLOSED'])(
  'blocks existing worksheet mutations when readiness reports %s', async blocker => {
    const original = api.getMockImplementation()!;
    api.mockImplementation(async (...args) => args[1].path.endsWith('/readiness')
      ? { ...readiness, blockers: [blocker] } as never : original(...args));
    render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
    await openSource();
    expect(screen.getByLabelText('Source system')).toBeDisabled();
    await userEvent.click(screen.getByRole('tab', { name: 'Posting and completion' }));
    expect(await screen.findByRole('button', { name: 'Prepare remaining drafts' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Finalize financial opening' })).toBeDisabled();
  },
);

it('respects native write denial for outstanding documents', async () => {
  const native = [...metadata.native.filter(set => set.resource !== 'open-items'), { resource: 'open-items', fields: [
    { key: 'reference', label: 'Reference', required: true, visible: true, readable: true, writable: false, definition: {} },
  ] }];
  render(<FinancialOpeningEntry company={COMPANY} declaration={declaration()} initial={line()}
    metadata={{ ...metadata, capture_permissions: { ...metadata.capture_permissions, open_items: { ...metadata.capture_permissions.open_items, reference: false } } }} native={native} disabled={false} onSave={vi.fn()} onCancel={vi.fn()} onDirty={vi.fn()} />);
  expect(await screen.findByRole('button', { name: 'Add outstanding document' })).toBeDisabled();
  expect(screen.getByText(/document fields are restricted/i)).toBeVisible();
});

it('uses opening capture permissions even when generic open-item metadata is empty', async () => {
  render(<FinancialOpeningEntry company={COMPANY} declaration={declaration()} initial={line()}
    metadata={metadata} native={[]} disabled={false} onSave={vi.fn()} onCancel={vi.fn()} onDirty={vi.fn()} />);
  expect(await screen.findByRole('button', { name: 'Add outstanding document' })).toBeEnabled();
});

it('keeps replacement creation separate from another active company opening', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => args[1].path.endsWith('/workspaces/' + BATCH)
    ? { ...workspace, status: 'REVERSED' } as never : original(...args));
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} initialBatchId={BATCH} />);
  await openSource();
  await userEvent.click(screen.getByRole('tab', { name: 'Posting and completion' }));
  expect(await screen.findByRole('button', { name: 'Prepare a replacement opening' })).toBeDisabled();
});

it('creates a replacement with its reversed predecessor instead of revising it', async () => {
  newCompany = true;
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => args[1].path.endsWith('/workspaces/' + BATCH)
    ? { ...workspace, status: 'REVERSED' } as never : original(...args));
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} initialBatchId={BATCH} />);
  await openSource();
  await userEvent.click(screen.getByRole('tab', { name: 'Posting and completion' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Prepare a replacement opening' }));
  await openSource();
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getByRole('button', { name: /^Review/ }));
  await userEvent.click(await screen.findByRole('button', { name: 'Validate and preview' }));
  await screen.findByText(/Preview passed/);
  await userEvent.click(screen.getByRole('button', { name: 'Save reviewed opening' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save opening' }));
  await waitFor(() => expect(api.mock.calls.some(([, req]) => req.method === 'POST' && req.path.endsWith('/workspaces'))).toBe(true));
  expect(api.mock.calls.find(([, req]) => req.method === 'POST' && req.path.endsWith('/workspaces'))![1].body).toMatchObject({ replacement_of_id: BATCH });
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/replace'))).toBe(false);
});
it('preserves the exact request and key when preparation has an uncertain outcome', async () => {
  uncertain = true;
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await openSource();
  await userEvent.click(screen.getByRole('tab', { name: 'Posting and completion' }));
  fireEvent.change(await screen.findByLabelText('Action review reason'), { target: { value: 'Reviewed native opening plan' } });
  await userEvent.click(screen.getByRole('button', { name: 'Prepare remaining drafts' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Prepare drafts' }));
  await userEvent.click(await within(screen.getByRole('dialog')).findByRole('button', { name: 'Retry the same request' }));
  await screen.findByText(/Native opening drafts prepared/);
  const requests = api.mock.calls.filter(([, req]) => req.path.endsWith('/prepare-drafts')).map(([, req]) => req);
  expect(requests).toHaveLength(2); expect(requests[1]).toEqual(requests[0]);
});
it('hides retained financial data when current read authority is denied', async () => {
  deny = true;
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await screen.findByText('Opening amounts are protected.');
  expect(screen.queryByLabelText('Source system')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Add account balance' })).not.toBeInTheDocument();
});
it('keeps read access separate from capture and completion authority', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={{ manage: false, post: false, export: false }} />);
  await openSource();
  expect(screen.getByLabelText('Source system')).toBeDisabled();
  await userEvent.click(screen.getByRole('tab', { name: 'Posting and completion' }));
  expect(await screen.findByRole('button', { name: 'Prepare remaining drafts' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Finalize financial opening' })).toBeDisabled();
});
it('captures an explicit on-account document and cannot lose an unfinished document through line save', async () => {
  const onSave = vi.fn();
  render(<FinancialOpeningEntry company={COMPANY} declaration={declaration()} initial={line()} metadata={metadata} native={metadata.native} disabled={false} onSave={onSave} onCancel={vi.fn()} onDirty={vi.fn()} />);
  await screen.findByRole('button', { name: 'Add outstanding document' });
  await userEvent.click(screen.getByRole('button', { name: 'Add outstanding document' }));
  expect(screen.getByRole('button', { name: 'Keep account line' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Document type'), { target: { value: 'ON_ACCOUNT' } });
  fireEvent.change(screen.getByLabelText('Document reference'), { target: { value: 'Old unallocated opening' } });
  fireEvent.change(screen.getByLabelText('Outstanding amount (INR)'), { target: { value: '100' } });
  expect(screen.queryByLabelText('Document date')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Keep document' }));
  await userEvent.click(screen.getByRole('button', { name: 'Keep account line' }));
  expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ documents: [expect.objectContaining({ document_kind: 'ON_ACCOUNT', document_date: null, due_date: null, amount: '100', base_amount: '100' })] }));
});
it('renders native field denies and refuses a party opening without bill evidence', async () => {
  const native = structuredClone(metadata.native); native[0]!.fields.find(field => field.key === 'amount')!.writable = false;
  render(<FinancialOpeningEntry company={COMPANY} declaration={declaration()} initial={line()} metadata={{ ...metadata, capture_permissions: { ...metadata.capture_permissions, journal_lines: { ...metadata.capture_permissions.journal_lines, amount: false } } }} native={native} disabled={false} onSave={vi.fn()} onCancel={vi.fn()} onDirty={vi.fn()} />);
  await screen.findByRole('button', { name: 'Add outstanding document' });
  expect(screen.getByLabelText('Opening amount')).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Keep account line' }));
  await screen.findByText(/Add outstanding documents or an explicit on-account balance/);
});
it('posts only a verified native opening journal after an explicit review', async () => {
  render(<FinancialOpeningPosting company={COMPANY} workspace={{ ...workspace, journal_ids: [JOURNAL] }} access={access} onDirty={vi.fn()} onChanged={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Review journal 1' }));
  await screen.findByRole('button', { name: 'Post this opening journal' });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Post this opening journal' })).toBeEnabled());
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/post'))).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Post this opening journal' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Post journal' }));
  await screen.findByText(/Journal posted. Completion waits/);
  expect(api.mock.calls.find(([, req]) => req.path.endsWith('/post'))![1]).toMatchObject({ key: expect.any(String), body: { expected_version: 1 } });
});
it('finalizes only after successful reconciliation and records an explicit reason', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await openSource();
  await userEvent.click(screen.getByRole('tab', { name: 'Posting and completion' }));
  fireEvent.change(await screen.findByLabelText('Action review reason'), { target: { value: 'Reconciled and confirmed all journals' } });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Finalize financial opening' })).toBeEnabled());
  await userEvent.click(screen.getByRole('button', { name: 'Finalize financial opening' }));
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/finalize'))).toBe(false);
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Finalize opening' }));
  await screen.findByText('Opening finalized. The company can use its posted starting balances.');
  expect(api.mock.calls.find(([, req]) => req.path.endsWith('/finalize'))![1]).toMatchObject({ body: { reason: 'Reconciled and confirmed all journals', manifest_hash: workspace.manifest_hash } });
});
it('blocks section changes while a worksheet has unsaved edits', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await openSource();
  fireEvent.change(screen.getByLabelText('Source system'), { target: { value: 'tally' } });
  await userEvent.click(screen.getByRole('tab', { name: 'Import' }));
  await screen.findByText('Save or discard your worksheet changes before changing sections.');
  expect(screen.getByRole('tab', { name: 'Balances and bills' })).toHaveAttribute('aria-selected', 'true');
  await userEvent.click(screen.getByRole('button', { name: 'Discard worksheet changes' }));
  await userEvent.click(screen.getByRole('tab', { name: 'Import' }));
  expect(screen.getByRole('tab', { name: 'Import' })).toHaveAttribute('aria-selected', 'true');
});
it('validates source references locally and requires a reason before opening action confirmation', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await openSource();
  fireEvent.change(screen.getByLabelText('Source system'), { target: { value: 'invalid source' } });
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getByRole('button', { name: /^Review/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
  await screen.findByText('Enter valid source system and migration references.');
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/preview'))).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Discard worksheet changes' }));
  await userEvent.click(screen.getByRole('tab', { name: 'Posting and completion' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Prepare remaining drafts' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Action review reason')).toHaveFocus();
});
it('captures YTD scope, explicit same-day review and credit cash explanation through shared controls', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await openSource();
  fireEvent.change(screen.getByLabelText('Historical reporting'), { target: { value: 'YTD_SUMMARY' } });
  fireEvent.change(screen.getByLabelText('Originating financial year start'), { target: { value: '2025-04-01' } });
  fireEvent.change(screen.getByLabelText('Migration reference'), { target: { value: 'migration-ytd' } });
  await userEvent.click(screen.getByLabelText('I reviewed same-day source overlap'));
  await userEvent.click(screen.getByLabelText('I reviewed a credit cash opening'));
  fireEvent.change(screen.getByLabelText('Credit cash explanation'), { target: { value: 'Reviewed temporary cash credit at migration' } });
  const nominal = screen.getByRole('combobox', { name: 'Nominal account' });
  await userEvent.type(nominal, 'Test');
  await userEvent.click(await screen.findByRole('option', { name: 'Test ledger' }));
  fireEvent.change(screen.getByLabelText('YTD amount'), { target: { value: '100' } });
  await userEvent.click(screen.getByRole('button', { name: 'Add YTD summary' }));
  await userEvent.click(screen.getByRole('button', { name: 'Remove summary 1' }));
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getByRole('button', { name: /^Review/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
  await screen.findByText(/Preview passed/);
  expect(api.mock.calls.find(([, req]) => req.path.endsWith('/workspaces/preview'))![1].body).toMatchObject({ coverage_mode: 'YTD_SUMMARY', originating_year_start: '2025-04-01', ytd_summary: [], credit_cash_reviewed: true, same_day_reviewed: true });
});
it('keeps and edits dated bills, checks original amounts, and removes a mistaken bill', async () => {
  render(<FinancialOpeningEntry company={COMPANY} declaration={declaration()} initial={line()} metadata={metadata} native={metadata.native} disabled={false} onSave={vi.fn()} onCancel={vi.fn()} onDirty={vi.fn()} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Add outstanding document' }));
  fireEvent.change(screen.getByLabelText('Document reference'), { target: { value: 'INV-OLD' } });
  fireEvent.change(screen.getByLabelText('Outstanding amount (INR)'), { target: { value: '100' } });
  fireEvent.change(screen.getByLabelText('Original face amount'), { target: { value: '90' } });
  await userEvent.click(screen.getByRole('button', { name: 'Keep document' }));
  await screen.findByText('Outstanding cannot exceed the original document amount.');
  fireEvent.change(screen.getByLabelText('Original face amount'), { target: { value: '200' } });
  fireEvent.change(screen.getByLabelText('Document date'), { target: { value: '2026-01-01' } });
  fireEvent.change(screen.getByLabelText('Due date'), { target: { value: '2026-02-01' } });
  await userEvent.click(screen.getByRole('button', { name: 'Keep document' }));
  await userEvent.click(screen.getByRole('button', { name: 'Edit INV-OLD' }));
  await userEvent.click(screen.getByRole('button', { name: 'Cancel document' }));
  await userEvent.click(screen.getByRole('button', { name: 'Remove INV-OLD' }));
  expect(screen.queryByText('INV-OLD')).not.toBeInTheDocument();
});
it('creates a new balanced company declaration from authorized ledger selections', async () => {
  newCompany = true; accountKind = 'GENERAL';
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} initialAccountId={ACCOUNT} />);
  await openEntries();
  for (const side of ['DEBIT', 'CREDIT']) {
    await userEvent.click(screen.getByRole('button', { name: 'Add account balance' }));
    fireEvent.change(await screen.findByLabelText('Opening amount'), { target: { value: '100' } });
    fireEvent.change(screen.getByLabelText('Balance side'), { target: { value: side } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Keep account line' })).toBeEnabled());
    await userEvent.click(screen.getByRole('button', { name: 'Keep account line' }));
  }
  await openSource();
  fireEvent.change(screen.getByLabelText('Opening source and reason'), { target: { value: 'Initial balances from signed trial balance' } });
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getByRole('button', { name: /^Review/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
  await screen.findByText(/Preview passed/);
  await userEvent.click(screen.getByRole('button', { name: 'Save reviewed opening' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save opening' }));
  await screen.findByText('Opening worksheet saved. No balances have been posted.');
  expect(api.mock.calls.find(([, req]) => req.path.endsWith('/workspaces') && req.method === 'POST')![1]).toMatchObject({ body: { entries: [expect.objectContaining({ side: 'DEBIT', amount: '100' }), expect.objectContaining({ side: 'CREDIT', amount: '100' })] } });
});
it('preserves foreign exchange and historical carrying values as exact text', async () => {
  accountKind = 'GENERAL'; const onSave = vi.fn();
  render(<FinancialOpeningEntry company={COMPANY} declaration={declaration()} initial={line()} metadata={metadata} native={metadata.native} disabled={false} onSave={onSave} onCancel={vi.fn()} onDirty={vi.fn()} />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Keep account line' })).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Currency'), { target: { value: 'USD' } });
  fireEvent.change(screen.getByLabelText('Historical exchange rate'), { target: { value: '85.00000001' } });
  fireEvent.change(screen.getByLabelText('Base carrying value (INR)'), { target: { value: '8500.0001' } });
  fireEvent.change(screen.getByLabelText('Line description'), { target: { value: 'Preserved USD migration carry' } });
  fireEvent.change(screen.getByLabelText('Line source reference'), { target: { value: 'source-usd' } });
  await userEvent.click(screen.getByRole('button', { name: 'Keep account line' }));
  expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ currency: 'USD', amount: '100', exchange_rate: '85.00000001', base_amount: '8500.0001', source_key: 'source-usd' }));
});
it('explains retained legacy openings without offering an overwrite or a misleading error', async () => {
  legacyOpening = true;
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await screen.findByText(/This opening was recorded through the earlier company setup flow/);
  expect(screen.queryByText('use the legacy opening workflow for this batch')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Source system')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('tab', { name: 'History' }));
  await screen.findByRole('heading', { name: 'Retained company openings' });
});
const balancedHeld = () => heldPage([held(1), heldInvoice(2, { amount: '100.2500', base_amount: '100.2500' })]);
async function openWorksheetWithHeld(page: ReturnType<typeof heldPage>) {
  newCompany = true;
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => args[1].path.includes('/party-balances') ? page as never : original(...args));
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await openEntries();
}
it('adds balances held from party imports to the worksheet and sends exactly those entries to preview', async () => {
  await openWorksheetWithHeld(balancedHeld());
  expect(await screen.findByText('Balances held from party imports')).toBeVisible();
  expect(screen.getByText('Account lines').nextSibling).toHaveTextContent('0');
  await userEvent.click(screen.getByRole('button', { name: 'Add 2 held balances to this worksheet' }));
  expect(await screen.findByText(held(1).source_key)).toBeVisible();
  expect(screen.getByText(heldInvoice(2).source_key)).toBeVisible();
  expect(screen.getByText('Account lines').nextSibling).toHaveTextContent('2');
  expect(screen.getByText('Debit base total').nextSibling).toHaveTextContent('100.2500');
  expect(screen.getByText('Credit base total').nextSibling).toHaveTextContent('100.2500');
  expect(screen.queryByText('Balances held from party imports')).not.toBeInTheDocument();
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getByRole('button', { name: /^Review/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
  await waitFor(() => expect(api.mock.calls.some(call => call[1].path.endsWith('/workspaces/preview'))).toBe(true));
  const previewed = api.mock.calls.find(call => call[1].path.endsWith('/workspaces/preview'))![1].body as { entries: unknown[] };
  expect(previewed.entries).toEqual([heldEntry(held(1)), heldEntry(heldInvoice(2, { amount: '100.2500', base_amount: '100.2500' }))]);
});
it('requires balanced held lines before preview in manual mode', async () => {
  await openWorksheetWithHeld(heldPage([held(1), heldInvoice(2)]));
  await userEvent.click(await screen.findByRole('button', { name: 'Add 2 held balances to this worksheet' }));
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getByRole('button', { name: /^Review/ }));
  await userEvent.click(screen.getByRole('switch', { name: 'Prepare and post automatically' }));
  await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
  expect(await screen.findByText('Base-currency debit and credit totals must balance before preview.')).toBeVisible();
  expect(api.mock.calls.some(call => call[1].path.endsWith('/workspaces/preview'))).toBe(false);
});
