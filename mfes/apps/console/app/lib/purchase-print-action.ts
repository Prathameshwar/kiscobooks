import { purchasePrintHref } from './purchase-print';
import { trackingId } from './stock-tracking-resources';

/**
 * Whether the Purchase page may offer to print, and why not when it may not.
 *
 * Printing is of a SAVED revision, named by the identifiers of the last confirmed save: the print
 * service freezes that revision's facts, so a copy cannot describe edits that are still only on this
 * screen, or a command whose outcome is not yet known. Permissions only decide whether the action is
 * shown at all — the services authorize again — which is why a missing right is `hidden`, not
 * `blocked`: there is nothing the person can do here to get it.
 */
export type PurchasePrintAction =
  | { kind: 'hidden' }
  | { kind: 'blocked'; reason: string }
  | { kind: 'ready'; href: string };

/** Vouchers owns the print job; Accounting owns the supplier account and totals it prints, and checks this right itself. */
export const PRINT_PERMISSIONS = ['vouchers.read', 'vouchers.artifact.create', 'vouchers.artifact.read', 'accounting.account.read'] as const;

export function purchasePrintAction(input: {
  saved: { id: string; revisionId: string; version: number } | null;
  /** Whether the person holds a permission, by its full key, for this company. */
  permitted: (permission: string) => boolean;
  dirty: boolean;
  /** A command whose outcome is unconfirmed, or a retained execution, or a failed readback. */
  uncertain: boolean;
  busy: boolean;
  /** A posting is running: a copy would freeze a version that is about to change. */
  executing: boolean;
  /** A detail editor or a historical revision is open over the bill. */
  editorOpen: boolean;
}): PurchasePrintAction {
  const { saved } = input;
  // Only a fully identified saved revision can be named in a print link.
  if (!saved || !trackingId.test(saved.id) || !trackingId.test(saved.revisionId) || !Number.isSafeInteger(saved.version) || saved.version < 1) return { kind: 'hidden' };
  if (!PRINT_PERMISSIONS.every(permission => input.permitted(permission))) return { kind: 'hidden' };
  if (input.uncertain) return { kind: 'blocked', reason: 'Resolve the pending request before printing.' };
  if (input.busy) return { kind: 'blocked', reason: 'Wait for the current request to finish before printing.' };
  if (input.executing) return { kind: 'blocked', reason: 'Wait for the posting to finish before printing.' };
  if (input.dirty) return { kind: 'blocked', reason: 'Save your changes before printing. A copy shows the saved bill.' };
  if (input.editorOpen) return { kind: 'blocked', reason: 'Close the open details before printing.' };
  return { kind: 'ready', href: purchasePrintHref({ voucherId: saved.id, revisionId: saved.revisionId, version: saved.version }) };
}
