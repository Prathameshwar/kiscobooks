import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseEntryConnected } from '../app/components/PurchaseEntryConnected';
import { serviceCall } from '../app/lib/service-call';
import { purchaseSource, supplierPayables } from '../app/lib/purchase-entry';
import { company, draft as sources, metadata as fixture } from './purchase-entry-fixtures';
import type { PurchaseWorkspaceController } from '../app/components/PurchaseWorkspace';
import type { PurchaseWorkspacePolicy } from '../app/lib/purchase-workspace';
import type { QuickCreated } from '../app/lib/purchase-quick-create';

/*
 * How the connected purchase bill uses the create-from-here drawers: who is offered them, what is verified
 * before a created record is chosen, what the person is told, and where focus goes. The workspace and the
 * drawers are stand-ins here; each has its own tests.
 */
const spies = vi.hoisted(() => ({ staged: vi.fn() }));
vi.mock('../app/lib/service-call', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/purchase-entry', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/purchase-entry')>(), purchaseSource: vi.fn(), supplierPayables: vi.fn(), purchaseLookup: vi.fn(() => vi.fn()) }));
vi.mock('../app/components/PurchaseWorkspace', () => ({ PurchaseWorkspace: ({ controller: c, policy }: { controller: PurchaseWorkspaceController; policy: PurchaseWorkspacePolicy }) => <section>{c.header}{c.banner(null)}
  {c.quickCreate?.supplier ? <button onClick={c.quickCreate.supplier}>New supplier</button> : null}
  {c.quickCreate?.account ? <button onClick={() => c.quickCreate!.account!({ lineKey: c.draft.lines[0]!.key })}>New account</button> : null}
  {c.quickCreate?.account ? <button onClick={() => c.quickCreate!.account!({ lineKey: c.draft.lines[0]!.key, apply: spies.staged })}>New account (staged)</button> : null}
  <button onClick={() => c.dispatch({ type: 'supplier', value: sources.party!.id, policy: {} as never })}>Choose supplier</button>
  <div data-purchase-field="supplier"><input aria-label="Supplier" readOnly value={c.draft.supplier} /></div>
  <div data-purchase-field="invoice"><input aria-label="Invoice" value={c.draft.invoice} disabled={c.pending} onChange={() => undefined} /></div>
  <input aria-label="Amount" data-entry-row={c.draft.lines[0]!.key} data-entry-col="amount" disabled={c.pending} value={c.draft.lines[0]!.amount} onChange={() => undefined} />
  <output aria-label="Line account">{c.draft.lines[0]!.subject}</output>
  <output aria-label="Known accounts">{policy.subjects.map(subject => subject.id).join(',')}</output>
  {c.actions({ validate: () => true, review: () => undefined })}</section> }));
vi.mock('../app/components/PurchaseQuickCreate', () => ({
  SupplierQuickCreate: ({ company: owner, companyCountry, canTax, onCreated, onClose }: { company: string; companyCountry: string; canTax: boolean; onCreated: (created: QuickCreated) => void; onClose: () => void }) =>
    <div role="dialog" aria-label="Supplier drawer" data-company={owner} data-country={companyCountry} data-tax={String(canTax)}>
      <button onClick={() => onCreated(createdSupplier)}>Finish supplier</button><button onClick={onClose}>Close supplier</button></div>,
  ExpenseAccountQuickCreate: ({ company: owner, onCreated, onClose }: { company: string; onCreated: (created: QuickCreated) => void; onClose: () => void }) =>
    <div role="dialog" aria-label="Account drawer" data-company={owner}>
      <button onClick={() => onCreated(createdAccount)}>Finish account</button><button onClick={onClose}>Close account</button></div>,
}));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const createdSupplier: QuickCreated = { id: id(70), label: 'Sharma Traders', meta: 'SHARMA' };
const createdAccount: QuickCreated = { id: id(71), label: 'Office rent', meta: 'RENT' };
const manage = { party: 'accounting.party.manage', account: 'accounting.account.manage', groups: 'accounting.group.read', heads: 'accounting.head.read', taxManage: 'accounting.tax.manage', taxRead: 'accounting.tax.read' };
const base = ['vouchers.read', 'vouchers.create', 'vouchers.edit'];
const everything = [...base, manage.party, manage.account, manage.groups, manage.heads];
const props = { company, currency: 'INR', actor: id(12), year: id(13), canCreate: true, permissions: everything };

