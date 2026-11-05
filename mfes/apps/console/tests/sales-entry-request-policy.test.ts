/**
 * W1: the sales bill page's allowlist. Every call the wiring makes is allowed, and the near
 * misses around it — another method, another service, a walked-off path — are refused.
 */
import { describe, expect, it } from 'vitest';
import { allowedSalesEntryRequest } from '../app/lib/sales-entry-request-policy';
import { allowedVoucherRequest } from '../app/lib/voucher-request-policy';

const COMPANY = '01990000-0000-7000-8000-000000000001';
const ID = '01990000-0000-7000-8000-0000000000aa';
const at = (rest: string) => `/v1/companies/${COMPANY}${rest}`;

describe('what the sales bill page may call', () => {
  const allowed: readonly [string, string, string][] = [
    ['identity', 'GET', at('')],
    ['identity', 'GET', at('/tax-registrations')],
    ['accounting', 'GET', at(`/party-address-uses?party_id=${ID}`)],
    ['accounting', 'GET', at(`/party-credit-policies?party_id=${ID}`)],
    ['accounting', 'GET', at(`/party-tax-registrations?party_id=${ID}`)],
    ['catalog', 'GET', at(`/items/${ID}/unit-bindings?as_of=2026-10-29`)],
    ['catalog', 'GET', at(`/item-unit-bindings/${ID}/revisions?as_of=2026-10-29`)],
    ['vouchers', 'GET', at('/voucher-types?kind=SALES&status=ACTIVE')],
    ['vouchers', 'GET', at(`/voucher-types/${ID}/effective-configuration?date=2026-10-29`)],
    ['vouchers', 'GET', at(`/voucher-types/${ID}/field-set?date=2026-10-29`)],
    ['vouchers', 'GET', at('/voucher-classes?type_revision_id=' + ID)],
    ['vouchers', 'GET', at('/voucher-series')],
    ['vouchers', 'GET', at('/voucher-capabilities')],
    ['vouchers', 'POST', at('/vouchers')],
    ['vouchers', 'GET', at(`/vouchers/${ID}`)],
    ['vouchers', 'PUT', at(`/vouchers/${ID}`)],
    ['vouchers', 'GET', at(`/vouchers/${ID}/history`)],
    ['vouchers', 'POST', at(`/vouchers/${ID}/invoice-preview`)],
    ['vouchers', 'POST', at(`/vouchers/${ID}/invoice-acceptance`)],
    ['vouchers', 'POST', at(`/vouchers/${ID}/submit`)],
    ['vouchers', 'POST', at(`/vouchers/${ID}/approve`)],
    ['accounting', 'GET', at('/parties?role=CUSTOMER&q=nan')],
    ['accounting', 'GET', at(`/parties/${ID}`)],
    ['accounting', 'GET', at(`/accounts?party_id=${ID}&kind=PARTY`)],
    // The customer's receivable: its customer-role account only (`resolveCustomer`).
    ['accounting', 'GET', at(`/accounts?party_id=${ID}&kind=PARTY&role=CUSTOMER&status=ACTIVE&limit=50`)],
    ['accounting', 'GET', at(`/party-addresses?party_id=${ID}`)],
    ['accounting', 'GET', at(`/open-items?party_id=${ID}&direction=CREDIT`)],
    ['accounting', 'GET', at(`/open-items/${ID}/balance`)],
    ['accounting', 'GET', at(`/subledger/ageing?party_id=${ID}`)],
    ['accounting', 'POST', at('/credit/check')],
    ['catalog', 'GET', at('/items?q=rice&sellable=true')],
    ['catalog', 'GET', at('/units')],
    ['catalog', 'GET', at('/price-levels')],
    ['catalog', 'GET', at(`/customer-pricing/effective?party_id=${ID}`)],
    ['catalog', 'GET', at('/tax-reference/hsn-sac?q=1006')],
    ['catalog', 'POST', at('/prices/resolve')],
    ['catalog', 'POST', at('/tax-configurations/resolve')],
  ];
  it.each(allowed)('allows %s %s %s', (service, method, path) => {
    expect(allowedSalesEntryRequest(service, method, path)).toBe(true);
  });

  const refused: readonly [string, string, string, string][] = [
    ['a write the page never makes', 'vouchers', 'DELETE', at(`/vouchers/${ID}`)],
    ['issue — blocked for Sales, and not this page’s', 'vouchers', 'POST', at(`/vouchers/${ID}/issue`)],
    ['posting', 'vouchers', 'POST', at(`/vouchers/${ID}/post`)],
    ['creating a party', 'accounting', 'POST', at('/parties')],
    ['creating a party with its role and ledger account', 'accounting', 'POST', at('/parties/create-with-details')],
    ['creating an account', 'accounting', 'POST', at('/accounts')],
    ['editing an account', 'accounting', 'PUT', at(`/accounts/${ID}`)],
    ['a price write', 'catalog', 'POST', at('/prices')],
    ['the right path on the wrong service', 'catalog', 'GET', at('/parties')],
    ['a service this page has no business with', 'reports', 'GET', at('/report-runs')],
    ['an identity write', 'identity', 'PUT', at('')],
    ['identity beyond the company and its registrations', 'identity', 'GET', at('/users')],
    ['an internal route', 'vouchers', 'POST', '/internal/v1/voucher-invoice-previews'],
    ['a path walked off its prefix', 'vouchers', 'GET', at(`/vouchers/${ID}/../../voucher-types`)],
    ['an encoded slash', 'vouchers', 'GET', at('/voucher-types%2fhidden')],
    ['a company that is not an id', 'vouchers', 'GET', '/v1/companies/all/vouchers'],
    ['a suffix on an allowed route', 'accounting', 'GET', at('/parties/export')],
  ];
  it.each(refused)('refuses %s', (_why, service, method, path) => {
    expect(allowedSalesEntryRequest(service, method, path)).toBe(false);
  });
});

describe('the general voucher workflow', () => {
  it('may calculate and accept an invoice, which the proxy used to refuse', () => {
    // `VoucherWorkflow`'s Preview and Accept buttons called these and got a 422 from the proxy.
    expect(allowedVoucherRequest('POST', at(`/vouchers/${ID}/invoice-preview`))).toBe(true);
    expect(allowedVoucherRequest('POST', at(`/vouchers/${ID}/invoice-acceptance`))).toBe(true);
    expect(allowedVoucherRequest('GET', at(`/vouchers/${ID}/field-set`))).toBe(true);
    expect(allowedVoucherRequest('GET', at(`/vouchers/${ID}/invoice-preview`))).toBe(false);
  });
});
