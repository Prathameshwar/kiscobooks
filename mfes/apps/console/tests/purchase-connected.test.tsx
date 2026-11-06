import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseEntryConnected } from '../app/components/PurchaseEntryConnected';
import { serviceCall } from '../app/lib/service-call';
import { purchaseSource, supplierPayables } from '../app/lib/purchase-entry';
import { company, draft as sources, metadata as fixture } from './purchase-entry-fixtures';
import type { PurchaseWorkspaceController } from '../app/components/PurchaseWorkspace';
import type { FieldSet } from '../app/lib/voucher-fields';
vi.mock('../app/lib/service-call', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/purchase-entry', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/purchase-entry')>(), purchaseSource: vi.fn(), supplierPayables: vi.fn(), purchaseLookup: vi.fn(() => vi.fn()) }));
vi.mock('../app/components/PurchaseWorkspace', () => ({ PurchaseWorkspace: ({ controller: c }: { controller: PurchaseWorkspaceController }) => <section>{c.header}{c.banner(null)}{c.reviewNotice}
  <button onClick={() => c.dispatch({ type: 'supplier', value: sources.party!.id, policy: {} as never })}>Choose supplier</button>
  <button onClick={() => c.dispatch({ type: 'subject', key: c.draft.lines[0]!.key, subject: { id: sources.supplies[0]!.account!.id, label: 'Expense', kind: 'ACCOUNT', unit: '', meta: '' } })}>Choose expense</button>
  <input aria-label="Invoice" value={c.draft.invoice} onChange={e => c.dispatch({ type: 'header', field: 'invoice', value: e.target.value })} />
  <input aria-label="Amount" value={c.draft.lines[0]!.amount} onChange={e => c.dispatch({ type: 'line', key: c.draft.lines[0]!.key, patch: { amount: e.target.value } })} />
  <span>{c.note}</span>{c.sections}{c.actions({ validate: () => true, review: () => undefined })}</section> }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const base = '/v1/companies/' + company;
const props = { company, currency: 'INR', actor: id(12), year: id(13), canCreate: true, permissions: ['vouchers.read', 'vouchers.create', 'vouchers.edit', 'vouchers.submit', 'vouchers.approve', 'vouchers.reject', 'vouchers.cancel'] };
let metadata: FieldSet, saved: Record<string, unknown>, writes: { request: import('../app/lib/service-call').ServiceRequest }[];
beforeEach(() => {
  sessionStorage.clear(); vi.mocked(serviceCall).mockReset(); vi.mocked(purchaseSource).mockReset(); vi.mocked(supplierPayables).mockReset(); writes = [];
  metadata = structuredClone(fixture); Object.assign(metadata.native.properties!, Object.fromEntries(['document_date', 'currency', 'narration', 'mode', 'lines', 'attachments', 'links', 'custom_fields'].map(key => [key, {}])));
  saved = {};
  vi.mocked(purchaseSource).mockImplementation(async (_company, resource) => resource === 'suppliers' ? sources.party! : resource === 'payables' ? sources.payable! : sources.supplies[0]!.account!);
  // Choosing a supplier reads its one payable account (a supplier is never asked for it); `purchase-supplier-account` holds the real read.
  vi.mocked(supplierPayables).mockImplementation(async () => [sources.payable!]);
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('/voucher-types?')) return { items: [{ id: id(2), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', name: 'Account purchases' }], page: { next_cursor: null } };
    if (request.path.endsWith('/voucher-capabilities')) return { financial_execution: false, invoice_execution: false, kinds: [{ kind: 'PURCHASE', execution_ready: false }] };
    if (request.path.includes('/field-set')) return metadata;
    if (request.service === 'accounting') {
      return { id: request.path.split('/').at(-1), company_id: company, name: request.path.includes('/parties/') ? 'Supplier' : 'Expense' };
    }
    if (request.path.endsWith('/invoice-preview')) return { calculation_version: 1, calculation_hash: 'a'.repeat(64), currency: 'INR', commercial_total: '42.1234', tax_total: '0.0000', charged_tax_total: '0.0000', rounding: '-0.0034', payable: '42.1200', supplier_difference: null, lines: [], components: [], allocations: [], tax_evidence: [] };
    if (request.method === 'POST' || request.method === 'PUT') {
      writes.push({ request: structuredClone(request) });
      const body = request.body as Record<string, unknown>;
      if (request.path.endsWith('/invoice-acceptance')) saved = { ...saved, row_version: Number(saved.row_version) + 1, revision_number: Number(saved.revision_number) + 1, revision_id: id(93), invoice: { ...(saved.invoice as object), accepted_calculation_hash: body.calculation_hash } };
      else if (request.path.endsWith('/submit') || request.path.endsWith('/approve')) saved = { ...saved, row_version: Number(saved.row_version) + 1, status: request.path.endsWith('/submit') ? 'SUBMITTED' : 'APPROVED' };
      else saved = { ...((body.content ?? body) as object), id: id(90), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', status: 'DRAFT', row_version: 7, revision_number: 3, revision_id: id(91), lines: [], attachments: [], links: [], custom_fields: {} };
      return saved;
    }
    if (request.path.includes('/vouchers/')) return saved;
    throw Error('Unexpected test route ' + request.path);
  });
});
async function enter() {
  await screen.findByRole('heading', { name: 'New purchase' });
  // The heading is there before the configuration has loaded; the workspace follows.
  fireEvent.click(await screen.findByRole('button', { name: 'Choose supplier' }));
  await waitFor(() => expect(supplierPayables).toHaveBeenCalledWith(company, sources.party!.id));
  await waitFor(() => expect(screen.getByRole('button', { name: /^(Create|Update)$/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button', { name: 'Choose expense' }));
  await waitFor(() => expect(purchaseSource).toHaveBeenCalledWith(company, 'expenses', sources.supplies[0]!.account!.id));
  await waitFor(() => expect(screen.getByRole('button', { name: /^(Create|Update)$/ })).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText('Invoice'), { target: { value: 'SUP-NEW' } });
  fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '42.1234' } });
  fireEvent.click(screen.getByRole('checkbox', { name: 'This bill carries no tax' }));
}
it('locks writes when a retained execution cannot be verified after reload', async () => {
  const scope = JSON.stringify([props.actor, company, props.year]);
  sessionStorage.setItem('purchase-api-operation:' + scope, JSON.stringify({ id: id(80), voucherId: id(90), revisionId: id(91) }));
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].path.includes('/voucher-operations/')) throw { status: 403, message: 'Execution access denied' }; return original(...args); });
  render(<PurchaseEntryConnected {...props} />); await screen.findByText('Execution access denied');
  expect(screen.getByRole('button', { name: /^(Create|Update)$/ })).toBeDisabled();
});
it('opens the exact purchase type without a bounded type-list selection', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path === base + '/voucher-types/' + id(2)
    ? { id: id(2), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', status: 'ACTIVE', name: 'Specific supplier bills' }
    : original(...args));
  render(<PurchaseEntryConnected {...props} initialTypeId={id(2)} />);
  await screen.findByRole('button', { name: 'Choose supplier' });
  expect(vi.mocked(serviceCall).mock.calls.some(call => call[1].path.includes('/voucher-types?'))).toBe(false);
  expect(vi.mocked(serviceCall).mock.calls.some(call => call[1].path.includes('/voucher-types/' + id(2) + '/field-set?'))).toBe(true);
});
it.each([['foreign', id(40), 'ACTIVE'], ['retired', company, 'RETIRED'], ['wrong identity', company, 'ACTIVE']])('refuses the %s selected purchase type', async (reason, owner, status) => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path === base + '/voucher-types/' + id(2)
    ? { id: reason === 'wrong identity' ? id(40) : id(2), company_id: owner, kind: 'PURCHASE', profile: 'STANDARD', status }
    : original(...args));
  render(<PurchaseEntryConnected {...props} initialTypeId={id(2)} />);
  await screen.findByText(reason === 'foreign' ? 'Purchase configuration could not be verified.' : 'The selected purchase type is unavailable for this company.');
  expect(screen.queryByRole('button', { name: 'Choose supplier' })).not.toBeInTheDocument();
});
it('creates a real draft, previews saved version, accepts a new revision, then submits that returned version', async () => {
  render(<PurchaseEntryConnected {...props} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
  await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  expect(writes[0]!.request).toMatchObject({ path: base + '/vouchers', method: 'POST', body: { invoice: { supplies: [{ amount: '42.1234', account_version: 4 }] } } });
  fireEvent.click(screen.getByRole('button', { name: 'Calculate saved bill' })); await screen.findByRole('button', { name: 'Accept Accounting calculation' });
  fireEvent.click(screen.getByRole('button', { name: 'Accept Accounting calculation' })); await screen.findByRole('heading', { name: 'Purchase bill · revision 4' });
  expect(writes[1]!.request.body).toEqual({ expected_version: 7, calculation_hash: 'a'.repeat(64) });
  fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
  await waitFor(() => expect(writes[2]?.request.body).toEqual({ expected_version: 8 }));
  await screen.findByText(/Purchase submitted for approval. It has not been posted/);
});
it('requires explicit untaxed confirmation before sending a draft', async () => {
  render(<PurchaseEntryConnected {...props} />); await enter(); fireEvent.click(screen.getByRole('checkbox', { name: 'This bill carries no tax' }));
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByText(/Confirm that this is an untaxed/); expect(writes).toHaveLength(0);
});
it('offers Print for the last saved revision, and blocks it while there are unsaved edits', async () => {
  render(<PurchaseEntryConnected {...props} permissions={[...props.permissions, 'vouchers.artifact.create', 'vouchers.artifact.read', 'accounting.account.read']} />); await enter();
  expect(screen.queryByText('Print')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  expect(screen.getByRole('link', { name: 'Print' })).toHaveAttribute('href', `/vouchers/${id(90)}/print?revision=${id(91)}&version=7`);
  fireEvent.change(screen.getByLabelText('Invoice'), { target: { value: 'SUP-EDITED' } });
  expect(screen.queryByRole('link', { name: 'Print' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Print' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Print' })).toHaveAccessibleDescription(/Save your changes before printing/);
});
it.each([['vouchers.artifact.read'], ['accounting.account.read']])('does not offer Print without %s, even for a saved bill', async missing => {
  const permissions = [...props.permissions, 'vouchers.artifact.create', 'vouchers.artifact.read', 'accounting.account.read'].filter(permission => permission !== missing);
  render(<PurchaseEntryConnected {...props} permissions={permissions} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  expect(screen.queryByText('Print')).toBeNull();
});
it('says what the service said for a conflict, and keeps the stale-version wording for a stale version', { timeout: 20000 }, async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  let message = 'refresh fiscal evidence and open the posting period';
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    if (args[1].method === 'POST' && args[1].path === base + '/vouchers') throw { status: 409, message };
    return original(...args);
  });
  render(<PurchaseEntryConnected {...props} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
  expect(await screen.findByText('refresh fiscal evidence and open the posting period')).toBeVisible();
  expect(screen.queryByText(/changed elsewhere/)).toBeNull();
  message = 'voucher version changed; reload before retrying';
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
  expect(await screen.findByText(/This Purchase changed elsewhere/)).toBeVisible();
});
it('keeps the invoice number and supplier in the action bar note, so they stay in view on a long bill', async () => {
  render(<PurchaseEntryConnected {...props} />); await enter();
  expect(screen.getByText(/SUP-NEW · Supplier · Unsaved changes/)).toBeVisible();
});
it('does not carry a spent action reason into a later save', { timeout: 20000 }, async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    const request = args[1];
    if (request.path.endsWith('/reject')) { writes.push({ request: structuredClone(request) }); saved = { ...saved, status: 'REJECTED', row_version: Number(saved.row_version) + 1 }; return saved; }
    return original(...args);
  });
  render(<PurchaseEntryConnected {...props} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  fireEvent.click(screen.getByRole('button', { name: 'Calculate saved bill' })); await screen.findByRole('button', { name: 'Accept Accounting calculation' });
  fireEvent.click(screen.getByRole('button', { name: 'Accept Accounting calculation' })); await screen.findByRole('heading', { name: 'Purchase bill · revision 4' });
  fireEvent.click(screen.getByRole('button', { name: 'Submit' })); await screen.findByRole('button', { name: 'Reject' });
  fireEvent.change(screen.getByLabelText('Action reason'), { target: { value: 'Wrong supplier on the bill' } });
  fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
  await waitFor(() => expect(writes.find(row => row.request.path.endsWith('/reject'))?.request.body).toMatchObject({ reason: 'Wrong supplier on the bill' }));
  // A rejected bill can still be cancelled, so the field stays, but what was typed for the rejection is spent: it is empty, and is not sent.
  await waitFor(() => expect(screen.getByLabelText('Action reason')).toHaveValue(''));
  fireEvent.change(screen.getByLabelText('Invoice'), { target: { value: 'SUP-FIXED' } });
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
  await waitFor(() => expect(writes.at(-1)?.request.method).toBe('PUT'));
  expect(writes.at(-1)!.request.body).not.toHaveProperty('reason');
});
it('does not send Purchase cancellation until the confirmation is accepted', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    if (args[1].path.endsWith('/cancel')) {
      writes.push({ request: structuredClone(args[1]) });
      saved = { ...saved, status: 'CANCELLED', row_version: Number(saved.row_version) + 1 };
      return saved;
    }
    return original(...args);
  });
  render(<PurchaseEntryConnected {...props} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
  await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  fireEvent.change(screen.getByLabelText('Action reason'), { target: { value: 'Entered twice by mistake' } });
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.getByRole('dialog', { name: 'Cancel this Purchase bill?' })).toBeVisible();
  expect(screen.getByRole('dialog', { name: 'Cancel this Purchase bill?' })).toHaveTextContent('Supplier invoice: SUP-NEW');
  expect(writes.some(row => row.request.path.endsWith('/cancel'))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Keep bill' }));
  expect(writes.some(row => row.request.path.endsWith('/cancel'))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  fireEvent.click(screen.getByRole('button', { name: 'Cancel Purchase' }));
  await waitFor(() => expect(writes.find(row => row.request.path.endsWith('/cancel'))?.request.body).toMatchObject({ reason: 'Entered twice by mistake' }));
});
it('keeps accepted posting pending, recovers the same operation and waits for reconciled POSTED', { timeout: 20000 }, async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  let status = 'PENDING', version = 1;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    const request = args[1];
    if (request.path.endsWith('/voucher-capabilities')) return { financial_execution: false, invoice_execution: true, kinds: [{ kind: 'PURCHASE', execution_ready: true }] };
    if (request.path.endsWith('/post')) { writes.push({ request: structuredClone(request) }); return { operation_id: id(80), voucher_id: id(90), status, row_version: version }; }
    if (request.path.endsWith('/recover')) { writes.push({ request: structuredClone(request) }); version++; return { id: id(80), status, row_version: version }; }
    if (request.path.endsWith('/voucher-operations/' + id(80))) return { id: id(80), voucher_id: id(90), revision_id: id(93), status, row_version: version };
    return original(...args);
  });
  render(<PurchaseEntryConnected {...props} permissions={[...props.permissions, 'vouchers.post', 'vouchers.operation.read', 'vouchers.operation.recover']} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  fireEvent.click(screen.getByRole('button', { name: 'Calculate saved bill' })); await screen.findByRole('button', { name: 'Accept Accounting calculation' });
  fireEvent.click(screen.getByRole('button', { name: 'Accept Accounting calculation' })); await screen.findByRole('heading', { name: 'Purchase bill · revision 4' });
  fireEvent.click(screen.getByRole('button', { name: 'Submit' })); await screen.findByRole('button', { name: 'Approve' });
  fireEvent.click(screen.getByRole('button', { name: 'Approve' })); await screen.findByRole('button', { name: 'Post approved Purchase' });
  fireEvent.click(screen.getByRole('button', { name: 'Post approved Purchase' })); await screen.findByText('PENDING');
  expect(screen.queryByText(/Posted Purchase is retained/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Retry execution delivery' }));
  await waitFor(() => expect(writes.find(row => row.request.path.endsWith('/recover'))?.request.body).toEqual({ expected_version: 1 }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh Purchase execution' })).not.toBeDisabled());
  status = 'COMMITTED'; saved = { ...saved, status: 'POSTED', row_version: Number(saved.row_version) + 1 };
  fireEvent.click(screen.getByRole('button', { name: 'Refresh Purchase execution' })); await screen.findByText('COMMITTED');
  expect(screen.getByText(/Posted Purchase is retained/)).toBeVisible();
  // A finished execution is forgotten: a later visit must not be pinned to this bill.
  expect(sessionStorage.getItem('purchase-api-operation:' + JSON.stringify([props.actor, company, props.year]))).toBeNull();
});
it.each([
  ['PENDING', 'APPROVED', true], ['COMMITTED', 'APPROVED', true], ['COMMITTED', 'POSTED', false], ['REJECTED', 'APPROVED', false], ['CANCELLED', 'APPROVED', false],
])('on reload, an execution that is %s for a %s bill %s its reference', { timeout: 20000 }, async (operationStatus, voucherStatus, kept) => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  const scope = JSON.stringify([props.actor, company, props.year]);
  const view = render(<PurchaseEntryConnected {...props} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  view.unmount();
  saved = { ...saved, status: voucherStatus };
  sessionStorage.setItem('purchase-api-operation:' + scope, JSON.stringify({ id: id(80), voucherId: id(90), revisionId: id(91) }));
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    if (args[1].path.endsWith('/voucher-operations/' + id(80))) return { id: id(80), voucher_id: id(90), revision_id: id(91), status: operationStatus, row_version: 2 };
    return original(...args);
  });
  render(<PurchaseEntryConnected {...props} permissions={[...props.permissions, 'vouchers.post', 'vouchers.operation.read', 'vouchers.operation.recover']} />);
  await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.some(call => call[1].path.endsWith('/voucher-operations/' + id(80)))).toBe(true));
  await screen.findByText(operationStatus);
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 50)); });
  // A running or just-committed execution is still being followed; a finished one must not pin the tab to this bill.
  expect(sessionStorage.getItem('purchase-api-operation:' + scope) !== null).toBe(kept);
});
it('retains and retries the identical body and key after an uncertain outcome', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!; let calls = 0;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].method === 'POST' && args[1].path === base + '/vouchers' && calls++ === 0) { writes.push({ request: structuredClone(args[1]) }); throw { status: 503, message: 'Owner unavailable' }; } return original(...args); });
  render(<PurchaseEntryConnected {...props} />); await enter(); fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
  await screen.findByRole('button', { name: 'Retry previous request' }); fireEvent.click(screen.getByRole('button', { name: 'Retry previous request' }));
  await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  expect(writes[0]!.request).toEqual(writes[1]!.request); expect(sessionStorage.length).toBe(0);
});
it('refuses wrong-company voucher types before rendering the workspace', async () => {
  vi.mocked(serviceCall).mockResolvedValue({ items: [{ id: id(2), company_id: id(99), kind: 'PURCHASE' }], page: { next_cursor: null } });
  render(<PurchaseEntryConnected {...props} />); await screen.findByText(/configuration could not be verified/); expect(screen.queryByRole('button', { name: /^(Create|Update)$/ })).toBeNull();
});
it('withholds creation controls for a role without creation access', async () => {
  render(<PurchaseEntryConnected {...props} canCreate={false} />); await screen.findByRole('heading', { name: 'New purchase' }); expect(screen.queryByRole('button', { name: /^(Create|Update)$/ })).toBeNull();
});
it('hides New purchase when creation access is revoked while reviewing a saved bill', async () => {
  const view = render(<PurchaseEntryConnected {...props} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
  await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  expect(screen.getByRole('link', { name: 'New purchase' })).toBeVisible();
  view.rerender(<PurchaseEntryConnected {...props} canCreate={false} permissions={['vouchers.read']} />);
  expect(screen.queryByRole('link', { name: 'New purchase' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^(Create|Update)$/ })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Saved drafts' })).toBeVisible();
  expect(writes).toHaveLength(1);
});
it('renders a recoverable 403 configuration failure', async () => {
  vi.mocked(serviceCall).mockRejectedValue({ status: 403, message: 'Purchase access denied' });
  render(<PurchaseEntryConnected {...props} />); await screen.findByText('Purchase access denied'); expect(screen.getByRole('button', { name: 'Refresh Purchase setup' })).toBeVisible();
});
it('explains a misconfigured account type and links to the selected type rules', async () => {
  metadata.configuration.policy.allowed_party_roles = ['CUSTOMER'];
  render(<PurchaseEntryConnected {...props} permissions={[...props.permissions, 'vouchers.type.manage']} />);
  await screen.findByText(/Supplier parties are disabled/);
  expect(screen.getByRole('link', { name: 'Edit Purchase entry rules' })).toHaveAttribute('href', '/masters/voucher-types/' + id(2) + '/edit');
  expect(screen.getByRole('combobox', { name: 'Purchase voucher type' })).toBeVisible();
  expect(screen.queryByRole('button', { name: /^(Create|Update)$/ })).toBeNull();
});
it.each([
  ['an items-only product type', { allowed_modes: ['ITEMS'], default_mode: 'ITEMS', required_sections: ['ITEMS'] }],
  ['a mixed type', { allowed_modes: ['ITEMS', 'MIXED'], default_mode: 'MIXED' }],
  ['an account-mode type that requires items', { required_sections: ['ITEMS'] }],
])('says plainly that %s cannot take products while its rules refuse goods, and never advises editing its rules', async (_, policy) => {
  Object.assign(metadata.configuration.policy, policy);
  render(<PurchaseEntryConnected {...props} permissions={[...props.permissions, 'vouchers.type.manage']} />);
  expect(await screen.findByText('This Purchase type cannot take products')).toBeVisible();
  expect(screen.getByText(/its rules do not allow goods supplies/)).toBeVisible();
  expect(screen.queryByText('Purchase needs configuration')).toBeNull();
  expect(screen.queryByText(/Accounts mode is disabled|Item lines are required/)).toBeNull();
  expect(screen.queryByRole('link', { name: 'Edit Purchase entry rules' })).toBeNull();
  expect(screen.getByRole('link', { name: 'Review Purchase voucher type' })).toBeVisible();
  expect(screen.getByRole('combobox', { name: 'Purchase voucher type' })).toBeVisible();
  expect(screen.queryByRole('button', { name: /^(Create|Update)$/ })).toBeNull();
});
it('stages credit terms until Apply and discards cancelled detail edits', async () => {
  render(<PurchaseEntryConnected {...props} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: 'Edit terms and details' }));
  fireEvent.change(screen.getByLabelText('Credit days'), { target: { value: '45' } });
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  await screen.findByRole('dialog', { name: 'Discard bill detail changes?' });
  fireEvent.click(screen.getByRole('button', { name: 'Discard detail changes' }));
  fireEvent.click(screen.getByRole('button', { name: 'Edit terms and details' }));
  expect(screen.getByLabelText('Credit days')).toHaveValue('30');
  fireEvent.change(screen.getByLabelText('Credit days'), { target: { value: '45' } });
  fireEvent.click(screen.getByRole('button', { name: 'Apply bill details' }));
  expect(writes).toHaveLength(0); fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
  await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  const body = writes[0]!.request.body as { document_date: string; invoice: { due_date: string } };
  expect((Date.parse(body.invoice.due_date) - Date.parse(body.document_date)) / 86400000).toBe(45);
});
it('restores an uncertain command after reload and retries its retained key', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!; let first;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].method === 'POST' && args[1].path === base + '/vouchers') { first = structuredClone(args[1]); throw { status: 503, message: 'Owner unavailable' }; } return original(...args); });
  const view = render(<PurchaseEntryConnected {...props} />); await enter(); fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('button', { name: 'Retry previous request' }); view.unmount();
  vi.mocked(serviceCall).mockImplementation(original); render(<PurchaseEntryConnected {...props} />);
  await screen.findByRole('button', { name: 'Retry previous request' }); fireEvent.click(screen.getByRole('button', { name: 'Retry previous request' }));
  await screen.findByRole('heading', { name: 'Purchase bill · revision 3' }); expect(writes[0]!.request).toEqual(first);
});
it('does not send a second create on a rapid repeated save', async () => {
  render(<PurchaseEntryConnected {...props} />); await enter(); const save = screen.getByRole('button', { name: /^(Create|Update)$/ }); fireEvent.click(save); fireEvent.click(save);
  await screen.findByRole('heading', { name: 'Purchase bill · revision 3' }); expect(writes).toHaveLength(1);
});
it('locks further writes after a confirmed save whose readback fails, then reloads without replaying create', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!; let unavailable = true;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    if (!args[1].method && args[1].path === base + '/vouchers/' + id(90) && unavailable) throw { status: 503, message: 'Read temporarily unavailable' };
    return original(...args);
  });
  render(<PurchaseEntryConnected {...props} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
  await screen.findByText(/request succeeded, but its saved details could not be refreshed/);
  expect(screen.getByRole('button', { name: /^(Create|Update)$/ })).toBeDisabled();
  expect(screen.queryByRole('button', { name: 'Retry previous request' })).toBeNull();
  unavailable = false; fireEvent.click(screen.getByRole('button', { name: 'Load latest saved revision' }));
  await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  expect(writes).toHaveLength(1);
});
it('reviews an immutable historical revision without replacing unsaved bill entries', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    const request = args[1];
    if (request.path.includes('/history?')) return { items: [{ id: id(70), revision_id: id(71), action: 'EDIT', from_status: 'DRAFT', to_status: 'DRAFT' }], page: { next_cursor: null } };
    if (request.path.endsWith('/revisions/' + id(71))) return { ...saved, revision_number: 1, revision_id: id(71) };
    return original(...args);
  });
  render(<PurchaseEntryConnected {...props} permissions={[...props.permissions, 'vouchers.history.read']} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  fireEvent.change(screen.getByLabelText('Invoice'), { target: { value: 'UNSAVED-REFERENCE' } });
  fireEvent.click(screen.getByRole('button', { name: 'View revision history' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Review saved revision' }));
  await screen.findByRole('dialog', { name: 'Purchase revision 1' });
  fireEvent.click(screen.getByRole('button', { name: 'Done reviewing revision' }));
  expect(screen.getByLabelText('Invoice')).toHaveValue('UNSAVED-REFERENCE'); expect(writes).toHaveLength(1);
});

const posting = [...props.permissions, 'vouchers.post', 'vouchers.operation.read', 'vouchers.operation.recover'];
/** A saved bill A with a finished execution, and a second saved draft B in the drafts list. */
async function withFinishedExecutionOfAnotherBill(operationStatus: string) {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  const view = render(<PurchaseEntryConnected {...props} />); await enter();
  fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
  view.unmount();
  saved = { ...saved, status: 'POSTED' };
  const other = () => ({ ...saved, id: id(95), status: 'DRAFT', revision_id: id(96), row_version: 2 });
  sessionStorage.setItem('purchase-api-operation:' + JSON.stringify([props.actor, company, props.year]), JSON.stringify({ id: id(80), voucherId: id(90), revisionId: id(91) }));
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    const request = args[1];
    if (request.path.endsWith('/voucher-operations/' + id(80))) return { id: id(80), voucher_id: id(90), revision_id: id(91), status: operationStatus, row_version: 2 };
    if (request.path.includes('/vouchers?kind=PURCHASE')) return { items: [{ id: id(95), company_id: company, kind: 'PURCHASE', status: 'DRAFT', document_date: '2026-10-30' }], page: { next_cursor: null } };
    if (request.path === base + '/vouchers/' + id(95)) return other();
    if (request.path.startsWith(base + '/vouchers/' + id(95) + '/field-set')) return metadata;
    return original(...args);
  });
  render(<PurchaseEntryConnected {...props} permissions={posting} />);
  await screen.findByText(operationStatus);
  await screen.findByText(/Posted Purchase is retained/);
}
it('does not lock the next bill that is opened because another bill’s execution finished', { timeout: 20000 }, async () => {
  await withFinishedExecutionOfAnotherBill('COMMITTED');
  fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
  fireEvent.click(await screen.findByRole('button', { name: /^Open draft/ }));
  await waitFor(() => expect(screen.getByLabelText('Invoice')).toHaveValue('SUP-NEW'));
  expect(await screen.findByRole('button', { name: /^(Create|Update)$/ })).toBeVisible();
  expect(screen.queryByText(/posting is in progress/i)).toBeNull();
  expect(screen.queryByText('Purchase execution:')).toBeNull();
  // The finished execution belongs to the other bill; this one shows none.
  expect(screen.queryByText('COMMITTED')).toBeNull();
});

