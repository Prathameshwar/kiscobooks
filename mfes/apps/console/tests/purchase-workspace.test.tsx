import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { PurchaseWorkspace } from '../app/components/PurchaseWorkspace';
import { PURCHASE_DEMO_POLICY as policy, blankPurchaseLine, newPurchaseWorkspace, payableCountIssue, purchaseExample, purchaseLineAmounts, purchaseWorkspacePreview, purchaseWorkspaceProblems, purchaseWorkspaceReducer as reduce, type PurchaseWorkspaceDraft } from '../app/lib/purchase-workspace';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const today = '2026-10-31';
vi.setConfig({ testTimeout: 15_000 });
function mount(initialDraft?: PurchaseWorkspaceDraft, options: { canCreate?: boolean; onDemoSave?: () => Promise<void> } = {}) {
  return render(<DisplayConfigProvider config={{ currency: 'INR', currencySymbol: '₹' }}><PurchaseWorkspace today={today} initialDraft={initialDraft} canCreate={options.canCreate ?? true} onDemoSave={options.onDemoSave} /></DisplayConfigProvider>);
}
const table = () => screen.getByRole('table', { name: /^Purchase lines\./ });

it('shows the discounted net amount consistently in item and account grids', async () => {
  const user = userEvent.setup();
  const draft = purchaseExample(today);
  draft.mode = 'MIXED';
  draft.lines.push({ ...blankPurchaseLine('account', 'ACCOUNT'), subject: 'demo-stationery', label: 'Stationery', amount: '100', discount: '10' });
  mount(draft);
  const grid = within(table());
  expect(grid.getByRole('columnheader', { name: 'Net amount' })).toBeVisible();
  expect(grid.getByRole('cell', { name: /Net amount, line 1:.*2,850\.00/ })).toBeVisible();
  expect(grid.getByRole('cell', { name: /Net amount, line 3:.*90\.00/ })).toBeVisible();
  const amount = grid.getByRole('textbox', { name: /Base amount, line 3/ });
  await user.clear(amount); await user.type(amount, '120'); await user.tab();
  expect(grid.getByRole('cell', { name: /Net amount, line 3:.*110\.00/ })).toBeVisible();
});

