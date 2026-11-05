/**
 * The provisional preview's arithmetic, with no component rendered.
 *
 * Exact decimal arithmetic is the first thing tested, because everything else rests on it: a
 * preview that drifts by a paisa from the accepted invoice for floating-point reasons would make
 * every genuine difference unexplainable. Then the calculation contract's own rules, each with
 * the worked figures it is stated with:
 *
 *  - stages apply to what the stage before left — 10% then 5% is **14.5%**, not 15%;
 *  - an apportioned amount reconciles to its source **exactly**, by largest remainder;
 *  - CGST and SGST are separate half-rate components, each rounded;
 *  - a tax-inclusive rate is taken back to its base before any discount;
 *  - round-off is its own line, never a nudge to tax;
 *  - anything unknown is `null` with a sentence, never zero.
 */
import { describe, expect, it } from 'vitest';
import * as D from '../app/lib/fixed-decimal';
import { previewInvoice } from '../app/lib/sales-entry-preview';
import {
  initialDraft,
  reduceDraft,
  type DraftLine,
  type SalesDraft,
} from '../app/lib/sales-entry-draft';
import { SAMPLE_SALES_POLICY, type SalesEntryPolicy } from '../app/lib/sales-entry-policy';

const TODAY = '2026-10-28';
const KARNATAKA = { companyState: 'Karnataka', places: 2 };
const policy = SAMPLE_SALES_POLICY;

/** A draft with these lines and this customer state. */
function draftWith(
  lines: Partial<DraftLine>[],
  extra: (draft: SalesDraft) => SalesDraft = (draft) => draft,
): SalesDraft {
  let draft = initialDraft(policy, TODAY);
  draft = reduceDraft(draft, { type: 'header', patch: { customerState: 'Karnataka' } });
  lines.forEach((line, index) => {
    if (index > 0) draft = reduceDraft(draft, { type: 'addLine' });
    const key = draft.lines[index]!.key;
    draft = reduceDraft(draft, {
      type: 'line',
      key,
      patch: {
        subjectId: `item-${index}`,
        subjectLabel: `Item ${index}`,
        actualQuantity: '1',
        billedQuantity: '1',
        rate: '100',
        taxRate: '18',
        ...line,
      },
    });
  });
  return extra(draft);
}

describe('exact decimals', () => {
  it('adds what a float cannot', () => {
    // The canonical demonstration of why none of this is a `number`.
    expect(D.format(D.add(D.parse('0.1')!, D.parse('0.2')!))).toBe('0.3000');
  });

  it('parses and formats at the storage scale', () => {
    expect(D.parse('1234.5678')).toBe(12345678n);
    expect(D.parse('1.5')).toBe(15000n);
    expect(D.format(15000n)).toBe('1.5000');
    expect(D.format(15000n, 2)).toBe('1.50');
    expect(D.parse('1.23456')).toBeNull();
    expect(D.parse('')).toBeNull();
    expect(D.parse('abc')).toBeNull();
  });

  it('rounds half-up away from zero, once', () => {
    expect(D.format(D.round(D.parse('2.345')!, 2), 2)).toBe('2.35');
    expect(D.format(D.round(D.parse('2.344')!, 2), 2)).toBe('2.34');
    expect(D.format(D.round(D.parse('-2.345')!, 2), 2)).toBe('-2.35');
  });

  it('multiplies and divides without drifting', () => {
    expect(D.format(D.mul(D.parse('2450')!, D.parse('3')!), 2)).toBe('7350.00');
    expect(D.format(D.percent(D.parse('1000')!, D.parse('18')!), 2)).toBe('180.00');
    expect(() => D.div(D.parse('1')!, D.ZERO)).toThrow(RangeError);
  });

  it('allocates so the parts sum to the whole exactly', () => {
    // 100 across three equal weights cannot divide evenly at two places. Independent rounding
    // gives 33.33 × 3 = 99.99 — a paisa short of its source, which the contract rejects.
    const parts = D.allocate(D.parse('100')!, [1n, 1n, 1n], 2);
    expect(parts.map((part) => D.format(part, 2))).toEqual(['33.34', '33.33', '33.33']);
    expect(D.format(D.add(...parts), 2)).toBe('100.00');
  });

  it('allocates by weight and breaks ties by position, so it is stable', () => {
    const parts = D.allocate(D.parse('10')!, [D.parse('300')!, D.parse('100')!], 2);
    expect(parts.map((part) => D.format(part, 2))).toEqual(['7.50', '2.50']);
    // Same input, same output — every time.
    expect(D.allocate(D.parse('10')!, [D.parse('300')!, D.parse('100')!], 2)).toEqual(parts);
  });
});

