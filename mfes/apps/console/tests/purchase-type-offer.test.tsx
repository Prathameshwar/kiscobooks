import { screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseEntryConnected } from '../app/components/PurchaseEntryConnected';
import { offeredPurchaseTypes } from '../app/lib/voucher-types';
import { serviceCall } from '../app/lib/service-call';
import { renderWithProviders } from './helpers';

/*
 * Which Purchase types the entry screen offers. Company provisioning creates the specific bill types
 * (account, product, mixed); a hand-made catch-all "Purchase voucher" does the account bill's job, so
 * the New → Purchase chooser must not list it beside them — Operate already doesn't.
 */
vi.mock('../app/lib/service-call', async original => ({ ...await original<object>(), serviceCall: vi.fn() }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1);
const type = (n: number, name: string) => ({ id: id(n), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', status: 'ACTIVE', name });
const props = { company, currency: 'INR', actor: id(12), year: id(13), canCreate: true, permissions: ['vouchers.read', 'vouchers.create'] };

function serve(items: ReturnType<typeof type>[]) {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('/voucher-types?')) return { items, page: { next_cursor: null } };
    if (request.path.endsWith('/voucher-capabilities')) return { financial_execution: false, invoice_execution: false, kinds: [{ kind: 'PURCHASE', execution_ready: false }] };
    // the workspace itself is not under test: stop at the field set and let the screen show its setup state
    if (request.path.includes('/field-set')) throw { status: 409, message: 'stopped at the field set' };
    throw { status: 404, message: 'unexpected ' + request.path };
  });
}
const requested = (fragment: string) => vi.mocked(serviceCall).mock.calls.some(call => call[1].path.includes(fragment));
// braces: a beforeEach that *returns* the mock would be run by vitest as a cleanup hook
beforeEach(() => { vi.mocked(serviceCall).mockReset(); });

describe('offeredPurchaseTypes', () => {
  const generic = ['Purchase voucher', 'purchase vouchers', 'All Purchase vouchers', '  Purchase   voucher  '];
  it.each(generic)('drops the catch-all %j when a specific type remains', name => {
    const specific = type(3, 'Purchase - Account Bill');
    expect(offeredPurchaseTypes([type(2, name), specific])).toEqual([specific]);
  });

  it('keeps the catch-all when it is the only type, so a company is never locked out of Purchase', () => {
    const only = type(2, 'Purchase voucher');
    expect(offeredPurchaseTypes([only])).toEqual([only]);
  });

  it('keeps every specific type, in order, and does not match names that merely contain the words', () => {
    const types = [type(2, 'Purchase - Account Bill'), type(3, 'Purchase vouchers (imports)'), type(4, 'Purchase - Product Bill'), type(5, 'Mixed Purchase voucher')];
    expect(offeredPurchaseTypes(types)).toEqual(types);
  });

  it('does not invent types from nothing, and tolerates a type with no name', () => {
    expect(offeredPurchaseTypes([])).toEqual([]);
    const unnamed = { id: id(9), name: null };
    expect(offeredPurchaseTypes([unnamed, type(2, 'Purchase voucher')])).toEqual([unnamed]);
  });
});

describe('the New → Purchase chooser', () => {
  it('lists only the specific bill types when the company also has the catch-all', async () => {
    serve([type(2, 'Purchase voucher'), type(3, 'Purchase - Account Bill'), type(4, 'Purchase - Product Bill'), type(5, 'Purchase - Mixed Bill')]);
    await renderWithProviders(<PurchaseEntryConnected {...props} />);
    const chooser = await screen.findByRole('combobox', { name: 'Purchase voucher type' });
    expect(within(chooser).getAllByRole('option').map(option => option.textContent)).toEqual(['Choose a Purchase type', 'Purchase - Account Bill', 'Purchase - Product Bill', 'Purchase - Mixed Bill']);
  });

  it('opens the lone specific type without asking, instead of offering it beside the catch-all', async () => {
    serve([type(2, 'Purchase voucher'), type(3, 'Purchase - Account Bill')]);
    await renderWithProviders(<PurchaseEntryConnected {...props} />);
    await waitFor(() => expect(requested('/voucher-types/' + id(3) + '/field-set')).toBe(true));
    expect(requested('/voucher-types/' + id(2) + '/field-set')).toBe(false);
  });

  it('still lets a company whose only type is the catch-all raise a bill', async () => {
    serve([type(2, 'Purchase voucher')]);
    await renderWithProviders(<PurchaseEntryConnected {...props} />);
    await waitFor(() => expect(requested('/voucher-types/' + id(2) + '/field-set')).toBe(true));
  });

  it('opens a type named in the link even when it is the catch-all, exactly as asked', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (request.path.endsWith('/voucher-types/' + id(2))) return type(2, 'Purchase voucher');
      if (request.path.endsWith('/voucher-capabilities')) return { financial_execution: false, invoice_execution: false, kinds: [{ kind: 'PURCHASE', execution_ready: false }] };
      if (request.path.includes('/field-set')) throw { status: 409, message: 'stopped at the field set' };
      throw { status: 404, message: 'unexpected ' + request.path };
    });
    await renderWithProviders(<PurchaseEntryConnected {...props} initialTypeId={id(2)} />);
    await waitFor(() => expect(requested('/voucher-types/' + id(2) + '/field-set')).toBe(true));
  });

  it('renders the navigation it is given above the setup state', async () => {
    serve([type(3, 'Purchase - Account Bill'), type(4, 'Purchase - Product Bill')]);
    await renderWithProviders(<PurchaseEntryConnected {...props} navigation={<a href="/operate/expense/purchase/purchase">Back to voucher list</a>} />);
    expect(await screen.findByRole('combobox', { name: 'Purchase voucher type' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Back to voucher list' })).toHaveAttribute('href', '/operate/expense/purchase/purchase');
  });
});
