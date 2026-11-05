/**
 * Regression tests for the third review's money and rules findings, without a DOM. Each states
 * the input that used to produce the wrong answer.
 */
import { describe, expect, it } from 'vitest';
import {
  addMonths,
  draftProblems,
  initialDraft,
  reduceDraft,
  type DraftLine,
  type SalesDraft,
} from '../app/lib/sales-entry-draft';
import { previewInvoice, previewProblems } from '../app/lib/sales-entry-preview';
import { SAMPLE_SALES_POLICY, type SalesEntryPolicy } from '../app/lib/sales-entry-policy';
import { advanceToApply } from '../app/components/SalesSettlementDrawer';

const policy = SAMPLE_SALES_POLICY;
const CONTEXT = { companyState: 'Karnataka', places: 2 };

function bill(patch: Partial<DraftLine> = {}, header: Partial<SalesDraft> = {}, base = policy): SalesDraft {
  let draft = initialDraft(base, '2026-10-28');
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
      subjectNature: 'GOODS',
      actualQuantity: '10',
      billedQuantity: '10',
      rate: '2450',
      taxRate: '5',
      ...patch,
    },
  });
}
const all = (draft: SalesDraft, base = policy, granted?: (key: string) => boolean) => [
  ...draftProblems(draft, base, granted ? { granted } : {}),
  ...previewProblems(previewInvoice(draft, base, CONTEXT)),
];
const messages = (draft: SalesDraft, base = policy, granted?: (key: string) => boolean) =>
  all(draft, base, granted).map((problem) => problem.message);
const errors = (draft: SalesDraft, base = policy) =>
  all(draft, base).filter((problem) => problem.severity === 'error').map((problem) => problem.message);

describe('A1 zero consideration, however it is reached', () => {
  it('refuses a rate that rounds to nothing', () => {
    // 1 × 0.004 billed 0.00 with no word.
    expect(errors(bill({ actualQuantity: '1', billedQuantity: '1', rate: '0.004' }))).toContain(
      'This line comes to nothing once its rate is rounded to the company’s precision. Check the rate.',
    );
  });

  it('refuses a 100% line discount, and an amount equal to the line', () => {
    const percent = bill({ discountKind: 'PERCENT', discountInput: '100' });
    const amount = bill({ actualQuantity: '1', billedQuantity: '1', rate: '100', discountKind: 'AMOUNT', discountInput: '100' });
    // Said on the line's own discount, and worded by what the policy allows.
    const expected = 'This discount takes the line to nothing. This bill type does not allow free lines.';
    expect(errors(percent)).toContain(expected);
    expect(errors(amount)).toContain(expected);
  });

  it('accepts a declared free line where the policy allows one', () => {
    const allowing: SalesEntryPolicy = {
      ...policy,
      quantities: { ...policy.quantities, freeItem: { available: true, required: false, editable: true } },
    };
    const zero = bill({ rate: '0' }, {}, allowing);
    expect(errors(zero, allowing)).toContain('Choose why this line is free.');
    const declared = reduceDraft(zero, { type: 'line', key: zero.lines[0]!.key, patch: { freePurpose: 'Sample' } });
    expect(errors(declared, allowing)).toEqual([]);
  });
});

describe('A2 rate overrides follow the policy', () => {
  const listed = (rate: string, reason = 'Agreed') =>
    bill({ rate, resolvedRate: '2450', rateSource: 'MANUAL', rateReason: reason });

  it('warns past the approval threshold', () => {
    // 100 against a 2,450 list — 96% off — raised nothing.
    expect(messages(listed('100'))).toContain(
      'This rate is more than 10% from the list price of 2450 and needs approval before the bill can proceed.',
    );
    expect(messages(listed('2300')).some((message) => /needs approval/.test(message))).toBe(false);
  });

  it('refuses an override the policy forbids', () => {
    const forbidding: SalesEntryPolicy = {
      ...policy,
      pricing: { ...policy.pricing, rateOverride: { available: false, reason: 'This bill type uses list prices only.' } },
    };
    expect(errors(bill({ rate: '1', resolvedRate: '2450', rateSource: 'MANUAL' }, {}, forbidding), forbidding)).toContain(
      'This bill type uses list prices only. The list price is 2450.',
    );
  });

  it('refuses an override to a reader without the grant', () => {
    const none = () => false;
    expect(messages(listed('2400'), policy, none)).toContain(
      'Changing the list price needs a permission you do not have. Use the list price, or ask someone who can.',
    );
    expect(messages(listed('2400'), policy, () => true).some((message) => /permission/.test(message))).toBe(false);
  });
});

