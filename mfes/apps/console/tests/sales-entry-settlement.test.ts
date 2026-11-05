/**
 * Settlement: one equation, and the money rules around it.
 *
 * The data model is specific about what payment may and may not do, and every rule here is one
 * of its sentences:
 *
 *  - **payment method never changes revenue or tax** — only what is left owing;
 *  - an advance **points at an existing credit** and is capped at what is left of it;
 *  - cash tendered, cash applied and **change returned are separate facts**, and change comes
 *    only out of cash;
 *  - a cheque is **recorded, not cleared** bank cash;
 *  - a due date is a **business date**, never shifted by a time zone;
 *  - **no card number is ever stored** (CLAUDE.md §5.10).
 */
import { describe, expect, it } from 'vitest';
import { addDays, previewInvoice, previewProblems } from '../app/lib/sales-entry-preview';
import {
  draftProblems,
  inSentence,
  initialDraft,
  reduceDraft,
  type SalesDraft,
} from '../app/lib/sales-entry-draft';
import { SAMPLE_SALES_POLICY, type SalesEntryPolicy } from '../app/lib/sales-entry-policy';

const policy = SAMPLE_SALES_POLICY;
const CONTEXT = { companyState: 'Karnataka', places: 2 };

/** A bill for 1,000 at 18% to a local customer: total 1,180. */
function bill(): SalesDraft {
  let draft = initialDraft(policy, '2026-10-28');
  draft = reduceDraft(draft, {
    type: 'header',
    patch: { customerId: 'c1', customerLabel: 'Nandini', customerState: 'Karnataka', creditDays: '' },
  });
  return reduceDraft(draft, {
    type: 'line',
    key: draft.lines[0]!.key,
    patch: {
      subjectId: 'i1',
      subjectLabel: 'Rice',
      actualQuantity: '10',
      billedQuantity: '10',
      rate: '100',
      taxRate: '18',
    },
  });
}

function tender(draft: SalesDraft, mode: 'CASH' | 'UPI' | 'CARD' | 'BANK_TRANSFER' | 'CHEQUE', amount: string, reference = ''): SalesDraft {
  const added = reduceDraft(draft, { type: 'addTender', mode, amount });
  const key = added.tenders.at(-1)!.key;
  return reduceDraft(added, { type: 'tender', key, patch: { reference } });
}

function advance(draft: SalesDraft, available: string, amount: string, sourceId = 'adv-1'): SalesDraft {
  const applied = reduceDraft(draft, {
    type: 'applyAdvance',
    sourceId,
    sourceLabel: `Advance ${sourceId}`,
    available,
  });
  return reduceDraft(applied, { type: 'advance', key: applied.advances.at(-1)!.key, amount });
}

const settle = (draft: SalesDraft, p: SalesEntryPolicy = policy) =>
  previewInvoice(draft, p, CONTEXT).settlement;

describe('the equation', () => {
  it('leaves the whole bill owing when nothing is paid', () => {
    expect(settle(bill()).outstanding).toBe('1180.00');
  });

  it('subtracts advances and money received, and nothing else', () => {
    const draft = tender(advance(bill(), '500', '300'), 'UPI', '200', 'UTR123');
    const s = settle(draft);

    // The data model's own example, rescaled: an advance and a UPI receipt against one bill.
    expect(s.advances).toBe('300.00');
    expect(s.received).toBe('200.00');
    expect(s.outstanding).toBe('680.00');
  });

  it('does not change revenue or tax with the payment method', () => {
    // A UPI payment and a cash payment for the same bill produce the same invoice.
    const upi = previewInvoice(tender(bill(), 'UPI', '1180', 'UTR1'), policy, CONTEXT);
    const cash = previewInvoice(tender(bill(), 'CASH', '1180'), policy, CONTEXT);

    expect(upi.taxableValue).toBe(cash.taxableValue);
    expect(upi.tax).toEqual(cash.tax);
    expect(upi.total).toBe(cash.total);
  });

  it('cannot know what is owed before it knows the total', () => {
    let draft = bill();
    draft = reduceDraft(draft, { type: 'line', key: draft.lines[0]!.key, patch: { taxRate: '' } });
    expect(settle(draft).outstanding).toBeNull();
  });
});

