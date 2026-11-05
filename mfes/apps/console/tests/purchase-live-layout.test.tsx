import type { ReactNode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PurchaseWorkspace, type PurchaseWorkspaceController } from '../app/components/PurchaseWorkspace';
import { PURCHASE_DEMO_POLICY, blankPurchaseLine, newPurchaseWorkspace, payableCountIssue, purchaseWorkspaceProblems, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from '../app/lib/purchase-workspace';
import { livePurchasePolicy } from '../app/lib/purchase-api';
import { metadata } from './purchase-entry-fixtures';

const TODAY = '2026-10-31';
const payable = (value: string) => ({ value, label: 'Payable ' + value });
const supplier = (payables: { value: string; label: string }[]) => ({ id: 'sup-1', label: 'Sharma Office Supplies', meta: 'Supplier', payables });
const accountDraft = (patch: Partial<PurchaseWorkspaceDraft> = {}): PurchaseWorkspaceDraft => ({ ...newPurchaseWorkspace(TODAY), mode: 'ACCOUNTS', lines: [blankPurchaseLine('p1', 'ACCOUNT')], ...patch });
const filled = (): PurchaseWorkspaceDraft => accountDraft({ supplier: 'sup-1', payable: 'pay-1', invoice: 'SOS/1', lines: [{ ...blankPurchaseLine('p1', 'ACCOUNT'), subject: 'acc-1', label: 'Office expenses', amount: '100.5' }] });

function mount(options: { draft?: PurchaseWorkspaceDraft; policy?: Partial<PurchaseWorkspacePolicy>; controller?: Partial<PurchaseWorkspaceController>; sections?: ReactNode } = {}) {
  const dispatch = vi.fn();
  const policy: PurchaseWorkspacePolicy = { ...livePurchasePolicy('INR', metadata), suppliers: [supplier([payable('pay-1')])], ...options.policy };
  const controller: PurchaseWorkspaceController = {
    live: true, draft: options.draft ?? filled(), dispatch, readOnly: false, pending: false, dirty: false, title: 'New purchase', note: 'Not saved yet',
    onTransientChange: vi.fn(), header: <h1>Page header slot</h1>, banner: () => null, sections: options.sections ?? <p>Sections slot</p>,
    actions: () => <button type="button">Save draft</button>, ...options.controller,
  };
  return { dispatch, ...render(<PurchaseWorkspace today={TODAY} canCreate policy={policy} controller={controller} />) };
}

describe('live Purchase workspace layout', () => {
  it('uses the page header it is given, in place of its own heading', () => {
    mount();
    expect(screen.getByRole('heading', { level: 1, name: 'Page header slot' })).toBeVisible();
    expect(screen.queryByText(/Capture your supplier bill/)).toBeNull();
    expect(screen.queryByText(/Purchases \/ Supplier bill/)).toBeNull();
  });

  it('is one column with no totals rail, and puts the sections after the lines', () => {
    const { container } = mount();
    expect(container.querySelector('.janso-entry-workspace__layout')).toHaveClass('janso-entry-workspace__layout--single');
    expect(container.querySelector('aside')).toBeNull();
    for (const text of ['Bill summary', 'Before you finish', 'Payment & terms', 'Accounting totals']) expect(screen.queryByText(text)).toBeNull();
    const lines = screen.getByRole('region', { name: 'Purchase line entry' });
    expect(lines.compareDocumentPosition(screen.getByText('Sections slot'))).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it('keeps the synthetic preview as it was: its own heading, mode choice and totals rail', () => {
    render(<PurchaseWorkspace today={TODAY} canCreate policy={PURCHASE_DEMO_POLICY} />);
    expect(screen.getByText(/Capture your supplier bill/)).toBeVisible();
    expect(screen.getByText('Entry mode')).toBeVisible();
    expect(screen.getByText('Bill summary')).toBeVisible();
    expect(screen.getByRole('columnheader', { name: /Discount/ })).toBeVisible();
  });

  it('does not offer an entry mode when only one is allowed', () => {
    mount();
    expect(screen.queryByText('Entry mode')).toBeNull();
    expect(screen.queryByRole('group', { name: 'Purchase entry mode' })).toBeNull();
  });

  it('does not render the invoice strip, which the header and action bar replace', () => {
    mount();
    expect(screen.queryByRole('group', { name: 'Current purchase bill' })).toBeNull();
  });

  it('hides the details card when the connected profile offers no panel, and shows it when one is offered', () => {
    const { unmount } = mount();
    expect(screen.queryByText('Purchase details')).toBeNull();
    unmount();
    const live = livePurchasePolicy('INR', metadata);
    mount({ policy: { details: { ...live.details, panels: { ...live.details.panels, components: { available: true, writable: true } } } } });
    expect(screen.getByText('Purchase details')).toBeVisible();
  });
});

describe('live supplier and bill card', () => {
  it('never shows the payable account: the supplier chooses it, so the card has no control and no text for it', () => {
    const { container } = mount();
    expect(screen.queryByText('Payable pay-1')).toBeNull();
    expect(screen.queryByText(/Chosen automatically/)).toBeNull();
    expect(screen.queryByRole('combobox', { name: /payable/i })).toBeNull();
    expect(container.querySelector('[data-purchase-field="payable"]')).toBeNull();
    expect(container).not.toHaveTextContent(/payable account/i);
    // Only the supplier is asked for, and it carries no complaint when it has its one account.
    expect(screen.getByRole('combobox', { name: /Supplier/ })).not.toHaveAttribute('aria-invalid', 'true');
  });

  it('lays the card out as the supplier first, then the bill’s number, dates and due date', () => {
    const { container } = mount();
    const fields = [...container.querySelector('.janso-purchase-fields')!.children];
    expect(fields.map(field => field.getAttribute('data-purchase-field') ?? field.tagName)).toEqual(['supplier', 'invoice', 'invoiceDate', 'postingDate', 'DL']);
    expect(fields[4]).toHaveTextContent(/^Payment due/);
    expect(container.querySelector('[data-purchase-field="supplier"]')).toHaveAttribute('data-span', '6');
  });

  it('says a supplier with several payable accounts cannot be billed, on the supplier, without offering a choice', () => {
    const { container } = mount({ policy: { suppliers: [supplier([payable('pay-1'), payable('pay-2')])] }, draft: { ...filled(), payable: '' } });
    expect(screen.queryByRole('combobox', { name: /payable/i })).toBeNull();
    expect(container.querySelector('[data-purchase-field="payable"]')).toBeNull();
    expect(container.querySelector('[data-purchase-field="supplier"]')).toHaveTextContent(payableCountIssue(2)!);
    expect(container).not.toHaveTextContent(/Choose the payable account/);
  });

  it('says a supplier with no payable account cannot be billed, on the supplier, as soon as it is chosen', () => {
    const { container } = mount({ policy: { suppliers: [supplier([])] }, draft: { ...filled(), payable: '' } });
    expect(container.querySelector('[data-purchase-field="supplier"]')).toHaveTextContent(payableCountIssue(0)!);
    expect(screen.queryByRole('combobox', { name: /payable/i })).toBeNull();
    expect(container).not.toHaveTextContent(/Supplier setup needed|No readable payable account/);
  });

  it('says nothing about an account before a supplier is chosen', () => {
    const { container } = mount({ draft: accountDraft() });
    expect(container).not.toHaveTextContent(/payable account/i);
    expect(screen.queryByRole('combobox', { name: /payable/i })).toBeNull();
    expect(container).not.toHaveTextContent(/Choose a supplier first/);
  });

  it('shows the payment due date worked out from the credit terms, read-only', () => {
    const draft = filled(); draft.invoiceDate = '2026-10-28'; draft.details.termsDays = '30'; draft.details.termsBasis = 'INVOICE_DATE';
    mount({ draft });
    const due = screen.getByText('Payment due').closest('dl')!;
    expect(due).toHaveTextContent('27 Nov 2026');
    expect(due.querySelector('input')).toBeNull();
    expect(screen.getByText('Accounting assigns the journal number when the bill is posted')).toBeVisible();
  });

  it('shows a dash for the due date when the credit terms cannot give one', () => {
    const draft = filled(); draft.details.termsDays = 'abc';
    mount({ draft });
    expect(screen.getByText('Payment due').closest('dl')).toHaveTextContent('—');
  });

  it('reports header edits to the controller', () => {
    const { dispatch } = mount();
    fireEvent.change(screen.getByLabelText(/Supplier invoice number/), { target: { value: 'SOS/2' } });
    expect(dispatch).toHaveBeenCalledWith({ type: 'header', field: 'invoice', value: 'SOS/2' });
  });
});

describe('live bill lines', () => {
  it('is an account bill: account, description and one amount, with no discount or net columns', () => {
    mount();
    const headers = screen.getAllByRole('columnheader').map(header => header.textContent?.replace(/\*/g, '').trim());
    expect(headers).toEqual(expect.arrayContaining(['Expense / service account', 'Description', 'Amount']));
    expect(headers.join('|')).not.toMatch(/Discount|Net amount|Base amount/);
    expect(screen.getByText(/Amounts in INR · no tax on this bill/)).toBeVisible();
  });

  it('types the line description in the grid', () => {
    const { dispatch } = mount();
    fireEvent.change(screen.getByPlaceholderText('Defaults to the account name'), { target: { value: 'Monthly supplies' } });
    expect(dispatch).toHaveBeenCalledWith({ type: 'line', key: 'p1', patch: { description: 'Monthly supplies' } });
  });

  it('brings the discount and net columns back when the type allows discounts', () => {
    mount({ policy: { discountsAllowed: true } });
    const headers = screen.getAllByRole('columnheader').map(header => header.textContent ?? '').join('|');
    expect(headers).toMatch(/Discount/);
    expect(headers).toMatch(/Net amount/);
  });
});

describe('live action bar total', () => {
  it('shows what has been typed as a lines total until Accounting has calculated', () => {
    const { container } = mount();
    const total = container.querySelector('.janso-entry__actions-total')!;
    expect(total).toHaveTextContent('Lines total');
    expect(total).toHaveTextContent(/100\.50/);
    expect(total).not.toHaveTextContent('Bill total');
  });

  it('says the lines are before GST for a bill that carries it, since the figure leaves the tax out', () => {
    const { container } = mount({ controller: { linesLabel: 'Lines before GST' } });
    const total = container.querySelector('.janso-entry__actions-total')!;
    expect(total).toHaveTextContent('Lines before GST');
    expect(total).not.toHaveTextContent('Lines total');
    // Once Accounting has calculated, the figure is the bill's total whatever it was called before.
    const calculated = mount({ controller: { linesLabel: 'Lines before GST', total: '118.0000' } }).container.querySelectorAll('.janso-entry__actions-total');
    expect(calculated[calculated.length - 1]).toHaveTextContent('Bill total');
  });

  it('switches to Accounting’s bill total once there is one', () => {
    const { container } = mount({ controller: { total: '24650.4966' } });
    const total = container.querySelector('.janso-entry__actions-total')!;
    expect(total).toHaveTextContent('Bill total');
    expect(total).toHaveTextContent(/24,650\.50/);
    expect(total).not.toHaveTextContent('Lines total');
  });

  it('shows a dash rather than a made-up total when nothing is entered or a line is incomplete', () => {
    const { container, unmount } = mount({ draft: accountDraft() });
    expect(container.querySelector('.janso-entry__actions-total')).toHaveTextContent('Lines total—');
    unmount();
    const incomplete = filled(); incomplete.lines[0]!.amount = 'abc';
    const second = mount({ draft: incomplete });
    expect(second.container.querySelector('.janso-entry__actions-total')).toHaveTextContent('Lines total—');
  });

  it('carries the state note and the page’s own actions', () => {
    const { container } = mount({ controller: { note: 'Draft · saved' } });
    expect(container.querySelector('.janso-entry__actions-note')).toHaveTextContent('Draft · saved');
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeVisible();
  });
});

describe('live bill line description', () => {
  const policy = (): PurchaseWorkspacePolicy => ({ ...livePurchasePolicy('INR', metadata), suppliers: [supplier([payable('pay-1')])], subjects: [{ id: 'acc-1', label: 'Office expenses', meta: '', kind: 'ACCOUNT', unit: '' }] });

  it('accepts a description up to the service limit', () => {
    const draft = filled(); draft.lines[0]!.description = 'x'.repeat(1000);
    expect(purchaseWorkspaceProblems(draft, policy()).filter(problem => problem.field === 'description')).toEqual([]);
  });

  it('refuses a longer one here, on its own line, instead of leaving the service to refuse the whole bill', () => {
    const draft = filled(); draft.lines[0]!.description = 'x'.repeat(1001);
    expect(purchaseWorkspaceProblems(draft, policy()).filter(problem => problem.field === 'description')).toEqual([
      expect.objectContaining({ lineKey: 'p1', message: 'Use at most 1,000 characters in the description.' }),
    ]);
  });
});

describe('live review-only notice', () => {
  it('says the bill itself cannot be edited, when the page supplies that reason', () => {
    render(<PurchaseWorkspace today={TODAY} canCreate={false} policy={livePurchasePolicy('INR', metadata)} controller={{ live: true, draft: filled(), dispatch: vi.fn(), readOnly: true, pending: false, dirty: false, title: 'Bill', note: '', onTransientChange: vi.fn(), banner: () => null, actions: () => null,
      reviewNotice: <p>This purchase is posted and can no longer be edited here.</p> }} />);
    expect(screen.getByText('This purchase is posted and can no longer be edited here.')).toBeVisible();
    expect(screen.queryByText('You do not have permission to create vouchers for this company.')).toBeNull();
  });

  it('keeps the permission wording when nothing else explains it', () => {
    render(<PurchaseWorkspace today={TODAY} canCreate={false} policy={livePurchasePolicy('INR', metadata)} controller={{ live: true, draft: filled(), dispatch: vi.fn(), readOnly: true, pending: false, dirty: false, title: 'Bill', note: '', onTransientChange: vi.fn(), banner: () => null, actions: () => null }} />);
    expect(screen.getByText('You do not have permission to create vouchers for this company.')).toBeVisible();
  });
});
