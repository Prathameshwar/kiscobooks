'use client';

import { Badge, Button, Notice, TextField } from '@janso/ui';
import type { PurchaseOperation, PurchaseVoucher } from '../lib/purchase-api';
import { purchaseStatusView, purchaseTrack } from '../lib/purchase-page';
import { DuplicateBillNotice } from './PurchaseDuplicateBill';

export type PurchaseHistoryRow = { id: string; action: string; from_status: string; to_status: string; revision_id?: string };

type Props = {
  record: PurchaseVoucher; accepted: boolean; locked: boolean; dirty: boolean;
  /** The person may change this bill: what saving would do to its approval is stated. */
  editable: boolean;
  /** The voucher type asks for a separate approval. When it does not, submitting approves the bill. */
  approvalRequired: boolean;
  /** Other bills that carry this supplier's invoice number this year; advice before submitting. */
  duplicates: readonly import('../lib/purchase-api').DuplicateBill[];
  allowed: (action: string) => boolean;
  reason: string; onReason: (value: string) => void;
  transitions: readonly string[]; onTransition: (action: string) => void;
  /** The service reports Purchase posting as ready for this company. */
  executionReady: boolean; executing: boolean; onPost: () => void;
  history: readonly PurchaseHistoryRow[]; historyCursor: string | null;
  /** The history has been read (so an empty list means there are no steps, not that nobody asked). */
  historyLoaded?: boolean;
  onHistory: (cursor?: string) => void; onRevision: (revisionId: string) => void;
  operation: PurchaseOperation | null; onRefresh: () => void; onRecover: () => void;
};

const NEXT: Record<string, string> = { DRAFT: 'submit', SUBMITTED: 'approve', REJECTED: 'submit' };
const label = (action: string) => action[0]!.toUpperCase() + action.slice(1);

/**
 * Where a saved bill stands and what can be done next: a progress track, then only the actions this
 * person may take now, the next forward step as the one filled button. Reject and cancel need a
 * reason, so the reason field appears only when one of them is on offer.
 */
