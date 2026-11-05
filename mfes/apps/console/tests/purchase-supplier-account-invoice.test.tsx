import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseInvoice } from '../app/components/PurchaseInvoice';
import { productFieldRequest } from '../app/lib/product-fields';
import { initialPurchase, type PurchaseDraft } from '../app/lib/purchase-entry';
import { payableCountIssue } from '../app/lib/purchase-workspace';
import { company, draft as saved, metadata } from './purchase-entry-fixtures';

/**
 * The generic account-purchase form never asks for the supplier's payable account either: choosing the supplier resolves it.
 * Exactly one sets it; none or several set nothing and say why; changing or clearing the supplier clears it first.
 */
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
// The lookup is a plain input that reports what is typed as the chosen id, and it shows its error the way the real one does.
vi.mock('@janso/ui', async original => ({ ...await original<typeof import('@janso/ui')>(), SearchSelect: ({ label, disabled, value, error, onChange }: { label: string; disabled?: boolean; value: string | null; error?: string; onChange: (value: string | null) => void }) =>
  <><input aria-label={label} aria-invalid={error ? 'true' : undefined} disabled={disabled} value={value ?? ''} onChange={event => onChange(event.target.value || null)} />{error ? <span role="alert">{error}</span> : null}</> }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const A = id(10), B = id(11), C = id(12), A_PAYABLE = id(30), B_PAYABLE_1 = id(31), B_PAYABLE_2 = id(32), C_PAYABLE = id(33);
/** The accounts each supplier has; `gate` holds the read of supplier B's party record open. */
const accountsOf: Record<string, string[]> = { [A]: [A_PAYABLE], [B]: [B_PAYABLE_1, B_PAYABLE_2], [C]: [] };
let gate: Promise<void> | undefined;
function accounting(overrides: Record<string, string[]> = {}) {
  const held = { ...accountsOf, ...overrides };
  vi.mocked(productFieldRequest).mockImplementation((async (_service: string, _method: string, path: string) => {
    const party = Object.keys(held).find(supplier => path.includes('/parties/' + supplier) || path.includes('party_id=' + supplier));
    if (path.includes('/party-roles?')) return { items: [{ id: id(90), company_id: company, party_id: party, role: 'SUPPLIER', status: 'ACTIVE' }], page: { next_cursor: null } };
    if (path.includes('/parties/')) { if (party === B) await gate; return { id: party, company_id: company, row_version: 5, name: 'Supplier ' + party!.slice(-2), status: 'ACTIVE' }; }
    if (path.includes('/accounts?')) return { items: held[party!]!.map(account => ({ id: account, company_id: company, party_id: party, party_role: 'SUPPLIER' })), page: { next_cursor: null } };
    const account = Object.entries(held).find(([, list]) => list.some(entry => path.endsWith('/accounts/' + entry)));
    if (account) return { id: path.split('/').at(-1), company_id: company, row_version: 6, name: 'Payable ' + path.slice(-2), status: 'ACTIVE', kind: 'PARTY', party_id: account[0], party_role: 'SUPPLIER' };
    throw new Error('Unexpected read ' + path);
  }) as never);
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(productFieldRequest).mockReset(); gate = undefined; accounting(); });

function Form({ start, errors }: { start?: PurchaseDraft; errors?: Record<string, string> }) {
  const [value, setValue] = useState<PurchaseDraft>(start ?? initialPurchase('2026-10-30')), [pending, setPending] = useState(false);
  return <><PurchaseInvoice company={company} currency="INR" metadata={metadata} value={value} onChange={setValue} onPendingChange={setPending} disabled={pending} errors={errors} />
    <output data-testid="capture">{JSON.stringify({ party: value.party?.id ?? null, payable: value.payable?.id ?? null })}</output></>;
}
const captured = () => JSON.parse(screen.getByTestId('capture').textContent!) as { party: string | null; payable: string | null };
const choose = (supplier: string | '') => fireEvent.change(screen.getByLabelText('Supplier'), { target: { value: supplier } });
const settled = () => waitFor(() => expect(screen.queryByText('Verifying purchase reference')).toBeNull());

describe('the account-purchase form’s supplier', () => {
  it('has no payable account control at all', () => {
    render(<Form start={saved} />);
    expect(screen.queryByLabelText(/payable/i)).toBeNull();
    expect(screen.queryByText(/Supplier payable account/)).toBeNull();
    expect(screen.getByLabelText('Supplier')).toBeVisible();
  });

  it('takes the supplier’s one payable account with the supplier, and says nothing', async () => {
    render(<Form />);
    choose(A); await settled();
    expect(captured()).toEqual({ party: A, payable: A_PAYABLE });
    expect(screen.queryByRole('alert')).toBeNull();
    // The accounts were asked for by the supplier role, then each was verified by id.
    expect(vi.mocked(productFieldRequest).mock.calls.map(call => call[2])).toContain(`/v1/companies/${company}/accounts?kind=PARTY&party_id=${A}&role=SUPPLIER&status=ACTIVE&limit=200`);
    expect(vi.mocked(productFieldRequest).mock.calls.map(call => call[2])).toContain(`/v1/companies/${company}/accounts/${A_PAYABLE}`);
  });

  it('sets no account for a supplier with several, and says why in a notice and on the supplier', async () => {
    render(<Form />);
    choose(B); await settled();
    expect(captured()).toEqual({ party: B, payable: null });
    expect(screen.getAllByText(payableCountIssue(2)!).length).toBeGreaterThan(0);
    expect(screen.getByText(payableCountIssue(2)!)).toBeVisible();
  });

  it('sets no account for a supplier with none, and says why', async () => {
    render(<Form />);
    choose(C); await settled();
    expect(captured()).toEqual({ party: C, payable: null });
    expect(screen.getByText(payableCountIssue(0)!)).toBeVisible();
    expect(screen.getByText('This supplier has no payable account yet, so it cannot be billed. An administrator can add it with the party ledger repair.')).toBeVisible();
  });

  it('clears the earlier supplier’s account at once when another is chosen, before the new one is verified', async () => {
    let release!: () => void; gate = new Promise<void>(resolve => { release = resolve; });
    render(<Form start={saved} />);
    expect(captured().payable).toBe(saved.payable!.id);
    choose(B);
    expect(captured()).toEqual({ party: null, payable: null });
    expect(screen.getByLabelText('Supplier')).toBeDisabled();
    release(); await settled();
    expect(captured()).toEqual({ party: B, payable: null });
  });

  it('takes the new supplier’s account, and drops the notice, when a supplier with one follows one with several', async () => {
    render(<Form />);
    choose(B); await settled();
    expect(screen.getByText(payableCountIssue(2)!)).toBeVisible();
    choose(A); await settled();
    expect(captured()).toEqual({ party: A, payable: A_PAYABLE });
    expect(screen.queryByText(payableCountIssue(2)!)).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('clears the account and any notice when the supplier is cleared', async () => {
    render(<Form />);
    choose(C); await settled();
    expect(screen.getByText(payableCountIssue(0)!)).toBeVisible();
    choose(''); await settled();
    expect(captured()).toEqual({ party: null, payable: null });
    expect(screen.queryByText(payableCountIssue(0)!)).toBeNull();
  });

  it('asks for nothing when a supplier that was chosen is cleared', async () => {
    render(<Form />);
    choose(A); await settled();
    expect(captured()).toEqual({ party: A, payable: A_PAYABLE });
    const reads = vi.mocked(productFieldRequest).mock.calls.length;
    choose(''); await settled();
    expect(captured()).toEqual({ party: null, payable: null });
    expect(vi.mocked(productFieldRequest).mock.calls.length).toBe(reads);
  });

  it('shows the supplier’s error, or the account’s when there is none, on the supplier field', () => {
    const { unmount } = render(<Form errors={{ party: 'Select a verified active supplier.', payable: 'Select this supplier’s active payable account.' }} />);
    expect(screen.getByLabelText('Supplier')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Select a verified active supplier.')).toBeVisible();
    expect(screen.queryByText('Select this supplier’s active payable account.')).toBeNull();
    unmount();
    render(<Form errors={{ payable: 'Select this supplier’s active payable account.' }} />);
    expect(screen.getByText('Select this supplier’s active payable account.')).toBeVisible();
    expect(screen.getByLabelText('Supplier')).toHaveAttribute('aria-invalid', 'true');
  });

  it('keeps the supplier unchosen and says what happened when the account list cannot be verified', async () => {
    vi.mocked(productFieldRequest).mockImplementation((async (_service: string, _method: string, path: string) => {
      if (path.includes('/party-roles?')) return { items: [{ id: id(90), company_id: company, party_id: A, role: 'SUPPLIER', status: 'ACTIVE' }], page: { next_cursor: null } };
      if (path.includes('/parties/')) return { id: A, company_id: company, row_version: 5, name: 'Supplier 10', status: 'ACTIVE' };
      if (path.includes('/accounts?')) return { items: [{ id: A_PAYABLE, company_id: company, party_id: A, party_role: 'CUSTOMER' }], page: { next_cursor: null } };
      throw new Error('Unexpected read ' + path);
    }) as never);
    render(<Form start={saved} />);
    choose(A);
    expect(await screen.findByText('The supplier payable accounts could not be verified.')).toBeVisible();
    expect(captured()).toEqual({ party: null, payable: null });
  });
});
