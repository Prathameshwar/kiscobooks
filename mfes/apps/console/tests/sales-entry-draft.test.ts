/**
 * The sales draft, with no component rendered at all.
 *
 * The rules live in a pure reducer so they can be read in one place and tested without a DOM —
 * the same reason the designer's history and publication logic are pure. What is asserted here
 * is the handful of platform rules the form is not allowed to re-decide:
 *
 *  - amounts and quantities are **strings**, because money is `DECIMAL(19,4)` and a float
 *    round-trip re-scales it;
 *  - actual and billed quantity are separate facts, and a difference needs a stated reason;
 *  - a zero rate is not a route to "free";
 *  - a manual rate override is visible and needs a reason;
 *  - the posting date is its own field and never inferred from the invoice date.
 */
import { describe, expect, it } from 'vitest';
import {
  draftProblems,
  emptyLine,
  initialDraft,
  isAmount,
  isBlank,
  isQuantity,
  isSavable,
  reduceDraft,
  type SalesDraft,
} from '../app/lib/sales-entry-draft';
import { SAMPLE_SALES_POLICY, columnsFor, type SalesEntryPolicy } from '../app/lib/sales-entry-policy';

const TODAY = '2026-10-28';
const policy = SAMPLE_SALES_POLICY;

function filled(draft: SalesDraft, patch: Partial<ReturnType<typeof emptyLine>> = {}): SalesDraft {
  const key = draft.lines[0]!.key;
  return reduceDraft(draft, {
    type: 'line',
    key,
    patch: {
      subjectId: '01990000-0000-7000-8000-0000000000d1',
      subjectLabel: 'Basmati rice 25kg',
      billedQuantity: '10',
      actualQuantity: '10',
      rate: '100',
      ...patch,
    },
  });
}

function usable(policy: SalesEntryPolicy): SalesDraft {
  const start = initialDraft(policy, TODAY);
  const dated = reduceDraft(start, {
    type: 'header',
    patch: {
      customerId: '01990000-0000-7000-8000-0000000000c1',
      customerLabel: 'Nandini Trading Company',
      documentDate: TODAY,
      postingDate: TODAY,
    },
  });
  return filled(dated);
}

describe('the draft a form opens on', () => {
  it('takes its defaults from policy, not from the form', () => {
    const draft = initialDraft(policy, TODAY);

    expect(draft.mode).toBe(policy.modes.default);
    expect(draft.priceLevel).toBe('Retail');
    expect(draft.creditDays).toBe('30');
    // One blank row, because "add a line" as the only thing on screen is a worse empty state.
    expect(draft.lines).toHaveLength(1);
    expect(isBlank(draft.lines[0]!)).toBe(true);
    expect(draft.revision).toBe(0);
  });

  it('starts both dates on the same day and keeps them separate fields', () => {
    const draft = initialDraft(policy, TODAY);
    expect(draft.documentDate).toBe(TODAY);
    expect(draft.postingDate).toBe(TODAY);

    // Moving the invoice date must not drag the posting date with it: the posting date decides
    // the period, and a late invoice posts into the open one (CLAUDE.md §6.4).
    const moved = reduceDraft(draft, { type: 'header', patch: { documentDate: '2026-09-30' } });
    expect(moved.postingDate).toBe(TODAY);
  });

  it('ignores a default a policy does not offer', () => {
    const narrowed: SalesEntryPolicy = {
      ...policy,
      pricing: { ...policy.pricing, priceLevel: { available: false, reason: 'No price books.' } },
    };
    expect(initialDraft(narrowed, TODAY).priceLevel).toBe('');
  });
});

