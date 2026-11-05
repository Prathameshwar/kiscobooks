import { describe, expect, it } from 'vitest';
import { purchasePrintAction } from '../app/lib/purchase-print-action';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const saved = { id: id(90), revisionId: id(91), version: 7 };
const all = () => true;
const PERMISSIONS = ['vouchers.read', 'vouchers.artifact.create', 'vouchers.artifact.read', 'accounting.account.read'];
const base = { saved, permitted: all, dirty: false, uncertain: false, busy: false, executing: false, editorOpen: false };

describe('whether the Purchase page may print', () => {
  it('offers the saved revision, by the identifiers of the last confirmed save', () => {
    expect(purchasePrintAction(base)).toEqual({ kind: 'ready', href: `/vouchers/${id(90)}/print?revision=${id(91)}&version=7` });
  });

  it('shows nothing before there is a saved bill', () => expect(purchasePrintAction({ ...base, saved: null })).toEqual({ kind: 'hidden' }));

  it.each(PERMISSIONS)('shows nothing without the %s right, because there is nothing to do here to get it', missing => {
    expect(purchasePrintAction({ ...base, permitted: permission => permission !== missing })).toEqual({ kind: 'hidden' });
  });

  it('shows nothing, rather than a reason, when a right is missing even if the bill is also unsaved', () => {
    expect(purchasePrintAction({ ...base, dirty: true, permitted: permission => permission !== 'vouchers.artifact.read' })).toEqual({ kind: 'hidden' });
  });

  it.each([
    ['uncertain', { uncertain: true }, /pending request/],
    ['busy', { busy: true }, /current request/],
    ['executing', { executing: true }, /posting to finish/],
    ['dirty', { dirty: true }, /Save your changes/],
    ['editorOpen', { editorOpen: true }, /open details/],
  ])('is blocked, with its reason, when %s', (_name, patch, reason) => {
    const action = purchasePrintAction({ ...base, ...patch });
    expect(action.kind).toBe('blocked');
    expect((action as { reason: string }).reason).toMatch(reason);
  });

  it('puts an unconfirmed outcome ahead of unsaved edits, because it must be resolved first', () => {
    expect((purchasePrintAction({ ...base, uncertain: true, dirty: true }) as { reason: string }).reason).toMatch(/pending request/);
  });

  it('never builds a link for a saved bill that is not fully identified', () => {
    for (const bad of [{ ...saved, id: '' }, { ...saved, id: 'not-an-id' }, { ...saved, revisionId: '' }, { ...saved, version: 0 }, { ...saved, version: 1.5 }, { ...saved, version: Number.NaN }])
      expect(purchasePrintAction({ ...base, saved: bad })).toEqual({ kind: 'hidden' });
  });
});
