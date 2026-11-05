'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AmountField, Button, Drawer, Modal, Notice, QuantityField, useFormatters } from '@janso/ui';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { purchaseWorkspacePreview, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from '../lib/purchase-workspace';
import { PURCHASE_PANELS, normalizePurchaseCustom, purchaseDetailProblems, type PurchaseDetails, type PurchasePanel } from '../lib/purchase-workspace-details';
import * as D from '../lib/fixed-decimal';
import { PurchaseComponentsPanel } from './PurchaseComponentsPanel';
import { PurchaseReceiptPanel, PurchaseTrackingPanel } from './PurchaseReceiptPanels';
import { PurchaseSettlementPanel } from './PurchaseSettlementPanel';
import { PurchaseEvidencePanel } from './PurchaseEvidencePanel';
import type { PurchaseDetailEditorProps } from './PurchaseDetailEditor';

export function PurchaseDetailsPanel({ panel, draft, policy, canEdit, focusField, onApply, onClose }: {
  panel: PurchasePanel; draft: PurchaseWorkspaceDraft; policy: PurchaseWorkspacePolicy; canEdit: boolean;
  focusField?: string; onApply: (details: PurchaseDetails) => void; onClose: () => void;
}) {
  const [details, setDetails] = useState(draft.details);
  const [discard, setDiscard] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [raw, setRaw] = useState<Record<string, string>>({});
  const content = useRef<HTMLDivElement>(null);
  const initial = useRef(JSON.stringify(draft.details));
  const dirty = JSON.stringify(details) !== initial.current || Object.keys(raw).length > 0;
  const writable = canEdit && policy.details.panels[panel].writable && panel !== 'tax';
  useUnsavedChanges(useCallback(() => dirty, [dirty]));
  const proposal = { ...draft, details }, preview = purchaseWorkspacePreview(proposal, Object.keys(raw).length > 0);
  const problems = purchaseDetailProblems(proposal, policy, preview.total, 'APPLY').filter(problem => problem.panel === panel);
  if (panel === 'components') for (const entry of preview.components.entries) {
    if (entry.amount === null&&!(policy.live&&entry.requiresOwner) || !details.components.find(component => component.id === entry.id)?.label.trim()) problems.push({ panel, field: `component-${entry.id}`, message: 'Enter a component name and a supported amount, basis and line selection.' });
  }
  const error = (field: string) => raw[field] ?? (attempted ? problems.find(problem => problem.field === field)?.message : undefined);
  const focus = (field: string) => {
    const wrapper = [...content.current?.querySelectorAll<HTMLElement>('[data-purchase-detail-field]') ?? []].find(element => element.dataset.purchaseDetailField === field);
    const customLabel = policy.details.customFields.find(definition => definition.key === field)?.label;
    const label = customLabel ? [...content.current?.querySelectorAll<HTMLLabelElement>('label') ?? []].find(element => element.textContent?.trim().startsWith(customLabel)) : undefined;
    const target = wrapper?.querySelector<HTMLElement>('input,select,textarea,button') ?? wrapper ?? (label ? document.getElementById(label.htmlFor) : null);
    target?.focus();
  };
  useEffect(() => { if (focusField) focus(focusField); }, [focusField]);
  const requestClose = () => dirty ? setDiscard(true) : onClose();
  const apply = () => {
    if (!writable || details.attachments.some(file => file.status === 'checking')) return;
    setAttempted(true);
    const firstRaw = Object.keys(raw)[0];
    if (firstRaw || problems.length) { focus(firstRaw ?? problems[0]!.field); return; }
    onApply(normalizePurchaseCustom(details, policy.details));
  };
  const number: PurchaseDetailEditorProps['number'] = (field, label, value, onChange, options) => {
    const Control = options?.quantity ? QuantityField : AmountField;
    return <div key={field} data-purchase-detail-field={field}><Control label={label} value={value} onChange={onChange} disabled={!writable}
      unit={options?.unit} hint={options?.hint} error={error(field)}
      onUnstorable={message => setRaw(current => {
        if ((message === null && !(field in current)) || current[field] === message) return current;
        const next = { ...current }; if (message) next[field] = message; else delete next[field]; return next;
      })} /></div>;
  };
  const editor: PurchaseDetailEditorProps = { draft: proposal, policy, setDetails, disabled: !writable, number, error };
  const checking = details.attachments.some(file => file.status === 'checking');
  return <>
    <Drawer open title={PURCHASE_PANELS[panel]} size="lg" onClose={requestClose} footer={<>
      <Button variant={writable ? 'ghost' : 'primary'} type="button" onClick={requestClose}>{writable ? 'Cancel' : 'Done'}</Button>
      {writable ? <Button type="button" disabled={checking} onClick={apply}>{checking ? 'Checking files…' : 'Apply details'}</Button> : null}
    </>}>
      <div className="janso-entry-detail" ref={content}>
        <p className="janso-entry-workspace__caption">{writable ? policy.live ? 'Changes stay in this panel until you apply them to the bill.' : 'Changes stay in this panel until you apply them to the demo bill.' : 'Review the supplied details. These fields are read-only.'}</p>
        {attempted && (problems.length > 0 || Object.keys(raw).length > 0) ? <Notice tone="danger" title="Check these details"><ul>{[...problems.map(problem => problem.message), ...Object.values(raw)].map((message, index) => <li key={index}>{message}</li>)}</ul></Notice> : null}
        {panel === 'components' ? <PurchaseComponentsPanel {...editor} /> : null}
        {panel === 'tax' ? <PurchaseTaxPanel draft={proposal} /> : null}
        {panel === 'receipt' ? <PurchaseReceiptPanel {...editor} /> : null}
        {panel === 'tracking' ? <PurchaseTrackingPanel {...editor} /> : null}
        {panel === 'settlement' ? <PurchaseSettlementPanel {...editor} /> : null}
        {panel === 'evidence' ? <PurchaseEvidencePanel {...editor} /> : null}
      </div>
    </Drawer>
    <Modal open={discard} title="Discard panel changes?" onClose={() => setDiscard(false)} footer={<>
      <Button variant="ghost" type="button" onClick={() => setDiscard(false)}>Keep editing</Button><Button type="button" onClick={onClose}>Discard panel changes</Button>
    </>}><p>Your bill will keep the details it had before this panel opened. Files selected in this panel will be discarded too.</p></Modal>
  </>;
}

