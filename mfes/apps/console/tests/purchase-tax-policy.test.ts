import { describe, expect, it } from 'vitest';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import { loadAccountTaxDefault, loadCompanyGst, loadSupplierGst } from '../app/lib/purchase-tax';
import type { ServiceRequest } from '../app/lib/service-call';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), party = id(3), account = id(7);
const base = `/v1/companies/${company}`;

/**
 * The Purchase page reaches Identity and Accounting through the product proxy, which forwards only the calls it names. These
 * run the loaders themselves against a reader that records what they ask, so the allow-list is checked against the real paths
 * and queries and cannot drift from them: a request the proxy would refuse is a page that reads nothing and says "unavailable".
 */
function asked() {
  const requests: ServiceRequest[] = [];
  const read = async <T,>(request: ServiceRequest): Promise<T> => {
    requests.push(request);
    const path = request.path;
    if (request.service === 'identity') return { items: [], page: { next_cursor: null } } as T;
    if (path.includes('/party-tax-registrations?')) return { items: [{ id: id(30), company_id: company, party_id: party, scheme: 'GST_IN' }], page: { next_cursor: null } } as T;
    if (path.includes('/party-tax-registrations/')) return { id: id(30), company_id: company, party_id: party, scheme: 'GST_IN', registration_type: 'REGULAR', state_code: 'IN-MH' } as T;
    if (path.includes('/account-tax-defaults?')) return { items: [{ id: id(40), company_id: company, account_id: account, direction: 'PURCHASE' }], page: { next_cursor: null } } as T;
    return { id: id(40), company_id: company, account_id: account, direction: 'PURCHASE', treatment: 'TAXABLE', supply_kind: 'SERVICE' } as T;
  };
  return { requests, read };
}

describe('the product proxy and the Purchase page’s GST reads', () => {
  it('forwards the company’s registrations read', async () => {
    const { requests, read } = asked();
    await loadCompanyGst(read, company);
    expect(requests).toHaveLength(1);
    expect(requests.map(request => allowedProductRequest(request.service!, request.method ?? 'GET', request.path))).toEqual([true]);
  });
  it('forwards the supplier’s registration list and each registration', async () => {
    const { requests, read } = asked();
    await loadSupplierGst(read, company, party);
    expect(requests.map(request => request.path)).toEqual([`${base}/party-tax-registrations?party_id=${party}&limit=50`, `${base}/party-tax-registrations/${id(30)}`]);
    expect(requests.map(request => allowedProductRequest(request.service!, request.method ?? 'GET', request.path))).toEqual([true, true]);
  });
  it('forwards an account’s purchase tax default and its detail', async () => {
    const { requests, read } = asked();
    await loadAccountTaxDefault(read, company, account, '2026-10-30');
    expect(requests).toHaveLength(2);
    expect(requests.map(request => allowedProductRequest(request.service!, request.method ?? 'GET', request.path))).toEqual([true, true]);
  });

  it('forwards reads only: nothing the page does here can write a registration or a default', () => {
    for (const [service, path] of [['identity', `${base}/tax-registrations?limit=50`], ['accounting', `${base}/party-tax-registrations?party_id=${party}&limit=50`], ['accounting', `${base}/account-tax-defaults?account_id=${account}&direction=PURCHASE&as_of=2026-10-30&limit=5`]] as const)
      for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) expect(allowedProductRequest(service, method, path), `${method} ${path}`).toBe(false);
  });
  it('refuses a read that has wandered off the company, or onto an encoded path', () => {
    expect(allowedProductRequest('identity', 'GET', `/v1/tax-registrations?limit=50`)).toBe(false);
    expect(allowedProductRequest('identity', 'GET', `${base}/tax-registrations/..%2f..%2fusers`)).toBe(false);
    expect(allowedProductRequest('accounting', 'GET', `${base}/account-tax-defaults?account_id=${account}&direction=PURCHASE&as_of=2026-10-30&limit=5&include=everything`)).toBe(false);
    expect(allowedProductRequest('accounting', 'GET', `${base}/account-tax-defaults?account_id=${account}&account_id=${id(8)}`)).toBe(false);
  });
});