describe('A3 discount approval on what a discount comes to', () => {
  it('warns on an amount that is a large share of the bill', () => {
    // ₹20,000 off ₹24,500 is 82%; only percentages were checked against the 5% threshold.
    let draft = bill();
    draft = reduceDraft(draft, { type: 'addDiscount', scope: 'DOCUMENT' });
    draft = reduceDraft(draft, { type: 'discount', key: draft.discounts[0]!.key, patch: { kind: 'AMOUNT', input: '20000' } });
    expect(messages(draft).some((message) => /comes to 81\.63% .* above 5% needs approval/.test(message))).toBe(true);
  });

  it('still warns on a typed percentage with no lines yet', () => {
    let draft = initialDraft(policy, '2026-10-28');
    draft = reduceDraft(draft, { type: 'addDiscount', scope: 'DOCUMENT' });
    draft = reduceDraft(draft, { type: 'discount', key: draft.discounts[0]!.key, patch: { input: '8' } });
    expect(messages(draft)).toContain('A bill discount above 5% needs approval before the bill can proceed.');
  });
});

describe('A4 a rate equal to the list price', () => {
  it('is not an override when written with places', () => {
    // `2450.00` against a 2450 list showed "Override" and asked for a reason.
    const draft = bill({ rate: '2450', resolvedRate: '2450', rateSource: 'PRICE_LEVEL' });
    const typed = reduceDraft(draft, { type: 'line', key: draft.lines[0]!.key, patch: { rate: '2450.00' } });
    expect(typed.lines[0]!.rateSource).toBe('PRICE_LEVEL');
    expect(messages(typed)).not.toContain('Say why this rate differs from the price list.');
  });
});

describe('A6 figures past what storage holds', () => {
  it('refuses a line and a bill beyond fifteen integer digits', () => {
    const huge = bill({ actualQuantity: '100000', billedQuantity: '100000', rate: '99999999999' });
    const found = errors(huge);
    expect(found).toContain('This line comes to more than the platform can store. Check the quantity and the rate.');
    expect(found).toContain('The bill comes to more than the platform can store. Check the quantities and the rates.');
  });
});

describe('A7 settlement in exact decimals', () => {
  it('refuses a payment that rounds to nothing', () => {
    let draft = bill();
    draft = reduceDraft(draft, { type: 'addTender', mode: 'CASH', amount: '0.004' });
    expect(errors(draft)).toContain('0.004 is less than the smallest amount this company records (0.01).');
  });

  it('compares a very large advance exactly', () => {
    let draft = bill();
    draft = reduceDraft(draft, {
      type: 'applyAdvance',
      sourceId: 'a1',
      sourceLabel: 'A1',
      available: '999999999999999.9998',
    });
    draft = reduceDraft(draft, { type: 'advance', key: draft.advances[0]!.key, amount: '999999999999999.9999' });
    expect(errors(draft)).toContain('Only 999999999999999.9998 of A1 is unallocated.');
  });
});

describe('A8 the reason matches the difference', () => {
  it('refuses "Short supply" where more leave than are billed', () => {
    const more = bill({ actualQuantity: '11', billedQuantity: '10', quantityReason: 'Short supply' });
    expect(errors(more)).toContain('“Short supply” is for fewer leaving than are billed. Here more leave.');
    const either = bill({ actualQuantity: '11', billedQuantity: '10', quantityReason: 'Measured variance' });
    expect(errors(either).some((message) => /“Measured variance”/.test(message))).toBe(false);
  });
});

