import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { usePurchaseTaxFacts } from '../app/lib/use-purchase-tax-facts';
import { defaultKey } from '../app/lib/purchase-tax';
import type { ServiceRequest } from '../app/lib/service-call';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), supplier = id(3);
const accountIds = Array.from({ length: 6 }, (_, index) => id(100 + index));

type Fake = { calls: ServiceRequest[]; inFlight: number; peak: number; fail: Set<string>; signals: AbortSignal[] };
let party = supplier;
/** A tiny stand-in for the three services, with a record of how it was asked. */
function fake(): Fake & { read: <T>(request: ServiceRequest) => Promise<T> } {
  const state: Fake = { calls: [], inFlight: 0, peak: 0, fail: new Set(), signals: [] };
  const read = async <T,>(request: ServiceRequest): Promise<T> => {
    state.calls.push(request); if (request.signal) state.signals.push(request.signal);
    // Only a bill's accounts are the reads that must not become a burst; the other two are one request each.
    const counted = request.path.includes('account-tax-defaults');
    if (counted) { state.inFlight += 1; state.peak = Math.max(state.peak, state.inFlight); }
    await new Promise(resolve => setTimeout(resolve, 5));
    if (counted) state.inFlight -= 1;
    const path = request.path;
    for (const key of state.fail) if (path.includes(key)) throw new Error('Could not read ' + key);
    if (request.service === 'identity') return { items: [{ id: id(20), is_primary: true, jurisdiction_code: 'IN-MH', number: '27AAAAA0000A1Z5', tax_system: 'gst_in', valid_from: '2020-04-01', valid_to: null }], page: { next_cursor: null } } as T;
    party = /party_id=([^&]+)/.exec(path)?.[1] ?? party;
    if (path.includes('/party-tax-registrations?')) return { items: [{ id: id(30), company_id: company, party_id: party, scheme: 'GST_IN' }], page: { next_cursor: null } } as T;
    if (path.includes('/party-tax-registrations/')) return { id: id(30), company_id: company, party_id: party, scheme: 'GST_IN', registration_type: 'REGULAR', state_code: 'IN-GJ', registration_number: '24BBBBB1111B1Z6', valid_from: '2019-07-01', valid_to: null } as T;
    // A default's id is its account's with another prefix, so the detail read can say whose it is.
    const account = /account_id=([^&]+)/.exec(path)?.[1] ?? /account-tax-defaults\/(.+)$/.exec(path)![1]!.replace('20000000-', '10000000-');
    if (path.includes('/account-tax-defaults?')) return { items: [{ id: account.replace('10000000-', '20000000-'), company_id: company, account_id: account, direction: 'PURCHASE' }], page: { next_cursor: null } } as T;
    return { id: path.split('/').at(-1), company_id: company, account_id: account, direction: 'PURCHASE', code: '998399', code_system: 'SAC', supply_kind: 'SERVICE', treatment: 'TAXABLE', rcm_applicable: false } as T;
  };
  return Object.assign(state, { read });
}
type Input = Parameters<typeof usePurchaseTaxFacts>[0];
const input = (server: ReturnType<typeof fake>, patch: Partial<Input> = {}): Input => ({ enabled: true, active: true, read: server.read, company, supplier, accounts: [accountIds[0]!], on: '2026-10-30', ...patch });
const run = (server: ReturnType<typeof fake>, patch: Partial<Input> = {}) => renderHook((props: Input) => usePurchaseTaxFacts(props), { initialProps: input(server, patch) });
const paths = (server: Fake, match: RegExp) => server.calls.filter(call => match.test(call.path)).length;

