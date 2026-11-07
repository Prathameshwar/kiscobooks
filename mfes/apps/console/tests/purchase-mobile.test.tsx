import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { PurchaseLineEditor } from '../app/components/PurchaseLineEditor';
import { PurchaseMobileLines } from '../app/components/PurchaseMobileLines';
import { PurchaseWorkspace } from '../app/components/PurchaseWorkspace';
import { PurchaseWorkflowWorkspace } from '../app/components/PurchaseWorkflowWorkspace';
import { PURCHASE_DEMO_POLICY as policy, blankPurchaseLine, purchaseExample, purchaseWorkspaceProblems } from '../app/lib/purchase-workspace';
import { purchaseScenario } from '../app/lib/purchase-workspace-scenarios';
import { purchaseItem } from '../app/lib/purchase-goods';

vi.mock('../app/lib/purchase-goods', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/purchase-goods')>(), purchaseItem: vi.fn() }));

const today = '2026-10-31';
vi.setConfig({ testTimeout: 15000 });
afterEach(() => vi.restoreAllMocks());
function editor(options: { empty?: boolean; canEdit?: boolean; locale?: boolean; focusField?: string; mixed?: boolean; remoteKind?: 'ITEM' | 'ACCOUNT'; verifyItem?: boolean } = {}) {
  const draft = purchaseExample(today), onApply = vi.fn(), onClose = vi.fn();
  if (options.mixed) draft.mode = 'MIXED';
  if (options.remoteKind === 'ACCOUNT') draft.mode = 'ACCOUNTS';
  const line = options.empty || options.remoteKind ? blankPurchaseLine('p1', options.remoteKind ?? 'ITEM') : draft.lines[0]!;
  const remote = options.remoteKind ? { ...policy, subjects: [], ...(options.verifyItem ? { stockCompany: '10000000-0000-7000-8000-000000000001' } : {}),
    [options.remoteKind === 'ITEM' ? 'itemLookup' : 'subjectLookup']: vi.fn(async () => ({ items: [{ id: 'live-choice', label: 'Live choice' }], nextCursor: null })) } : policy;
  render(<DisplayConfigProvider config={options.locale ? { decimalSeparator: ',', groupSeparator: '.', locale: 'de-DE' } : {}}><PurchaseLineEditor draft={draft} line={line} ordinal={1} policy={remote}
    canEdit={options.canEdit ?? true} focusField={options.focusField} onApply={onApply} onClose={onClose} /></DisplayConfigProvider>);
  return { draft, line, onApply, onClose, user: userEvent.setup() };
}

describe('compact purchase line editor', () => {
  it('stages exact decimal edits until Apply and preserves the source line', async () => {
    const { user, line, onApply } = editor();
    await user.clear(screen.getByLabelText('Unit rate')); await user.type(screen.getByLabelText('Unit rate'), '130.1250');
    expect(line.rate).toBe('125'); expect(onApply).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Apply line' }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ key: 'p1', rate: '130.1250', received: '24', billed: '24' }));
  });
  it('confirms dirty dismissal and can keep or discard the staged line', async () => {
    const { user, onClose, onApply } = editor();
    await user.type(screen.getByLabelText('Line description'), 'Staged reference');
    await user.click(screen.getByRole('button', { name: 'Cancel line edit' }));
    expect(screen.getByRole('dialog', { name: 'Discard line changes?' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Keep editing line' }));
    expect(screen.getByLabelText('Line description')).toHaveValue('Staged reference');
    await user.keyboard('{Escape}'); await user.click(screen.getByRole('button', { name: 'Discard line changes' }));
    expect(onClose).toHaveBeenCalledOnce(); expect(onApply).not.toHaveBeenCalled();
  });
  it('focuses required lookup errors and blocks incomplete lines', async () => {
    const { user, onApply } = editor({ empty: true });
    await user.click(screen.getByRole('button', { name: 'Apply line' }));
    expect(screen.getByRole('combobox', { name: 'Item' })).toHaveFocus();
    expect(screen.getByText('Check this line')).toBeVisible(); expect(onApply).not.toHaveBeenCalled();
  });
  it.each(['ITEM', 'ACCOUNT'] as const)('accepts a selected live %s lookup before the controller verifies it', async kind => {
    const { user, onApply } = editor({ remoteKind: kind });
    const lookup = screen.getByRole('combobox', { name: kind === 'ITEM' ? 'Item' : 'Expense / service account' });
    await user.type(lookup, 'Live');
    await user.click(await screen.findByRole('option', { name: /Live choice/ }));
    if (kind === 'ITEM') {
      await user.type(screen.getByLabelText('Receipt quantity'), '23');
      expect(screen.getByLabelText('Billed quantity')).toHaveValue('');
      await user.tab();
      expect(screen.getByLabelText('Billed quantity')).toHaveValue('23');
      await user.type(screen.getByLabelText('Unit rate'), '25');
    } else await user.type(screen.getByLabelText('Base amount'), '50');
    await user.click(screen.getByRole('button', { name: 'Apply line' }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ kind, subject: 'live-choice', label: 'Live choice' }));
    expect(screen.queryByText('Choose an item or account from the list.')).not.toBeInTheDocument();
  });
  it('copies the first mobile receipt quantity into an empty billed quantity and keeps later billed edits', async () => {
    const { user } = editor({ empty: true });
    await user.type(screen.getByLabelText('Receipt quantity'), '3');
    expect(screen.getByLabelText('Billed quantity')).toHaveValue('');
    await user.tab();
    expect(screen.getByLabelText('Billed quantity')).toHaveValue('3');
    await user.clear(screen.getByLabelText('Billed quantity'));
    await user.type(screen.getByLabelText('Billed quantity'), '2');
    expect(screen.getByLabelText('Receipt quantity')).toHaveValue('3.0000');
    expect(screen.getByLabelText('Billed quantity')).toHaveValue('2');
  });
  it('fills the verified product name and base unit before mobile Apply', async () => {
    const company = '10000000-0000-7000-8000-000000000001';
    vi.mocked(purchaseItem).mockResolvedValue({ id: 'live-choice', company, version: 1, baseUnitId: '10000000-0000-7000-8000-000000000002', label: 'Verified milk', unit: 'L' });
    const { user, onApply } = editor({ remoteKind: 'ITEM', verifyItem: true });
    await user.type(screen.getByRole('combobox', { name: 'Item' }), 'Live');
    await user.click(await screen.findByRole('option', { name: /Live choice/ }));
    expect(await screen.findByText('Verified milk')).toBeVisible();
    await user.type(screen.getByLabelText('Receipt quantity'), '2');
    await user.tab();
    await user.type(screen.getByLabelText('Unit rate'), '25');
    await user.click(screen.getByRole('button', { name: 'Apply line' }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ subject: 'live-choice', label: 'Verified milk', unit: 'L', received: '2', billed: '2' }));
  });
  it('keeps a rejected product lookup out of the purchase line', async () => {
    vi.mocked(purchaseItem).mockRejectedValue(Error('This product is not set up to be purchased.'));
    const { user, onApply } = editor({ remoteKind: 'ITEM', verifyItem: true });
    await user.type(screen.getByRole('combobox', { name: 'Item' }), 'Live');
    await user.click(await screen.findByRole('option', { name: /Live choice/ }));
    expect(await screen.findByText('This product is not set up to be purchased.')).toBeVisible();
    await user.type(screen.getByLabelText('Receipt quantity'), '2');
    await user.type(screen.getByLabelText('Unit rate'), '25');
    await user.click(screen.getByRole('button', { name: 'Apply line' }));
    expect(onApply).not.toHaveBeenCalled();
  });
  it('withholds the total and blocks Apply while invalid numeric text is retained', async () => {
    const { user, onApply } = editor();
    const rate = screen.getByLabelText('Unit rate');
    await user.clear(rate); await user.type(rate, '125.12345'); await user.tab();
    expect(rate).toHaveAttribute('aria-invalid', 'true'); expect(rate).toHaveValue('125.12345');
    await user.click(screen.getByRole('button', { name: 'Apply line' }));
    expect(rate).toHaveFocus(); expect(onApply).not.toHaveBeenCalled();
    expect(screen.getByText('—')).toBeVisible();
  });
  it('rejects a quantity difference before applying a direct goods bill', async () => {
    const { user, onApply } = editor();
    const received = screen.getByLabelText('Receipt quantity'); await user.clear(received); await user.type(received, '25');
    await user.click(screen.getByRole('button', { name: 'Apply line' })); expect(screen.getByLabelText('Receipt quantity')).toHaveFocus();
    expect(screen.getAllByText(/direct Purchase bill must receive the same quantity/i).length).toBeGreaterThan(0);
    expect(onApply).not.toHaveBeenCalled();
    await user.clear(received); await user.type(received, '24');
    await user.click(screen.getByRole('button', { name: 'Apply line' }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ received: '24', billed: '24', rate: '125' }));
  });
  it('parses configured comma decimals into canonical decimal strings', async () => {
    const { user, onApply } = editor({ locale: true });
    await user.clear(screen.getByLabelText('Unit rate')); await user.type(screen.getByLabelText('Unit rate'), '130,1250');
    await user.click(screen.getByRole('button', { name: 'Apply line' }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ rate: '130.1250' }));
  });
  it('supports read-only review without editing or Apply', async () => {
    const { user, onClose } = editor({ canEdit: false });
    expect(screen.getByRole('dialog', { name: 'Review purchase line 1' })).toBeVisible();
    expect(screen.getByLabelText('Unit rate')).toBeDisabled(); expect(screen.queryByRole('button', { name: 'Apply line' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Done' })); expect(onClose).toHaveBeenCalledOnce();
  });
  it('keeps the line type fixed until an invalid numeric buffer is corrected', async () => {
    const { user } = editor({ mixed: true });
    await user.clear(screen.getByLabelText('Unit rate')); await user.type(screen.getByLabelText('Unit rate'), '125.12345'); await user.tab();
    expect(screen.getByLabelText('Line type')).toBeDisabled();
    expect(screen.getByText('Correct the invalid number before changing line type.')).toBeVisible();
  });
  it('switches mixed line kinds and validates account amounts without dummy quantities', async () => {
    const { user, onApply } = editor({ mixed: true });
    await user.selectOptions(screen.getByLabelText('Line type'), 'ACCOUNT');
    expect(screen.queryByLabelText('Receipt quantity')).not.toBeInTheDocument();
    const account = screen.getByRole('combobox', { name: 'Expense / service account' }); await user.type(account, 'Repairs'); await user.keyboard('{ArrowDown}{Enter}');
    await user.clear(screen.getByLabelText('Base amount')); await user.type(screen.getByLabelText('Base amount'), '500');
    await user.click(screen.getByRole('button', { name: 'Apply line' }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ kind: 'ACCOUNT', subject: 'demo-maintenance', amount: '500', received: '24' }));
  });
});

describe('compact purchase composition and supplied capabilities', () => {
  it('labels complete line cards and dispatches accessible row actions', async () => {
    const draft = purchaseExample(today), dispatch = vi.fn(), onEdit = vi.fn(), user = userEvent.setup();
    render(<PurchaseMobileLines draft={draft} policy={policy} dispatch={dispatch} onEdit={onEdit} disabled={false} problems={[]} />);
    expect(screen.getByRole('list', { name: 'Purchase line cards' })).toBeVisible();
    expect(screen.getByRole('list', { name: 'Purchase line cards' }).tagName).toBe('UL');
    expect(screen.getByRole('button', { name: 'Add purchase line' }).closest('[role="list"],ul')).toBeNull();
    expect(screen.getByText(draft.lines[0]!.label)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Edit line 1' })); expect(onEdit).toHaveBeenCalledWith('p1');
    await user.click(screen.getByRole('button', { name: 'Actions for line 1' }));
    expect(screen.getByRole('menuitem', { name: /Move up/ })).toHaveAttribute('aria-disabled', 'true');
    await user.click(screen.getByRole('menuitem', { name: 'Duplicate line' })); expect(dispatch).toHaveBeenCalledWith({ type: 'duplicate', key: 'p1' });
    await user.click(screen.getByRole('button', { name: 'Add purchase line' })); expect(dispatch).toHaveBeenCalledWith({ type: 'add' });
  });
  it('switches to one compact editor and preserves applied edits and removal undo', async () => {
    vi.spyOn(window, 'getComputedStyle').mockImplementation(() => ({ getPropertyValue: name => name === '--janso-entry-compact' ? '1' : '' }) as CSSStyleDeclaration);
    const user = userEvent.setup(); render(<PurchaseWorkspace today={today} canCreate initialDraft={purchaseExample(today)} />);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Edit line 1' }));
    await user.type(screen.getByLabelText('Line description'), 'Applied from mobile');
    await user.click(screen.getByRole('button', { name: 'Apply line' }));
    await user.click(screen.getByRole('button', { name: 'Edit line 1' })); expect(screen.getByLabelText('Line description')).toHaveValue('Applied from mobile');
    await user.click(screen.getByRole('button', { name: 'Cancel line edit' }));
    await user.click(screen.getByRole('button', { name: 'Actions for line 1' })); await user.click(screen.getByRole('menuitem', { name: 'Remove line' }));
    expect(screen.getAllByRole('listitem').filter(element => element.hasAttribute('data-purchase-mobile-line'))).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Undo removal' })); expect(screen.getByRole('button', { name: 'Edit line 2' })).toBeVisible();
  });
  it.each(['core', 'workflow'])('withholds every cost surface for supplied read denial: %s', kind => {
    const restricted = { ...policy, costAccess: 'DENIED' as const }, draft = purchaseExample(today);
    const { container } = render(kind === 'core' ? <PurchaseWorkspace today={today} canCreate initialDraft={draft} policy={restricted} /> : <PurchaseWorkflowWorkspace context={{ company: 'test', year: '2026' }} today={today} initialExample="APPROVED" permissions={{ create: true, edit: true, submit: true }} policy={restricted} />);
    expect(screen.getByText('Purchase costs are restricted')).toBeVisible();
    expect(screen.getByRole('heading', { level: 1, name: 'Purchase voucher' })).toBeVisible();
    expect(container.querySelector('input, [role="table"], [data-purchase-mobile-line]')).toBeNull(); expect(container).not.toHaveTextContent('5,723');
    expect(screen.queryByRole('button', { name: /Review|Save|Submit/ })).not.toBeInTheDocument();
  });
  it('shows supplied duplicate references, refuses continuation, and never reuses that check for a different invoice', async () => {
    const draft = purchaseExample(today), user = userEvent.setup(), onDemoSave = vi.fn();
    const duplicateCheck = { supplier: draft.supplier, invoice: draft.invoice, references: ['DEMO-PUR-0042 · Submitted example'] };
    render(<PurchaseWorkspace today={today} canCreate initialDraft={draft} policy={{ ...policy, duplicateCheck }} onDemoSave={onDemoSave} />);
    expect(screen.getByText(duplicateCheck.references[0]!)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Save demo draft' })); expect(onDemoSave).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveFocus();
    await user.type(screen.getByLabelText(/Supplier invoice number/), '-B'); expect(screen.queryByText('Possible duplicate supplier bill')).not.toBeInTheDocument();
    expect(screen.queryByText(/No duplicates|Duplicate check passed/)).not.toBeInTheDocument();
  });
  it('supplies mixed, paid-bundle and mismatch examples with explicit expected outcomes', () => {
    const mixed = purchaseScenario('mixed', today), bundle = purchaseScenario('bundle', today), mismatch = purchaseScenario('mismatch', today);
    expect(mixed.mode).toBe('MIXED'); expect(mixed.lines.map(line => line.kind)).toEqual(['ITEM', 'ITEM', 'ACCOUNT']);
    expect(purchaseWorkspaceProblems(mixed, policy)).toEqual([]); expect(purchaseWorkspaceProblems(bundle, policy).some(problem => problem.field === 'received')).toBe(true);
    expect(bundle.lines[0]).toMatchObject({ received: '11', billed: '10' }); expect(mismatch.details.declaredTotal).toBe('5800');
    expect(purchaseWorkspaceProblems(mismatch, policy).some(problem => problem.field === 'declaredTotal')).toBe(true);
  });
  it('keeps an invalid desktop numeric buffer visible after resizing to compact entry', async () => {
    let compact = false;
    vi.spyOn(window, 'getComputedStyle').mockImplementation(() => ({ getPropertyValue: name => name === '--janso-entry-compact' && compact ? '1' : '' }) as CSSStyleDeclaration);
    const user = userEvent.setup(); render(<PurchaseWorkspace today={today} canCreate initialDraft={purchaseExample(today)} />);
    const rate = screen.getByRole('textbox', { name: /Rate, line 2/ }); await user.clear(rate); await user.type(rate, '125.12345'); await user.tab();
    const focusedBeforeResize = document.activeElement;
    act(() => { compact = true; fireEvent(window, new Event('resize')); });
    expect(document.activeElement).toBe(focusedBeforeResize);
    expect(screen.getByRole('textbox', { name: /Rate, line 2/ })).toHaveValue('125.12345');
    expect(screen.queryByRole('list', { name: 'Purchase line cards' })).not.toBeInTheDocument();
    await user.clear(rate); await user.type(rate, '125'); await user.tab();
    expect(screen.getByRole('textbox', { name: /Rate, line 2/ })).toHaveValue('125.0000');
    await user.click(screen.getByRole('button', { name: 'Use line cards' }));
    expect(screen.getByRole('list', { name: 'Purchase line cards' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Edit line 2' })).toHaveFocus();
  });
  it('routes a compact line validation error into the editor at its field', async () => {
    vi.spyOn(window, 'getComputedStyle').mockImplementation(() => ({ getPropertyValue: name => name === '--janso-entry-compact' ? '1' : '' }) as CSSStyleDeclaration);
    const draft = purchaseExample(today); draft.lines[0] = { ...draft.lines[0]!, received: '25', quantityReason: '' };
    render(<PurchaseWorkspace today={today} canCreate initialDraft={draft} />);
    await userEvent.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(screen.getByRole('dialog', { name: 'Edit purchase line 1' })).toBeVisible();
    expect(screen.getByLabelText('Receipt quantity')).toHaveFocus();
  });
  it('uses the supplied supplier lookup without letting a late query replace newer results', async () => {
    let resolveLate!: (result: { items: typeof policy.suppliers[number][]; nextCursor: null }) => void;
    const lookup = vi.fn(({ q }: { q: string }) => q === 'Pa' ? new Promise<{ items: typeof policy.suppliers[number][]; nextCursor: null }>(resolve => { resolveLate = resolve; }) : Promise.resolve({ items: policy.suppliers.filter(supplier => supplier.label.includes(q)), nextCursor: null }));
    render(<PurchaseWorkspace today={today} canCreate initialDraft={purchaseExample(today)} supplierLookup={lookup} />);
    const supplier = screen.getByRole('combobox', { name: 'Supplier' });
    fireEvent.change(supplier, { target: { value: 'Pa' } });
    await waitFor(() => expect(lookup).toHaveBeenCalledWith(expect.objectContaining({ q: 'Pa' })));
    fireEvent.change(supplier, { target: { value: 'North' } });
    const north = await screen.findByRole('option', { name: /Northstar/ });
    await act(async () => resolveLate({ items: [policy.suppliers[0]!], nextCursor: null }));
    expect(screen.queryByRole('option', { name: /Paper/ })).not.toBeInTheDocument();
    await userEvent.click(north);
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034');
    // The newer result is the one chosen from, and the supplier brings its own payable account: nothing to pick.
    expect(screen.getByRole('combobox', { name: 'Supplier' })).toHaveValue('Northstar Business Services');
    expect(screen.queryByLabelText(/payable account/i)).not.toBeInTheDocument();
  });
});
