'use client';

import { Button, Modal, Notice, useFormatters } from '@janso/ui';
import { purchaseWorkspacePreview, type PurchaseWorkspaceDraft } from '../lib/purchase-workspace';
import type { PurchaseWorkflowRecord } from '../lib/purchase-workflow';
import * as D from '../lib/fixed-decimal';

export function PurchaseWorkflowReview({ draft, record, pending, onConfirm, onClose }: {
  draft: PurchaseWorkspaceDraft; record: PurchaseWorkflowRecord;
  pending: boolean; onConfirm: () => void; onClose: () => void;
}) {
  const { money, date, quantity } = useFormatters(), preview = purchaseWorkspacePreview(draft);
  return <Modal open title="Review before demo submission" size="lg" busy={pending} onClose={onClose} footer={<>
    <Button type="button" variant="ghost" disabled={pending} onClick={onClose}>Back to draft</Button>
    <Button type="button" loading={pending} disabled={preview.total === null} onClick={onConfirm}>Submit demo for review</Button>
  </>}>
    <div className="janso-entry-workspace__details janso-entry-workflow__dialog">
      <Notice tone="info" title="Simulation only">Confirm this exact demo revision. Submission freezes its contents in this tab; nothing is saved to a service, approved, posted or paid.</Notice>
      <dl className="janso-entry-workspace__review"><dt>Demo record</dt><dd>{record.id} · revision {record.revision}</dd>
        <dt>Supplier</dt><dd>{record.snapshot.supplier.label}</dd>
        <dt>Supplier invoice</dt><dd>{draft.invoice}</dd><dt>Invoice date</dt><dd>{date(draft.invoiceDate)}</dd><dt>Posting date</dt><dd>{date(draft.postingDate)}</dd>
        <dt>Full supplier bill</dt><dd>{preview.total === null ? 'Unavailable' : money(D.format(preview.total))}</dd>
        <dt>Remaining if applied</dt><dd>{preview.settlement.remaining === null ? 'Unavailable' : money(D.format(preview.settlement.remaining))}</dd>
        <dt>Receipt intent</dt><dd>{draft.details.receiptIntent === 'REFERENCE' ? 'Match existing receipts · no second receipt' : draft.details.receiptIntent === 'DEFERRED' ? 'Receive later' : 'Receive with bill · proposed'}</dd>
        <dt>Supporting files</dt><dd>{draft.details.attachments.length} selected locally</dd>
      </dl>
      <ol className="janso-entry-workflow__review-lines">{draft.lines.filter(line => line.subject).map(line => <li key={line.key}><strong>{line.label}</strong>
        <span>{line.kind === 'ITEM' ? `Billed ${quantity(line.billed)} ${line.unit} · received ${quantity(line.received)} ${line.unit}` : 'Account / service amount'}{line.description ? ' · ' + line.description : ''}</span></li>)}</ol>
      {record.correctionOf ? <Notice tone="info" title="Correction lineage">Corrects {record.correctionOf.id}, revision {record.correctionOf.revision}. {record.correctionOf.reason}</Notice> : null}
    </div>
  </Modal>;
}
