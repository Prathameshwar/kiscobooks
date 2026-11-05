import { describe, expect, it } from 'vitest';
import { allowedProductRequest } from '../app/lib/product-request-policy';

/**
 * Every request the Purchase page makes, run through the proxy's real allowlist. The page's own
 * tests answer from mocks, so a path the proxy refuses (or a query the service would refuse) passes
 * them and fails for the first real user — which is how a supplier could not be chosen at all.
 */
const C = '10000000-0000-7000-8000-000000000001';
const X = '10000000-0000-7000-8000-000000000002';
const base = `/v1/companies/${C}`;

describe('Accounting reads the Purchase page makes', () => {
  it.each([
    `/parties?status=ACTIVE&limit=50&role=SUPPLIER&q=sharma`,
    `/parties/${X}`,
    `/party-roles?party_id=${X}&role=SUPPLIER&limit=50`,
    `/accounts?status=ACTIVE&limit=50&kind=GENERAL&q=office`,
    `/accounts?status=ACTIVE&limit=50&kind=PARTY&party_id=${X}`,
    `/accounts?kind=PARTY&party_id=${X}&status=ACTIVE&limit=200`,
    // How choosing a supplier finds its payable: the account's own role, so a party that is also a customer is not asked for its receivable.
    `/accounts?kind=PARTY&party_id=${X}&role=SUPPLIER&status=ACTIVE&limit=200`,
    `/accounts?kind=BANK&status=ACTIVE&limit=50`,
    `/accounts?kind=CASH&status=ACTIVE&limit=50&q=main`,
    `/accounts/${X}`,
    `/account-groups/${X}`,
    `/account-heads/${X}`,
    `/open-items?party_id=${X}&role=SUPPLIER&direction=CREDIT&account_id=${X}&limit=50`,
    `/open-items/${X}/balance?as_of=2026-10-31`,
    `/ledger/balance?as_of=2026-10-31&basis=BASE&currency=INR&party_id=${X}&account_id=${X}`,
  ])('allows GET %s', path => expect(allowedProductRequest('accounting', 'GET', base + path)).toBe(true));

  it('allows the ledger balance to be read only: no write, no path beyond it, no other company shape', () => {
    for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) expect(allowedProductRequest('accounting', method, `${base}/ledger/balance?as_of=2026-10-31`)).toBe(false);
    expect(allowedProductRequest('accounting', 'GET', `${base}/ledger/balance/extra`)).toBe(false);
    expect(allowedProductRequest('accounting', 'GET', `${base}/ledger/balances`)).toBe(false);
    expect(allowedProductRequest('accounting', 'GET', `/v1/companies/not-an-id/ledger/balance`)).toBe(false);
    expect(allowedProductRequest('catalog', 'GET', `${base}/ledger/balance?as_of=2026-10-31`)).toBe(false);
  });

  it('does not allow the balance of an open item to be written, or paths beyond it', () => {
    for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) expect(allowedProductRequest('accounting', method, `${base}/open-items/${X}/balance`)).toBe(false);
    expect(allowedProductRequest('accounting', 'GET', `${base}/open-items/${X}/balance/extra`)).toBe(false);
    expect(allowedProductRequest('accounting', 'GET', `${base}/open-items/not-an-id/balance`)).toBe(false);
  });

  it('refuses a party_role filter on accounts, which the service does not have either', () => {
    expect(allowedProductRequest('accounting', 'GET', `${base}/accounts?kind=PARTY&party_id=${X}&party_role=SUPPLIER&status=ACTIVE&limit=200`)).toBe(false);
  });
});

describe('Vouchers requests the Purchase page makes', () => {
  it.each([
    ['GET', `/voucher-types?kind=PURCHASE&status=ACTIVE&limit=200`],
    ['GET', `/voucher-capabilities`],
    ['GET', `/voucher-types/${X}/field-set?date=2026-10-31&posting_date=2026-10-31`],
    ['GET', `/vouchers/${X}/field-set?revision_id=${X}`],
    ['GET', `/vouchers/duplicate-bills?party_id=${X}&bill_reference=SOS/26-27/0418&document_date=2026-10-31&exclude_voucher_id=${X}`],
    ['GET', `/vouchers?kind=PURCHASE&status=DRAFT&limit=25`],
    ['GET', `/vouchers?kind=PURCHASE&status=DRAFT&limit=25&cursor=abc`],
    ['POST', `/vouchers`],
    ['PUT', `/vouchers/${X}`],
    ['GET', `/vouchers/${X}`],
    ['GET', `/vouchers/${X}/history?limit=50`],
    ['GET', `/vouchers/${X}/revisions/${X}`],
    ['POST', `/vouchers/${X}/invoice-preview`],
    ['POST', `/vouchers/${X}/invoice-acceptance`],
    ['POST', `/vouchers/${X}/submit`],
    ['POST', `/vouchers/${X}/approve`],
    ['POST', `/vouchers/${X}/reject`],
    ['POST', `/vouchers/${X}/cancel`],
    ['POST', `/vouchers/${X}/post`],
    ['GET', `/voucher-operations/${X}`],
    ['POST', `/voucher-operations/${X}/recover`],
  ])('allows %s %s', (method, path) => expect(allowedProductRequest('vouchers', method!, base + path!)).toBe(true));

  it('lets the designer read what each printer prints, and nothing else', () => {
    expect(allowedProductRequest('vouchers', 'GET', base + '/print-capabilities')).toBe(true);
    expect(allowedProductRequest('vouchers', 'GET', base + '/print-capabilities?kind=PURCHASE')).toBe(false);
    for (const method of ['POST', 'PUT', 'DELETE']) expect(allowedProductRequest('vouchers', method, base + '/print-capabilities')).toBe(false);
  });

  it('lets the duplicate bill check be read and nothing else be done to it', () => {
    for (const method of ['POST', 'PUT', 'DELETE']) expect(allowedProductRequest('vouchers', method, base + '/vouchers/duplicate-bills?party_id=' + X)).toBe(false);
    expect(allowedProductRequest('vouchers', 'GET', base + '/vouchers/duplicate-bills/extra')).toBe(false);
  });
});