function PurchaseTaxPanel({ draft }: { draft: PurchaseWorkspaceDraft }) {
  const { money, quantity } = useFormatters(), preview = purchaseWorkspacePreview(draft);
  if (!preview.evidence) return <Notice tone="warning" title="Calculation evidence unavailable">The supplied tax recipe no longer matches these inputs, or a component treatment is unresolved. No tax rate is guessed. Keep a demo draft or reload an example to restore its supplied evidence.</Notice>;
  const evidence = preview.evidence;
  return <>
    <Notice tone="info" title="Supplied example evidence">Rates and classifications are read-only. This preview is not a legal tax determination or an accepted Accounting calculation.</Notice>
    <dl className="janso-entry-workspace__review"><dt>Source</dt><dd>{evidence.reference}</dd><dt>Jurisdiction</dt><dd>{evidence.jurisdiction}</dd><dt>Registration</dt><dd>{evidence.registration}</dd><dt>Classification</dt><dd>{evidence.classification}</dd><dt>Example tax base</dt><dd>{preview.taxBase === null ? '—' : money(D.format(preview.taxBase))}</dd></dl>
    {preview.taxes.length === 0 ? <p>This supplied example has no supplier or recipient tax.</p> : preview.taxes.map((component, index) => <section key={index} className="janso-entry-detail__group"><h3>{component.label}</h3>
      <p className="janso-entry-detail__figure">Rate <strong>{quantity(component.rate)}%</strong></p><p className="janso-entry-detail__figure">Amount <strong>{money(component.amount)}</strong></p>
      <p className="janso-entry-workspace__caption">{component.liability === 'RECIPIENT' ? 'Recipient liability · excluded from the supplier bill. No input-tax-credit recognition is implied.' : 'Supplier-charged tax · included once in the supplier bill.'}</p>
    </section>)}
  </>;
}