describe('B1 a mixed bill', () => {
  it('prices an account line as one amount and asks it for no quantity', () => {
    // Accounts → Mixed turned every account line into "Enter a billed quantity" and a 0.00 total.
    let draft = initialDraft(policy, '2026-10-28');
    draft = reduceDraft(draft, { type: 'mode', mode: 'ACCOUNTS' });
    draft = reduceDraft(draft, {
      type: 'header',
      patch: { customerId: 'c1', customerLabel: 'Nandini', customerState: 'Karnataka' },
    });
    draft = reduceDraft(draft, {
      type: 'line',
      key: draft.lines[0]!.key,
      patch: { subjectId: 'f1', subjectLabel: 'Sales — services', subjectKind: 'ACCOUNT', rate: '1000', taxRate: '18' },
    });
    expect(previewInvoice(draft, policy, CONTEXT).total).toBe('1180.00');

    const mixed = reduceDraft(draft, { type: 'mode', mode: 'MIXED' });
    expect(errors(mixed)).toEqual([]);
    expect(previewInvoice(mixed, policy, CONTEXT).total).toBe('1180.00');
  });
});

describe('B6 goods move stock', () => {
  it('refuses "no stock effect" on a goods line, and allows it on a service', () => {
    expect(errors(bill({ stockIntent: 'NONE' }))).toContain(
      'Goods move stock. Choose dispatch now, already dispatched or dispatch later.',
    );
    expect(errors(bill({ stockIntent: 'NONE', subjectNature: 'SERVICE' }))).toEqual([]);
  });
});

describe('C1 the place of supply', () => {
  it('is the ship-to state when one is chosen', () => {
    // A Karnataka customer shipping to Tamil Nadu is an inter-state supply.
    const shipped = bill({}, { shipToId: 'd2', shipToLabel: 'Warehouse, Hosur', shipToState: 'Tamil Nadu' });
    expect(previewInvoice(shipped, policy, CONTEXT).supply).toBe('INTER_STATE');
    expect(previewInvoice(bill(), policy, CONTEXT).supply).toBe('INTRA_STATE');
  });

  it('is forgotten with the customer', () => {
    const shipped = bill({}, { shipToId: 'd2', shipToLabel: 'Warehouse, Hosur', shipToState: 'Tamil Nadu' });
    const other = reduceDraft(shipped, { type: 'header', patch: { customerId: 'c3', customerLabel: 'Sharma' } });
    expect(other.shipToId).toBeNull();
    expect(other.shipToState).toBe('');
  });
});

describe('C4 applying an advance', () => {
  it('prefills the smaller of the balance and what is owed', () => {
    expect(advanceToApply('5000', '2572.50')).toBe('2572.5000');
    expect(advanceToApply('800', '2572.50')).toBe('800.0000');
    expect(advanceToApply('800', '0.00')).toBeNull();
    expect(advanceToApply('800', null)).toBeNull();
  });
});

describe('C5 cheques', () => {
  const cheque = (instrumentDate: string) => {
    let draft = bill();
    draft = reduceDraft(draft, { type: 'addTender', mode: 'CHEQUE', amount: '100' });
    return reduceDraft(draft, {
      type: 'tender',
      key: draft.tenders[0]!.key,
      patch: { reference: '004512', instrumentDate },
    });
  };

  it('needs the date on the cheque', () => {
    expect(errors(cheque(''))).toContain('Enter the date on the cheque.');
  });

  it('warns about a post-dated cheque and a stale one', () => {
    expect(messages(cheque('2026-11-05'))).toContain('This cheque is post-dated: it cannot be presented before 2026-11-05.');
    expect(messages(cheque('2026-07-01'))).toContain(
      'This cheque is dated more than three months before the bill. Banks normally refuse a cheque that old.',
    );
    expect(messages(cheque('2026-10-20')).some((message) => /cheque/.test(message))).toBe(false);
  });

  it('counts months on the calendar', () => {
    expect(addMonths('2026-05-31', -3)).toBe('2026-02-28');
    expect(addMonths('2026-10-28', -3)).toBe('2026-07-28');
  });
});

