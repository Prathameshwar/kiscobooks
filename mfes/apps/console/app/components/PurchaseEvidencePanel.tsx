'use client';

import { useEffect, useRef, useState } from 'react';
import { Button, CustomFields, FileUpload, Modal, Notice, Select, TextField, useFormatters } from '@janso/ui';
import { purchaseWorkspacePreview } from '../lib/purchase-workspace';
import { checkPurchaseAttachment } from '../lib/purchase-workspace-attachments';
import type { PurchaseAttachment } from '../lib/purchase-workspace-details';
import * as D from '../lib/fixed-decimal';
import type { PurchaseDetailEditorProps } from './PurchaseDetailEditor';

export function PurchaseEvidencePanel({ draft, policy, disabled, setDetails, error, number }: PurchaseDetailEditorProps) {
  const { money } = useFormatters(), preview = purchaseWorkspacePreview(draft), details = draft.details;
  const alive = useRef(true);
  const [selected, setSelected] = useState<PurchaseAttachment | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    setImageFailed(false);
    if (!selected || !selected.file.type.startsWith('image/')) { setUrl(null); return; }
    const objectUrl = URL.createObjectURL(selected.file);
    setUrl(objectUrl);
    return () => { URL.revokeObjectURL(objectUrl); };
  }, [selected]);
  const patch = (values: Partial<typeof details>) => setDetails(current => ({ ...current, ...values }));
  const check = async (attachment: PurchaseAttachment) => {
    const message = await checkPurchaseAttachment(attachment.file, policy.details.maxFileBytes);
    if (!alive.current) return;
    setDetails(current => ({ ...current, attachments: current.attachments.map(entry => entry.id === attachment.id ? { ...entry, status: message ? 'failed' : 'ready', error: message ?? undefined } : entry) }));
  };
  const selectFiles = (files: File[]) => {
    const additions = files.map(file => ({ id: crypto.randomUUID(), file, name: file.name, size: file.size, status: 'checking' as const }));
    setDetails(current => ({ ...current, attachments: [...current.attachments, ...additions] }));
    additions.forEach(attachment => { void check(attachment); });
  };
  const difference = preview.settlement.difference;
  return <>
    {number('declaredTotal', 'Supplier-declared bill total', details.declaredTotal, declaredTotal => patch({ declaredTotal }), { hint: 'Keep the amount printed on the supplier’s original bill.' })}
    <div className="janso-entry-detail__calculation"><p>Calculated bill total <strong>{preview.total === null ? '—' : money(D.format(preview.total))}</strong></p>
      <p>Supplier minus calculated <strong>{difference === null ? '—' : (difference > 0n ? '+' : '') + money(D.format(difference))}</strong></p></div>
    {difference === 0n ? <Notice tone="success" title="Supplier total matches">The declared or supported revised total matches this provisional calculation.</Notice> : difference !== null ? <Notice tone="warning" title="Supplier total needs attention">Correct the entry amounts or keep the original total and record a matching supplier revision. A reason alone does not balance the bill.</Notice> : <p className="janso-entry-workspace__caption">Enter a supplier total and complete the calculation evidence to compare amounts.</p>}
    <Select label="Difference resolution" value={details.comparison} disabled={disabled} options={[{ value: 'REVIEW_ENTRY', label: 'Review and correct entry amounts' }, { value: 'SUPPLIER_REVISED', label: 'Supplier supplied a revised total' }]}
      onChange={value => patch({ comparison: value as typeof details.comparison })} />
    {details.comparison === 'SUPPLIER_REVISED' ? <>
      {number('revisedTotal', 'Supplier revised total', details.revisedTotal, revisedTotal => patch({ revisedTotal }))}
      <TextField label="Supplier revision reason or reference" required value={details.comparisonReason} disabled={disabled} maxLength={500} onChange={event => patch({ comparisonReason: event.target.value })} />
    </> : null}
    <fieldset className="janso-entry-detail__group" data-purchase-detail-field="attachments"><legend>Supporting files · local selection only</legend>
      <FileUpload label="Supplier bill attachments" items={details.attachments.map(attachment => ({ ...attachment, status: attachment.status === 'ready' ? 'selected' : attachment.status === 'checking' ? 'pending' : 'failed' }))}
        accept=".pdf,.png,.jpg,.jpeg,.webp" acceptLabel="PDF, PNG, JPEG or WebP" maxFiles={policy.details.maxFiles} maxSizeBytes={policy.details.maxFileBytes}
        disabled={disabled} onSelect={selectFiles} onRemove={disabled ? undefined : item => patch({ attachments: details.attachments.filter(attachment => attachment.id !== item.id) })}
        onRetry={disabled ? undefined : item => { const attachment = details.attachments.find(entry => entry.id === item.id); if (attachment) { patch({ attachments: details.attachments.map(entry => entry.id === item.id ? { ...entry, status: 'checking', error: undefined } : entry) }); void check(attachment); } }}
        error={error('attachments')} hint="Files stay in memory on this page. Nothing is uploaded or queued for upload; reloading discards the files." />
      {details.attachments.filter(attachment => attachment.status === 'ready').map((attachment, index) => <Button key={attachment.id} type="button" variant="ghost" onClick={() => setSelected(attachment)}>Preview attachment {index + 1}</Button>)}
    </fieldset>
    <div className="janso-field"><label className="janso-label" htmlFor="purchase-notes">Purchase notes</label><textarea id="purchase-notes" className="janso-input" rows={3} maxLength={2000} value={details.notes} disabled={disabled} onChange={event => patch({ notes: event.target.value })} /></div>
    <fieldset className="janso-entry-detail__group"><legend>Additional purchase information</legend>
      <CustomFields fields={policy.details.customFields} values={details.custom} creating disabled={disabled}
        errors={Object.fromEntries(policy.details.customFields.map(field => [field.key, error(field.key) ?? '']))}
        onChange={custom => patch({ custom })} />
      <p className="janso-entry-workspace__caption">These descriptive fields never change amounts, tax or approval behavior.</p>
    </fieldset>
    <Modal open={!!selected} title="Local attachment preview" onClose={() => setSelected(null)} footer={<Button type="button" onClick={() => setSelected(null)}>Close preview</Button>}>
      {imageFailed ? <Notice tone="warning" title="Image preview unavailable">This image could not be decoded. Check the original file or remove it and choose another image.</Notice>
        : selected?.file.type.startsWith('image/') && url ? <img className="janso-entry-detail__image" src={url} alt="Selected purchase attachment" onError={() => setImageFailed(true)} />
        : <p>Inline preview is available for supported images. For PDFs, review the original file in your trusted PDF reader. No file has been uploaded.</p>}
    </Modal>
  </>;
}
