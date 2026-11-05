'use client';

import { Badge, useFormatters } from '@janso/ui';
import { purchaseWorkspacePreview, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from '../lib/purchase-workspace';
import { PURCHASE_PANELS, type PurchasePanel } from '../lib/purchase-workspace-details';

export function PurchaseDetailSections({ draft, policy, onOpen, disabled }: {
  draft: PurchaseWorkspaceDraft; policy: PurchaseWorkspacePolicy; onOpen: (panel: PurchasePanel) => void; disabled: boolean;
}) {
  const { date } = useFormatters(), preview = purchaseWorkspacePreview(draft), details = draft.details;
  const summaries: Record<PurchasePanel, string> = {
    components: details.components.length ? `${details.components.length} document ${details.components.length === 1 ? 'component' : 'components'} · line discounts stay in the grid` : 'Document discounts, freight and other charges',
    tax: preview.evidence ? 'Supplied tax evidence · rates are read-only' : 'Calculation evidence needs review',
    receipt: details.receiptIntent === 'REFERENCE' ? 'Match existing receipts · no second receipt' : details.receiptIntent === 'DEFERRED' ? 'Goods receipt pending · no on-hand change' : 'Receive with bill · planned quantities',
    tracking: 'Location, batch, expiry and serial details by item',
    settlement: preview.settlement.dueDate ? `Due ${date(preview.settlement.dueDate)} · advances and payment intentions` : 'Credit terms, advances and proposed payment',
    evidence: `${details.attachments.length} local ${details.attachments.length === 1 ? 'file' : 'files'} · supplier total, notes and additional fields`,
  };
  const available = (Object.keys(PURCHASE_PANELS) as PurchasePanel[]).filter(panel => policy.details.panels[panel].available);
  // A card that offers nothing is only a heading over empty space.
  if (!available.length) return null;
  return <section className="janso-entry-workspace__panel" aria-labelledby="purchase-details-title">
    <div className="janso-entry-workspace__section-head"><h2 id="purchase-details-title">Purchase details</h2><span className="janso-entry-workspace__caption">Open only what this bill needs</span></div>
    <div className="janso-entry-detail-cards">{available.map(panel => <button className="janso-entry-detail-card" key={panel} type="button" disabled={disabled} onClick={() => onOpen(panel)}>
      <span className="janso-entry-detail-card__title">{PURCHASE_PANELS[panel]}<span aria-hidden="true">↗</span></span>
      <span className="janso-entry-workspace__caption">{summaries[panel]}</span>
      {panel === 'tax' ? <Badge tone={preview.evidence ? 'neutral' : 'warn'}>{preview.evidence ? 'Example evidence' : 'Needs review'}</Badge> : null}
    </button>)}</div>
  </section>;
}
