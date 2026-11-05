import { describe, expect, it } from 'vitest';
import { purchaseStatusView, purchaseTermsText, purchaseTrack } from '../app/lib/purchase-page';

const states = (status: string | null, accepted = false) => purchaseTrack(status, accepted).map(step => `${step.label}:${step.state}`);

describe('purchase status wording', () => {
  it.each([
    ['DRAFT', 'Draft', 'neutral'], ['SUBMITTED', 'Submitted for approval', 'info'], ['APPROVED', 'Approved', 'success'],
    ['REJECTED', 'Rejected', 'danger'], ['CANCELLED', 'Cancelled', 'neutral'], ['POSTED', 'Posted', 'success'], ['REVERSED', 'Reversed', 'warn'],
  ])('names %s for the reader', (status, label, tone) => expect(purchaseStatusView(status)).toEqual({ label, tone }));

  it('says "Not saved" before there is a record, and keeps an unknown status readable', () => {
    expect(purchaseStatusView(null)).toEqual({ label: 'Not saved', tone: 'neutral' });
    expect(purchaseStatusView(undefined).label).toBe('Not saved');
    expect(purchaseStatusView('ON_HOLD')).toEqual({ label: 'On_hold', tone: 'neutral' });
  });
});

describe('purchase progress track', () => {
  it('has nothing to track before the bill is saved', () => expect(purchaseTrack(null, false)).toEqual([]));

  it('points a new draft at the calculation, and a calculated one at submission', () => {
    expect(states('DRAFT')).toEqual(['Draft saved:done', 'Calculation accepted:current', 'Submitted:upcoming', 'Approved:upcoming', 'Posted:upcoming']);
    expect(states('DRAFT', true)).toEqual(['Draft saved:done', 'Calculation accepted:done', 'Submitted:current', 'Approved:upcoming', 'Posted:upcoming']);
  });

  it('moves forward with each status and ends complete once posted', () => {
    expect(states('SUBMITTED')).toEqual(['Draft saved:done', 'Calculation accepted:done', 'Submitted:done', 'Approved:current', 'Posted:upcoming']);
    expect(states('APPROVED')).toEqual(['Draft saved:done', 'Calculation accepted:done', 'Submitted:done', 'Approved:done', 'Posted:current']);
    expect(states('POSTED').every(step => step.endsWith(':done'))).toBe(true);
  });

  it('treats an issued bill like an approved one, which is also ready to post', () => {
    expect(states('ISSUED')).toEqual(states('APPROVED'));
    expect(states('ISSUED').at(-1)).toBe('Posted:current');
  });

  it('shows where a rejected bill stopped, and that it can still go on once corrected', () => {
    expect(states('REJECTED')).toEqual(['Draft saved:done', 'Calculation accepted:done', 'Submitted:done', 'Rejected:stopped', 'Approved:upcoming', 'Posted:upcoming']);
  });

  it('ends a cancelled bill at the cancellation, because nothing follows it and what it had reached is not known', () => {
    expect(states('CANCELLED')).toEqual(['Draft saved:done', 'Cancelled:stopped']);
    expect(states('CANCELLED', true)).toEqual(['Draft saved:done', 'Calculation accepted:done', 'Cancelled:stopped']);
  });

  it('shows a reversed bill as fully posted and then reversed', () => {
    expect(states('REVERSED')).toEqual(['Draft saved:done', 'Calculation accepted:done', 'Submitted:done', 'Approved:done', 'Posted:done', 'Reversed:stopped']);
  });

  it('shows a status it does not know as that one labelled step, not as a fresh draft', () => {
    expect(states('ON_HOLD')).toEqual(['On_hold:current']);
  });

  it('never marks more than one step as the next one', () => {
    for (const status of ['DRAFT', 'SUBMITTED', 'APPROVED', 'ISSUED', 'POSTED', 'REJECTED', 'CANCELLED', 'REVERSED', 'ON_HOLD'])
      expect(purchaseTrack(status, false).filter(step => step.state === 'current').length).toBeLessThanOrEqual(1);
  });
});

describe('credit terms sentence', () => {
  it('reads the days and the date they count from', () => {
    expect(purchaseTermsText('30', 'INVOICE_DATE')).toBe('30 days from the supplier invoice date');
    expect(purchaseTermsText('1', 'POSTING_DATE')).toBe('1 day from the posting date');
    expect(purchaseTermsText('0', 'INVOICE_DATE')).toBe('Due on the supplier invoice date');
    expect(purchaseTermsText('0', 'POSTING_DATE')).toBe('Due on the posting date');
  });

  it('does not invent terms from unusable input', () => {
    for (const days of ['', 'abc', '-3', '2.5']) expect(purchaseTermsText(days, 'INVOICE_DATE')).toBe('Not set');
  });
});