describe('the masters a taxed Purchase bill is checked against', () => {
  it('reads nothing at all for someone who may not read tax masters', async () => {
    const server = fake(); const { result } = run(server, { enabled: false });
    await new Promise(resolve => setTimeout(resolve, 30));
    expect(server.calls).toEqual([]);
    expect(result.current.facts.companies).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('reads only the company’s registrations while the bill is not taxed', async () => {
    const server = fake(); const { result } = run(server, { active: false });
    await waitFor(() => expect(result.current.facts.companies).toHaveLength(1));
    expect(server.calls.map(call => call.service + ' ' + call.path)).toEqual([`identity /v1/companies/${company}/tax-registrations?limit=50`]);
    expect(result.current.loading).toBe(false);
  });

  it('reads the supplier’s registrations and each distinct account’s default once the bill is taxed, and says it is loading until then', async () => {
    const server = fake(); const { result } = run(server, { accounts: [accountIds[0]!, accountIds[1]!, accountIds[0]!, ''] });
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.facts.suppliers.get(supplier)).toEqual([{ id: id(30), type: 'REGULAR', state: 'IN-GJ', number: '24BBBBB1111B1Z6', from: '2019-07-01', to: null }]);
    expect([...result.current.facts.defaults.keys()].sort()).toEqual([defaultKey(accountIds[0]!, '2026-10-30'), defaultKey(accountIds[1]!, '2026-10-30')].sort());
    expect(paths(server, /account-tax-defaults\?/)).toBe(2);
    expect(paths(server, /party-tax-registrations\?/)).toBe(1);
  });

  it('does not read again what it already has', async () => {
    const server = fake(); const { result, rerender } = run(server);
    await waitFor(() => expect(result.current.loading).toBe(false));
    const calls = server.calls.length;
    rerender(input(server)); rerender(input(server, { accounts: [accountIds[0]!] }));
    await new Promise(resolve => setTimeout(resolve, 30));
    expect(server.calls.length).toBe(calls);
  });

  it('reads a defaults again for another date, and the supplier again for another supplier', async () => {
    const server = fake(); const { result, rerender } = run(server);
    await waitFor(() => expect(result.current.loading).toBe(false));
    rerender(input(server, { on: '2026-11-15' }));
    await waitFor(() => expect(result.current.facts.defaults.has(defaultKey(accountIds[0]!, '2026-11-15'))).toBe(true));
    expect(result.current.facts.defaults.has(defaultKey(accountIds[0]!, '2026-10-30'))).toBe(true);
    rerender(input(server, { supplier: id(4) }));
    await waitFor(() => expect(result.current.facts.suppliers.has(id(4))).toBe(true));
  });

  it('does not read a default for a date that is not a date', async () => {
    const server = fake(); const { result } = run(server, { on: 'tomorrow' });
    await waitFor(() => expect(result.current.facts.companies).not.toBeNull());
    await new Promise(resolve => setTimeout(resolve, 30));
    expect(paths(server, /account-tax-defaults/)).toBe(0);
  });

  it('reads a long bill’s accounts a few at a time, never all at once', async () => {
    const server = fake(); const { result } = run(server, { accounts: accountIds });
    await waitFor(() => expect(result.current.facts.defaults.size).toBe(6), { timeout: 3000 });
    expect(paths(server, /account-tax-defaults\?/)).toBe(6);
    // Four accounts at a time, each a list and then a detail read: never more than four of these requests in flight.
    expect(server.peak).toBeGreaterThan(1);
    expect(server.peak).toBeLessThanOrEqual(4);
  });

  describe('when a read fails', () => {
    it('says which, once, and does not retry until it is asked to', async () => {
      const server = fake(); server.fail.add('party-tax-registrations');
      const { result } = run(server);
      await waitFor(() => expect(result.current.failures.supplier).toBe('Could not read party-tax-registrations'));
      const calls = server.calls.length;
      await new Promise(resolve => setTimeout(resolve, 40));
      expect(server.calls.length).toBe(calls);
      // Asked once, not once and again when the failure was recorded.
      expect(paths(server, /party-tax-registrations\?/)).toBe(1);
      expect(result.current.loading).toBe(false);
      // The company’s registrations and the accounts were not affected by the supplier's failure.
      expect(result.current.facts.companies).toHaveLength(1);
    });
    it('reports a failed company read, and an account read, separately', async () => {
      const server = fake(); server.fail.add('tax-registrations?limit'); server.fail.add('account-tax-defaults');
      const { result } = run(server);
      await waitFor(() => expect(result.current.failures).toMatchObject({ companies: expect.stringContaining('tax-registrations'), defaults: expect.stringContaining('account-tax-defaults') }));
      expect(result.current.facts.companies).toBeNull();
    });
    it('reads everything again on reload, and clears the failure', async () => {
      const server = fake(); server.fail.add('party-tax-registrations');
      const { result } = run(server);
      await waitFor(() => expect(result.current.failures.supplier).toBeTruthy());
      server.fail.clear(); server.calls.length = 0;
      act(() => result.current.reload());
      expect(result.current.failures).toEqual({});
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.facts.suppliers.has(supplier)).toBe(true);
      expect(paths(server, /tax-registrations\?limit=50/)).toBe(1);
      expect(paths(server, /account-tax-defaults\?/)).toBe(1);
    });
    it('explains a failure that is not an Error in the words the service gave', async () => {
      const server = fake();
      const read = (async (request: ServiceRequest) => { if (request.service === 'identity') throw { status: 403, message: 'You do not have access to tax registrations.' }; return server.read(request); }) as typeof server.read;
      const { result } = run(server, { read });
      await waitFor(() => expect(result.current.failures.companies).toMatch(/access/i));
    });
  });

  it('stops reading what it no longer needs when the page goes away', async () => {
    const server = fake(); const { unmount } = run(server);
    await waitFor(() => expect(server.calls.length).toBeGreaterThan(0));
    unmount();
    expect(server.signals.length).toBeGreaterThan(0);
    expect(server.signals.every(signal => signal.aborted)).toBe(true);
  });
});

