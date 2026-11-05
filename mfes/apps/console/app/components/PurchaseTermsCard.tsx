'use client';

import type { ReactNode } from 'react';
import { Button, Checkbox, useFormatters } from '@janso/ui';
import type { PurchaseWorkspaceDraft } from '../lib/purchase-workspace';
import { purchaseTermsText } from '../lib/purchase-page';

export const TAX_CONFIRMATION_MESSAGE = 'Confirm that this is an untaxed account bill before saving.';
export const TAX_CONFIRMATION_NAME = 'purchase-tax-confirmed';
const DEFAULT_HINT = 'Required before saving.';

/**
 * What the bill says about tax and terms, beside the one decision it needs.
 *
 * A bill that carries tax would be saved wrong if the person simply did not notice, so "no tax" is a
 * statement they make in words, never a default. Where GST can be recorded, unticking it opens the
 * tax section (`children`); where it cannot, `taxHint` says why, and the box is the only way to save.
 */
export function PurchaseTermsCard({ draft, taxConfirmed, taxError, onTaxConfirmed, editable, locked, onEdit, taxHint, children }: {
  draft: PurchaseWorkspaceDraft; taxConfirmed: boolean; taxError: boolean; onTaxConfirmed: (value: boolean) => void;
  editable: boolean; locked: boolean; onEdit: () => void;
  /** What sits under the box: the hint, when it is not the default one. */
  taxHint?: string;
  /** The GST section, shown while the box is unticked. */
  children?: ReactNode;
}) {
  const { money } = useFormatters();
  const { details } = draft;
  const files = details.supportingFiles?.length ?? 0;
  // The refusal belongs to an unticked box: once it is ticked, by the person or by reopening a saved bill, it is stale.
  const refused = taxError && !taxConfirmed;
  return <section className="janso-entry-workspace__panel" aria-label="Terms and tax">
    <div className="janso-entry-workspace__section-head"><h2>Terms and tax</h2>
      <Button variant="ghost" disabled={locked} onClick={onEdit}>{editable ? 'Edit terms and details' : 'View terms and details'}</Button></div>
    <div className="janso-purchase-confirm" data-invalid={refused ? 'true' : undefined}>
      <Checkbox name={TAX_CONFIRMATION_NAME} checked={taxConfirmed} disabled={!editable || locked} aria-invalid={refused || undefined}
        hint={taxHint ?? DEFAULT_HINT}
        onChange={event => onTaxConfirmed(event.target.checked)}>This bill carries no tax</Checkbox>
      {refused ? <p className="janso-error" role="alert">{TAX_CONFIRMATION_MESSAGE}</p> : null}
    </div>
    {children}
    <dl className="janso-purchase-facts">
      <div><dt>Credit terms</dt><dd>{purchaseTermsText(details.termsDays, details.termsBasis)}</dd></div>
      <div><dt>Supplier’s own total</dt><dd>{details.declaredTotal ? money(details.declaredTotal) : 'Not entered'}</dd></div>
      <div><dt>Notes</dt><dd>{details.notes.trim() ? details.notes.trim() : 'None'}</dd></div>
      {files ? <div><dt>Supporting files</dt><dd>{files} {files === 1 ? 'file' : 'files'}</dd></div> : null}
    </dl>
  </section>;
}
