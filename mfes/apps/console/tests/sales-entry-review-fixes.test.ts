/**
 * Regression tests for the S7 review, one per finding that the arithmetic or the draft could
 * get wrong without a DOM. Each states the input that used to produce the wrong answer.
 */
import { describe, expect, it } from 'vitest';
import {
  draftProblems,
  initialDraft,
  problemTarget,
  quantitiesDiffer,
  reduceDraft,
  type DraftLine,
  type SalesDraft,
} from '../app/lib/sales-entry-draft';
import { previewInvoice, previewProblems } from '../app/lib/sales-entry-preview';
import { freeQuantity, isRewardLine, shortQuantity } from '../app/lib/sales-entry-columns';
import { SAMPLE_SALES_POLICY } from '../app/lib/sales-entry-policy';

const policy = SAMPLE_SALES_POLICY;
const CONTEXT = { companyState: 'Karnataka', places: 2 };

function bill(patch: Partial<DraftLine> = {}, header: Partial<SalesDraft> = {}): SalesDraft {
  let draft = initialDraft(policy, '2026-10-28');
  draft = reduceDraft(draft, {
    type: 'header',
    patch: { customerId: 'c1', customerLabel: 'Nandini', customerState: 'Karnataka', ...header },
  });
  return reduceDraft(draft, {
    type: 'line',
    key: draft.lines[0]!.key,
    patch: {
      subjectId: 'i1',
      subjectLabel: 'Rice',
      subjectKind: 'ITEM',
      actualQuantity: '10',
      billedQuantity: '10',
      rate: '2450',
      taxRate: '5',
      ...patch,
    },
  });
}
const messages = (draft: SalesDraft) => draftProblems(draft, policy).map((p) => p.message);
const preview = (draft: SalesDraft) => previewInvoice(draft, policy, CONTEXT);

describe('switching to Accounts with item lines', () => {
  it('reports the item instead of repricing it as one unit', () => {
    // 10 bags at 2,450 used to become a 2,450 bill with no error at all.
    const switched = reduceDraft(bill(), { type: 'mode', mode: 'ACCOUNTS' });
    expect(messages(switched)).toContain(
      'This line is an item, and an accounts-only bill takes accounts. Choose an account, or switch back to Items.',
    );
    expect(preview(switched).taxableValue).toBe('0.00');
  });

  it('accepts an item line in Mixed mode', () => {
    const mixed = reduceDraft(bill(), { type: 'mode', mode: 'MIXED' });
    expect(messages(mixed).some((m) => /accounts-only|items bill/.test(m))).toBe(false);
  });
});

describe('quantities that differ', () => {
  it('compares as decimals, so 10 and 10.0 owe no reason', () => {
    const same = bill({ actualQuantity: '10.0', billedQuantity: '10' });
    expect(quantitiesDiffer(same.lines[0]!)).toBe(false);
    expect(messages(same)).not.toContain('Say why the actual and billed quantities differ.');
  });

  it('asks a short supply for its reason and sends the link to the line’s detail', () => {
    // Actual 9, billed 10: the reason picker used to appear only for a bonus, so this error
    // could never be cleared.
    const short = bill({ actualQuantity: '9', billedQuantity: '10' });
    const problem = draftProblems(short, policy).find((p) => p.field === 'quantityReason')!;
    expect(problemTarget(problem, short)).toMatchObject({ kind: 'detail', label: 'Line 1' });
    expect(shortQuantity(short.lines[0]!)).toBe('1');
  });

  it('derives a free quantity exactly', () => {
    // Floats said 0.10000000000000009.
    const line = bill({ actualQuantity: '1.1', billedQuantity: '1' }).lines[0]!;
    expect(isRewardLine(line)).toBe(true);
    expect(freeQuantity(line)).toBe('0.1');
  });
});

