import type { ReactNode } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseEntryConnected } from '../app/components/PurchaseEntryConnected';
import { PurchaseWorkspace, type PurchaseWorkspaceController } from '../app/components/PurchaseWorkspace';
import { livePurchasePolicy } from '../app/lib/purchase-api';
import { PURCHASE_DEMO_POLICY, blankPurchaseLine, newPurchaseWorkspace, payableCountIssue, purchaseExample, purchaseWorkspaceProblems, purchaseWorkspaceReducer, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from '../app/lib/purchase-workspace';
import { metadata } from './purchase-entry-fixtures';
import { COMPANY, SUPPLIERS, id, installFakeServices, payableOf, receivableOf, secondPayableOf, type FakeServices } from './purchase-fake-service';

/**
 * A bill never asks for the supplier's payable account: a supplier has exactly one, and choosing the supplier chooses it
 * (docs/party-ledger-mandatory-plan.md PL-D06). A supplier that has none, or several, cannot be billed and says why on the
 * Supplier field. These hold that on both header cards (the connected page's and the synthetic preview's) and on the real page
 * against stand-ins for the services, where a party that is also a customer must still be billed to its supplier account.
 */
vi.setConfig({ testTimeout: 60_000 });
const TODAY = '2026-10-31', SEARCH = 'Search a supplier by name or code';
const accounts = (count: number) => Array.from({ length: count }, (_, index) => ({ value: 'pay-' + (index + 1), label: 'Payable ' + (index + 1) }));
const supplierWith = (count: number) => ({ id: 'sup-1', label: 'Sharma Office Supplies', meta: 'Supplier', payables: accounts(count) });
const CASES: [string, number][] = [['exactly one payable account', 1], ['no payable account', 0], ['several payable accounts', 2]];
const issueFor = (count: number) => payableCountIssue(count);

/** Nothing on the card is a control, a label or a line of text that asks for, or announces the choice of, a payable account. */
function expectNoAccountChoice(region: HTMLElement) {
  expect(region.querySelector('[data-purchase-field="payable"]')).toBeNull();
  expect(within(region).queryByRole('combobox', { name: /payable/i })).toBeNull();
  expect(within(region).queryByLabelText(/payable/i)).toBeNull();
  expect(within(region).queryByText('Supplier payable account')).toBeNull();
  expect(within(region).queryByText(/Chosen automatically|Selected automatically|Choose the payable account|Supplier setup needed|Choose a supplier first|No readable payable account/)).toBeNull();
}
const supplierRegion = () => screen.getByRole('region', { name: 'Supplier and invoice details' });
const supplierField = (region: HTMLElement) => region.querySelector<HTMLElement>('[data-purchase-field="supplier"]')!;

describe.each([
  ['connected page’s card', true],
  ['synthetic preview’s card', false],
] as const)('the %s', (_card, isLive) => {
  /** Mounts the card for a chosen supplier with `count` payable accounts; `save` is called only when the workspace's own validation lets a save through. */
  function mount(count: number) {
    const policy: PurchaseWorkspacePolicy = isLive ? { ...livePurchasePolicy('INR', metadata), suppliers: [supplierWith(count)] } : { ...PURCHASE_DEMO_POLICY, suppliers: [supplierWith(count)] };
    // The example's advance belongs to its own supplier, so it is dropped: this is about the supplier's account, not its advances.
    const example = purchaseExample(TODAY);
    const base: PurchaseWorkspaceDraft = isLive ? { ...newPurchaseWorkspace(TODAY), mode: 'ACCOUNTS', lines: [blankPurchaseLine('p1', 'ACCOUNT')] } : { ...example, details: { ...example.details, advances: [] } };
    const draft = purchaseWorkspaceReducer({ ...base, invoice: 'SOS/1' }, { type: 'supplier', value: 'sup-1', policy });
    const save = vi.fn();
    if (!isLive) return { policy, draft, save, ...render(<PurchaseWorkspace today={TODAY} canCreate policy={policy} initialDraft={draft} onDemoSave={async () => save()} />) };
    const controller: PurchaseWorkspaceController = {
      live: true, draft, dispatch: vi.fn(), readOnly: false, pending: false, dirty: false, title: 'New purchase', note: 'Not saved yet', onTransientChange: vi.fn(),
      header: <h1>Header</h1>, banner: () => null, sections: <p>Sections</p>,
      actions: ({ validate }: { validate: () => boolean }): ReactNode => <button type="button" onClick={() => { if (validate()) save(); }}>Save draft</button>,
    };
    return { policy, draft, save, ...render(<PurchaseWorkspace today={TODAY} canCreate policy={policy} controller={controller} />) };
  }
  const saveName = isLive ? 'Save draft' : 'Save demo draft';

  it.each(CASES)('has no control, label or text for a payable account with %s', (_name, count) => {
    mount(count);
    expectNoAccountChoice(supplierRegion());
  });

  it('shows nothing against the supplier, and no complaint, when it has its one payable account', () => {
    mount(1);
    expect(screen.getByRole('combobox', { name: /Supplier$/ })).not.toHaveAttribute('aria-invalid', 'true');
    expect(supplierField(supplierRegion())).not.toHaveTextContent(/payable account/i);
  });

  it.each([['no payable account', 0], ['several payable accounts', 2]] as const)('says on the Supplier field, as soon as it is chosen, why a supplier with %s cannot be billed', (_name, count) => {
    mount(count);
    const field = supplierField(supplierRegion());
    expect(within(field).getByText(issueFor(count)!)).toBeVisible();
    expect(screen.getByRole('combobox', { name: /Supplier$/ })).toHaveAttribute('aria-invalid', 'true');
  });

  it.each([['no payable account', 0], ['several payable accounts', 2]] as const)('does not let a bill for a supplier with %s be saved, and takes the person to the Supplier', async (_name, count) => {
    const user = userEvent.setup();
    const { policy, draft, save } = mount(count);
    // The same words are what the workspace reports as the problem, so they cannot differ from what the field says.
    expect(purchaseWorkspaceProblems(draft, policy).filter(problem => problem.field === 'payable').map(problem => problem.message)).toEqual([issueFor(count)]);
    await user.click(screen.getByRole('button', { name: saveName }));
    expect(save).not.toHaveBeenCalled();
    expect(screen.getByRole('combobox', { name: /Supplier$/ })).toHaveFocus();
    expect(within(supplierField(supplierRegion())).getByText(issueFor(count)!)).toBeVisible();
  });

  it('lets the same bill through validation when the supplier has its one payable account', async () => {
    const user = userEvent.setup();
    const { policy, draft, save } = mount(1);
    expect(purchaseWorkspaceProblems(draft, policy).filter(problem => problem.field === 'payable')).toEqual([]);
    if (!isLive) { await user.click(screen.getByRole('button', { name: saveName })); await waitFor(() => expect(save).toHaveBeenCalledOnce()); }
  });
});

describe('the connected Purchase page against the services’ rules', () => {
  const permissions = ['vouchers.read', 'vouchers.create', 'vouchers.edit', 'vouchers.submit', 'vouchers.approve', 'vouchers.reject', 'vouchers.cancel',
    'vouchers.history.read', 'vouchers.post', 'vouchers.operation.read', 'vouchers.operation.recover'];
  const props = { company: COMPANY, currency: 'INR', actor: id(12), year: id(13), canCreate: true, permissions };
  let services: FakeServices;
  beforeEach(() => { sessionStorage.clear(); services = installFakeServices(); });
  afterEach(() => vi.unstubAllGlobals());
  const wrote = () => services.requests.filter(row => row.method !== 'GET');
  const lists = () => services.requests.filter(row => row.path.includes('/accounts?kind=PARTY'));

  async function open() {
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
  }
  /** Types into the supplier lookup and picks the match; the supplier shows in its field only once it and its account have been verified. */
  async function choose(user: ReturnType<typeof userEvent.setup>, search: string, name: string) {
    const box = await screen.findByPlaceholderText(SEARCH);
    await user.click(box); await user.type(box, search);
    await user.click(await screen.findByRole('option', { name: new RegExp(name) }));
    await waitFor(() => expect(screen.getByPlaceholderText(SEARCH)).toHaveValue(name));
  }
  async function fillRest(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText(/Supplier invoice number/), 'SOS/26-27/0418');
    await user.click(screen.getByPlaceholderText('Find an expense account'));
    await user.type(screen.getByPlaceholderText('Find an expense account'), 'Office');
    await user.click(await screen.findByRole('option', { name: /Office expenses/ }));
    await waitFor(() => expect(services.requests.some(row => row.path.includes('/account-heads/'))).toBe(true));
    await user.type(await screen.findByRole('textbox', { name: 'Amount, line 1' }), '18450');
    await user.click(screen.getByRole('checkbox', { name: 'This bill carries no tax' }));
  }

  it('bills a party that is also a customer to its supplier account, never to its customer account', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    const both = services.seedSupplier({ name: 'Mehta Trading', code: 'SUP-0040', alsoCustomer: true });
    await open();
    await choose(user, 'Mehta', both.name);
    await fillRest(user);
    await user.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 1' });
    const create = services.requests.find(row => row.method === 'POST' && row.path.endsWith('/vouchers'))!;
    expect(create.body.parties).toEqual([expect.objectContaining({ role: 'SUPPLIER', party_id: both.id })]);
    expect(create.body.invoice.party_account_id).toBe(payableOf(both.id));
    expect(create.body.invoice.party_account_id).not.toBe(receivableOf(both.id));
    expect(create.body.invoice.party_account_version).toBe(3);
    // The service was asked for the supplier role only, and the customer account was never even read.
    expect(lists().map(row => row.path)).toEqual([`/v1/companies/${COMPANY}/accounts?kind=PARTY&party_id=${both.id}&role=SUPPLIER&status=ACTIVE&limit=200`]);
    expect(services.requests.some(row => row.path.includes(receivableOf(both.id)))).toBe(false);
    expect(screen.queryByText('Purchase needs attention')).toBeNull();
    expect(screen.queryByRole('combobox', { name: /payable/i })).toBeNull();
  });

  it('does not let the bill be saved for a supplier with no payable account, and says why on the Supplier field', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    const none = services.seedSupplier({ name: 'No Ledger Traders', code: 'SUP-0041', payables: 0 });
    await open();
    await choose(user, 'No Ledger', none.name);
    // Immediately, before anything has been saved or validated.
    expect(within(supplierField(supplierRegion())).getByText(payableCountIssue(0)!)).toBeVisible();
    expectNoAccountChoice(supplierRegion());
    await fillRest(user);
    await user.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
    expect(wrote()).toEqual([]);
    expect(screen.getByPlaceholderText(SEARCH)).toHaveFocus();
    expect(within(supplierField(supplierRegion())).getByText(payableCountIssue(0)!)).toBeVisible();
    expect(screen.queryByRole('heading', { name: /Purchase bill · revision/ })).toBeNull();
  });

  it('does not let the bill be saved for a supplier with several payable accounts, reads each to prove it, and offers no choice between them', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    const two = services.seedSupplier({ name: 'Twin Ledger Traders', code: 'SUP-0042', payables: 2 });
    await open();
    await choose(user, 'Twin', two.name);
    expect(within(supplierField(supplierRegion())).getByText(payableCountIssue(2)!)).toBeVisible();
    expectNoAccountChoice(supplierRegion());
    // Both accounts were verified as this supplier's; neither was chosen.
    for (const account of two.payables) expect(services.requests.some(row => row.method === 'GET' && row.path === `/v1/companies/${COMPANY}/accounts/${account}`)).toBe(true);
    await fillRest(user);
    await user.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
    expect(wrote()).toEqual([]);
    expect(screen.getByPlaceholderText(SEARCH)).toHaveFocus();
    expect(two.payables).toContain(secondPayableOf(two.id));
  });

  it('takes the complaint away when another supplier, with its one account, is chosen instead', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    const none = services.seedSupplier({ name: 'No Ledger Traders', code: 'SUP-0041', payables: 0 });
    await open();
    await choose(user, 'No Ledger', none.name);
    expect(screen.getByText(payableCountIssue(0)!)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Clear Supplier' }));
    await waitFor(() => expect(screen.queryByText(payableCountIssue(0)!)).toBeNull());
    await choose(user, 'Sharma', SUPPLIERS[0]!.name);
    expect(screen.queryByText(payableCountIssue(0)!)).toBeNull();
    expect(screen.getByRole('combobox', { name: /Supplier$/ })).not.toHaveAttribute('aria-invalid', 'true');
    await fillRest(user);
    await user.click(screen.getByRole('button', { name: /^(Create|Update)$/ }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 1' });
    expect(wrote().find(row => row.path.endsWith('/vouchers'))!.body.invoice.party_account_id).toBe(payableOf(SUPPLIERS[0]!.id));
  });
});