let metadata: typeof fixture;
beforeEach(() => {
  sessionStorage.clear(); vi.mocked(serviceCall).mockReset(); vi.mocked(purchaseSource).mockReset(); vi.mocked(supplierPayables).mockReset(); spies.staged.mockReset();
  metadata = structuredClone(fixture);
  Object.assign(metadata.native.properties!, Object.fromEntries(['document_date', 'currency', 'narration', 'mode', 'lines', 'attachments', 'links', 'custom_fields'].map(key => [key, {}])));
  vi.mocked(purchaseSource).mockImplementation(async (_company, resource, which) => resource === 'suppliers'
    ? { ...sources.party!, id: which, label: 'Sharma Traders (verified)' }
    : resource === 'payables' ? sources.payable! : { ...sources.supplies[0]!.account!, id: which, label: 'Office rent (verified)' });
  // Choosing a supplier reads its one payable account (a supplier is never asked for it); purchase-supplier-account holds the real read.
  vi.mocked(supplierPayables).mockImplementation(async () => [sources.payable!]);
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('/voucher-types?')) return { items: [{ id: id(2), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', name: 'Account purchases' }], page: { next_cursor: null } };
    if (request.path.endsWith('/voucher-capabilities')) return { financial_execution: false, invoice_execution: false, kinds: [{ kind: 'PURCHASE', execution_ready: false }] };
    if (request.path.includes('/field-set')) return metadata;
    throw Error('Unexpected test route ' + request.path);
  });
});
async function ready(extra: Partial<typeof props> & { companyCountry?: string } = {}) {
  render(<PurchaseEntryConnected {...props} {...extra} />);
  await screen.findByRole('button', { name: 'Choose supplier' });
}
const notice = (text: RegExp | string) => waitFor(() => expect(within(screen.getAllByRole('status').find(node => node.textContent?.includes('Purchase status')) ?? document.body).getByText(text)).toBeVisible());

describe('who is offered the create icons', () => {
  it.each([
    ['everything', everything, true, true],
    ['only voucher access', base, false, false],
    ['party management without account management', [...base, manage.party], false, false],
    ['supplier management with the account right, but no group or head read', [...base, manage.party, manage.account], true, false],
    ['account management with group and head read, but not party management', [...base, manage.account, manage.groups, manage.heads], false, true],
    ['account management without being able to read groups and heads', [...base, manage.account], false, false],
    ['group and head read alone', [...base, manage.groups, manage.heads], false, false],
  ])('with %s', async (_who, permissions, supplier, account) => {
    await ready({ permissions });
    expect(!!screen.queryByRole('button', { name: 'New supplier' })).toBe(supplier);
    expect(!!screen.queryByRole('button', { name: 'New account' })).toBe(account);
  });

  it('offers neither on a bill the actor cannot edit', async () => {
    await ready({ canCreate: false });
    expect(screen.queryByRole('button', { name: 'New supplier' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'New account' })).toBeNull();
  });
});

describe('creating a supplier from the bill', () => {
  it('opens the drawer for this company, with the company’s country as the default', async () => {
    await ready({ companyCountry: 'US' });
    fireEvent.click(screen.getByRole('button', { name: 'New supplier' }));
    const drawer = screen.getByRole('dialog', { name: 'Supplier drawer' });
    expect(drawer).toHaveAttribute('data-company', company);
    expect(drawer).toHaveAttribute('data-country', 'US');
  });

  it.each([
    ['everything', [...everything, manage.taxManage, manage.taxRead], 'true'],
    ['no tax permissions', everything, 'false'],
    ['tax management without reading registrations', [...everything, manage.taxManage], 'false'],
    ['tax reading without managing registrations', [...everything, manage.taxRead], 'false'],
  ])('offers the GST fields only to someone who can both read and manage tax registrations: %s', async (_who, permissions, tax) => {
    await ready({ permissions });
    fireEvent.click(screen.getByRole('button', { name: 'New supplier' }));
    expect(screen.getByRole('dialog', { name: 'Supplier drawer' })).toHaveAttribute('data-tax', tax);
  });

  it('defaults the country to India when the page could not say', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'New supplier' }));
    expect(screen.getByRole('dialog', { name: 'Supplier drawer' })).toHaveAttribute('data-country', 'IN');
  });

  it('closing the drawer changes nothing on the bill', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'New supplier' }));
    fireEvent.click(screen.getByRole('button', { name: 'Close supplier' }));
    expect(screen.queryByRole('dialog', { name: 'Supplier drawer' })).toBeNull();
    expect(screen.getByLabelText('Supplier')).toHaveValue('');
    expect(purchaseSource).not.toHaveBeenCalled();
  });

  it('chooses the new supplier through the bill’s own verified path, then says so and moves on to the invoice number', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'New supplier' }));
    fireEvent.click(screen.getByRole('button', { name: 'Finish supplier' }));
    expect(screen.queryByRole('dialog', { name: 'Supplier drawer' })).toBeNull();
    await waitFor(() => expect(purchaseSource).toHaveBeenCalledWith(company, 'suppliers', createdSupplier.id));
    await waitFor(() => expect(supplierPayables).toHaveBeenCalledWith(company, createdSupplier.id));
    await waitFor(() => expect(screen.getByLabelText('Supplier')).toHaveValue(createdSupplier.id));
    await notice('Supplier Sharma Traders was created and selected.');
    await waitFor(() => expect(screen.getByLabelText('Invoice')).toHaveFocus());
  });

  it('does not select anything it could not verify, and says what happened instead of announcing success', async () => {
    vi.mocked(purchaseSource).mockRejectedValue({ status: 502, message: 'The supplier could not be verified.' });
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'New supplier' }));
    fireEvent.click(screen.getByRole('button', { name: 'Finish supplier' }));
    expect(await screen.findByText('Purchase needs attention')).toBeVisible();
    expect(screen.getByLabelText('Supplier')).toHaveValue('');
    expect(screen.queryByText(/was created and selected/)).toBeNull();
  });

  it('still tells the person the supplier exists when the bill is busy and cannot take it just now', async () => {
    let release!: () => void;
    vi.mocked(purchaseSource).mockImplementationOnce(() => new Promise((resolve, reject) => { release = () => reject(new Error('stop')); }));
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'New supplier' }));
    fireEvent.click(screen.getByRole('button', { name: 'Choose supplier' }));
    // the bill is now waiting on another selection
    fireEvent.click(screen.getByRole('button', { name: 'Finish supplier' }));
    await notice('Supplier Sharma Traders was created. Choose it in the Supplier field when this bill is ready.');
    expect(screen.getByLabelText('Supplier')).toHaveValue('');
    await act(async () => { release(); });
  });
});