describe('the base, and tax', () => {
  it('previews a plain intra-state line: 1,000 at 18% is CGST 90 + SGST 90', () => {
    const preview = previewInvoice(draftWith([{ billedQuantity: '10', rate: '100' }]), policy, KARNATAKA);

    expect(preview.subtotal).toBe('1000.00');
    expect(preview.taxableValue).toBe('1000.00');
    expect(preview.supply).toBe('INTRA_STATE');
    expect(preview.tax).toEqual({ cgst: '90.00', sgst: '90.00', igst: '0.00', total: '180.00' });
    expect(preview.total).toBe('1180.00');
    expect(preview.status).toBe('PROVISIONAL');
  });

  it('charges IGST instead when the customer is in another state', () => {
    const draft = draftWith([{ billedQuantity: '10', rate: '100' }], (d) =>
      reduceDraft(d, { type: 'header', patch: { customerState: 'Delhi' } }),
    );
    const preview = previewInvoice(draft, policy, KARNATAKA);

    expect(preview.supply).toBe('INTER_STATE');
    expect(preview.tax).toEqual({ cgst: '0.00', sgst: '0.00', igst: '180.00', total: '180.00' });
  });

  it('rounds CGST and SGST separately, as the components they are', () => {
    // 333.33 at 5%: each half (2.5%) is 8.33325 → 8.33, so the tax is 16.66. Halving a rounded
    // 5% (16.67) would give 8.335 → 8.34 each, a paisa more than the components that exist.
    const preview = previewInvoice(draftWith([{ rate: '333.33', taxRate: '5' }]), policy, KARNATAKA);

    expect(preview.tax?.cgst).toBe('8.33');
    expect(preview.tax?.sgst).toBe('8.33');
    expect(preview.tax?.total).toBe('16.66');
  });

  it('knows the tax total but not its split while the customer is unknown', () => {
    const draft = draftWith([{ billedQuantity: '10' }], (d) =>
      reduceDraft(d, { type: 'header', patch: { customerState: '' } }),
    );
    const preview = previewInvoice(draft, policy, KARNATAKA);

    // CGST + SGST and IGST are the same total at the same rate; only the split depends on the
    // place of supply — so the total is shown and the split is honestly unknown.
    expect(preview.supply).toBe('UNKNOWN');
    expect(preview.tax?.total).toBe('180.00');
    expect(preview.tax?.cgst).toBeNull();
    expect(preview.tax?.igst).toBeNull();
    expect(preview.unresolved.some((reason) => /intra-state or an inter-state/.test(reason))).toBe(true);
  });

  it('refuses to invent a tax for a line whose rate is unresolved', () => {
    const preview = previewInvoice(
      draftWith([{ billedQuantity: '10' }, { billedQuantity: '1', taxRate: '' }]),
      policy,
      KARNATAKA,
    );

    // A partial tax total is a wrong one, and zero would read as "no tax".
    expect(preview.tax).toBeNull();
    expect(preview.total).toBeNull();
    expect(preview.lines[1]!.tax).toBeNull();
    expect(preview.lines[1]!.taxableValue).toBe('100.00');
    expect(preview.unresolved.some((reason) => /no resolved tax rate/.test(reason))).toBe(true);
  });

  it('takes a tax-inclusive rate back to its base before anything else', () => {
    // 118 including 18% is 100 of value and 18 of tax.
    const draft = draftWith([{ rate: '118' }], (d) =>
      reduceDraft(d, { type: 'header', patch: { taxInclusive: true } }),
    );
    const preview = previewInvoice(draft, policy, KARNATAKA);

    expect(preview.taxableValue).toBe('100.00');
    expect(preview.tax?.total).toBe('18.00');
    expect(preview.total).toBe('118.00');
  });

  it('cannot split an inclusive rate whose tax is unknown, and says so', () => {
    const draft = draftWith([{ rate: '118', taxRate: '' }], (d) =>
      reduceDraft(d, { type: 'header', patch: { taxInclusive: true } }),
    );
    const preview = previewInvoice(draft, policy, KARNATAKA);

    expect(preview.lines).toHaveLength(0);
    expect(preview.unresolved.some((reason) => /tax-inclusive rate cannot be split/.test(reason))).toBe(true);
  });

  it('leaves out an incomplete line and says which one', () => {
    const preview = previewInvoice(
      draftWith([{ billedQuantity: '10' }, { billedQuantity: '', rate: '' , subjectId: 'x' }]),
      policy,
      KARNATAKA,
    );

    expect(preview.lines).toHaveLength(1);
    expect(preview.unresolved).toContain('Line 2 is not complete, so it is not in the totals yet.');
  });
});

