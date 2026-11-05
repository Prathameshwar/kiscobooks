'use client';

import { Button, Modal, Notice, useFormatters } from '@janso/ui';
import { purchaseStatusView } from '../lib/purchase-page';
import type { DuplicateBill } from '../lib/purchase-api';

/** Each bill the supplier's reference already appears on: where it stands, and from when. */
function DuplicateRows({ matches }: { matches: readonly DuplicateBill[] }) {
  const format = useFormatters();
  return <ul className="janso-purchase-duplicates">{matches.map(row => <li key={row.id}>
    <a className="janso-link" href={'/vouchers/' + row.id}>{row.bill_reference}</a>{' · '}{purchaseStatusView(row.status).label}{' · '}{format.date(row.document_date)}{' · revision ' + row.revision_number}</li>)}</ul>;
}

/** Shown beside the bill's status while it is still a draft: advice only, the service decides at submit. */
export function DuplicateBillNotice({ matches }: { matches: readonly DuplicateBill[] }) {
  if (!matches.length) return null;
  return <Notice tone="warning" title="This supplier invoice number is already recorded">
    <p>Another bill from this supplier carries the same invoice number this year. Check it is not the same bill before you submit.</p>
    <DuplicateRows matches={matches} />
  </Notice>;
}

type Props = { matches: readonly DuplicateBill[] | null; /** The service could not read every bill of this supplier this year, so it cannot rule a repeat out. */ incomplete?: boolean; busy: boolean; onCancel: () => void; onConfirm: () => void };

/** The service refused a submit as a likely repeat. Submitting anyway is a recorded, deliberate choice. */
export function DuplicateBillModal({ matches, incomplete = false, busy, onCancel, onConfirm }: Props) {
  return <Modal open={!!matches} title="Submit a possible duplicate bill?" onClose={onCancel}
    footer={<><Button variant="ghost" disabled={busy} onClick={onCancel}>Do not submit</Button><Button disabled={busy} onClick={onConfirm}>Submit anyway</Button></>}>
    <p>{incomplete && !matches?.length
      ? 'This supplier has so many bills this financial year that the check could not read them all, so it cannot rule out that this one is already recorded.'
      : 'This supplier invoice number is already recorded for this supplier in the same financial year.'}</p>
    {matches?.length ? <DuplicateRows matches={matches} /> : null}
    <p>Submitting it anyway is recorded against your name.</p>
  </Modal>;
}
