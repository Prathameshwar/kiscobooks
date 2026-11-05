import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PurchaseLineEditor } from '../app/components/PurchaseLineEditor';
import { PurchaseWorkspace, type PurchaseWorkspaceController } from '../app/components/PurchaseWorkspace';
import { blankPurchaseLine, newPurchaseWorkspace, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from '../app/lib/purchase-workspace';
import { livePurchasePolicy } from '../app/lib/purchase-api';
import type { PurchaseQuickCreate } from '../app/lib/purchase-quick-create';
import { metadata } from './purchase-entry-fixtures';

vi.setConfig({ testTimeout: 15000 });
const TODAY = '2026-10-31';
const supplier = { id: 'sup-1', label: 'Sharma Office Supplies', meta: 'Supplier', payables: [{ value: 'pay-1', label: 'Payable pay-1' }] };
const accountDraft = (patch: Partial<PurchaseWorkspaceDraft> = {}): PurchaseWorkspaceDraft => ({ ...newPurchaseWorkspace(TODAY), mode: 'ACCOUNTS', lines: [blankPurchaseLine('p1', 'ACCOUNT')], ...patch });
const policyFor = (patch: Partial<PurchaseWorkspacePolicy> = {}): PurchaseWorkspacePolicy => ({ ...livePurchasePolicy('INR', metadata), suppliers: [supplier], ...patch });

function mount(options: { draft?: PurchaseWorkspaceDraft; quickCreate?: PurchaseQuickCreate; pending?: boolean; policy?: Partial<PurchaseWorkspacePolicy> } = {}) {
  const dispatch = vi.fn();
  const controller: PurchaseWorkspaceController = {
    live: true, draft: options.draft ?? accountDraft(), dispatch, readOnly: false, pending: options.pending ?? false, dirty: false, title: 'New purchase', note: 'Not saved yet',
    onTransientChange: vi.fn(), header: <h1>Header</h1>, banner: () => null, sections: null, actions: () => null, quickCreate: options.quickCreate,
  };
  render(<PurchaseWorkspace today={TODAY} canCreate policy={policyFor(options.policy)} controller={controller} />);
  return { dispatch, user: userEvent.setup() };
}

describe('the supplier field’s create icon', () => {
  it('is not offered when the actor cannot create suppliers', () => {
    mount();
    expect(screen.queryByRole('button', { name: 'Create a new supplier' })).toBeNull();
  });

  it('sits in the same row as the Supplier box, after it — not above it with the label — named for what it does', () => {
    mount({ quickCreate: { supplier: vi.fn() } });
    const button = screen.getByRole('button', { name: 'Create a new supplier' });
    const field = document.querySelector('[data-purchase-field="supplier"]') as HTMLElement;
    const combobox = within(field).getByRole('combobox', { name: /Supplier/ });
    const layout = field.querySelector('.console-reference-create') as HTMLElement;
    expect(layout).toContainElement(button);
    expect(layout).toContainElement(combobox);
    expect(layout).toHaveClass('console-reference-create--flush');
    // not in the label row, and after the control in reading order
    expect(field.querySelector('.janso-field__row')).not.toContainElement(button);
    expect(combobox.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(button).toHaveClass('console-reference-create__action');
    expect(button).toHaveAttribute('aria-haspopup', 'dialog');
    expect(button).toHaveAttribute('title', 'Create a new supplier');
  });

  it('adds no wrapper at all when there is nothing to create', () => {
    mount();
    expect(document.querySelector('[data-purchase-field="supplier"] .console-reference-create')).toBeNull();
    expect(within(document.querySelector('[data-purchase-field="supplier"]') as HTMLElement).getByRole('combobox', { name: /Supplier/ })).toBeVisible();
  });

  it('opens the supplier creation on click and on the keyboard', async () => {
    const supplierCreate = vi.fn();
    const { user } = mount({ quickCreate: { supplier: supplierCreate } });
    await user.click(screen.getByRole('button', { name: 'Create a new supplier' }));
    expect(supplierCreate).toHaveBeenCalledTimes(1);
    screen.getByRole('button', { name: 'Create a new supplier' }).focus();
    await user.keyboard('{Enter}');
    await user.keyboard(' ');
    expect(supplierCreate).toHaveBeenCalledTimes(3);
  });

  it('is disabled while the bill is busy, rather than vanishing from under the pointer', () => {
    mount({ quickCreate: { supplier: vi.fn() }, pending: true });
    expect(screen.getByRole('button', { name: 'Create a new supplier' })).toBeDisabled();
  });

  it('is not offered for an account-only permission: no supplier icon without a supplier entry', () => {
    mount({ quickCreate: { account: vi.fn() } });
    expect(screen.queryByRole('button', { name: 'Create a new supplier' })).toBeNull();
  });
});

describe('the expense account create icon on a bill line', () => {
  const lines = () => accountDraft({ lines: [blankPurchaseLine('p1', 'ACCOUNT'), blankPurchaseLine('p2', 'ACCOUNT')] });

  it('is not offered when the actor cannot create expense accounts', () => {
    mount({ draft: lines() });
    expect(screen.queryByRole('button', { name: /Create a new expense account/ })).toBeNull();
  });

  it('appears on every account line, named for its line', () => {
    mount({ draft: lines(), quickCreate: { account: vi.fn() } });
    for (const n of [1, 2]) {
      const button = screen.getByRole('button', { name: `Create a new expense account for line ${n}` });
      expect(button).toHaveAttribute('aria-haspopup', 'dialog');
      expect(button.closest('.janso-entry-cell__with-action')).not.toBeNull();
    }
  });

  it('names the line it was clicked on', async () => {
    const account = vi.fn();
    const { user } = mount({ draft: lines(), quickCreate: { account } });
    await user.click(screen.getByRole('button', { name: 'Create a new expense account for line 2' }));
    expect(account).toHaveBeenCalledWith({ lineKey: 'p2' });
  });

  it('works from the keyboard without the grid taking Enter as "next row"', async () => {
    const account = vi.fn();
    const { user, dispatch } = mount({ draft: lines(), quickCreate: { account } });
    screen.getByRole('button', { name: 'Create a new expense account for line 1' }).focus();
    await user.keyboard('{Enter}');
    expect(account).toHaveBeenCalledTimes(1);
    expect(account).toHaveBeenCalledWith({ lineKey: 'p1' });
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('keeps the lookup beside it working: the cell still names and fills its line', () => {
    mount({ draft: lines(), quickCreate: { account: vi.fn() } });
    const cell = document.querySelector('[data-entry-row="p1"][data-entry-col="subject"]') as HTMLElement;
    expect(cell).not.toBeNull();
    // the button is a sibling of the cell the grid navigates, not inside it
    expect(cell).not.toContainElement(screen.getByRole('button', { name: 'Create a new expense account for line 1' }));
    expect(within(cell).getByRole('combobox')).toBeVisible();
  });

  it('is disabled with the rest of the line while the bill is busy', () => {
    mount({ draft: lines(), quickCreate: { account: vi.fn() }, pending: true });
    expect(screen.getByRole('button', { name: 'Create a new expense account for line 1' })).toBeDisabled();
  });

  it('is not offered on an item line of a mixed bill, where an expense account makes no sense', () => {
    mount({ draft: { ...newPurchaseWorkspace(TODAY), mode: 'MIXED', lines: [blankPurchaseLine('p1', 'ITEM'), blankPurchaseLine('p2', 'ACCOUNT')] }, quickCreate: { account: vi.fn() },
      policy: { modes: ['ITEMS', 'ACCOUNTS', 'MIXED'] } });
    expect(screen.queryByRole('button', { name: 'Create a new expense account for line 1' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Create a new expense account for line 2' })).toBeVisible();
  });

  it('shows the icon on a line as soon as the actor is allowed, with no change to its rows’ other cells', () => {
    mount({ draft: lines(), quickCreate: { account: vi.fn() } });
    const row = document.querySelector('[data-entry-row="p1"][data-entry-col="subject"]')!.closest('tr')!;
    expect(within(row).getAllByRole('button', { name: /Create a new expense account/ })).toHaveLength(1);
    expect(within(row).getByRole('textbox', { name: /Description/ })).toBeVisible();
  });
});

describe('the mobile line editor’s create icon', () => {
  const accountLine = { ...blankPurchaseLine('p1', 'ACCOUNT'), amount: '10' };
  function editor(options: { canEdit?: boolean; line?: ReturnType<typeof blankPurchaseLine>; create?: (target: { lineKey: string; apply?: (created: { id: string; label: string }) => void }) => void } = {}) {
    const onApply = vi.fn(), onClose = vi.fn(), line = options.line ?? accountLine;
    // the connected bill has verified the created account by the time it fills the editor, so the editor knows it
    const known = { id: 'acc-9', label: 'Office rent', meta: '', kind: 'ACCOUNT' as const, unit: '' };
    render(<PurchaseLineEditor draft={accountDraft({ lines: [line] })} line={line} ordinal={1} policy={policyFor({ subjects: [known] })} canEdit={options.canEdit ?? true} onCreateAccount={options.create} onApply={onApply} onClose={onClose} />);
    return { onApply, user: userEvent.setup() };
  }

  it('is offered in the same row as the expense account box of an account line', () => {
    editor({ create: vi.fn() });
    const field = document.querySelector('[data-purchase-line-field="subject"]') as HTMLElement;
    const button = within(field).getByRole('button', { name: 'Create a new expense account' });
    expect(field.querySelector('.console-reference-create')).toContainElement(button);
    expect(field.querySelector('.janso-field__row')).not.toContainElement(button);
  });

  it.each([
    ['without the permission', { create: undefined }],
    ['for a review-only line', { create: vi.fn(), canEdit: false }],
    ['on an item line', { create: vi.fn(), line: blankPurchaseLine('p1', 'ITEM') }],
  ])('is not offered %s', (_when, options) => {
    editor(options);
    expect(screen.queryByRole('button', { name: 'Create a new expense account' })).toBeNull();
  });

  it('stages the created account in the editor, and only applies it to the bill with the line', async () => {
    let target!: { lineKey: string; apply?: (created: { id: string; label: string }) => void };
    const { user, onApply } = editor({ create: next => { target = next; } });
    await user.click(screen.getByRole('button', { name: 'Create a new expense account' }));
    expect(target.lineKey).toBe('p1');
    expect(target.apply).toBeTypeOf('function');
    // the connected bill calls this once Accounting has created the account
    act(() => target.apply!({ id: 'acc-9', label: 'Office rent' }));
    expect(onApply).not.toHaveBeenCalled();
    expect(await screen.findByText('Office rent', { selector: '.janso-entry-line-card__name' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Apply line' }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ key: 'p1', subject: 'acc-9', label: 'Office rent' }));
  });
});
