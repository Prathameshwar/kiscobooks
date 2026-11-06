import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PurchasePageHeader } from '../app/components/PurchasePageHeader';
import { PurchaseDraftsDrawer, type PurchaseDraftRow } from '../app/components/PurchaseDraftsDrawer';
import { PurchaseTermsCard } from '../app/components/PurchaseTermsCard';
import { PurchaseCalculationCard } from '../app/components/PurchaseCalculationCard';
import { PurchaseLifecycle } from '../app/components/PurchaseLifecycle';
import { newPurchaseWorkspace } from '../app/lib/purchase-workspace';
import type { PurchaseCalculation, PurchaseOperation, PurchaseVoucher } from '../app/lib/purchase-api';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');

describe('PurchasePageHeader', () => {
  const props = { title: 'New purchase', status: null, typeName: 'Account purchases', currency: 'INR', canStartNew: false, locked: false, onDrafts: vi.fn() };

  it('is the page heading, with the scope in plain words and the facts as chips', () => {
    render(<PurchasePageHeader {...props} />);
    expect(screen.getByRole('heading', { level: 1, name: 'New purchase' })).toBeVisible();
    expect(screen.getByText(/expenses, services, products, or a mix, with or without GST/)).toBeVisible();
    for (const chip of ['Not saved', 'Account purchases', 'Amounts in INR']) expect(screen.getByText(chip)).toBeVisible();
    expect(screen.getByRole('link', { name: 'Purchases' })).toHaveAttribute('href', '/vouchers');
  });

  it('names the saved status instead of echoing the raw value', () => {
    render(<PurchasePageHeader {...props} status="SUBMITTED" />);
    expect(screen.getByText('Submitted for approval')).toBeVisible();
    expect(screen.queryByText('SUBMITTED')).toBeNull();
  });

  it('leaves out the type chip when the type name is unknown', () => {
    render(<PurchasePageHeader {...props} typeName={undefined} />);
    expect(screen.queryByText('Account purchases')).toBeNull();
    expect(screen.getByText('Amounts in INR')).toBeVisible();
  });

  it('offers a fresh bill only once there is a saved one on screen', () => {
    const { rerender } = render(<PurchasePageHeader {...props} />);
    expect(screen.queryByRole('link', { name: 'New purchase' })).toBeNull();
    rerender(<PurchasePageHeader {...props} canStartNew status="DRAFT" />);
    expect(screen.getByRole('link', { name: 'New purchase' })).toHaveAttribute('href', '/vouchers/new/purchase');
  });

  it('offers Print as a link to the saved revision once it may be printed', () => {
    render(<PurchasePageHeader {...props} status="DRAFT" canStartNew print={{ kind: 'ready', href: '/vouchers/abc/print?revision=r&version=3' }} />);
    expect(screen.getByRole('link', { name: 'Print' })).toHaveAttribute('href', '/vouchers/abc/print?revision=r&version=3');
  });

  it('shows Print disabled, and says why to assistive technology, when it may not be printed yet', () => {
    render(<PurchasePageHeader {...props} status="DRAFT" canStartNew print={{ kind: 'blocked', reason: 'Save your changes before printing.' }} />);
    const button = screen.getByRole('button', { name: 'Print' });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription('Save your changes before printing.');
    expect(screen.getByText('Save your changes before printing.')).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Print' })).toBeNull();
  });

  it('shows no Print at all by default or when it is hidden', () => {
    const { rerender } = render(<PurchasePageHeader {...props} />);
    expect(screen.queryByText('Print')).toBeNull();
    rerender(<PurchasePageHeader {...props} print={{ kind: 'hidden' }} />);
    expect(screen.queryByText('Print')).toBeNull();
  });

  it('opens the saved drafts, unless a request is pending', () => {
    const onDrafts = vi.fn();
    const { rerender } = render(<PurchasePageHeader {...props} onDrafts={onDrafts} />);
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    expect(onDrafts).toHaveBeenCalledTimes(1);
    rerender(<PurchasePageHeader {...props} onDrafts={onDrafts} locked />);
    expect(screen.getByRole('button', { name: 'Saved drafts' })).toBeDisabled();
  });
});

