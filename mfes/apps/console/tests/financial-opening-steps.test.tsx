import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { StrictMode } from 'react';
import { FinancialOpeningWorkspace } from '../app/components/FinancialOpeningWorkspace';
import { FinancialOpeningAutomatic } from '../app/components/FinancialOpeningAutomatic';
import { serviceCall } from '../app/lib/service-call';
import { ACCOUNT, OTHER, BATCH, COMPANY, JOURNAL, access, metadata, page, readiness, workspace, declaration } from './financial-opening-fixtures';
import { OFFSET_SOURCE } from '../app/lib/financial-opening-worksheet';
import { sum, type Declaration, type Workspace } from '../app/lib/financial-opening';

vi.mock('../app/lib/service-call', async original => ({ ...(await original<typeof import('../app/lib/service-call')>()), serviceCall: vi.fn() }));
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn((service: string, method: string, path: string) => serviceCall('/api/product-fields', { service, method, path }, 'opening references')) }));
const api = vi.mocked(serviceCall);
const OFFSET = '01990000-0000-7000-8000-000000000020', GROUP = '01990000-0000-7000-8000-000000000021', HEAD = '01990000-0000-7000-8000-000000000022';
const account = (id: string, name: string) => ({ id, company_id: COMPANY, name, code: name.toUpperCase(), kind: 'PARTY', party_role: 'CUSTOMER', status: 'ACTIVE', currency_mode: 'BASE' });
const offset = { ...account(OFFSET, 'Opening Balance Offset'), code: 'OPENING_BALANCE_OFFSET', kind: 'GENERAL', group_id: GROUP, posting_policy: 'MANUAL_ALLOWED' };
let saved: Declaration | null, current: Workspace, posted: boolean, timeout: boolean, confirmationPending: boolean, finalizeTimeout: boolean, missingDefaults: boolean, setupTimeout: boolean;
const reconciliation = () => ({ batch_id: BATCH, revision_id: current.revision_id, posting_date: current.posting_date,
  currency: current.currency, coverage_mode: current.coverage_mode, expected_debit: current.expected_debit, expected_credit: current.expected_credit,
  posted_debit: current.expected_debit, posted_credit: current.expected_credit, declared_documents: current.document_count, posted_documents: current.document_count,
  gl_matches: true, party_items_match: true, clearing_balance: '0', confirmation_pending: confirmationPending,
  blockers: confirmationPending ? ['NATIVE_CONFIRMATION_PENDING'] : [], ready_to_finalize: posted && !confirmationPending && current.status === 'DRAFT' });
