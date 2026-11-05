import { describe, expect, it } from 'vitest';
import { newVoucherHref } from '../app/lib/operate-navigation';

const typeId = '10000000-0000-7000-8000-000000000002';
const salesList = '/operate/income/sales/sales';
const purchaseList = '/operate/expense/purchase/purchase?type_id=' + typeId;
const encoded = (value: string) => encodeURIComponent(value);

describe('newVoucherHref', () => {
  it('sends Sales and Purchase to their one entry screen', () => {
    expect(newVoucherHref('SALES')).toBe('/vouchers/new/sales');
    expect(newVoucherHref('PURCHASE')).toBe('/vouchers/new/purchase');
  });

  it('carries the exact type and a known Operate list as the way back', () => {
    expect(newVoucherHref('PURCHASE', typeId, purchaseList)).toBe('/vouchers/new/purchase?type_id=' + typeId + '&returnTo=' + encoded(purchaseList));
    expect(newVoucherHref('SALES', undefined, salesList)).toBe('/vouchers/new/sales?returnTo=' + encoded(salesList));
  });

  it('leaves the other kinds on the generic selection route, with kind and type in the query', () => {
    expect(newVoucherHref('RECEIPT')).toBe('/vouchers/entry?kind=RECEIPT');
    expect(newVoucherHref('PAYMENT', typeId)).toBe('/vouchers/entry?kind=PAYMENT&type_id=' + typeId);
    expect(newVoucherHref(undefined)).toBe('/vouchers/entry');
  });

  it.each(['https://evil.example/', '//evil.example', '/vouchers', '/operate/../admin', 'javascript:alert(1)', '/operate/expense/nowhere'])('never carries the unsafe back target %j', returnTo => {
    expect(newVoucherHref('PURCHASE', typeId, returnTo)).toBe('/vouchers/new/purchase?type_id=' + typeId);
    expect(newVoucherHref('JOURNAL', undefined, returnTo)).toBe('/vouchers/entry?kind=JOURNAL');
  });
});