describe('Purchase presentation state and exact preview', () => {
  it('matches the approved sample and invalidates supplied tax when financial inputs change', () => {
    const draft = purchaseExample(today);
    expect(purchaseWorkspacePreview(draft)).toMatchObject({ gross: 50000000n, discount: 2500000n, net: 47500000n, freight: 1000000n, tax: 8730000n, total: 57230000n });
    const edited = reduce(draft, { type: 'line', key: 'p1', patch: { rate: '130' } });
    expect(purchaseWorkspacePreview(edited)).toMatchObject({ net: 48700000n, evidence: null, tax: null, total: null });
    expect(purchaseWorkspacePreview(reduce(draft, { type: 'header', field: 'postingDate', value: '2026-11-01' })).total).toBeNull();
    expect(purchaseWorkspacePreview(reduce(draft, { type: 'supplier', value: 'demo-services', policy })).total).toBeNull();
    expect(purchaseWorkspacePreview(reduce(draft, { type: 'line', key: 'p1', patch: { description: 'Long reference' } })).total).toBe(57230000n);
    expect(purchaseWorkspacePreview(reduce(draft, { type: 'move', key: 'p1', by: 1 })).total).toBe(57230000n);
    expect(purchaseWorkspacePreview(draft, true).total).toBeNull();
  });
  it('adds decimal account amounts exactly and treats invalid text as unknown', () => {
    const draft = newPurchaseWorkspace(today);
    draft.lines = ['0.1', '0.2'].map((amount, index) => ({ ...blankPurchaseLine(`p${index + 1}`, 'ACCOUNT'), subject: 'demo-stationery', amount }));
    expect(purchaseWorkspacePreview(draft).net).toBe(3000n);
    for (const amount of ['', 'bad', '-1', '0.12345', '1000000000000000']) {
      expect(purchaseLineAmounts({ ...draft.lines[0]!, amount })).toBeNull();
    }
    expect(purchaseLineAmounts({ ...draft.lines[0]!, discount: '0.11' })).toBeNull();
    expect(purchaseLineAmounts({ ...draft.lines[0]!, received: '100', billed: '99', rate: '999' })?.gross).toBe(1000n);
  });
  it('preserves entered facts across mode changes and adjusts only untouched rows', () => {
    const blank = reduce(newPurchaseWorkspace(today), { type: 'mode', mode: 'ACCOUNTS' });
    expect(blank.lines[0]!.kind).toBe('ACCOUNT');
    const source = purchaseExample(today);
    const accounts = reduce(source, { type: 'mode', mode: 'ACCOUNTS' });
    expect(accounts.lines).toEqual(source.lines);
    expect(purchaseWorkspaceProblems(accounts, policy).filter(problem => problem.field === 'kind')).toHaveLength(2);
    expect(purchaseWorkspaceProblems(reduce(accounts, { type: 'mode', mode: 'MIXED' }), policy)).toHaveLength(0);
  });
  it('chooses the one payable account with the supplier and never guesses between several or none', () => {
    const source = purchaseExample(today);
    const services = reduce(source, { type: 'supplier', value: 'demo-services', policy });
    expect(services.payable).toBe('demo-services-inr'); expect(services.invoice).toBe(source.invoice); expect(services.lines).toEqual(source.lines);
    expect(purchaseWorkspaceProblems(services, policy).some(problem => problem.field === 'payable')).toBe(false);
    expect(reduce(services, { type: 'supplier', value: 'demo-paper', policy }).payable).toBe('demo-trade');
    // Older data can leave a supplier with none, or with several: nothing is chosen, and the problem says why.
    const several = { ...policy, suppliers: [...policy.suppliers, { id: 'demo-several', label: 'Two payables', meta: '', payables: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }] }] };
    const ambiguous = reduce(services, { type: 'supplier', value: 'demo-several', policy: several });
    expect(ambiguous.payable).toBe(''); expect(ambiguous.invoice).toBe(source.invoice); expect(ambiguous.lines).toEqual(source.lines);
    expect(purchaseWorkspaceProblems(ambiguous, several).filter(problem => problem.field === 'payable').map(problem => problem.message)).toEqual([payableCountIssue(2)]);
    const incomplete = reduce(source, { type: 'supplier', value: 'demo-incomplete', policy });
    expect(incomplete.payable).toBe('');
    expect(purchaseWorkspaceProblems(incomplete, policy).filter(problem => problem.field === 'payable').map(problem => problem.message)).toEqual([payableCountIssue(0)]);
  });
  it('keeps stable keys through duplicate, insert, move and remove actions', () => {
    let draft = reduce(purchaseExample(today), { type: 'duplicate', key: 'p1' });
    expect(draft.lines.map(line => line.key)).toEqual(['p1', 'p3', 'p2']);
    draft = reduce(draft, { type: 'move', key: 'p3', by: 1 });
    expect(draft.lines.map(line => line.key)).toEqual(['p1', 'p2', 'p3']);
    draft = reduce(draft, { type: 'add', after: 'p1' });
    expect(draft.lines.map(line => line.key)).toEqual(['p1', 'p4', 'p2', 'p3']);
    for (const key of ['p1', 'p4', 'p2', 'p3']) draft = reduce(draft, { type: 'remove', key });
    expect(draft.lines).toHaveLength(1); expect(draft.lines[0]!.key).toBe('p5');
  });
  it('requires a reason for paid bundles and validates dates without rollover', () => {
    const source = purchaseExample(today);
    const draft = reduce(source, { type: 'line', key: 'p1', patch: { received: '25' } });
    expect(purchaseWorkspaceProblems(draft, policy).some(problem => problem.field === 'quantityReason')).toBe(true);
    expect(purchaseWorkspaceProblems(reduce(draft, { type: 'line', key: 'p1', patch: { quantityReason: 'One promotional pack received' } }), policy)).toEqual([]);
    expect(purchaseWorkspaceProblems({ ...source, invoiceDate: '2026-02-30' }, policy).some(problem => problem.field === 'invoiceDate')).toBe(true);
  });
  it('keeps supplied evidence when decimal text changes without changing its value', () => {
    const draft = reduce(purchaseExample(today), { type: 'line', key: 'p1', patch: { billed: '24.0000', rate: '125.0000', discount: '150.0000' } });
    expect(purchaseWorkspacePreview(draft).total).toBe(57230000n);
  });
});