describe('discount stages', () => {
  it('applies a line discount to its own line', () => {
    const preview = previewInvoice(
      draftWith([{ billedQuantity: '10', discountInput: '10', discountKind: 'PERCENT' }]),
      policy,
      KARNATAKA,
    );
    expect(preview.discounts.line).toBe('100.00');
    expect(preview.taxableValue).toBe('900.00');
  });

  it('stacks 10% then 5% to 14.5%, not 15%', () => {
    // The worked example the calculation contract states in words.
    const draft = draftWith(
      [{ billedQuantity: '10', discountInput: '10', discountKind: 'PERCENT' }],
      (d) => {
        const added = reduceDraft(d, { type: 'addDiscount', scope: 'DOCUMENT' });
        return reduceDraft(added, {
          type: 'discount',
          key: added.discounts[0]!.key,
          patch: { kind: 'PERCENT', input: '5' },
        });
      },
    );
    const preview = previewInvoice(draft, policy, KARNATAKA);

    expect(preview.discounts.total).toBe('145.00');
    expect(preview.taxableValue).toBe('855.00');
  });

  it('apportions a document amount across lines and reconciles to the paisa', () => {
    const draft = draftWith(
      [{ rate: '100' }, { rate: '100' }, { rate: '100' }],
      (d) => {
        const added = reduceDraft(d, { type: 'addDiscount', scope: 'DOCUMENT' });
        return reduceDraft(added, {
          type: 'discount',
          key: added.discounts[0]!.key,
          patch: { kind: 'AMOUNT', input: '10' },
        });
      },
    );
    const preview = previewInvoice(draft, policy, KARNATAKA);

    expect(preview.lines.map((line) => line.allocatedDiscount)).toEqual(['3.34', '3.33', '3.33']);
    expect(preview.discounts.document).toBe('10.00');
    expect(preview.taxableValue).toBe('290.00');
  });

  it('discounts only the lines a selected-line discount names', () => {
    const draft = draftWith([{ rate: '100' }, { rate: '200' }], (d) => {
      const added = reduceDraft(d, { type: 'addDiscount', scope: 'SELECTED' });
      return reduceDraft(added, {
        type: 'discount',
        key: added.discounts[0]!.key,
        patch: { kind: 'PERCENT', input: '50', lineKeys: [added.lines[1]!.key] },
      });
    });
    const preview = previewInvoice(draft, policy, KARNATAKA);

    expect(preview.lines[0]!.allocatedDiscount).toBe('0.00');
    expect(preview.lines[1]!.allocatedDiscount).toBe('100.00');
    expect(preview.discounts.selected).toBe('100.00');
  });

  it('never discounts below zero', () => {
    // A negative taxable value is not a sale.
    const draft = draftWith([{ rate: '100' }], (d) => {
      const added = reduceDraft(d, { type: 'addDiscount', scope: 'DOCUMENT' });
      return reduceDraft(added, {
        type: 'discount',
        key: added.discounts[0]!.key,
        patch: { kind: 'AMOUNT', input: '500' },
      });
    });
    const preview = previewInvoice(draft, policy, KARNATAKA);

    expect(preview.discounts.document).toBe('100.00');
    expect(preview.taxableValue).toBe('0.00');
  });

  it('ignores a discount the policy forbids rather than previewing it', () => {
    const narrowed: SalesEntryPolicy = {
      ...policy,
      components: { ...policy.components, documentDiscount: { available: false, reason: 'Off.' } },
    };
    const draft = draftWith([{ rate: '100' }], (d) => {
      const added = reduceDraft(d, { type: 'addDiscount', scope: 'DOCUMENT' });
      return reduceDraft(added, {
        type: 'discount',
        key: added.discounts[0]!.key,
        patch: { kind: 'PERCENT', input: '10' },
      });
    });
    expect(previewInvoice(draft, narrowed, KARNATAKA).discounts.document).toBe('0.00');
  });
});