beforeEach(() => {
  saved = null; current = structuredClone(workspace); posted = false; timeout = false; confirmationPending = false; finalizeTimeout = false; missingDefaults = false; setupTimeout = false; api.mockReset();
  api.mockImplementation(async (_endpoint, req) => {
    const url = new URL(req.path, 'https://accounting.test');
    if (url.pathname.endsWith('/readiness')) return { ...readiness, batch_id: saved ? BATCH : null, can_prepare: !saved, status: saved ? 'DRAFT' : 'NOT_STARTED' } as never;
    if (url.pathname.endsWith('/workspaces/field-set')) return metadata as never;
    if (url.pathname.includes('/finance/field-sets/')) return { fields: [] } as never;
    if (url.pathname.endsWith('/accounts')) {
      if (url.searchParams.get('code')) return { items: !missingDefaults && url.searchParams.get('code') === offset.code ? [offset] : [], page } as never;
      const query = url.searchParams.get('q');
      return { items: query ? [account(OTHER, 'Beta')] : url.searchParams.get('cursor') ? [account(OTHER, 'Beta')] : [account(ACCOUNT, 'Alpha')], page: { ...page, has_more: !query && !url.searchParams.get('cursor'), next_cursor: !query && !url.searchParams.get('cursor') ? 'page-2' : null } } as never;
    }
    if (url.pathname.endsWith('/accounts/' + OFFSET)) return offset as never;
    if (url.pathname.includes('/accounts/')) return account(url.pathname.split('/').at(-1)!, 'Alpha') as never;
    if (url.pathname.endsWith('/account-groups')) return { items: [{ id: GROUP, company_id: COMPANY, name: 'Capital', code: 'CAPITAL' }], page } as never;
    if (url.pathname.endsWith('/account-groups/' + GROUP)) return { id: GROUP, company_id: COMPANY, name: 'Capital', code: 'CAPITAL', head_id: HEAD } as never;
    if (url.pathname.endsWith('/account-heads/' + HEAD)) return { id: HEAD, company_id: COMPANY, nature: 'EQUITY' } as never;
    if (url.pathname.endsWith('/accounting-setup/initialize')) {
      missingDefaults = false;
      if (setupTimeout) { setupTimeout = false; throw { status: 503, message: 'Setup reply interrupted.' }; }
      return { id: HEAD, company_id: COMPANY, row_version: 1 } as never;
    }
    if (url.pathname.endsWith('/workspaces/preview')) {
      const body = req.body as Declaration;
      return { company_id: COMPANY, manifest_hash: current.manifest_hash, posting_date: body.posting_date, entry_count: body.entries.length, document_count: 1, journal_count: 1 } as never;
    }
    if (url.pathname.endsWith('/workspaces') && req.method === 'POST') {
      saved = req.body as Declaration;
      current = { ...current, entry_count: saved.entries.length, document_count: saved.entries.reduce((n, row) => n + (row.documents?.length ?? 0), 0),
        expected_debit: sum(saved.entries.filter(row => row.side === 'DEBIT').map(row => row.base_amount!)), expected_credit: sum(saved.entries.filter(row => row.side === 'CREDIT').map(row => row.base_amount!)) };
      return current as never;
    }
    if (url.pathname.includes('/revisions/')) return saved as never;
    if (url.pathname.endsWith('/prepare-drafts')) { current = { ...current, expected_version: 2, journal_ids: [JOURNAL], blockers: [] }; return current as never; }
    if (url.pathname.endsWith('/journals/' + JOURNAL + '/post')) {
      posted = true; current = { ...current, posted_journals: 1, effect_kind: 'POSTED' };
      if (timeout) { timeout = false; throw { status: 503, message: 'Posting reply interrupted.' }; }
      return { id: JOURNAL, company_id: COMPANY, row_version: 2, kind: 'OPENING', source_type: 'financial_opening_chunk', status: 'POSTED' } as never;
    }
    if (url.pathname.endsWith('/journals/' + JOURNAL)) return { id: JOURNAL, company_id: COMPANY, row_version: posted ? 2 : 1, kind: 'OPENING', source_type: 'financial_opening_chunk', status: posted ? 'POSTED' : 'DRAFT' } as never;
    if (url.pathname.endsWith('/reconciliation')) return reconciliation() as never;
    if (url.pathname.endsWith('/finalize')) {
      current = { ...current, status: 'FINALIZED', expected_version: current.expected_version + 1 };
      if (finalizeTimeout) { finalizeTimeout = false; throw { status: 503, message: 'Finalization reply interrupted.' }; }
      return current as never;
    }
    if (url.search) return { items: [], page } as never;
    return current as never;
  });
});
async function entries() {
  await screen.findByRole('radio', { name: /Buyer/ });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Next step' })).toBeEnabled());
  await userEvent.click(screen.getByRole('button', { name: 'Next step' }));
  return screen.findByLabelText('Opening for Alpha');
}
it('starts with only account selection and requires one group for Other Accounts', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await userEvent.click(await screen.findByRole('radio', { name: /Other Accounts/ }));
  expect(screen.getByRole('combobox', { name: /Account group/ })).toBeVisible();
  expect(screen.queryByLabelText('Source system')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /^Enter openings/ }));
  expect(await screen.findByText('Select one account group before continuing.')).toBeVisible();
  expect(screen.queryByLabelText('Quick account search')).not.toBeInTheDocument();
});
it('moves keyboard focus to the new step and keeps generated source details out of the primary review', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  fireEvent.change(await entries(), { target: { value: '10' } });
  expect(screen.getByRole('heading', { name: 'Enter opening balances' })).toHaveFocus();
  await userEvent.click(screen.getByRole('button', { name: 'Next step' }));
  expect(screen.queryByRole('button', { name: 'Next step' })).not.toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Opening source and settings' })).toHaveFocus();
  expect(screen.getByLabelText('Historical reporting')).toBeVisible();
  const source = screen.getByLabelText('Source system');
  expect(source.closest('details')).not.toHaveAttribute('open');
  await userEvent.click(screen.getByText('View automatically filled source details'));
  expect(source).toBeVisible();
  expect(source).toHaveAttribute('readonly');
  expect(api.mock.calls.some(([, req]) => req.method === 'POST')).toBe(false);
});
it('retains edits across server pages and quick search, and rejects invalid values before step three', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  fireEvent.change(await entries(), { target: { value: '-2' } });
  expect(screen.getByLabelText('Opening date for Alpha')).toHaveValue('2026-04-01');
  expect(screen.getByLabelText('Opening date for Alpha')).toHaveAttribute('readonly');
  await userEvent.click(screen.getByRole('button', { name: 'Next step' }));
  expect(await screen.findByText(/Enter positive amounts/)).toBeVisible();
  expect(screen.queryByLabelText('Source system')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Opening for Alpha'), { target: { value: '125.1234' } });
  await userEvent.click(screen.getByRole('button', { name: 'Next page of accounts' }));
  await screen.findByLabelText('Opening for Beta');
  await userEvent.click(screen.getByRole('button', { name: 'Previous page of accounts' }));
  expect(await screen.findByLabelText('Opening for Alpha')).toHaveValue('125.1234');
  fireEvent.change(screen.getByLabelText('Quick account search'), { target: { value: 'Be' } });
  await screen.findByLabelText('Opening for Beta');
  expect(api.mock.calls.some(([, req]) => req.path.includes('sort=name') && req.path.includes('role=CUSTOMER') && req.path.includes('q=Be') && !req.path.includes('cursor='))).toBe(true);
  fireEvent.change(screen.getByLabelText('Quick account search'), { target: { value: '' } });
  expect(await screen.findByLabelText('Opening for Alpha')).toHaveValue('125.1234');
});
it('filters Other Accounts to one selected group and retains its label when returning to the first step', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await userEvent.click(await screen.findByRole('radio', { name: /Other Accounts/ }));
  await userEvent.click(screen.getByRole('combobox', { name: /Account group/ }));
  await userEvent.click(await screen.findByRole('option', { name: /Capital/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Next step' }));
  await screen.findByLabelText('Opening for Alpha');
  expect(api.mock.calls.some(([, req]) => req.path.includes('group_id=' + GROUP) && req.path.includes('sort=name'))).toBe(true);
  await userEvent.click(screen.getByRole('button', { name: 'Previous step' }));
  await waitFor(() => expect(screen.getByRole('combobox', { name: /Account group/ })).toHaveValue('Capital'));
});
it('shows automatic readonly defaults, discloses the offset and posts only after explicit review and confirmation', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  fireEvent.change(await entries(), { target: { value: '125.1234' } });
  await userEvent.click(screen.getByRole('button', { name: 'Next step' }));
  expect(await screen.findByLabelText('Source system')).toHaveAttribute('readonly');
  expect(screen.getByLabelText('Opening source and reason')).toHaveValue('Opening balances entered in the account opening worksheet.');
  expect(screen.getByText('125.1234 INR Cr')).toBeVisible();
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/post'))).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
  await screen.findByText(/Preview passed/);
  expect(screen.getByRole('button', { name: 'Prepare and post opening' })).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox', { name: /I reviewed the opening amounts/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Prepare and post opening' }));
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/post'))).toBe(false);
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Prepare and post' }));
  await screen.findByText(/Opening posted, reconciled and finalized/);
  await screen.findByRole('heading', { name: 'Financial opening complete' });
  expect(screen.queryByLabelText('Action review reason')).not.toBeInTheDocument();
  expect(screen.getByText(/All opening journals are posted/)).toBeVisible();
  expect(screen.getByText('Related bank and inventory workflows')).toBeVisible();
  expect(saved?.entries).toHaveLength(2);
  expect(saved?.entries[1]).toMatchObject({ source_key: OFFSET_SOURCE, account_id: OFFSET, side: 'CREDIT', amount: '125.1234' });
  expect(api.mock.calls.filter(([, req]) => req.path.endsWith('/post'))).toHaveLength(1);
  expect(api.mock.calls.filter(([, req]) => req.path.endsWith('/finalize'))).toHaveLength(1);
  expect(current.status).toBe('FINALIZED');
});
it('makes source controls editable in manual mode and keeps posting permission separate', async () => {
  render(<FinancialOpeningWorkspace company={COMPANY} access={{ ...access, post: false }} />);
  fireEvent.change(await entries(), { target: { value: '30' } });
  await userEvent.click(screen.getByRole('button', { name: 'Next step' }));
  expect(await screen.findByRole('button', { name: 'Prepare and post opening' })).toBeDisabled();
  await userEvent.click(screen.getByRole('switch', { name: 'Prepare and post automatically' }));
  expect(screen.getByLabelText('Source system')).not.toHaveAttribute('readonly');
  expect(screen.getByRole('combobox', { name: 'Migration clearing account' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Save reviewed opening' })).toBeDisabled();
});
it('requires the saved receipt to match the reviewed declaration before automatic posting', async () => {
  const original = api.getMockImplementation()!; let mismatch = true;
  api.mockImplementation(async (...args) => {
    const result = await original(...args);
    if (args[1].path.endsWith('/workspaces') && args[1].method === 'POST' && mismatch) {
      mismatch = false; return { ...(result as Workspace), manifest_hash: 'b'.repeat(64) } as never;
    }
    return result;
  });
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  fireEvent.change(await entries(), { target: { value: '30' } });
  await userEvent.click(screen.getByRole('button', { name: 'Next step' }));
  await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
  await screen.findByText(/Preview passed/);
  await userEvent.click(screen.getByRole('checkbox', { name: /I reviewed the opening amounts/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Prepare and post opening' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Prepare and post' }));
  await screen.findAllByText(/saved opening does not match the reviewed preview/);
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/post') || req.path.endsWith('/prepare-drafts'))).toBe(false);
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Retry the same request' }));
  await screen.findByRole('heading', { name: 'Financial opening complete' });
  const saves = api.mock.calls.filter(([, req]) => req.path.endsWith('/workspaces') && req.method === 'POST').map(([, req]) => req);
  expect(saves).toHaveLength(2); expect(saves[1]).toEqual(saves[0]);
});
it.each([false, true])('sets up missing opening accounts during review without leaving the worksheet (interrupted: %s)', async interrupted => {
  missingDefaults = true; setupTimeout = interrupted;
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  fireEvent.change(await entries(), { target: { value: '25.1234' } });
  await userEvent.click(screen.getByRole('button', { name: 'Next step' }));
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/accounting-setup/initialize'))).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
  if (interrupted) {
    await screen.findByText(/Setup reply interrupted/);
    expect(screen.getByLabelText('Source system')).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Retry opening account setup' }));
  }
  await screen.findByText(/Preview passed/);
  expect(screen.getByText('25.1234 INR Cr')).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Review company setup' })).not.toBeInTheDocument();
  const setups = api.mock.calls.filter(([, req]) => req.path.endsWith('/accounting-setup/initialize')).map(([, req]) => req);
  expect(setups).toHaveLength(interrupted ? 2 : 1);
  if (interrupted) expect(setups[1]).toEqual(setups[0]);
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/post'))).toBe(false);
});
it('replays an uncertain journal post with the identical key and body, then resumes confirmed progress', async () => {
  current = { ...workspace, journal_ids: [JOURNAL] }; saved = declaration(); timeout = true;
  const done = vi.fn();
  render(<FinancialOpeningAutomatic company={COMPANY} initial={current} access={access} reason="Reviewed opening" onDirty={vi.fn()} onDone={done} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Retry the same request' }));
  await waitFor(() => expect(done).toHaveBeenCalledWith(true));
  const posts = api.mock.calls.filter(([, req]) => req.path.endsWith('/post')).map(([, req]) => req);
  expect(posts).toHaveLength(2); expect(posts[1]).toEqual(posts[0]);
});
it('retains the preparation request when its receipt names a different revision', async () => {
  const original = api.getMockImplementation()!; let mismatch = true;
  api.mockImplementation(async (...args) => {
    const result = await original(...args);
    if (args[1].path.endsWith('/prepare-drafts') && mismatch) { mismatch = false; return { ...(result as Workspace), revision_id: ACCOUNT } as never; }
    return result;
  });
  const done = vi.fn();
  render(<FinancialOpeningAutomatic company={COMPANY} initial={current} access={access} reason="Reviewed opening" onDirty={vi.fn()} onDone={done} />);
  await screen.findByRole('button', { name: 'Retry the same request' });
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/post'))).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Retry the same request' }));
  await waitFor(() => expect(done).toHaveBeenCalledWith(true));
  const preparations = api.mock.calls.filter(([, req]) => req.path.endsWith('/prepare-drafts')).map(([, req]) => req);
  expect(preparations).toHaveLength(2); expect(preparations[1]).toEqual(preparations[0]);
});
it('stops automatic posting if the saved declaration changes or current company cannot be verified', async () => {
  const initial = { ...workspace, journal_ids: [JOURNAL] };
  current = { ...initial, manifest_hash: 'c'.repeat(64) };
  render(<FinancialOpeningAutomatic company={COMPANY} initial={initial} access={access} reason="Reviewed opening" onDirty={vi.fn()} onDone={vi.fn()} />);
  await screen.findByText(/The opening changed/);
  expect(api.mock.calls.some(([, req]) => req.method === 'POST')).toBe(false);
});
it('never starts automatic commands without journal posting authority', async () => {
  render(<FinancialOpeningAutomatic company={COMPANY} initial={workspace} access={{ ...access, post: false }} reason="Reviewed opening" onDirty={vi.fn()} onDone={vi.fn()} />);
  expect(screen.getByRole('button', { name: 'Continue automatic opening' })).toBeDisabled();
  expect(api).not.toHaveBeenCalled();
});

it('waits for native confirmation and finalizes on this page without asking for another action', async () => {
  current = { ...workspace, journal_ids: [JOURNAL] }; confirmationPending = true;
  const done = vi.fn();
  render(<FinancialOpeningAutomatic company={COMPANY} initial={current} access={access} reason="Reviewed opening" onDirty={vi.fn()} onDone={done} />);
  await screen.findByText(/Waiting for posting confirmation/);
  expect(done).not.toHaveBeenCalled();
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/finalize'))).toBe(false);
  confirmationPending = false;
  await waitFor(() => expect(done).toHaveBeenCalledWith(true), { timeout: 5000 });
  expect(api.mock.calls.filter(([, req]) => req.path.endsWith('/post'))).toHaveLength(1);
  expect(current.status).toBe('FINALIZED');
});
it('replays uncertain finalization with exactly the same key and body before declaring completion', async () => {
  current = { ...workspace, journal_ids: [JOURNAL] }; finalizeTimeout = true;
  const done = vi.fn();
  render(<FinancialOpeningAutomatic company={COMPANY} initial={current} access={access} reason="Reviewed opening" onDirty={vi.fn()} onDone={done} />);
  await screen.findByText('Finalization reply interrupted.');
  expect(done).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Retry the same request' }));
  await waitFor(() => expect(done).toHaveBeenCalledWith(true));
  const finalizations = api.mock.calls.filter(([, req]) => req.path.endsWith('/finalize')).map(([, req]) => req);
  expect(finalizations).toHaveLength(2); expect(finalizations[1]).toEqual(finalizations[0]);
  expect(api.mock.calls.filter(([, req]) => req.path.endsWith('/post'))).toHaveLength(1);
});
it('completes a saved opening from this page after reloading, without reposting confirmed journals', async () => {
  saved = declaration(); posted = true;
  current = { ...workspace, journal_ids: [JOURNAL], posted_journals: 1, effect_kind: 'POSTED' };
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  await userEvent.click(await screen.findByRole('tab', { name: 'Posting and completion' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Complete opening automatically' }));
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/finalize'))).toBe(false);
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Prepare and post' }));
  await screen.findByRole('heading', { name: 'Financial opening complete' });
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/post'))).toBe(false);
  const finalized = api.mock.calls.find(([, req]) => req.path.endsWith('/finalize'));
  expect(finalized?.[1].body).toMatchObject({ reason: saved.reason });
});
it('runs once under StrictMode and reconciles aggregate totals larger than a single account amount', async () => {
  current = { ...workspace, journal_ids: [JOURNAL], expected_debit: '1999999999999999.9998', expected_credit: '1999999999999999.9998' };
  const done = vi.fn();
  render(<StrictMode><FinancialOpeningAutomatic company={COMPANY} initial={current} access={access} reason="Reviewed opening" onDirty={vi.fn()} onDone={done} /></StrictMode>);
  await waitFor(() => expect(done).toHaveBeenCalledWith(true));
  expect(done).toHaveBeenCalledTimes(1);
  expect(api.mock.calls.filter(([, req]) => req.path.endsWith('/post'))).toHaveLength(1);
  expect(api.mock.calls.filter(([, req]) => req.path.endsWith('/finalize'))).toHaveLength(1);
});
it('stops further commands if the opening screen unmounts during a status read', async () => {
  current = { ...workspace, journal_ids: [JOURNAL] };
  let resolve!: (value: never) => void;
  api.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  const done = vi.fn();
  const view = render(<FinancialOpeningAutomatic company={COMPANY} initial={current} access={access} reason="Reviewed opening" onDirty={vi.fn()} onDone={done} />);
  view.unmount(); resolve(current as never);
  await Promise.resolve(); await Promise.resolve();
  expect(api.mock.calls.some(([, req]) => req.method === 'POST')).toBe(false);
  expect(done).not.toHaveBeenCalled();
});
it.each([
  { revision_id: ACCOUNT },
  { posted_debit: '99' },
  { posted_documents: 2 },
  { clearing_balance: '0.0001' },
  { gl_matches: false, blockers: ['DECLARATION_GL_DIFFERENCE'] },
])('does not finalize inconsistent reconciliation evidence: %j', async mismatch => {
  current = { ...workspace, journal_ids: [JOURNAL] };
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => args[1].path.endsWith('/reconciliation') ? { ...reconciliation(), ...mismatch } as never : original(...args));
  const done = vi.fn();
  render(<FinancialOpeningAutomatic company={COMPANY} initial={current} access={access} reason="Reviewed opening" onDirty={vi.fn()} onDone={done} />);
  await screen.findByRole('alert');
  expect(done).not.toHaveBeenCalled();
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/finalize'))).toBe(false);
  expect(screen.getByRole('button', { name: 'Continue automatic opening' })).toBeEnabled();
});
it('disables inline amount capture when native journal or outstanding permissions deny it', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => args[1].path.endsWith('/workspaces/field-set') ? { ...metadata, capture_permissions: { ...metadata.capture_permissions, open_items: { ...metadata.capture_permissions.open_items, amount: false } } } as never : original(...args));
  render(<FinancialOpeningWorkspace company={COMPANY} access={access} />);
  expect(await entries()).toBeDisabled();
});