describe('entering a line', () => {
  it('counts every accepted change, so “not saved yet” is answerable', () => {
    const draft = initialDraft(policy, TODAY);
    expect(filled(draft).revision).toBe(1);
  });

  it('follows billed with actual while they agree, then stops', () => {
    // One keystroke per row in the ordinary case, and hands the two apart the moment they are
    // deliberately different.
    const one = filled(initialDraft(policy, TODAY), { actualQuantity: '', billedQuantity: '' });
    const key = one.lines[0]!.key;

    const typed = reduceDraft(one, { type: 'line', key, patch: { actualQuantity: '11' } });
    expect(typed.lines[0]!.billedQuantity).toBe('11');

    const split = reduceDraft(typed, { type: 'line', key, patch: { billedQuantity: '10' } });
    expect(split.lines[0]!.actualQuantity).toBe('11');

    const again = reduceDraft(split, { type: 'line', key, patch: { actualQuantity: '12' } });
    expect(again.lines[0]!.billedQuantity).toBe('10');
  });

  it('calls a rate an override only once there is a resolved price to depart from', () => {
    // The distinction the reducer tests forced: typing the only rate anyone could have entered
    // is not an amendment, and treating it as one made every ordinary line demand a reason.
    const typed = usable(policy);
    expect(typed.lines[0]!.rateSource).toBe('MANUAL');
    expect(typed.lines[0]!.resolvedRate).toBe('');

    const key = typed.lines[0]!.key;
    const priced = reduceDraft(typed, {
      type: 'line',
      key,
      patch: { rate: '100', resolvedRate: '100', rateSource: 'PRICE_LEVEL' },
    });
    expect(priced.lines[0]!.rateSource).toBe('PRICE_LEVEL');

    // 5% under the list: inside the 10% approval threshold, so a reason is all it needs.
    const cut = reduceDraft(priced, { type: 'line', key, patch: { rate: '95' } });
    expect(cut.lines[0]!.rateSource).toBe('MANUAL');

    // And back again: the badge goes quiet rather than leaving the line looking amended.
    const restored = reduceDraft(cut, { type: 'line', key, patch: { rate: '100' } });
    expect(restored.lines[0]!.rateSource).toBe('PRICE_LEVEL');
  });

  it('never drops below one row', () => {
    const draft = initialDraft(policy, TODAY);
    expect(reduceDraft(draft, { type: 'removeLine', key: draft.lines[0]!.key }).lines).toHaveLength(1);

    const two = reduceDraft(draft, { type: 'addLine' });
    expect(reduceDraft(two, { type: 'removeLine', key: two.lines[0]!.key }).lines).toHaveLength(1);
  });

  it('keeps the lines when the mode changes', () => {
    // The mode changes which columns show and how the draft validates — it does not select a
    // different store (data model §4) — so discarding the lines would be the form inventing a
    // rule the platform does not have.
    const draft = usable(policy);
    const switched = reduceDraft(draft, { type: 'mode', mode: 'ACCOUNTS' });

    expect(switched.lines).toHaveLength(1);
    expect(switched.lines[0]!.subjectLabel).toBe('Basmati rice 25kg');
    expect(reduceDraft(switched, { type: 'mode', mode: 'ACCOUNTS' })).toBe(switched);
  });
});

describe('what the form says is wrong', () => {
  const messages = (draft: SalesDraft, p: SalesEntryPolicy = policy) =>
    draftProblems(draft, p).map((problem) => problem.message);

  it('accepts a complete bill', () => {
    expect(draftProblems(usable(policy), policy)).toEqual([]);
    expect(isSavable(usable(policy), policy)).toBe(true);
  });

  it('asks for a customer, the dates and at least one line', () => {
    const bare = initialDraft({ ...policy, dates: { ...policy.dates } }, '');
    expect(messages(bare)).toEqual(
      expect.arrayContaining([
        'Choose the customer this is billed to.',
        'A document date is required.',
        'A posting date is required.',
        'Add at least one line.',
      ]),
    );
  });

  it('ignores a blank trailing row', () => {
    const draft = reduceDraft(usable(policy), { type: 'addLine' });
    expect(draftProblems(draft, policy)).toEqual([]);
  });

  it('demands a reason when actual and billed differ', () => {
    // The documented rule: a bare difference is not evidence of an authorised bonus
    // (commercial configuration §4.1).
    const deal = filled(usable(policy), { actualQuantity: '11', billedQuantity: '10' });
    expect(messages(deal)).toContain('Say why the actual and billed quantities differ.');

    const explained = reduceDraft(deal, {
      type: 'line',
      key: deal.lines[0]!.key,
      patch: { quantityReason: 'Manual bonus quantity' },
    });
    expect(draftProblems(explained, policy)).toEqual([]);
  });

  it('refuses a quantity difference the company does not record', () => {
    const narrowed: SalesEntryPolicy = {
      ...policy,
      quantities: {
        ...policy.quantities,
        actualVersusBilled: { available: false, reason: 'Not recorded on a sale.' },
      },
    };
    const deal = filled(usable(narrowed), {
      actualQuantity: '11',
      billedQuantity: '10',
      quantityReason: 'Manual bonus quantity',
    });
    expect(messages(deal, narrowed)).toContain(
      'This company does not record a quantity difference on a sale.',
    );
  });

  it('refuses a zero rate as a way to make something free', () => {
    // Zero consideration is not zero taxable value or zero cost, and a blank rate declares
    // nothing (commercial configuration §4.2). The fixture does not permit free items, so the
    // message is the policy's own reason rather than a generic complaint.
    const free = filled(usable(policy), { rate: '0' });
    expect(messages(free)).toContain(policy.quantities.freeItem.available === false
      ? policy.quantities.freeItem.reason
      : 'unreachable');
  });

  it('asks for a reason only when a rate departs from a resolved price', () => {
    const draft = usable(policy);
    const key = draft.lines[0]!.key;
    // Nothing resolved a price, so the rate that was typed is simply the rate.
    expect(messages(draft)).not.toContain('Say why this rate differs from the price list.');

    const priced = reduceDraft(draft, {
      type: 'line',
      key,
      patch: { rate: '100', resolvedRate: '100', rateSource: 'PRICE_LEVEL' },
    });
    expect(messages(priced)).not.toContain('Say why this rate differs from the price list.');

    // 5% under the list: inside the 10% approval threshold, so a reason is all it needs.
    const cut = reduceDraft(priced, { type: 'line', key, patch: { rate: '95' } });
    expect(messages(cut)).toContain('Say why this rate differs from the price list.');

    const explained = reduceDraft(cut, {
      type: 'line',
      key,
      patch: { rateReason: 'Agreed volume price' },
    });
    expect(draftProblems(explained, policy)).toEqual([]);
  });

  it('caps a percentage discount at 100 and refuses one the policy forbids', () => {
    const over = filled(usable(policy), { discountInput: '140', discountKind: 'PERCENT' });
    expect(messages(over)).toContain('A percentage discount cannot exceed 100.');

    // An amount discount of 140 is ordinary, so the cap must not apply to it.
    const amount = filled(usable(policy), { discountInput: '140', discountKind: 'AMOUNT' });
    expect(draftProblems(amount, policy)).toEqual([]);
  });

  it('warns rather than blocks when the posting date precedes the invoice date', () => {
    // A late posting is legitimate and the open period decides; the service owns
    // `assert_postable`. This only asks "did you mean that?".
    const draft = reduceDraft(usable(policy), {
      type: 'header',
      patch: { postingDate: '2026-10-01' },
    });
    const problem = draftProblems(draft, policy).find((entry) => entry.field === 'postingDate');

    expect(problem?.severity).toBe('warning');
    expect(isSavable(draft, policy)).toBe(true);
  });

  it('does not ask an accounts-only bill for quantities', () => {
    const accounts = reduceDraft(
      filled(usable(policy), { actualQuantity: '', billedQuantity: '', unit: '' }),
      { type: 'mode', mode: 'ACCOUNTS' },
    );
    expect(messages(accounts)).not.toContain('Enter a billed quantity.');
  });
});