describe('advances', () => {
  it('applies only up to the bill, leaving the rest on the advance', () => {
    // An advance larger than the bill must not become a negative debt here — the remainder
    // belongs to the advance, for another document.
    const s = settle(advance(bill(), '5000', '5000'));
    expect(s.advances).toBe('1180.00');
    expect(s.outstanding).toBe('0.00');
  });

  it('is refused above what the advance has unallocated', () => {
    const problems = draftProblems(advance(bill(), '500', '800'), policy);
    expect(problems.map((p) => p.message)).toContain('Only 500 of Advance adv-1 is unallocated.');
  });

  it('cannot be applied twice from the same source', () => {
    // Applying one credit twice is how one advance gets spent twice.
    const twice = advance(advance(bill(), '500', '100'), '500', '100');
    expect(twice.advances).toHaveLength(1);
  });

  it('is dropped when the customer changes, because it was the other party’s money', () => {
    const applied = advance(bill(), '500', '300');
    const switched = reduceDraft(applied, { type: 'header', patch: { customerId: 'c2', customerLabel: 'Other' } });

    expect(switched.advances).toEqual([]);
  });

  it('is kept when an unrelated header field changes', () => {
    const applied = advance(bill(), '500', '300');
    const edited = reduceDraft(applied, { type: 'header', patch: { creditDays: '15' } });
    expect(edited.advances).toHaveLength(1);
  });
});

describe('change and overpayment', () => {
  it('returns change out of cash', () => {
    const s = settle(tender(bill(), 'CASH', '1200'));
    expect(s.outstanding).toBe('0.00');
    expect(s.changeDue).toBe('20.00');
    expect(s.excess).toBe('0.00');
  });

  it('returns no change on UPI, and calls the excess a problem', () => {
    // Nobody hands back change on a UPI payment.
    const draft = tender(bill(), 'UPI', '1200', 'UTR9');
    const preview = previewInvoice(draft, policy, CONTEXT);

    expect(preview.settlement.changeDue).toBe('0.00');
    expect(preview.settlement.excess).toBe('20.00');
    expect(previewProblems(preview)[0]?.message).toMatch(/only cash can be handed back/);
  });

  it('returns change only up to the cash tendered in a split payment', () => {
    // 1,100 by UPI and 100 in cash against 1,180: 20 over, all of it returnable from the cash.
    const draft = tender(tender(bill(), 'UPI', '1100', 'UTR1'), 'CASH', '100');
    const s = settle(draft);

    expect(s.changeDue).toBe('20.00');
    expect(s.excess).toBe('0.00');
  });

  it('raises no settlement problem when the amounts reconcile', () => {
    const preview = previewInvoice(tender(bill(), 'CASH', '1180'), policy, CONTEXT);
    expect(previewProblems(preview)).toEqual([]);
  });
});

describe('cheques', () => {
  it('records a cheque as to-clear, not as received', () => {
    // A cheque is not cleared bank cash (data model §4).
    const preview = previewInvoice(tender(bill(), 'CHEQUE', '1180', '004512'), policy, CONTEXT);

    expect(preview.settlement.received).toBe('0.00');
    expect(preview.settlement.pendingClearance).toBe('1180.00');
    expect(preview.settlement.outstanding).toBe('0.00');
    expect(preview.unresolved.some((reason) => /cleared when the bank confirms/.test(reason))).toBe(true);
  });
});

