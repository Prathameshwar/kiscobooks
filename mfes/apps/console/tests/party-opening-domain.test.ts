import { describe, expect, it } from 'vitest';
import { addable, heldEntry, heldPath, heldTotals, pendingQuery, verifyHeld } from '../app/lib/party-opening';
import { allowedFinancialOpeningRequest as allow } from '../app/lib/financial-opening-policy';
import { COMPANY } from './financial-opening-fixtures';
import { held, heldInvoice, heldPage } from './party-opening-fixtures';

describe('held party balances', () => {
  it('reads the pending lines through the opening proxy surface only', () => {
    expect(pendingQuery(COMPANY)).toBe(`${heldPath(COMPANY)}?status=PENDING&limit=200`);
    expect(allow('accounting', 'GET', pendingQuery(COMPANY))).toBe(true);
  });

  it('accepts a well-formed page and rejects anything the proxy should not have returned', () => {
    expect(() => verifyHeld(heldPage([held(1), heldInvoice(2)]))).not.toThrow();
    const broken: Array<[string, Partial<ReturnType<typeof held>>]> = [
      ['id', { id: 'not-an-id' }],
      ['key', { source_key: '-bad' }],
      ['side', { side: 'LEFT' as never }],
      ['amount', { amount: '1e5' }],
      ['currency', { currency: 'inr' }],
      ['version', { row_version: 0 }],
      ['included', { included: undefined as never }],
      ['reference', { document_reference: '' }],
      ['party', { party_id: 'nope' }],
      ['account', { account_id: 'nope' }],
      ['status', { status: 'DONE' as never }],
      ['role', { role: 'OTHER' as never }],
      ['base amount', { base_amount: '1,5' }],
      ['rate', { exchange_rate: '0' }],
      ['rate digits', { exchange_rate: '123456789012.5' }],
      ['dated invoice without a due date', { document_kind: 'INVOICE', document_date: '2026-02-10', due_date: null }],
      ['dated invoice without dates', { document_kind: 'INVOICE', document_date: null, due_date: null }],
      ['on-account with a due date', { due_date: '2026-03-12' }],
      ['on-account with dates', { document_date: '2026-01-01' }],
    ];
    for (const [name, change] of broken) expect(() => verifyHeld(heldPage([held(1, change)])), name).toThrow(/could not be verified/);
    expect(() => verifyHeld(heldPage(Array.from({ length: 201 }, (_, n) => held(n + 1))))).toThrow();
    expect(() => verifyHeld({ items: [] } as never)).toThrow();
    expect(() => verifyHeld(null as never)).toThrow();
  });

  it('offers only pending lines the worksheet does not already carry', () => {
    const items = [held(1), held(2, { included: true }), held(3, { status: 'WITHDRAWN' }), held(4), heldInvoice(5)];
    const rows = [{ ...heldEntry(held(4)), source_key: held(4).source_key.toUpperCase() }];
    expect(addable(items, rows).map(item => item.id)).toEqual([held(1).id, heldInvoice(5).id]);
    expect(addable([], [])).toEqual([]);
  });

  it('turns an undated line into an on-account entry with its base value explicit', () => {
    const entry = heldEntry(held(1));
    expect(entry).toMatchObject({
      source_key: held(1).source_key, account_id: held(1).account_id, side: 'CREDIT', currency: 'INR',
      amount: '100.2500', exchange_rate: '1.00000000', base_amount: '100.2500',
    });
    expect(entry.documents).toEqual([
      { line_sequence: 1, document_kind: 'ON_ACCOUNT', reference: 'Opening balance', amount: '100.2500', base_amount: '100.2500' },
    ]);
  });

  it('turns a dated line into one dated document of the named kind', () => {
    const entry = heldEntry(heldInvoice(2));
    expect(entry.side).toBe('DEBIT');
    expect(entry.documents).toEqual([
      {
        line_sequence: 1, reference: 'INV-77', amount: '900.0000', base_amount: '900.0000', document_kind: 'INVOICE',
        document_date: '2026-02-10', due_date: '2026-03-12',
      },
    ]);
    expect(heldEntry(heldInvoice(3, { document_kind: null })).documents?.[0]).toMatchObject({ document_kind: null });
  });

  it('keeps a foreign balance at its historical carrying value', () => {
    const entry = heldEntry(held(1, { currency: 'USD', amount: '10.0000', exchange_rate: '83.20000000', base_amount: '832.0000' }));
    expect(entry).toMatchObject({ currency: 'USD', exchange_rate: '83.20000000', base_amount: '832.0000' });
    expect(entry.documents?.[0]).toMatchObject({ amount: '10.0000', base_amount: '832.0000' });
  });

  it('adds base totals exactly, per side', () => {
    expect(heldTotals([held(1), held(2, { base_amount: '0.1000' }), heldInvoice(3), heldInvoice(4, { base_amount: '0.2000' })]))
      .toEqual({ debit: '900.2000', credit: '100.3500' });
    expect(heldTotals([])).toEqual({ debit: '0.0000', credit: '0.0000' });
  });
});

describe('held balance proxy policy', () => {
  const root = `/v1/companies/${COMPANY}/opening-batches/party-balances`;
  it.each([
    ['GET', root], ['GET', root + '?status=PENDING&limit=200'], ['GET', root + '?role=SUPPLIER&status=WITHDRAWN'],
    ['GET', root + '?party_id=' + held(1).party_id + '&sort=-id'], ['POST', `${root}/${held(1).id}/withdraw`],
  ])('permits %s %s', (method, path) => expect(allow('accounting', method!, path!)).toBe(true));
  it.each([
    ['GET', root + '?status=DONE'], ['GET', root + '?role=OTHER'], ['GET', root + '?q=anything'], ['GET', root + '?limit=201'],
    ['GET', root + '?party_id=nope'], ['GET', root + '?status=PENDING&status=WITHDRAWN'], ['POST', root], ['DELETE', root],
    ['GET', `${root}/${held(1).id}`], ['GET', `${root}/${held(1).id}/withdraw`], ['POST', `${root}/${held(1).id}/withdraw?x=1`],
    ['POST', `${root}/not-an-id/withdraw`], ['PUT', `${root}/${held(1).id}/withdraw`],
  ])('rejects %s %s', (method, path) => expect(allow('accounting', method!, path!)).toBe(false));
  it('is accounting-only', () => expect(allow('catalog', 'GET', root)).toBe(false));
});