describe('the numbers are strings', () => {
  it('stores what was typed, exactly', () => {
    // Four decimals is the storage scale and `0.1 + 0.2` is why none of this is a `number`.
    const draft = filled(usable(policy), { rate: '1234.5678', billedQuantity: '0.0001' });
    const line = draft.lines[0]!;

    expect(line.rate).toBe('1234.5678');
    expect(typeof line.rate).toBe('string');
    expect(line.billedQuantity).toBe('0.0001');
  });

  it('accepts four decimals and refuses a fifth', () => {
    expect(isAmount('0')).toBe(true);
    expect(isAmount('1234.5678')).toBe(true);
    expect(isAmount('1234.56789')).toBe(false);
    expect(isAmount('-1')).toBe(false);
    expect(isAmount('1e3')).toBe(false);
    expect(isAmount('')).toBe(false);
  });

  it('refuses a zero or negative quantity but allows a zero rate value', () => {
    expect(isQuantity('0')).toBe(false);
    expect(isQuantity('0.0001')).toBe(true);
    // Zero is a legitimate *rate* — a reward unit has one — so the two checks differ.
    expect(isAmount('0')).toBe(true);
  });
});

describe('the column set', () => {
  it('drops the quantity columns in accounts mode and keeps the money ones', () => {
    const items = columnsFor('ITEMS', policy);
    const accounts = columnsFor('ACCOUNTS', policy);

    expect(items).toContain('actual_quantity');
    expect(items).toContain('billed_quantity');
    expect(accounts).not.toContain('actual_quantity');
    expect(accounts).not.toContain('unit');
    expect(accounts).toContain('account');
    expect(accounts).toContain('rate');
    expect(accounts).toContain('amount');
  });

  it('shows one quantity column when the company does not separate them', () => {
    const narrowed: SalesEntryPolicy = {
      ...policy,
      quantities: {
        ...policy.quantities,
        actualVersusBilled: { available: false, reason: 'Not recorded.' },
      },
    };
    const columns = columnsFor('ITEMS', narrowed);

    expect(columns).toContain('billed_quantity');
    expect(columns).not.toContain('actual_quantity');
  });

  it('omits the discount column when no line discount is permitted', () => {
    const narrowed: SalesEntryPolicy = {
      ...policy,
      components: {
        ...policy.components,
        lineDiscount: { available: false, reason: 'Line discounts are off.' },
      },
    };
    expect(columnsFor('ITEMS', narrowed)).not.toContain('discount');
  });
});