describe('references and card data', () => {
  const messages = (draft: SalesDraft, using: SalesEntryPolicy = policy) =>
    draftProblems(draft, using).map((p) => p.message);
  const strict: SalesEntryPolicy = {
    ...policy,
    settlement: { ...policy.settlement, referenceRequired: ['UPI', 'BANK_TRANSFER', 'CHEQUE'] },
  };

  it('never demands a non-cash reference by default', () => {
    for (const mode of ['UPI', 'BANK_TRANSFER', 'CHEQUE', 'CARD'] as const) {
      const asked = messages(tender(bill(), mode, '100'));
      // The cheque's own date is still asked for; its number, a UTR or slip number never is.
      expect(asked.filter((m) => /^Enter the /.test(m) && m !== 'Enter the date on the cheque.')).toEqual([]);
    }
  });

  it('asks for the reference each mode requires where a policy requires one', () => {
    // "UTR", not "utr": a label is put into a sentence without lower-casing its acronym.
    expect(messages(tender(bill(), 'UPI', '100'), strict)).toContain('Enter the UTR.');
    expect(messages(tender(bill(), 'CHEQUE', '100'), strict)).toContain('Enter the cheque number.');
    // Cash needs none.
    expect(messages(tender(bill(), 'CASH', '100'), strict).some((m) => /reference/.test(m))).toBe(false);
  });

  it('refuses a card number typed into a card tender’s reference', () => {
    // Raw card data is never stored, and this field is exactly where it would be (CLAUDE.md §5.10).
    for (const pan of ['4111111111111111', '4111 1111 1111 1111', '4111-1111-1111-1111']) {
      expect(messages(tender(bill(), 'CARD', '100', pan))).toContain(
        'That looks like a card number. Enter only the approval code — card numbers are never stored.',
      );
    }
  });

  it('accepts an approval code', () => {
    expect(messages(tender(bill(), 'CARD', '1180', 'A1B2C3')).some((m) => /card number/.test(m))).toBe(false);
  });
});

describe('what the policy allows', () => {
  it('refuses a second mode when split payment is not offered', () => {
    const narrowed: SalesEntryPolicy = {
      ...policy,
      settlement: { ...policy.settlement, splitTender: { available: false, reason: 'One mode only.' } },
    };
    const draft = tender(tender(bill(), 'CASH', '100'), 'CASH', '100');
    expect(draftProblems(draft, narrowed).map((p) => p.message)).toContain(
      'This bill type takes one payment mode at a time.',
    );
  });

  it('refuses a mode the bill type does not accept', () => {
    const narrowed: SalesEntryPolicy = {
      ...policy,
      settlement: { ...policy.settlement, tenderModes: ['CASH', 'UPI'] },
    };
    expect(draftProblems(tender(bill(), 'CHEQUE', '100', '1'), narrowed).map((p) => p.message)).toContain(
      'Cheque is not accepted on this bill type.',
    );
  });

  it('ignores a payment the policy does not allow rather than counting it', () => {
    const narrowed: SalesEntryPolicy = {
      ...policy,
      settlement: { ...policy.settlement, immediateTender: { available: false, reason: 'Credit only.' } },
    };
    expect(settle(tender(bill(), 'CASH', '1180'), narrowed).outstanding).toBe('1180.00');
  });

  it('wants credit days as a whole number', () => {
    const draft = reduceDraft(bill(), { type: 'header', patch: { creditDays: '1.5' } });
    expect(draftProblems(draft, policy).map((p) => p.message)).toContain(
      'Credit days is a whole number of days, up to 999.',
    );
  });
});

describe('due dates', () => {
  it('falls due credit-days after the invoice date, when something is owed', () => {
    const draft = reduceDraft(bill(), { type: 'header', patch: { creditDays: '30' } });
    expect(settle(draft).dueDate).toBe('2026-11-27');
  });

  it('has no due date once nothing is owed', () => {
    const draft = tender(reduceDraft(bill(), { type: 'header', patch: { creditDays: '30' } }), 'CASH', '1180');
    expect(settle(draft).dueDate).toBeNull();
  });

  it('adds days to the calendar date, across months and leap days, in UTC', () => {
    // A business date never shifts by a day because a browser sits east of Greenwich.
    expect(addDays('2026-01-31', 1)).toBe('2026-02-01');
    expect(addDays('2028-02-28', 1)).toBe('2028-02-29');
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
    expect(addDays('2026-10-28', 0)).toBe('2026-10-28');
    expect(addDays('not a date', 3)).toBeNull();
  });
});

describe('labels in a sentence', () => {
  it('lower-cases a word and leaves an acronym alone', () => {
    expect(inSentence('Cheque number')).toBe('cheque number');
    expect(inSentence('Approval code')).toBe('approval code');
    expect(inSentence('UTR')).toBe('UTR');
    expect(inSentence('UPI')).toBe('UPI');
    expect(inSentence('UTR or transfer reference')).toBe('UTR or transfer reference');
    expect(inSentence('')).toBe('');
  });

  it('asks for the UPI amount by its name', () => {
    expect(draftProblems(tender(bill(), 'UPI', '', 'UTR1'), policy).map((p) => p.message)).toContain(
      'Enter the UPI amount.',
    );
  });
});