describe('charges and round off', () => {
  it('adds a charge after tax, and says its tax treatment is the service’s', () => {
    const draft = draftWith([{ billedQuantity: '10' }], (d) => {
      const added = reduceDraft(d, { type: 'addCharge', purpose: 'FREIGHT' });
      return reduceDraft(added, { type: 'charge', key: added.charges[0]!.key, patch: { amount: '50' } });
    });
    const preview = previewInvoice(draft, policy, KARNATAKA);

    expect(preview.charges).toBe('50.00');
    expect(preview.total).toBe('1230.00');
    expect(preview.unresolved.some((reason) => /preview adds charges untaxed/.test(reason))).toBe(true);
  });

  it('rounds the total as its own line, never by nudging tax', () => {
    // 333.33 at 5% is 333.33 + 16.66 = 349.99; the fixture rounds to the nearest 1.
    const preview = previewInvoice(draftWith([{ rate: '333.33', taxRate: '5' }]), policy, KARNATAKA);

    expect(preview.tax?.total).toBe('16.66');
    expect(preview.roundOff).toBe('0.01');
    expect(preview.total).toBe('350.00');
  });

  it('rounds down as well as up', () => {
    const preview = previewInvoice(draftWith([{ rate: '100.40', taxRate: '0' }]), policy, KARNATAKA);
    expect(preview.roundOff).toBe('-0.40');
    expect(preview.total).toBe('100.00');
  });

  it('leaves the total unrounded when the policy rounds nothing', () => {
    const narrowed: SalesEntryPolicy = {
      ...policy,
      components: { ...policy.components, rounding: { available: false, reason: 'No bill rounding.' } },
    };
    const preview = previewInvoice(draftWith([{ rate: '333.33', taxRate: '5' }]), narrowed, KARNATAKA);
    expect(preview.roundOff).toBe('0.00');
    expect(preview.total).toBe('349.99');
  });
});

describe('an empty draft', () => {
  it('previews zeros for sums and nothing invented', () => {
    const preview = previewInvoice(initialDraft(policy, TODAY), policy, KARNATAKA);

    expect(preview.lines).toHaveLength(0);
    expect(preview.subtotal).toBe('0.00');
    expect(preview.unresolved).toEqual([]);
  });
});