describe('C8 the customer’s credit', () => {
  it('warns over the limit and about an overdue balance', () => {
    const position = bill({}, { customerCredit: { limit: '50000', outstanding: '48000', overdue: '6500' } });
    const found = messages(position);
    // 24,500 + 5% = 25,725 more on top of 48,000 owed, against a 50,000 limit.
    expect(found).toContain('This bill takes Nandini 23725.00 over their credit limit of 50000.00.');
    expect(found).toContain('Nandini already has 6500.00 overdue.');
  });
});

describe('C9 tax-inclusive rates with a discount', () => {
  // Decision S8-1: a discount on a tax-inclusive price is inclusive too.
  const inclusive = (patch: Partial<DraftLine>) =>
    bill({ actualQuantity: '1', billedQuantity: '1', rate: '118', taxRate: '18', ...patch }, { taxInclusive: true });

  it('takes an amount off what the customer pays: ₹18 off ₹118 leaves ₹100', () => {
    const result = previewInvoice(inclusive({ discountKind: 'AMOUNT', discountInput: '18' }), policy, CONTEXT);
    expect(result.lines[0]!.amount).toBe('100.00');
    expect(result.taxableValue).toBe('84.75');
    expect(result.tax?.cgst).toBe('7.63');
    expect(result.tax?.sgst).toBe('7.62');
    // Subtotal less discounts is the taxable value, in pre-tax terms.
    expect(result.subtotal).toBe('100.00');
    expect(result.discounts.line).toBe('15.25');
    expect(result.unresolved.some((reason) => /come off the tax-inclusive price/.test(reason))).toBe(true);
  });

  it('gives a percentage the same answer either way', () => {
    const result = previewInvoice(inclusive({ discountKind: 'PERCENT', discountInput: '10' }), policy, CONTEXT);
    expect(result.lines[0]!.amount).toBe('106.20');
  });

  it('takes a bill discount off the inclusive figures too', () => {
    let draft = inclusive({});
    draft = reduceDraft(draft, { type: 'addDiscount', scope: 'DOCUMENT' });
    draft = reduceDraft(draft, { type: 'discount', key: draft.discounts[0]!.key, patch: { kind: 'AMOUNT', input: '18' } });
    const result = previewInvoice(draft, policy, CONTEXT);
    expect(result.lines[0]!.amount).toBe('100.00');
    expect(result.discounts.document).toBe('15.25');
  });
});

/* ------------------------------------------------------------------ the fourth review */

