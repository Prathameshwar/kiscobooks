import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseEntryConnected } from '../app/components/PurchaseEntryConnected';
import { COMPANY, SUPPLIERS, id, installFakeServices, payableOf, type FakeServices } from './purchase-fake-service';

/**
 * The real Purchase page — header, workspace, grid, lookups, cards, drawers — against stand-ins for
 * the services that answer with the real shapes and are reached through the Console's real proxy
 * allowlist. Not a substitute for a run against the live services, but the only test that notices when
 * the page asks for something the proxy or the service would refuse.
 */
const permissions = ['vouchers.read', 'vouchers.create', 'vouchers.edit', 'vouchers.submit', 'vouchers.approve', 'vouchers.reject', 'vouchers.cancel',
  'vouchers.history.read', 'vouchers.post', 'vouchers.operation.read', 'vouchers.operation.recover'];
const props = { company: COMPANY, currency: 'INR', actor: id(12), year: id(13), canCreate: true, permissions };
let services: FakeServices;
beforeEach(() => { sessionStorage.clear(); services = installFakeServices(); });
afterEach(() => vi.unstubAllGlobals());

const wrote = () => services.requests.filter(row => row.method !== 'GET');

async function chooseSupplier(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByPlaceholderText('Search a supplier by name or code'));
  await user.type(screen.getByPlaceholderText('Search a supplier by name or code'), 'Sharma');
  await user.click(await screen.findByRole('option', { name: /Sharma Office Supplies/ }));
  await waitFor(()=>expect(screen.getByPlaceholderText('Search a supplier by name or code')).toHaveValue(SUPPLIERS[0]!.name));
}

async function fillBill(user: ReturnType<typeof userEvent.setup>) {
  await chooseSupplier(user);
  await user.type(screen.getByLabelText(/Supplier invoice number/), 'SOS/26-27/0418');
  await user.click(screen.getByPlaceholderText('Find an expense account'));
  await user.type(screen.getByPlaceholderText('Find an expense account'), 'Office');
  await user.click(await screen.findByRole('option', { name: /Office expenses/ }));
  await waitFor(() => expect(services.requests.some(row => row.path.includes('/account-heads/'))).toBe(true));
  await user.type(await screen.findByRole('textbox', { name: 'Amount, line 1' }), '18450');
  await user.click(screen.getByRole('checkbox', { name: 'This bill carries no tax' }));
}