describe('what the saved bill says about Accounting’s calculation', () => {
  let hash = 'a'.repeat(64);
  beforeEach(() => {
    hash = 'a'.repeat(64);
    const original = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => {
      const result = await original(...args);
      return args[1].path.endsWith('/invoice-preview') ? { ...(result as object), calculation_hash: hash } : result;
    });
  });
  async function accepted() {
    render(<PurchaseEntryConnected {...props} />); await enter();
    fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    fireEvent.click(screen.getByRole('button', { name: 'Calculate saved bill' })); await screen.findByRole('button', { name: 'Accept Accounting calculation' });
    fireEvent.click(screen.getByRole('button', { name: 'Accept Accounting calculation' })); await screen.findByRole('heading', { name: 'Purchase bill · revision 4' });
  }
  it('says "Accepted" only for the calculation that was accepted', async () => {
    await accepted();
    fireEvent.click(screen.getByRole('button', { name: 'Calculate saved bill' }));
    const card = await screen.findByRole('region', { name: 'Accounting calculation' });
    expect(within(card).getByText('Accepted')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Submit' })).toBeEnabled();
  });
  it('says so, and holds Submit back, when Accounting now calculates something else', { timeout: 20000 }, async () => {
    await accepted();
    hash = 'b'.repeat(64);
    fireEvent.click(screen.getByRole('button', { name: 'Calculate saved bill' }));
    const card = await screen.findByRole('region', { name: 'Accounting calculation' });
    expect(within(card).getByText('Differs from the accepted calculation')).toBeVisible();
    expect(within(card).queryByText('Accepted')).toBeNull();
    expect(within(card).getByText(/Accept this calculation to submit the bill with it/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Submit' })).toBeDisabled();
    // Accepting the new one brings Submit back.
    fireEvent.click(screen.getByRole('button', { name: 'Accept Accounting calculation' })); await screen.findByRole('heading', { name: 'Purchase bill · revision 5' });
    fireEvent.click(screen.getByRole('button', { name: 'Calculate saved bill' }));
    expect(await within(await screen.findByRole('region', { name: 'Accounting calculation' })).findByText('Accepted')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Submit' })).toBeEnabled();
  });
  it('can be calculated again for a submitted bill, so the approver sees what is payable', { timeout: 20000 }, async () => {
    await accepted();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' })); await screen.findByRole('button', { name: 'Approve' });
    fireEvent.click(screen.getByRole('button', { name: 'Calculate saved bill' }));
    const card = await screen.findByRole('region', { name: 'Accounting calculation' });
    expect(card.querySelector('[data-emphasis="true"]')).toHaveTextContent('₹42.12');
    expect(within(card).getByText('Accepted')).toBeVisible();
    // Accepting is for a draft only.
    expect(screen.queryByRole('button', { name: 'Accept Accounting calculation' })).toBeNull();
  });
});
describe('why a saved bill cannot be changed', () => {
  it('says the person lacks edit access, not that they cannot create vouchers', async () => {
    const view = render(<PurchaseEntryConnected {...props} />); await enter();
    fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    view.unmount();
    render(<PurchaseEntryConnected {...props} permissions={['vouchers.read', 'vouchers.create']} initialVoucherId={id(90)} />);
    await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    expect(await screen.findByText('Review only')).toBeVisible();
    expect(screen.getByText(/changing it needs edit access/)).toBeVisible();
    expect(screen.queryByText(/permission to create vouchers/)).toBeNull();
  });
});
describe('a saved product bill opened on this screen', () => {
  it('is not edited here and links to voucher review, where its item lines are shown', async () => {
    const view = render(<PurchaseEntryConnected {...props} />); await enter();
    fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    view.unmount();
    saved = { ...saved, mode: 'ITEMS', lines: [{ line_key: id(70), description: 'Steel rod', item: { item_id: id(71) } }] };
    render(<PurchaseEntryConnected {...props} initialVoucherId={id(90)} />);
    expect(await screen.findByText(/requires a broader Purchase profile/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'Open it in voucher review' })).toHaveAttribute('href', '/vouchers/' + id(90));
    expect(screen.queryByRole('button', { name: /^(Create|Update)$/ })).toBeNull();
  });
});
describe('a retained execution reference and the bill in the address', () => {
  it('shows how to retry recovery, and then opens the bill the address names, not the one the reference was for', { timeout: 20000 }, async () => {
    const original = vi.mocked(serviceCall).getMockImplementation()!;
    const view = render(<PurchaseEntryConnected {...props} />); await enter();
    fireEvent.click(screen.getByRole('button', { name: /^(Create|Update)$/ })); await screen.findByRole('heading', { name: 'Purchase bill · revision 3' });
    view.unmount();
    let readable = false;
    const other = () => ({ ...saved, id: id(95), status: 'DRAFT', revision_id: id(96), row_version: 2, invoice: { ...(saved.invoice as object), bill_reference: 'OTHER-BILL' }, references: [{ purpose: 'SUPPLIER_INVOICE', reference: 'OTHER-BILL', reference_date: (saved.document_date as string) }] });
    sessionStorage.setItem('purchase-api-operation:' + JSON.stringify([props.actor, company, props.year]), JSON.stringify({ id: id(80), voucherId: id(90), revisionId: id(91) }));
    vi.mocked(serviceCall).mockImplementation(async (...args) => {
      const request = args[1];
      if (request.path.endsWith('/voucher-operations/' + id(80))) { if (!readable) throw { status: 403, message: 'Execution access denied' }; return { id: id(80), voucher_id: id(90), revision_id: id(91), status: 'REJECTED', row_version: 2 }; }
      if (request.path === base + '/vouchers/' + id(95)) return other();
      if (request.path.startsWith(base + '/vouchers/' + id(95) + '/field-set')) return metadata;
      return original(...args);
    });
    render(<PurchaseEntryConnected {...props} permissions={posting} initialVoucherId={id(95)} />);
    await screen.findByText('Execution access denied');
    // Nothing is open yet, and the way forward is on screen.
    expect(screen.queryByLabelText('Invoice')).toBeNull();
    readable = true;
    fireEvent.click(await screen.findByRole('button', { name: 'Retry execution recovery' }));
    await waitFor(() => expect(screen.getByLabelText('Invoice')).toHaveValue('OTHER-BILL'));
    expect(screen.getByRole('heading', { name: 'Purchase bill · revision 3' })).toBeVisible();
  });
});
