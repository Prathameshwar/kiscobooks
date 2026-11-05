import type { Tone } from '@janso/ui';

/**
 * Presentation rules for the live Purchase page that need no framework: how a saved status reads,
 * and where a bill is on its way from a draft to a posting. Accounting and the Vouchers service own
 * the real state machine; this only names it for the person looking at the page.
 */

export type PurchaseStatusView = { label: string; tone: Tone };

const STATUS: Record<string, PurchaseStatusView> = {
  DRAFT: { label: 'Draft', tone: 'neutral' },
  SUBMITTED: { label: 'Submitted for approval', tone: 'info' },
  APPROVED: { label: 'Approved', tone: 'success' },
  ISSUED: { label: 'Issued', tone: 'info' },
  REJECTED: { label: 'Rejected', tone: 'danger' },
  CANCELLED: { label: 'Cancelled', tone: 'neutral' },
  POSTED: { label: 'Posted', tone: 'success' },
  REVERSED: { label: 'Reversed', tone: 'warn' },
};

/** A status the service returned, or "Not saved" before there is a record. Unknown values stay readable. */
export function purchaseStatusView(status: string | null | undefined): PurchaseStatusView {
  if (!status) return { label: 'Not saved', tone: 'neutral' };
  return STATUS[status] ?? { label: status[0] + status.slice(1).toLowerCase(), tone: 'neutral' };
}

export type TrackState = 'done' | 'current' | 'upcoming' | 'stopped';
export type TrackStep = { key: string; label: string; state: TrackState };

const STAGES = [
  { key: 'draft', label: 'Draft saved' },
  { key: 'accepted', label: 'Calculation accepted' },
  { key: 'submitted', label: 'Submitted' },
  { key: 'approved', label: 'Approved' },
  { key: 'posted', label: 'Posted' },
] as const;

// How far each status has got, in finished stages. An issued bill is ready to post, like an approved one.
const REACHED: Record<string, number> = { DRAFT: 1, SUBMITTED: 3, APPROVED: 4, ISSUED: 4, POSTED: 5 };
const done = (count: number): TrackStep[] => STAGES.slice(0, count).map(stage => ({ ...stage, state: 'done' }));

/**
 * The steps to draw for a saved bill. `accepted` is whether the saved revision carries an accepted
 * Accounting calculation; it only matters while the bill is still a draft, because every later
 * status already implies it. Returns an empty list when there is nothing saved to track.
 *
 * A track only claims what the status proves:
 * - a rejected bill stopped after it was submitted, and can still go on once corrected;
 * - a cancelled bill ends at the cancellation — nothing follows it, and the status does not say how
 *   far it had got, so it shows only the stages every cancellable bill has passed;
 * - a reversed bill was posted, then reversed;
 * - a status this page does not know is shown as itself, never as a fresh draft.
 */
export function purchaseTrack(status: string | null | undefined, accepted: boolean): TrackStep[] {
  if (!status) return [];
  if (status === 'REVERSED') return [...done(STAGES.length), { key: 'reversed', label: 'Reversed', state: 'stopped' }];
  if (status === 'CANCELLED') return [...done(accepted ? 2 : 1), { key: 'cancelled', label: 'Cancelled', state: 'stopped' }];
  if (status === 'REJECTED') return [...done(3), { key: 'rejected', label: 'Rejected', state: 'stopped' }, ...STAGES.slice(3).map(stage => ({ ...stage, state: 'upcoming' as const }))];
  const reached = status === 'DRAFT' && accepted ? 2 : REACHED[status];
  if (reached === undefined) return [{ key: 'unknown', label: purchaseStatusView(status).label, state: 'current' }];
  return STAGES.map((stage, index) => ({ ...stage, state: index < reached ? 'done' : index === reached ? 'current' : 'upcoming' }));
}

/** The credit terms as a sentence, for the terms card. */
export function purchaseTermsText(days: string, basis: 'INVOICE_DATE' | 'POSTING_DATE'): string {
  // Not `Number(days)`: an empty field is 0 to it, and "due on the invoice date" is a claim, not a blank.
  if (!/^\d{1,4}$/.test(days.trim())) return 'Not set';
  const count = Number(days);
  if (count === 0) return 'Due on the ' + (basis === 'INVOICE_DATE' ? 'supplier invoice date' : 'posting date');
  return `${count} ${count === 1 ? 'day' : 'days'} from the ${basis === 'INVOICE_DATE' ? 'supplier invoice date' : 'posting date'}`;
}