describe('the Purchase page against the real wire rules', () => {
  it('takes a bill from an empty page to POSTED, with nothing the proxy or the service would refuse', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
    await fillBill(user);

    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(()=>expect(wrote().length).toBeGreaterThan(0));
    await waitFor(()=>expect(screen.queryByText('Purchase needs attention')?.parentElement?.parentElement?.textContent??'').toBe(''));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 1' });
    expect(screen.queryByText('Purchase needs attention')).toBeNull();
    expect(screen.getAllByText('Draft', { selector: '.janso-badge' }).length).toBeGreaterThan(0);

    await user.click(screen.getByRole('button', { name: 'Calculate saved bill' }));
    await user.click(await screen.findByRole('button', { name: 'Accept Accounting calculation' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 2' });
    await user.click(screen.getByRole('button', { name: 'Submit' }));
    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    await user.click(await screen.findByRole('button', { name: 'Post approved Purchase' }));
    await screen.findByText('PENDING');

    services.completeExecution();
    await user.click(screen.getByRole('button', { name: 'Refresh Purchase execution' }));
    await screen.findByText(/Posted Purchase is immutable/);
    expect(screen.queryByText('Purchase needs attention')).toBeNull();
    expect([...services.vouchers.values()].map(row => row.status)).toEqual(['POSTED']);
    expect(sessionStorage.getItem('purchase-api-operation:' + JSON.stringify([props.actor, COMPANY, props.year]))).toBeNull();
    // Every command that changes something carries its own idempotency key; only the read-only preview has none.
    expect(wrote().filter(row => !row.path.endsWith('/invoice-preview')).every(row => typeof row.key === 'string' && row.key.length > 8)).toBe(true);
    expect(new Set(wrote().filter(row => row.key).map(row => row.key)).size).toBe(wrote().filter(row => row.key).length);
    expect(wrote().map(row => row.method + ' ' + row.path.replace(`/v1/companies/${COMPANY}`, '').replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, ':id'))).toEqual([
      'POST /vouchers', 'POST /vouchers/:id/invoice-preview', 'POST /vouchers/:id/invoice-acceptance', 'POST /vouchers/:id/submit', 'POST /vouchers/:id/approve', 'POST /vouchers/:id/post',
    ]);
  });

  it('sends the bill the service expects: verified versions, UUID line identities, the exact amount', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
    await fillBill(user);
    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 1' });
    const create = services.requests.find(row => row.method === 'POST' && row.path.endsWith('/vouchers'))!;
    expect(create.body).toMatchObject({
      type_revision_id: id(3), mode: 'ACCOUNTS', currency: 'INR',
      parties: [{ role: 'SUPPLIER', party_id: SUPPLIERS[0]!.id, source_version: 2 }],
      invoice: { party_account_id: payableOf(SUPPLIERS[0]!.id), party_account_version: 3, bill_reference: 'SOS/26-27/0418', tax: { profile: 'UNTAXED_ACCOUNT' },
        supplies: [{ amount: '18450', account_version: 4, supply_kind: 'ACCOUNT', price_basis: 'NET_EXCL_TAX' }] },
    });
    expect(create.body.invoice.supplies[0].line_key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('reopens a saved bill from the drafts drawer, after the voucher type has been revised, and saves under the current revision', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
    await fillBill(user);
    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 1' });

    services.reviseType(id(77));
    await user.click(screen.getByRole('button', { name: 'Saved drafts' }));
    await user.click(await screen.findByRole('button', { name: /^Open draft/ }));
    await screen.findByText(/The voucher type has been revised since this bill was saved/);
    expect(screen.queryByText('Purchase needs attention')).toBeNull();

    const invoice = screen.getByLabelText(/Supplier invoice number/);
    await user.clear(invoice); await user.type(invoice, 'SOS/26-27/0419');
    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 2' });
    const edit = services.requests.filter(row => row.method === 'PUT').at(-1)!;
    expect(edit.body.content.type_revision_id).toBe(id(77));
    expect(edit.body.expected_version).toBe(1);
  });

  it('lists the supplier advances that can be applied, by the direction and balance reads the service has', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
    await chooseSupplier(user);
    await user.click(screen.getByRole('button', { name: 'Edit terms and details' }));
    const drawer = await screen.findByRole('dialog', { name: 'Bill details & terms' });
    await user.click(within(drawer).getByRole('button', { name: 'Refresh eligible supplier advances' }));
    expect(await within(drawer).findByText('ADV-1')).toBeVisible();
    expect(within(drawer).getByText(/Available/)).toBeVisible();
    const reads = services.requests.filter(row => row.path.includes('/open-items'));
    expect(reads.map(row => row.path.split('/open-items')[1]!.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, ':id').split('&').slice(0, 3).join('&'))).toEqual(
      expect.arrayContaining([expect.stringContaining('direction=CREDIT'), expect.stringContaining('/:id/balance?as_of=')]),
    );
    expect(reads.some(row => row.path.includes('DEBIT'))).toBe(false);
  });

  it('reads the supplier’s payable account with a lookup that the service accepts, and asks for no account on the page', { timeout: 60000 }, async () => {
    const user = userEvent.setup();
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
    await chooseSupplier(user);
    const lookups = services.requests.filter(row => row.path.includes('/accounts?kind=PARTY'));
    // The account's own role (`role`), never `party_role`, which is not a query parameter; the service answers 200, not 422.
    expect(lookups.map(row => row.path)).toEqual([`/v1/companies/${COMPANY}/accounts?kind=PARTY&party_id=${SUPPLIERS[0]!.id}&role=SUPPLIER&status=ACTIVE&limit=200`]);
    expect(lookups[0]!.path).not.toContain('party_role');
    expect(screen.queryByText('Purchase needs attention')).toBeNull();
    expect(screen.queryByRole('combobox', { name: /payable/i })).toBeNull();
    expect(screen.queryByText(/payable account|Chosen automatically/i)).toBeNull();
  });

  it('warns about a repeated supplier invoice number and submits it only when the person confirms', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    const earlier = services.seedBill({ supplier: SUPPLIERS[0]!.id, billReference: ' sos/26-27/0418 ' });
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
    await fillBill(user);
    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 1' });
    // Advice while it is still a draft, naming the earlier bill; it is not an error.
    expect(await screen.findByText('This supplier invoice number is already recorded')).toBeVisible();
    expect(screen.getByRole('link', { name: /sos\/26-27\/0418/ })).toHaveAttribute('href', '/vouchers/' + earlier);
    expect(screen.queryByText('Purchase needs attention')).toBeNull();
    const lookup = services.requests.find(row => row.path.includes('/vouchers/duplicate-bills'))!;
    expect(lookup.method).toBe('GET');
    expect(lookup.path).toContain('exclude_voucher_id=');

    await user.click(screen.getByRole('button', { name: 'Calculate saved bill' }));
    await user.click(await screen.findByRole('button', { name: 'Accept Accounting calculation' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 2' });
    await user.click(screen.getByRole('button', { name: 'Submit' }));
    const dialog = await screen.findByRole('dialog', { name: 'Submit a possible duplicate bill?' });
    expect(within(dialog).getByText(/posted/i)).toBeVisible();
    expect(screen.queryByText('Purchase needs attention')).toBeNull();
    // Declining leaves the bill a draft and sends nothing more.
    await user.click(within(dialog).getByRole('button', { name: 'Do not submit' }));
    const refused = services.requests.filter(row => row.path.endsWith('/submit'));
    expect(refused).toHaveLength(1);
    expect(refused[0]!.body).not.toHaveProperty('acknowledge_duplicate_bill');
    expect([...services.vouchers.values()].filter(row => row.status === 'DRAFT')).toHaveLength(1);

    await user.click(screen.getByRole('button', { name: 'Submit' }));
    await user.click(within(await screen.findByRole('dialog', { name: 'Submit a possible duplicate bill?' })).getByRole('button', { name: 'Submit anyway' }));
    await screen.findByText(/Current status: SUBMITTED/);
    const submits = services.requests.filter(row => row.path.endsWith('/submit'));
    expect(submits).toHaveLength(3);
    expect(submits[2]!.body).toMatchObject({ acknowledge_duplicate_bill: true });
    // The acknowledged submit is a new command with its own key, never a replay of the refused one.
    expect(new Set(submits.map(row => row.key)).size).toBe(3);
  });

  it('does not warn when the number belongs to another supplier', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    services.seedBill({ supplier: SUPPLIERS[1]!.id, billReference: 'SOS/26-27/0418' });
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
    await fillBill(user);
    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 1' });
    await waitFor(() => expect(services.requests.some(row => row.path.includes('/vouchers/duplicate-bills'))).toBe(true));
    expect(screen.queryByText('This supplier invoice number is already recorded')).toBeNull();
  });

  it('warns when the earlier bill carries no supplier of its own but posts to the same payable ledger', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    services.seedBill({ ledger: payableOf(SUPPLIERS[0]!.id), billReference: 'SOS/26-27/0418' });
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
    await fillBill(user);
    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 1' });
    expect(await screen.findByText('This supplier invoice number is already recorded')).toBeVisible();
    const lookup = services.requests.find(row => row.path.includes('/vouchers/duplicate-bills'))!;
    expect(lookup.path).toContain('party_account_id=' + payableOf(SUPPLIERS[0]!.id));
    expect(lookup.path).toContain('party_id=' + SUPPLIERS[0]!.id);
  });

  it('where the voucher type needs no approval, Submit approves the bill and it can be posted without a second person', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    services = installFakeServices({ approvalRequired: false });
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
    await fillBill(user);
    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 1' });
    expect(screen.getByText(/does not need a separate approval: submitting approves the bill/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Calculate saved bill' }));
    await user.click(await screen.findByRole('button', { name: 'Accept Accounting calculation' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 2' });
    await user.click(screen.getByRole('button', { name: 'Submit' }));
    await screen.findByText(/Current status: APPROVED/);
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    await user.click(await screen.findByRole('button', { name: 'Post approved Purchase' }));
    await screen.findByText('PENDING');
    expect(wrote().map(row => row.method + ' ' + row.path.replace(`/v1/companies/${COMPANY}`, '').replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, ':id'))).toEqual([
      'POST /vouchers', 'POST /vouchers/:id/invoice-preview', 'POST /vouchers/:id/invoice-acceptance', 'POST /vouchers/:id/submit', 'POST /vouchers/:id/post',
    ]);
  });
});