export function PurchaseLifecycle(p: Props) {
  const { record, allowed } = p;
  const view = purchaseStatusView(record.status);
  const track = purchaseTrack(record.status, p.accepted);
  const offered = p.transitions.filter(allowed);
  const needsReason = offered.some(action => ['reject', 'cancel'].includes(action));
  const canPost = p.executionReady && allowed('post') && allowed('operation.read') && ['APPROVED', 'ISSUED'].includes(record.status);
  return <section className="janso-entry-workspace__panel" aria-label="Purchase lifecycle">
    <div className="janso-entry-workspace__section-head"><h2>{p.approvalRequired ? 'Status and approval' : 'Status'}</h2>
      <div className="janso-purchase-status__meta"><span>Saved status</span><Badge tone={view.tone}>{view.label}</Badge><span>Revision {record.revision_number}</span><span>Version {record.row_version}</span></div></div>
    <ol className="janso-purchase-track" aria-label="Bill progress">{track.map((step, index) => <li key={step.key} data-state={step.state} aria-current={step.state === 'current' ? 'step' : undefined}>
      <span className="janso-purchase-track__mark" aria-hidden="true">{step.state === 'done' ? '✓' : step.state === 'stopped' ? '!' : index + 1}</span>
      {step.label}<span className="janso-visually-hidden">{step.state === 'done' ? ', done' : step.state === 'current' ? ', next' : step.state === 'stopped' ? ', stopped' : ', not yet'}</span></li>)}</ol>
    {p.editable && ['SUBMITTED', 'APPROVED'].includes(record.status) ? <p className="janso-entry-workspace__caption">Saving changes to this {record.status === 'SUBMITTED' ? 'submitted' : 'approved'} bill returns it to Draft{p.approvalRequired ? ' and voids its approval' : ''}. It must be calculated, accepted and submitted again.</p> : null}
    {p.executing ? <p className="janso-entry-workspace__caption">A posting is in progress. Other actions return when it finishes.</p> : null}
    {!p.approvalRequired && ['DRAFT', 'REJECTED'].includes(record.status) && allowed('submit') ? <p className="janso-entry-workspace__caption">This voucher type does not need a separate approval: submitting approves the bill, and it can then be posted.</p> : null}
    {['DRAFT', 'REJECTED'].includes(record.status) ? <DuplicateBillNotice matches={p.duplicates} /> : null}
    {record.status === 'DRAFT' && !p.accepted && allowed('submit') ? <p className="janso-entry-workspace__caption">Submitting becomes available once the Accounting calculation is accepted.</p> : null}
    <div className="janso-purchase-lifecycle-actions">
      {needsReason ? <TextField label="Action reason" value={p.reason} disabled={p.locked} maxLength={500} hint="Required to reject or cancel. The service enforces approval authority and separation of duties." onChange={event => p.onReason(event.target.value)} /> : null}
      <div className="janso-purchase-lifecycle-actions__buttons">
        {offered.map(action => <Button key={action} variant={NEXT[record.status] === action ? 'primary' : 'ghost'}
          disabled={p.locked || p.dirty || p.executing || ['reject', 'cancel'].includes(action) && p.reason.trim().length < 3 || action === 'submit' && !p.accepted}
          onClick={() => p.onTransition(action)}>{label(action)}</Button>)}
        {canPost ? <Button variant={record.status === 'APPROVED' ? 'primary' : 'ghost'} disabled={p.locked || p.dirty || !p.accepted || p.executing} onClick={p.onPost}>Post approved Purchase</Button> : null}
        {allowed('history.read') ? <Button variant="ghost" disabled={p.locked} onClick={() => p.onHistory()}>View revision history</Button> : null}
      </div>
    </div>
    {!p.executionReady ? <p className="janso-entry-workspace__caption">Posting is not activated for Purchase in this service.</p> : null}
    {p.historyLoaded && !p.history.length ? <p className="janso-entry-workspace__caption" role="status">No steps recorded yet. Each save keeps its own revision; steps such as submitting and approving are listed here once they happen.</p> : null}
    {p.history.length ? <ol className="janso-purchase-history" aria-label="Revision history">{p.history.map(row => <li key={row.id}>
      <span className="janso-purchase-history__what"><strong>{row.action}</strong> <span>{row.from_status} → {row.to_status}</span></span>
      <Button variant="ghost" disabled={p.locked} onClick={() => p.onRevision(row.revision_id!)}>Review saved revision</Button></li>)}</ol> : null}
    {p.historyCursor ? <div><Button variant="ghost" disabled={p.locked} onClick={() => p.onHistory(p.historyCursor!)}>More Purchase history</Button></div> : null}
    {p.operation && p.operation.voucher_id === record.id ? <div className="janso-flow"><p role="status">Purchase execution: <strong>{p.operation.status}</strong></p>
      <div className="janso-purchase-lifecycle-actions__buttons">
        {allowed('operation.read') ? <Button variant="ghost" disabled={p.locked} onClick={p.onRefresh}>Refresh Purchase execution</Button> : null}
        {p.operation.status === 'PENDING' && allowed('operation.recover') ? <Button variant="ghost" disabled={p.locked} onClick={p.onRecover}>Retry execution delivery</Button> : null}
      </div>
      {p.operation.status === 'REJECTED' ? <Notice tone="danger" title="Accounting refused execution">{p.operation.rejection_code ?? 'Review the saved bill and current source facts before requesting execution again.'}</Notice> : null}
      {p.operation.status === 'COMMITTED' && record.status !== 'POSTED' ? <Notice title="Reconciliation pending">The execution committed, but this voucher has not yet reconciled. Refresh execution; do not create another bill.</Notice> : null}
    </div> : null}
    {record.status === 'POSTED' ? <Notice title="Posted Purchase is immutable">This owner does not yet support Purchase reversal. Use the approved correction process when that contract is available.</Notice> : null}
    <div><a className="janso-link" href={'/vouchers/' + record.id}>Open saved voucher review</a></div>
  </section>;
}