describe('tax-inclusive prices', () => {
  it('add back to exactly what was entered', () => {
    // 100 at 18%: base 84.75, and CGST + SGST each rounded from it made 100.01.
    const draft = bill({ actualQuantity: '1', billedQuantity: '1', rate: '100', taxRate: '18' }, {});
    const inclusive = reduceDraft(draft, { type: 'header', patch: { taxInclusive: true } });
    const result = preview(inclusive);
    expect(result.taxableValue).toBe('84.75');
    expect(result.tax?.cgst).toBe('7.63');
    expect(result.tax?.sgst).toBe('7.62');
    expect(result.lines[0]!.amount).toBe('100.00');
  });

  it('leave the total unknown when a line cannot be split', () => {
    const inclusive = reduceDraft(bill({ taxRate: '' }), { type: 'header', patch: { taxInclusive: true } });
    expect(preview(inclusive).total).toBeNull();
  });
});

describe('caps are said, not only applied', () => {
  it('reports an amount line discount above the line', () => {
    const draft = bill({ actualQuantity: '1', billedQuantity: '1', rate: '100', discountKind: 'AMOUNT', discountInput: '150' });
    expect(previewProblems(preview(draft)).map((p) => p.message)).toContain(
      "The discount is more than the line's value of 100.00.",
    );
  });

  it('reports advances larger than the bill', () => {
    // Two advances of 1,200 and 800 against a smaller bill: 2,000 would have been handed over.
    let draft = bill({ actualQuantity: '1', billedQuantity: '1', rate: '1000', taxRate: '0' });
    draft = reduceDraft(draft, { type: 'applyAdvance', sourceId: 'a1', sourceLabel: 'A1', available: '1200' });
    draft = reduceDraft(draft, { type: 'advance', key: draft.advances[0]!.key, amount: '1200' });
    draft = reduceDraft(draft, { type: 'applyAdvance', sourceId: 'a2', sourceLabel: 'A2', available: '800' });
    draft = reduceDraft(draft, { type: 'advance', key: draft.advances[1]!.key, amount: '800' });

    const problems = previewProblems(preview(draft));
    expect(problems.map((p) => p.message)).toContain(
      'Advances of 2000.00 are more than the bill of 1000.00. Reduce an advance.',
    );
    expect(problemTarget(problems.find((p) => p.field === 'advances')!, draft)).toMatchObject({ kind: 'panel', panel: 'payment' });
  });

  it('reports an amount bill discount above what it discounts', () => {
    let draft = bill({ actualQuantity: '1', billedQuantity: '1', rate: '100' });
    draft = reduceDraft(draft, { type: 'addDiscount', scope: 'DOCUMENT' });
    draft = reduceDraft(draft, {
      type: 'discount',
      key: draft.discounts[0]!.key,
      patch: { kind: 'AMOUNT', input: '500' },
    });
    expect(previewProblems(preview(draft)).some((p) => /is more than the 100\.00 it applies to/.test(p.message))).toBe(true);
  });
});

describe('card numbers', () => {
  const card = (reference: string) => {
    const draft = reduceDraft(bill(), { type: 'addTender', mode: 'CARD', amount: '100' });
    return reduceDraft(draft, { type: 'tender', key: draft.tenders[0]!.key, patch: { reference } });
  };

  it('are refused whatever separates the digits', () => {
    expect(messages(card('4111.1111.1111.1111')).some((m) => /looks like a card number/.test(m))).toBe(true);
    expect(messages(card('4111/1111/1111/1111')).some((m) => /looks like a card number/.test(m))).toBe(true);
  });

  it('are not kept by switching the mode away from Card', () => {
    // Typed under Card, refused, then switched to Cash: the number used to stay in the draft.
    const typed = card('4111111111111111');
    const switched = reduceDraft(typed, { type: 'tender', key: typed.tenders[0]!.key, patch: { mode: 'CASH' } });
    expect(switched.tenders[0]!.reference).toBe('');
  });
});

describe('a selected-line discount', () => {
  it('needs a line that still has something on it', () => {
    let draft = bill();
    draft = reduceDraft(draft, { type: 'addLine' });
    const target = draft.lines[1]!.key;
    draft = reduceDraft(draft, { type: 'addDiscount', scope: 'SELECTED' });
    draft = reduceDraft(draft, {
      type: 'discount',
      key: draft.discounts[0]!.key,
      patch: { input: '5', lineKeys: [target] },
    });
    expect(messages(draft)).toContain('Choose the lines this discount applies to.');
  });
});