describe('PurchaseDraftsDrawer', () => {
  const rows: PurchaseDraftRow[] = [{ id: id(91), status: 'DRAFT', document_date: '2026-10-28' }, { id: id(92), status: 'DRAFT', document_date: null }];
  const base = { open: true, onClose: vi.fn(), drafts: rows, loaded: true, cursor: null, locked: false, failure: '', resume: '', onResume: vi.fn(), onOpen: vi.fn(), onMore: vi.fn(), onRetry: vi.fn() };

  it('lists drafts by date, and opens the one chosen', () => {
    const onOpen = vi.fn();
    render(<PurchaseDraftsDrawer {...base} onOpen={onOpen} />);
    const list = screen.getByRole('list', { name: 'Saved purchase drafts' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(within(list).getByText('Saved draft')).toBeVisible();
    fireEvent.click(within(list).getByRole('button', { name: new RegExp('without a date, ' + id(92)) }));
    expect(onOpen).toHaveBeenCalledWith(id(92));
  });

  it('says it is loading before the first read, and what an empty list means after it', () => {
    const { rerender } = render(<PurchaseDraftsDrawer {...base} drafts={[]} loaded={false} />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading saved drafts…');
    rerender(<PurchaseDraftsDrawer {...base} drafts={[]} loaded />);
    expect(screen.getByText('No saved drafts')).toBeVisible();
  });

  it('shows a failed read inside the drawer, where the person is looking, and offers to try again', () => {
    const onRetry = vi.fn();
    render(<PurchaseDraftsDrawer {...base} drafts={[]} failure="The saved Purchase list could not be verified." onRetry={onRetry} />);
    expect(screen.getByText('The saved Purchase list could not be verified.')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('offers no retry when nothing failed, and not while a request is pending', () => {
    const { rerender } = render(<PurchaseDraftsDrawer {...base} />);
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
    rerender(<PurchaseDraftsDrawer {...base} failure="Unavailable." locked />);
    expect(screen.getByRole('button', { name: 'Try again' })).toBeDisabled();
  });

  it('pages on request', () => {
    const onMore = vi.fn();
    render(<PurchaseDraftsDrawer {...base} cursor="next-page" onMore={onMore} />);
    fireEvent.click(screen.getByRole('button', { name: 'More saved purchases' }));
    expect(onMore).toHaveBeenCalledWith('next-page');
  });

  it('opens by a pasted ID only when it is a valid one', () => {
    const onOpen = vi.fn();
    const { rerender } = render(<PurchaseDraftsDrawer {...base} resume="not-an-id" onOpen={onOpen} />);
    expect(screen.getByRole('button', { name: 'Open saved purchase' })).toBeDisabled();
    rerender(<PurchaseDraftsDrawer {...base} resume={id(91)} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open saved purchase' }));
    expect(onOpen).toHaveBeenCalledWith(id(91));
  });

  it('cannot open anything while a request is pending', () => {
    render(<PurchaseDraftsDrawer {...base} locked cursor="x" resume={id(91)} />);
    for (const button of [...screen.getAllByRole('button', { name: /^Open draft/ }), screen.getByRole('button', { name: 'More saved purchases' }), screen.getByRole('button', { name: 'Open saved purchase' })])
      expect(button).toBeDisabled();
  });

  it('renders nothing when closed', () => {
    render(<PurchaseDraftsDrawer {...base} open={false} />);
    expect(screen.queryByText('Saved purchase drafts')).toBeNull();
  });
});

describe('PurchaseTermsCard', () => {
  const draft = () => { const value = newPurchaseWorkspace('2026-10-31'); value.details.termsDays = '30'; return value; };
  const base = { draft: draft(), taxConfirmed: false, taxError: false, onTaxConfirmed: vi.fn(), editable: true, locked: false, onEdit: vi.fn() };

  it('asks for the no-tax confirmation and reports the choice', () => {
    const onTaxConfirmed = vi.fn();
    render(<PurchaseTermsCard {...base} onTaxConfirmed={onTaxConfirmed} />);
    const box = screen.getByRole('checkbox', { name: 'This bill carries no tax' });
    expect(box).not.toBeChecked();
    expect(box).toHaveAccessibleDescription('Required before saving.');
    fireEvent.click(box);
    expect(onTaxConfirmed).toHaveBeenCalledWith(true);
  });

  it('marks the confirmation invalid, in words, when a save was refused', () => {
    render(<PurchaseTermsCard {...base} taxError />);
    expect(screen.getByRole('alert')).toHaveTextContent('Confirm that this is an untaxed account bill before saving.');
    expect(screen.getByRole('checkbox', { name: 'This bill carries no tax' })).toHaveAttribute('aria-invalid', 'true');
  });

  it('does not keep the refusal on screen once the box is ticked', () => {
    render(<PurchaseTermsCard {...base} taxError taxConfirmed />);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByRole('checkbox', { name: 'This bill carries no tax' })).not.toHaveAttribute('aria-invalid');
  });

  it('reads the terms back as sentences', () => {
    const value = draft(); value.details.declaredTotal = '24650.5'; value.details.notes = ' Paid by cheque '; value.details.supportingFiles = [{} as never, {} as never];
    render(<PurchaseTermsCard {...base} draft={value} taxConfirmed />);
    expect(screen.getByText('30 days from the supplier invoice date')).toBeVisible();
    expect(screen.getByText(/24,650\.50/)).toBeVisible();
    expect(screen.getByText('Paid by cheque')).toBeVisible();
    expect(screen.getByText('2 files')).toBeVisible();
  });

  it('says so when nothing was entered, and omits files that do not exist', () => {
    render(<PurchaseTermsCard {...base} />);
    expect(screen.getByText('Not entered')).toBeVisible();
    expect(screen.getByText('None')).toBeVisible();
    expect(screen.queryByText('Supporting files')).toBeNull();
  });

  it('is read-only for a reader, and locked during a request', () => {
    const { rerender } = render(<PurchaseTermsCard {...base} editable={false} />);
    expect(screen.getByRole('checkbox', { name: 'This bill carries no tax' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'View terms and details' })).toBeEnabled();
    rerender(<PurchaseTermsCard {...base} locked />);
    expect(screen.getByRole('button', { name: 'Edit terms and details' })).toBeDisabled();
  });

  it('opens the detail editor', () => {
    const onEdit = vi.fn();
    render(<PurchaseTermsCard {...base} onEdit={onEdit} />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit terms and details' }));
    expect(onEdit).toHaveBeenCalledTimes(1);
  });
});

describe('PurchaseCalculationCard', () => {
  const calculation = { commercial_total: '24650.5000', tax_total: '0.0000', rounding: '-0.0034', payable: '24650.4966', supplier_difference: null } as PurchaseCalculation;

  it('shows Accounting’s figures with the payable as the bottom line', () => {
    const { container } = render(<PurchaseCalculationCard calculation={calculation} accepted={false} revision={2} />);
    expect(screen.getByText('Ready to accept')).toBeVisible();
    expect(screen.getByText('Commercial total')).toBeVisible();
    expect(container.querySelector('[data-emphasis="true"]')).toHaveTextContent('Supplier payable');
    expect(screen.getByText(/revision 2\. Review it, then accept it/)).toBeVisible();
    expect(screen.queryByText(/Difference from supplier/)).toBeNull();
  });

  it('shows the difference from the supplier’s own total when there is one, and the accepted state', () => {
    render(<PurchaseCalculationCard calculation={{ ...calculation, supplier_difference: '-5.0000' } as PurchaseCalculation} accepted revision={3} />);
    expect(screen.getByText('Accepted')).toBeVisible();
    expect(screen.getByText('Difference from supplier’s own total')).toBeVisible();
    expect(screen.getByText(/Accepted for submission/)).toBeVisible();
  });
});

describe('PurchaseLifecycle', () => {
  const voucher = (status: string) => ({ id: id(90), status, revision_number: 2, row_version: 5 }) as unknown as PurchaseVoucher;
  const everything = () => true;
  const base = {
    record: voucher('DRAFT'), accepted: false, locked: false, dirty: false, editable: true, approvalRequired: true, duplicates: [], allowed: everything,
    reason: '', onReason: vi.fn(), transitions: ['submit', 'cancel'], onTransition: vi.fn(),
    executionReady: true, executing: false, onPost: vi.fn(), history: [], historyCursor: null, onHistory: vi.fn(), onRevision: vi.fn(),
    operation: null as PurchaseOperation | null, onRefresh: vi.fn(), onRecover: vi.fn(),
    today: '2026-11-06', onReverse: vi.fn(), onReplacement: vi.fn(),
  };

  it('says there are no steps yet, rather than showing nothing, once the history has been read and is empty', () => {
    const { rerender } = render(<PurchaseLifecycle {...base} />);
    expect(screen.queryByText(/No steps recorded yet/)).toBeNull();
    rerender(<PurchaseLifecycle {...base} historyLoaded />);
    expect(screen.getByText(/No steps recorded yet/)).toBeVisible();
    expect(screen.getByText(/Each save keeps its own revision/)).toBeVisible();
    rerender(<PurchaseLifecycle {...base} historyLoaded history={[{ id: id(70), action: 'submit', from_status: 'DRAFT', to_status: 'SUBMITTED', revision_id: id(91) }]} />);
    expect(screen.queryByText(/No steps recorded yet/)).toBeNull();
    expect(screen.getByRole('list', { name: 'Revision history' })).toBeVisible();
  });

  it('shows the status, revision and a progress track with the next step marked', () => {
    render(<PurchaseLifecycle {...base} />);
    expect(screen.getByText('Revision 2')).toBeVisible();
    expect(screen.getByText('Version 5')).toBeVisible();
    const track = screen.getByRole('list', { name: 'Bill progress' });
    expect(within(track).getAllByRole('listitem')).toHaveLength(5);
    expect(within(track).getByText('Calculation accepted').closest('li')).toHaveAttribute('aria-current', 'step');
    expect(within(track).getByText('Draft saved').closest('li')).not.toHaveAttribute('aria-current');
    expect(within(track).getByText('Draft saved').closest('li')).toHaveTextContent(', done');
  });

  it('explains why Submit is unavailable until the calculation is accepted', () => {
    const onTransition = vi.fn();
    const { rerender } = render(<PurchaseLifecycle {...base} onTransition={onTransition} />);
    expect(screen.getByText(/Submitting becomes available once the Accounting calculation is accepted/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Submit' })).toBeDisabled();
    rerender(<PurchaseLifecycle {...base} accepted onTransition={onTransition} />);
    expect(screen.queryByText(/Submitting becomes available/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    expect(onTransition).toHaveBeenCalledWith('submit');
  });

  it('says submitting approves the bill when the voucher type needs no separate approval, and does not otherwise', () => {
    const { rerender } = render(<PurchaseLifecycle {...base} accepted approvalRequired={false} />);
    expect(screen.getByRole('heading', { name: 'Status' })).toBeVisible();
    expect(screen.getByText(/does not need a separate approval: submitting approves the bill/)).toBeVisible();
    rerender(<PurchaseLifecycle {...base} accepted approvalRequired />);
    expect(screen.getByRole('heading', { name: 'Status and approval' })).toBeVisible();
    expect(screen.queryByText(/does not need a separate approval/)).toBeNull();
    rerender(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted approvalRequired={false} transitions={['cancel']} />);
    expect(screen.getByText(/returns it to Draft\. It must be calculated/)).toBeVisible();
    expect(screen.queryByText(/voids its approval/)).toBeNull();
    rerender(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted approvalRequired transitions={['cancel']} />);
    expect(screen.getByText(/returns it to Draft and voids its approval/)).toBeVisible();
  });

  it('asks for a reason only when reject or cancel is on offer, and requires one before they work', () => {
    const onReason = vi.fn();
    const { rerender } = render(<PurchaseLifecycle {...base} accepted onReason={onReason} />);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Action reason'), { target: { value: 'Duplicate bill' } });
    expect(onReason).toHaveBeenCalledWith('Duplicate bill');
    rerender(<PurchaseLifecycle {...base} accepted reason="Duplicate bill" />);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
    rerender(<PurchaseLifecycle {...base} accepted transitions={['submit']} />);
    expect(screen.queryByLabelText('Action reason')).toBeNull();
  });

  it('needs a reason of at least three characters, counting what is typed and not the spaces around it', () => {
    const { rerender } = render(<PurchaseLifecycle {...base} accepted reason="ab" />);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    rerender(<PurchaseLifecycle {...base} accepted reason="  ab  " />);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    rerender(<PurchaseLifecycle {...base} accepted reason="abc" />);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
  });

  it('requires an explicit confirmation before cancelling, and dismissing it sends nothing', () => {
    const onTransition = vi.fn();
    render(<PurchaseLifecycle {...base} accepted reason="Duplicate supplier bill" onTransition={onTransition} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    const dialog = screen.getByRole('dialog', { name: 'Cancel this Purchase bill?' });
    expect(onTransition).not.toHaveBeenCalled();
    expect(within(dialog).getByText('Reason: Duplicate supplier bill')).toBeVisible();
    expect(within(dialog).getByRole('button', { name: 'Keep bill' })).toHaveFocus();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep bill' }));
    expect(screen.queryByRole('dialog', { name: 'Cancel this Purchase bill?' })).not.toBeInTheDocument();
    expect(onTransition).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Cancel this Purchase bill?' })).getByRole('button', { name: 'Cancel Purchase' }));
    expect(onTransition).toHaveBeenCalledTimes(1);
    expect(onTransition).toHaveBeenCalledWith('cancel');
  });

  it('invalidates a cancellation confirmation when the saved version changes', () => {
    const onTransition = vi.fn();
    const { rerender } = render(<PurchaseLifecycle {...base} reason="Duplicate supplier bill" onTransition={onTransition} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('dialog', { name: 'Cancel this Purchase bill?' })).toBeVisible();
    rerender(<PurchaseLifecycle {...base} record={{ ...voucher('DRAFT'), row_version: 6 }} reason="Duplicate supplier bill" onTransition={onTransition} />);
    expect(screen.queryByRole('dialog', { name: 'Cancel this Purchase bill?' })).not.toBeInTheDocument();
    expect(onTransition).not.toHaveBeenCalled();
  });

  it('requires authority, reason and confirmation before reversing a posted Purchase', () => {
    const onReverse = vi.fn();
    const posted = voucher('POSTED');
    const { rerender } = render(<PurchaseLifecycle {...base} record={posted} transitions={[]} onReverse={onReverse} />);
    expect(screen.getByRole('button', { name: 'Full edit posted Purchase' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel posted Purchase' })).toBeDisabled();
    rerender(<PurchaseLifecycle {...base} record={posted} transitions={[]} reason="Supplier corrected invoice" onReverse={onReverse} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel posted Purchase' }));
    const dialog = screen.getByRole('dialog', { name: 'Cancel this posted Purchase?' });
    expect(onReverse).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep posted bill' }));
    expect(onReverse).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Full edit posted Purchase' }));
    const correction = screen.getByRole('dialog', { name: 'Correct this posted Purchase?' });
    expect(within(correction).getByLabelText('Correction posting date')).toHaveValue('2026-11-06');
    fireEvent.click(within(correction).getByRole('button', { name: 'Reverse and edit' }));
    expect(onReverse).toHaveBeenCalledWith('EDIT', '2026-11-06');
    rerender(<PurchaseLifecycle {...base} record={posted} transitions={[]} reason="Supplier corrected invoice" allowed={action => action !== 'reverse'} onReverse={onReverse} />);
    expect(screen.queryByRole('button', { name: 'Full edit posted Purchase' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Cancel posted Purchase' })).toBeNull();
    rerender(<PurchaseLifecycle {...base} record={voucher('REVERSED')} transitions={[]} onReverse={onReverse} />);
    expect(screen.getByRole('button', { name: 'Create linked replacement draft' })).toBeEnabled();
  });

  it('offers no action while a posting is running, and says why', () => {
    render(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted transitions={['cancel']} executing />);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByText(/A posting is in progress/)).toBeVisible();
  });

  it('warns that saving a submitted or approved bill returns it to Draft, only when it can be edited', () => {
    const { rerender } = render(<PurchaseLifecycle {...base} record={voucher('SUBMITTED')} accepted transitions={['approve']} />);
    expect(screen.getByText(/returns it to Draft and voids its approval/)).toHaveTextContent('submitted');
    rerender(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted transitions={['cancel']} />);
    expect(screen.getByText(/returns it to Draft and voids its approval/)).toHaveTextContent('approved');
    rerender(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted transitions={['cancel']} editable={false} />);
    expect(screen.queryByText(/voids its approval/)).toBeNull();
    rerender(<PurchaseLifecycle {...base} record={voucher('DRAFT')} />);
    expect(screen.queryByText(/voids its approval/)).toBeNull();
  });

  it('lets a rejected bill be submitted again, as the next step, once its calculation is accepted', () => {
    const { rerender } = render(<PurchaseLifecycle {...base} record={voucher('REJECTED')} accepted transitions={['submit', 'cancel']} />);
    expect(screen.getByRole('button', { name: 'Submit' })).toHaveClass('janso-btn--primary');
    expect(screen.getByRole('button', { name: 'Submit' })).toBeEnabled();
    rerender(<PurchaseLifecycle {...base} record={voucher('REJECTED')} transitions={['submit', 'cancel']} />);
    expect(screen.getByRole('button', { name: 'Submit' })).toBeDisabled();
  });

  it('offers posting for an issued bill, and shows posting as the next step', () => {
    render(<PurchaseLifecycle {...base} record={voucher('ISSUED')} accepted transitions={[]} />);
    expect(screen.getByRole('button', { name: 'Post approved Purchase' })).toBeEnabled();
    expect(screen.getByText('Posted').closest('li')).toHaveAttribute('aria-current', 'step');
  });

  it('offers only what the person is allowed to do', () => {
    render(<PurchaseLifecycle {...base} accepted allowed={action => action !== 'cancel' && action !== 'history.read'} />);
    expect(screen.getByRole('button', { name: 'Submit' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'View revision history' })).toBeNull();
    expect(screen.queryByLabelText('Action reason')).toBeNull();
  });

  it('locks every action while a request is pending or the bill has unsaved changes', () => {
    const { rerender } = render(<PurchaseLifecycle {...base} accepted locked />);
    for (const name of ['Submit', 'Cancel', 'View revision history']) expect(screen.getByRole('button', { name })).toBeDisabled();
    rerender(<PurchaseLifecycle {...base} accepted dirty />);
    expect(screen.getByRole('button', { name: 'Submit' })).toBeDisabled();
  });

  it('moves a submitted bill to approval, and an approved one to posting, as the filled button', () => {
    const { rerender } = render(<PurchaseLifecycle {...base} record={voucher('SUBMITTED')} accepted transitions={['approve', 'reject', 'cancel']} />);
    expect(screen.getByRole('button', { name: 'Approve' })).toHaveClass('janso-btn--primary');
    expect(screen.getByRole('button', { name: 'Reject' })).toHaveClass('janso-btn--ghost');
    const onPost = vi.fn();
    rerender(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted transitions={['cancel']} onPost={onPost} />);
    fireEvent.click(screen.getByRole('button', { name: 'Post approved Purchase' }));
    expect(onPost).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Post approved Purchase' })).toHaveClass('janso-btn--primary');
  });

  it('will not post while another execution runs, or without the posting and operation rights', () => {
    const { rerender } = render(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted transitions={[]} executing />);
    expect(screen.getByRole('button', { name: 'Post approved Purchase' })).toBeDisabled();
    rerender(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted transitions={[]} allowed={action => action !== 'post'} />);
    expect(screen.queryByRole('button', { name: 'Post approved Purchase' })).toBeNull();
    rerender(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted transitions={[]} executionReady={false} />);
    expect(screen.queryByRole('button', { name: 'Post approved Purchase' })).toBeNull();
    expect(screen.getByText('Posting is not activated for Purchase in this service.')).toBeVisible();
  });

  it('lists history and reviews a saved revision from it', () => {
    const onRevision = vi.fn(), onHistory = vi.fn();
    render(<PurchaseLifecycle {...base} historyCursor="more" onRevision={onRevision} onHistory={onHistory}
      history={[{ id: id(801), action: 'SUBMIT', from_status: 'DRAFT', to_status: 'SUBMITTED', revision_id: id(93) }]} />);
    const list = screen.getByRole('list', { name: 'Revision history' });
    expect(within(list).getByText('DRAFT → SUBMITTED')).toBeVisible();
    fireEvent.click(within(list).getByRole('button', { name: 'Review saved revision' }));
    expect(onRevision).toHaveBeenCalledWith(id(93));
    fireEvent.click(screen.getByRole('button', { name: 'More Purchase history' }));
    expect(onHistory).toHaveBeenCalledWith('more');
    fireEvent.click(screen.getByRole('button', { name: 'View revision history' }));
    expect(onHistory).toHaveBeenLastCalledWith();
  });

  it('shows where a stopped bill stopped', () => {
    render(<PurchaseLifecycle {...base} record={voucher('REJECTED')} transitions={[]} />);
    const stopped = screen.getByText('Rejected', { selector: 'li' });
    expect(stopped).toHaveAttribute('data-state', 'stopped');
    expect(stopped).toHaveTextContent(', stopped');
  });

  it('tracks an execution through refresh, recovery, refusal and reconciliation', () => {
    const onRefresh = vi.fn(), onRecover = vi.fn();
    const operation = (status: string, extra: object = {}) => ({ id: id(80), voucher_id: id(90), status, row_version: 1, ...extra }) as PurchaseOperation;
    const { rerender } = render(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted operation={operation('PENDING')} onRefresh={onRefresh} onRecover={onRecover} />);
    expect(screen.getByText('PENDING')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh Purchase execution' }));
    fireEvent.click(screen.getByRole('button', { name: 'Retry execution delivery' }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onRecover).toHaveBeenCalledTimes(1);
    rerender(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted operation={operation('REJECTED', { rejection_code: 'PERIOD_CLOSED' })} />);
    expect(screen.getByText('Accounting refused execution')).toBeVisible();
    expect(screen.getByText('PERIOD_CLOSED')).toBeVisible();
    rerender(<PurchaseLifecycle {...base} record={voucher('APPROVED')} accepted operation={operation('COMMITTED')} />);
    expect(screen.getByText('Reconciliation pending')).toBeVisible();
    rerender(<PurchaseLifecycle {...base} record={voucher('POSTED')} accepted operation={operation('COMMITTED')} transitions={[]} />);
    expect(screen.queryByText('Reconciliation pending')).toBeNull();
    expect(screen.getByText('Posted Purchase is retained')).toBeVisible();
  });

  it('ignores an execution that belongs to another voucher, and links to the saved voucher', () => {
    render(<PurchaseLifecycle {...base} operation={{ id: id(80), voucher_id: id(77), status: 'PENDING', row_version: 1 } as PurchaseOperation} />);
    expect(screen.queryByText(/Purchase execution/)).toBeNull();
    expect(screen.getByRole('link', { name: 'Open saved voucher review' })).toHaveAttribute('href', '/vouchers/' + id(90));
  });
});
