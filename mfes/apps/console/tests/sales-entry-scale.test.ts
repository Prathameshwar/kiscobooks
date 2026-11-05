/**
 * Two S7 properties that need no DOM: every problem names a place it is fixed, and a 200-line
 * bill is as exact and as quick to recompute as a two-line one.
 *
 * The grid's half of the 200-line budget — repainting one row rather than all of them — is
 * counted in `packages/ui/tests/entry-grid.test.tsx`, where the memo lives.
 */
import { describe, expect, it } from 'vitest';
import {
  draftProblems,
  initialDraft,
  problemTarget,
  reduceDraft,
  type DraftProblem,
  type SalesDraft,
} from '../app/lib/sales-entry-draft';
import { previewInvoice } from '../app/lib/sales-entry-preview';
import { SAMPLE_SALES_POLICY } from '../app/lib/sales-entry-policy';

const policy = SAMPLE_SALES_POLICY;
const CONTEXT = { companyState: 'Karnataka', places: 2 };

/** `n` lines of two bags at 100 and 5%, to a local customer. */
function bill(n: number): SalesDraft {
  let draft = initialDraft(policy, '2026-10-28');
  draft = reduceDraft(draft, {
    type: 'header',
    patch: { customerId: 'c1', customerLabel: 'Nandini', customerState: 'Karnataka' },
  });
  for (let i = 1; i < n; i += 1) draft = reduceDraft(draft, { type: 'addLine' });
  for (const line of draft.lines) {
    draft = reduceDraft(draft, {
      type: 'line',
      key: line.key,
      patch: {
        subjectId: `item-${line.key}`,
        subjectLabel: 'Rice',
        actualQuantity: '2',
        billedQuantity: '2',
        rate: '100',
        taxRate: '5',
      },
    });
  }
  return draft;
}

describe('where a problem is fixed', () => {
  // A policy that requires references, so a UPI tender carries a payment problem to route.
  const strict = { ...policy, settlement: { ...policy.settlement, referenceRequired: ['UPI' as const] } };
  const target = (draft: SalesDraft, match: (problem: DraftProblem) => boolean) => {
    const problem = draftProblems(draft, strict).find(match);
    if (!problem) throw new Error('no such problem');
    return problemTarget(problem, draft);
  };

  it('names a line by its position, not its key', () => {
    let draft = bill(3);
    draft = reduceDraft(draft, { type: 'line', key: draft.lines[2]!.key, patch: { rate: '' } });
    expect(target(draft, (p) => p.field === 'rate')).toEqual({
      kind: 'line',
      lineKey: draft.lines[2]!.key,
      label: 'Line 3',
    });
  });

  it('sends a document-bar problem to its field', () => {
    let draft = bill(1);
    draft = reduceDraft(draft, { type: 'header', patch: { customerId: null, customerLabel: '' } });
    expect(target(draft, (p) => p.field === 'customerId')).toEqual({
      kind: 'field',
      field: 'customerId',
      label: 'Customer',
    });
  });

  it('sends "add a line" to the first line', () => {
    const draft = initialDraft(policy, '2026-10-28');
    expect(target(draft, (p) => p.field === 'lines')).toMatchObject({ kind: 'line', label: 'Lines' });
  });

  it('sends a payment problem to the payment drawer', () => {
    const draft = reduceDraft(bill(1), { type: 'addTender', mode: 'UPI', amount: '10' });
    expect(target(draft, (p) => p.message === 'Enter the UTR.')).toEqual({
      kind: 'panel',
      panel: 'payment',
      label: 'Payment',
    });
  });

  it('sends a charge problem to the components drawer', () => {
    const draft = reduceDraft(bill(1), { type: 'addCharge', purpose: 'FREIGHT' });
    expect(target(draft, (p) => /freight/i.test(p.message))).toEqual({
      kind: 'panel',
      panel: 'components',
      label: 'Discounts and charges',
    });
  });
});

describe('a 200-line bill', () => {
  it('totals exactly', () => {
    // 200 × 2 × 100 = 40,000 taxable; 5% split as 2.5% + 2.5% per line, rounded per line.
    const preview = previewInvoice(bill(200), policy, CONTEXT);
    expect(preview.taxableValue).toBe('40000.00');
    expect(preview.tax?.cgst).toBe('1000.00');
    expect(preview.tax?.sgst).toBe('1000.00');
    expect(preview.total).toBe('42000.00');
  });

  it('recomputes a keystroke well inside a frame', () => {
    // Reduce, validate and preview — everything the page does per key before React paints.
    // Measured at about 2 ms; the budget is generous so a slow CI machine does not flake, and
    // still far below the point a clerk would feel it.
    const draft = bill(200);
    const key = draft.lines[0]!.key;
    const started = performance.now();
    for (let i = 0; i < 20; i += 1) {
      const next = reduceDraft(draft, { type: 'line', key, patch: { rate: String(100 + i) } });
      draftProblems(next, policy);
      previewInvoice(next, policy, CONTEXT);
    }
    expect((performance.now() - started) / 20).toBeLessThan(16);
  });
});