describe('Purchase workspace interactions', () => {
  it('anchors hidden grid labels inside their scroll container', () => {
    const css = readFileSync(join(__dirname, '../../../packages/ui/src/styles/entry.css'), 'utf8');
    expect(css).toMatch(/\.janso-entry-workspace \.janso-entry-grid__scroll\s*\{[^}]*position: relative/);
  });
  it('opens an honest, accessible preview with separate document identities', () => {
    mount();
    expect(screen.getByRole('heading', { name: 'New purchase' })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Supplier and invoice details' })).toBeVisible();
    expect(screen.getByRole('complementary', { name: 'Purchase totals' })).toBeVisible();
    expect(screen.getByText(/lost on reload/)).toBeVisible();
    expect(screen.getByText('Unassigned')).toBeVisible();
    expect(screen.getByLabelText(/Supplier invoice date/)).toHaveValue(today);
    expect(screen.getByLabelText(/Posting date/)).toHaveValue(today);
    expect(screen.queryByRole('button', { name: /post purchase|submit bill/i })).not.toBeInTheDocument();
  });
  it('loads the example, requires confirmation before replacing edits and preserves them on cancel', async () => {
    const user = userEvent.setup(); mount();
    await user.click(screen.getByRole('button', { name: 'Load example bill' }));
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034');
    expect(screen.getAllByText('₹5,723.00')).toHaveLength(2);
    await user.click(screen.getByRole('button', { name: 'Load example bill' }));
    expect(screen.getByRole('dialog', { name: 'Load the example bill?' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Keep my entries' }));
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034');
  });
  it('takes the supplier’s one payable account with the supplier, never asks for it, and says so for a supplier with none', async () => {
    const user = userEvent.setup(); mount();
    await user.click(screen.getByRole('combobox', { name: /Supplier$/ }));
    await user.click(screen.getByRole('option', { name: /Northstar/ }));
    expect(screen.queryByRole('combobox', { name: /payable/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/payable account|Selected automatically|Chosen automatically/i)).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /Supplier$/ })).not.toHaveAttribute('aria-invalid', 'true');
    await user.click(screen.getByRole('combobox', { name: /Supplier$/ }));
    await user.click(screen.getByRole('option', { name: /setup incomplete/ }));
    expect(screen.getByText(payableCountIssue(0)!)).toBeVisible();
    expect(screen.queryByRole('combobox', { name: /payable/i })).not.toBeInTheDocument();
  });
  it('focuses supplier selection when the chosen supplier has no payable account and so cannot be billed', async () => {
    const user = userEvent.setup();
    mount(reduce(purchaseExample(today), { type: 'supplier', value: 'demo-incomplete', policy }));
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(screen.getByRole('combobox', { name: /Supplier$/ })).toHaveFocus();
  });
  it('uses account rows without quantities, supports Mixed and retains item details', async () => {
    const user = userEvent.setup(); mount(purchaseExample(today));
    await user.click(screen.getByRole('button', { name: 'Accounts / services' }));
    expect(screen.getByText(/2 lines are retained/)).toBeVisible();
    expect(within(table()).getByRole('textbox', { name: /Billed qty, line 1/ })).toHaveValue('24.0000');
    await user.click(screen.getByRole('button', { name: 'Use Mixed mode' }));
    expect(within(table()).getByRole('combobox', { name: 'Line type, line 1' })).toBeVisible();
    expect(screen.queryByText(/2 lines are retained/)).not.toBeInTheDocument();
  });
  it('supports keyboard add, duplicate, move and detail with focus restoration', async () => {
    const user = userEvent.setup(); mount(purchaseExample(today));
    const rate = within(table()).getByRole('textbox', { name: /Rate, line 1/ });
    await user.click(rate); await user.keyboard('{Control>}{Enter}{/Control}');
    expect(within(table()).getAllByRole('row')).toHaveLength(5);
    await user.click(rate); await user.keyboard('{Control>}d{/Control}');
    expect(within(table()).getAllByRole('row')).toHaveLength(6);
    await user.click(within(table()).getByRole('textbox', { name: /Rate, line 1/ }));
    await user.keyboard('{Alt>}{Enter}{/Alt}');
    expect(screen.getByRole('dialog', { name: 'Line 1 details' })).toBeVisible();
    await user.type(screen.getByLabelText('Line description'), 'For the reception team');
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it('enters an account amount directly without creating quantities', async () => {
    const user = userEvent.setup(); mount();
    await user.click(screen.getByRole('button', { name: 'Accounts / services' }));
    expect(within(table()).queryByRole('textbox', { name: /Receipt qty/ })).not.toBeInTheDocument();
    await user.type(within(table()).getByRole('combobox', { name: /Expense \/ service account, line 1/ }), 'Office');
    await user.click(screen.getByRole('option', { name: /Office stationery expense/ }));
    const amount = within(table()).getByRole('textbox', { name: /Base amount, line 1/ });
    await user.clear(amount); await user.type(amount, '4200'); await user.tab();
    expect(within(screen.getByRole('complementary', { name: 'Purchase totals' })).getAllByText('₹4,200.00')).toHaveLength(2);
    expect(screen.getByText(/Tax and charges need calculation evidence/)).toBeVisible();
  });
  it('undoes line removal without rolling back later edits', async () => {
    const user = userEvent.setup(); mount(purchaseExample(today));
    await user.click(screen.getByRole('button', { name: 'Remove line 1' }));
    await user.type(screen.getByLabelText(/Supplier invoice number/), '-revised');
    await user.click(screen.getByRole('button', { name: 'Undo removal' }));
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveValue('PC-261034-revised');
    expect(within(table()).getByRole('combobox', { name: 'Item, line 1' })).toHaveValue('A5 ruled notebooks · pack of 4');
  });
  it('focuses the reason editor from a quantity validation issue', async () => {
    const user = userEvent.setup();
    mount(reduce(purchaseExample(today), { type: 'line', key: 'p1', patch: { received: '25' } }));
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(screen.getByLabelText('Quantity difference reason')).toHaveFocus();
    await user.type(screen.getByLabelText('Quantity difference reason'), 'Promotional pack');
    await user.click(screen.getByRole('button', { name: 'Done' }));
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(screen.getByText('Demo draft only')).toBeVisible();
  });
  it('resets invalid cell text when explicitly replacing the bill with an example', async () => {
    const user = userEvent.setup(); mount(purchaseExample(today));
    const rate = within(table()).getByRole('textbox', { name: /Rate, line 1/ });
    await user.clear(rate); await user.type(rate, '125.00000'); await user.tab();
    await user.click(screen.getByRole('button', { name: 'Load example bill' }));
    await user.click(screen.getByRole('button', { name: 'Replace with example' }));
    expect(within(table()).getByRole('textbox', { name: /Rate, line 1/ })).not.toHaveAttribute('aria-invalid', 'true');
    expect(screen.getAllByText('₹5,723.00')).toHaveLength(2);
  });
  it('shows validation and moves focus to the first missing detail', async () => {
    const user = userEvent.setup(); mount();
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(screen.getByRole('region', { name: 'Purchase issues' })).toBeVisible();
    expect(screen.getByRole('combobox', { name: /Supplier$/ })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Enter the supplier invoice number.' }));
    expect(screen.getByLabelText(/Supplier invoice number/)).toHaveFocus();
  });
  it('blocks a stale numeric preview while invalid text remains visible', async () => {
    const user = userEvent.setup(); const onDemoSave = vi.fn(); mount(purchaseExample(today), { onDemoSave });
    const rate = within(table()).getByRole('textbox', { name: /Rate, line 1/ });
    await user.clear(rate); await user.type(rate, '125.12345'); await user.tab();
    expect(rate).toHaveAttribute('aria-invalid', 'true');
    expect(within(table()).getByRole('cell', { name: 'Net amount, line 1: —' })).toBeVisible();
    expect(screen.queryByText('₹5,723.00')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(onDemoSave).not.toHaveBeenCalled();
  });
  it('handles pending, failure, retry and demo completion without a persisted claim', async () => {
    let reject!: () => void;
    const onDemoSave = vi.fn().mockImplementationOnce(() => new Promise<void>((_, fail) => { reject = () => fail(Error('demo')); })).mockResolvedValue(undefined);
    const user = userEvent.setup(); mount(purchaseExample(today), { onDemoSave });
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(screen.getByRole('button', { name: 'Checking demo…' })).toBeDisabled();
    expect(screen.getByLabelText(/Supplier invoice number/)).toBeDisabled();
    await act(async () => reject());
    expect(screen.getByText('Demo action failed')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(screen.getByText('Demo draft only')).toBeVisible();
    const event = new Event(BEFORE_COMPANY_CHANGE, { cancelable: true });
    window.dispatchEvent(event); expect(event.defaultPrevented).toBe(false); // Initial snapshot was the supplied draft.
    await user.type(screen.getByLabelText(/Supplier invoice number/), '-edited');
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    const dirty = new Event(BEFORE_COMPANY_CHANGE, { cancelable: true });
    window.dispatchEvent(dirty); expect(dirty.defaultPrevented).toBe(true);
  });
  it('provides a review dialog with formatted details and returns to editing', async () => {
    const user = userEvent.setup(); mount(purchaseExample(today));
    await user.click(screen.getByRole('button', { name: 'Review bill' }));
    const dialog = screen.getByRole('dialog', { name: 'Review purchase bill' });
    expect(within(dialog).getByText('PC-261034')).toBeVisible();
    expect(within(dialog).getByText('₹5,723.00')).toBeVisible();
    await user.keyboard('{Escape}'); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Review bill' })).toHaveFocus();
  });
  it('makes every editing surface read only when creation is unavailable', async () => {
    const user = userEvent.setup(); mount(purchaseExample(today), { canCreate: false });
    expect(screen.queryByRole('button', { name: 'Save demo draft' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Load example bill' })).toBeDisabled();
    expect(screen.getByLabelText(/Supplier invoice number/)).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Review bill' }));
    expect(screen.getByRole('dialog', { name: 'Review purchase bill' })).toBeVisible();
  });
  it('keeps fixture currency explicit while respecting company separators and dates', async () => {
    const user = userEvent.setup();
    render(<DisplayConfigProvider config={{ currency: 'USD', currencySymbol: '$', decimalSeparator: ',', groupSeparator: '.', digitGrouping: 'western', dateFormat: 'dd.MM.yyyy', locale: 'de-DE' }}>
      <PurchaseWorkspace today={today} canCreate initialDraft={purchaseExample(today)} />
    </DisplayConfigProvider>);
    expect(screen.getByText(/Synthetic examples in INR/)).toBeVisible();
    expect(screen.getAllByText('₹5.723,00')).toHaveLength(2);
    await user.click(screen.getByRole('button', { name: 'Review bill' }));
    expect(within(screen.getByRole('dialog')).getAllByText('31.10.2026')).toHaveLength(2);
  });
  it('does not offer modes unavailable in the supplied fixture policy', async () => {
    const user = userEvent.setup();
    render(<PurchaseWorkspace today={today} canCreate policy={{ ...policy, modes: ['ITEMS'] }} initialDraft={{ ...purchaseExample(today), mode: 'ACCOUNTS' }} />);
    expect(screen.queryByRole('button', { name: 'Use Mixed mode' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(screen.getAllByText('Choose an available entry mode.').length).toBeGreaterThan(0);
  });
});