describe('creating an expense account from a bill line', () => {
  it('opens the drawer for this company', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'New account' }));
    expect(screen.getByRole('dialog', { name: 'Account drawer' })).toHaveAttribute('data-company', company);
  });

  it('puts the account on its line through the bill’s own verified path, says so, and moves on to the amount', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'New account' }));
    fireEvent.click(screen.getByRole('button', { name: 'Finish account' }));
    expect(screen.queryByRole('dialog', { name: 'Account drawer' })).toBeNull();
    await waitFor(() => expect(purchaseSource).toHaveBeenCalledWith(company, 'expenses', createdAccount.id));
    await waitFor(() => expect(screen.getByLabelText('Line account')).toHaveTextContent(createdAccount.id));
    await notice('Expense account Office rent was created and selected.');
    await waitFor(() => expect(screen.getByLabelText('Amount')).toHaveFocus());
  });

  it('does not put an account it could not verify on the line', async () => {
    vi.mocked(purchaseSource).mockRejectedValue({ status: 502, message: 'Choose an account under an expense head for this account bill.' });
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'New account' }));
    fireEvent.click(screen.getByRole('button', { name: 'Finish account' }));
    expect(await screen.findByText('Choose an account under an expense head for this account bill.')).toBeVisible();
    expect(screen.getByLabelText('Line account')).toBeEmptyDOMElement();
  });

  describe('from the staged line editor', () => {
    it('verifies the account, teaches the bill about it, and only then fills the editor — never the bill', async () => {
      await ready();
      fireEvent.click(screen.getByRole('button', { name: 'New account (staged)' }));
      fireEvent.click(screen.getByRole('button', { name: 'Finish account' }));
      await waitFor(() => expect(spies.staged).toHaveBeenCalledTimes(1));
      expect(purchaseSource).toHaveBeenCalledWith(company, 'expenses', createdAccount.id);
      expect(spies.staged).toHaveBeenCalledWith({ ...createdAccount, label: 'Office rent (verified)' });
      expect(screen.getByLabelText('Known accounts')).toHaveTextContent(createdAccount.id);
      expect(screen.getByLabelText('Line account')).toBeEmptyDOMElement();
    });

    it('does not fill the editor with an account that failed verification', async () => {
      vi.mocked(purchaseSource).mockRejectedValue({ status: 502, message: 'The expense account group could not be verified.' });
      await ready();
      fireEvent.click(screen.getByRole('button', { name: 'New account (staged)' }));
      fireEvent.click(screen.getByRole('button', { name: 'Finish account' }));
      expect(await screen.findByText('The expense account group could not be verified.')).toBeVisible();
      expect(spies.staged).not.toHaveBeenCalled();
    });
  });
});

describe('one drawer at a time', () => {
  it('replaces a supplier drawer with an account drawer rather than stacking them', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'New supplier' }));
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Close supplier' }));
    fireEvent.click(screen.getByRole('button', { name: 'New account' }));
    expect(screen.getByRole('dialog', { name: 'Account drawer' })).toBeVisible();
    expect(screen.queryByRole('dialog', { name: 'Supplier drawer' })).toBeNull();
  });
});
