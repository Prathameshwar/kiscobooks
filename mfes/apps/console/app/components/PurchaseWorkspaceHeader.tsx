'use client';

import { Notice, SearchSelect, TextField, useFormatters, type SearchSelectLoader } from '@janso/ui';
import type { Dispatch } from 'react';
import { InlineCreate, PurchaseQuickCreateButton } from './PurchaseQuickCreateButton';
import { PurchaseSupplierBalance } from './PurchaseSupplierBalance';
import { PurchaseSupplierHistory } from './PurchaseSupplierHistory';
import { purchaseDueDate } from '../lib/purchase-workspace-details';
import { MODE_LABELS, supplierAccountIssue, type PurchaseProblem, type PurchaseWorkspaceAction, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from '../lib/purchase-workspace';

export type PurchaseWorkspaceSectionProps = {
  draft: PurchaseWorkspaceDraft; policy: PurchaseWorkspacePolicy; dispatch: Dispatch<PurchaseWorkspaceAction>;
  problems: readonly PurchaseProblem[]; disabled: boolean;
};

export function PurchaseWorkspaceHeader(props: PurchaseWorkspaceSectionProps & { supplierLookup?: SearchSelectLoader; onCreateSupplier?: () => void }) {
  return props.policy.live ? <LiveSupplierBill {...props} /> : <PreviewSupplierInvoice {...props} />;
}

/**
 * The connected page's header card. Rows read left to right: who, then which bill, then when —
 * with the due date shown, read-only, because it follows from the credit terms and the person
 * should see what they will have committed to without opening another panel.
 */
function LiveSupplierBill({ draft, policy, dispatch, problems, disabled, supplierLookup, onCreateSupplier }: PurchaseWorkspaceSectionProps & { supplierLookup?: SearchSelectLoader; onCreateSupplier?: () => void }) {
  const { date } = useFormatters();
  const supplier = policy.suppliers.find(entry => entry.id === draft.supplier);
  const duplicate = policy.duplicateCheck?.supplier === draft.supplier && policy.duplicateCheck.invoice === draft.invoice.trim() ? policy.duplicateCheck : undefined;
  const error = (field: string) => problems.find(problem => !problem.lineKey && problem.field === field)?.message;
  const header = (field: 'invoice' | 'invoiceDate' | 'postingDate', value: string) => dispatch({ type: 'header', field, value });
  const due = purchaseDueDate(draft);
  return <section className="janso-entry-workspace__panel" aria-label="Supplier and invoice details">
    <div className="janso-entry-workspace__section-head"><h2>Supplier and bill</h2><span className="janso-entry-workspace__caption">Accounting assigns the journal number when the bill is posted</span></div>
    <div className="janso-purchase-fields">
      <div data-span="6" data-purchase-field="supplier">
        <InlineCreate action={onCreateSupplier ? <PurchaseQuickCreateButton size="md" className="console-reference-create__action" label="Create a new supplier" disabled={disabled} onClick={onCreateSupplier} data-quick-create="supplier" /> : undefined}>
          {/* The supplier's payable account is never asked for: a supplier has exactly one, and choosing the supplier chooses it. */}
          <SearchSelect label="Supplier" required value={draft.supplier || null} options={supplierLookup ? undefined : policy.suppliers} loadOptions={supplierLookup}
            selected={supplier ?? null} disabled={disabled} error={error('supplier') ?? error('payable') ?? supplierAccountIssue(supplier)} placeholder="Search a supplier by name or code"
            onChange={id => dispatch({ type: 'supplier', value: id ?? '', policy })} />
        </InlineCreate>
        {draft.supplier ? <div className="janso-purchase-supplier-tools"><PurchaseSupplierBalance balance={policy.supplierBalance?.supplier === draft.supplier ? policy.supplierBalance : undefined} />
          {policy.supplierHistoryAccess && policy.stockCompany ? <PurchaseSupplierHistory key={draft.supplier} company={policy.stockCompany} supplier={draft.supplier} name={supplier?.label ?? 'supplier'} /> : null}</div> : null}
      </div>
      <div data-purchase-field="invoice"><TextField label="Supplier invoice number" required value={draft.invoice} disabled={disabled} maxLength={100}
        placeholder="e.g. PC-261034" error={error('invoice')} onChange={event => header('invoice', event.target.value)} /></div>
      <div data-purchase-field="invoiceDate"><TextField label="Supplier invoice date" required type="date" value={draft.invoiceDate} disabled={disabled}
        error={error('invoiceDate')} onChange={event => header('invoiceDate', event.target.value)} /></div>
      <div data-purchase-field="postingDate"><TextField label="Posting date" required type="date" value={draft.postingDate} disabled={disabled}
        hint="Decides the accounting period." error={error('postingDate')} onChange={event => header('postingDate', event.target.value)} /></div>
      <dl className="janso-purchase-static"><dt className="janso-purchase-static__label">Payment due</dt><dd className="janso-purchase-static__value">{due ? date(due) : '—'}</dd><dd className="janso-purchase-static__hint">Worked out from the credit terms below.</dd></dl>
    </div>
    {duplicate?.references.length ? <Notice tone="warning" title="Possible duplicate supplier bill"><p>An existing reference matches. Review it before continuing:</p><ul>{duplicate.references.map(reference => <li key={reference}>{reference}</li>)}</ul></Notice> : null}
    {policy.modes.length > 1 ? <div className="janso-entry-workspace__mode-row" data-purchase-field="mode">
      <div><strong>Entry mode</strong><p className="janso-entry-workspace__caption">Choose how this supplier bill is entered.</p></div>
      <div className="janso-entry-workspace__mode" role="group" aria-label="Purchase entry mode">
        {policy.modes.map(mode => <button key={mode} type="button" aria-pressed={draft.mode === mode} disabled={disabled} onClick={() => dispatch({ type: 'mode', mode })}>{MODE_LABELS[mode]}</button>)}
      </div>
    </div> : null}
    {error('mode') ? <p className="janso-error">{error('mode')}</p> : null}
  </section>;
}

function PreviewSupplierInvoice({ draft, policy, dispatch, problems, disabled, supplierLookup }: PurchaseWorkspaceSectionProps & { supplierLookup?: SearchSelectLoader }) {
  const supplier = policy.suppliers.find(entry => entry.id === draft.supplier);
  const duplicate = policy.duplicateCheck?.supplier === draft.supplier && policy.duplicateCheck.invoice === draft.invoice.trim() ? policy.duplicateCheck : undefined;
  const error = (field: string) => problems.find(problem => !problem.lineKey && problem.field === field)?.message;
  const header = (field: 'invoice' | 'invoiceDate' | 'postingDate', value: string) => dispatch({ type: 'header', field, value });
  return <section className="janso-entry-workspace__panel" aria-label="Supplier and invoice details">
    <div className="janso-entry-workspace__section-head"><h2>Supplier & invoice</h2><span className="janso-entry-workspace__caption">Internal reference <strong>Unassigned</strong></span></div>
    <div className="janso-form-grid janso-entry-workspace__supplier-grid">
      <div data-purchase-field="supplier">
        <SearchSelect label="Supplier" required value={draft.supplier || null}
          options={supplierLookup ? undefined : policy.suppliers} loadOptions={supplierLookup} selected={supplier ?? null} disabled={disabled} error={error('supplier') ?? error('payable') ?? supplierAccountIssue(supplier)}
          placeholder="Search a supplier by name or code"
          hint="Example suppliers only. No live supplier balances."
          onChange={id => dispatch({ type: 'supplier', value: id ?? '', policy })} />
      </div>
    </div>
    <div className="janso-form-grid janso-entry-workspace__fields">
      <div data-purchase-field="invoice"><TextField label="Supplier invoice number" required value={draft.invoice} disabled={disabled} maxLength={100}
        placeholder="e.g. PC-261034" error={error('invoice')} onChange={event => header('invoice', event.target.value)} /></div>
      <div data-purchase-field="invoiceDate"><TextField label="Supplier invoice date" required type="date" value={draft.invoiceDate} disabled={disabled}
        error={error('invoiceDate')} onChange={event => header('invoiceDate', event.target.value)} /></div>
      <div data-purchase-field="postingDate"><TextField label="Posting date" required type="date" value={draft.postingDate} disabled={disabled}
        hint="Determines the accounting period." error={error('postingDate')} onChange={event => header('postingDate', event.target.value)} /></div>
    </div>
    {duplicate?.references.length ? <Notice tone="warning" title="Possible duplicate supplier bill"><p>The supplied example check found an existing reference. Review it before continuing:</p><ul>{duplicate.references.map(reference => <li key={reference}>{reference}</li>)}</ul><p>Example check only. Actual duplicate decisions and reference navigation require the service contract.</p></Notice> : null}
    <div className="janso-entry-workspace__mode-row" data-purchase-field="mode">
      <div><strong>Entry mode</strong><p className="janso-entry-workspace__caption">Choose how this supplier bill is entered.</p></div>
      <div className="janso-entry-workspace__mode" role="group" aria-label="Purchase entry mode">
        {policy.modes.map(mode => <button key={mode} type="button" aria-pressed={draft.mode === mode} disabled={disabled}
          onClick={() => dispatch({ type: 'mode', mode })}>{MODE_LABELS[mode]}</button>)}
      </div>
    </div>
    {error('mode') ? <p className="janso-error">{error('mode')}</p> : null}
  </section>;
}