describe('the fourth review', () => {
  it('refuses an oversized bill whose tax rate is not resolved', () => {
    // The amount is unknown without a tax rate, so only the amount was checked — and passed.
    const huge = bill({ actualQuantity: '999999999', billedQuantity: '999999999', rate: '99999999', taxRate: '' });
    expect(errors(huge)).toContain('This line comes to more than the platform can store. Check the quantity and the rate.');
  });

  it('gives no credit-limit warning on a bill paid in full, and says what is overdue at once', () => {
    let paid = bill(
      { actualQuantity: '1', billedQuantity: '1', rate: '100', taxRate: '0' },
      { customerCredit: { limit: '1000', outstanding: '1500', overdue: '200' } },
    );
    paid = reduceDraft(paid, { type: 'addTender', mode: 'CASH', amount: '100' });
    const found = messages(paid);
    expect(found.some((message) => /credit limit/.test(message))).toBe(false);
    expect(found).toContain('Nandini already has 200.00 overdue.');
    // Overdue is said before any line is complete.
    const early = reduceDraft(initialDraft(policy, '2026-10-28'), {
      type: 'header',
      patch: { customerId: 'c3', customerLabel: 'Sharma', customerCredit: { limit: '', outstanding: '0', overdue: '50' } },
    });
    expect(messages(early)).toContain('Sharma already has 50.00 overdue.');
  });

  it('says a full bill discount once, on the discount, worded by the policy', () => {
    let draft = bill({ actualQuantity: '1', billedQuantity: '1', rate: '100' });
    draft = reduceDraft(draft, { type: 'addLine' });
    draft = reduceDraft(draft, {
      type: 'line',
      key: draft.lines[1]!.key,
      patch: {
        subjectId: 'i2',
        subjectLabel: 'Oil',
        subjectKind: 'ITEM',
        subjectNature: 'GOODS',
        actualQuantity: '1',
        billedQuantity: '1',
        rate: '50',
        taxRate: '5',
      },
    });
    draft = reduceDraft(draft, { type: 'addDiscount', scope: 'DOCUMENT' });
    draft = reduceDraft(draft, { type: 'discount', key: draft.discounts[0]!.key, patch: { kind: 'AMOUNT', input: '500' } });
    const found = all(draft);
    const zero = found.filter((problem) => /takes a line to nothing/.test(problem.message));
    expect(zero).toHaveLength(1);
    expect(zero[0]!.field).toBe(`${draft.discounts[0]!.key}.input`);
    expect(zero[0]!.message).toMatch(/does not allow free lines/);
    // Over its pool is the error; "comes to 100%" on top of it said nothing new.
    expect(found.some((problem) => /of what it applies to; above/.test(problem.message))).toBe(false);
  });

  it('does not stack an override and an approval on a zero rate', () => {
    const zero = bill({ rate: '0', resolvedRate: '2450', rateSource: 'MANUAL' });
    expect(messages(zero).some((message) => /differs from the price list|needs approval/.test(message))).toBe(false);
  });

  it('raises no approval on an override the reader may not make', () => {
    const denied = messages(
      bill({ rate: '100', resolvedRate: '2450', rateSource: 'MANUAL', rateReason: 'x' }),
      policy,
      () => false,
    );
    expect(denied.some((message) => /needs approval/.test(message))).toBe(false);
  });

  it('takes the bill-to state as the place of supply when nothing is shipped elsewhere', () => {
    const billed = bill({}, { billToId: 'd2', billToLabel: 'Hosur', billToState: 'Tamil Nadu' });
    expect(previewInvoice(billed, policy, CONTEXT).supply).toBe('INTER_STATE');
  });

  it('drops a free-item purpose once the line has a price', () => {
    const free = bill({ rate: '0', freePurpose: 'Sample' });
    const priced = reduceDraft(free, { type: 'line', key: free.lines[0]!.key, patch: { rate: '10' } });
    expect(priced.lines[0]!.freePurpose).toBe('');
  });

  it('asks a mixed bill’s empty line for an item or an account', () => {
    let draft = reduceDraft(initialDraft(policy, '2026-10-28'), { type: 'mode', mode: 'MIXED' });
    draft = reduceDraft(draft, { type: 'line', key: draft.lines[0]!.key, patch: { rate: '10' } });
    expect(messages(draft)).toContain('Choose an item or an account.');
  });

  it('quotes dates the company’s way when given its formatter', () => {
    let draft = bill();
    draft = reduceDraft(draft, { type: 'addTender', mode: 'CHEQUE', amount: '100' });
    draft = reduceDraft(draft, {
      type: 'tender',
      key: draft.tenders[0]!.key,
      patch: { reference: '1', instrumentDate: '2026-11-05' },
    });
    const found = draftProblems(draft, policy, { formatDate: () => '5 Nov 2026' }).map((problem) => problem.message);
    expect(found).toContain('This cheque is post-dated: it cannot be presented before 5 Nov 2026.');
  });
});
