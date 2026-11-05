import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DuplicateBillModal, DuplicateBillNotice } from '../app/components/PurchaseDuplicateBill';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import { duplicateBillQuery, duplicateBillsFromFields, verifyDuplicateBills, type DuplicateBill } from '../app/lib/purchase-api';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const row = (n: number, over: Partial<DuplicateBill> = {}): DuplicateBill => ({ id: id(n), status: 'POSTED', document_date: '2026-09-12', bill_reference: 'SOS/26-27/0418', revision_number: 3, ...over });
const base = '/v1/companies/' + id(1);

describe('the duplicate bill lookup the page sends', () => {
  const path = duplicateBillQuery(base, { partyId: id(10), billReference: 'SOS/26-27/0418 A', documentDate: '2026-10-31', excludeVoucherId: id(90) });

  it('is a request the proxy allows, with a slash in the reference left readable', () => {
    expect(path).toContain('bill_reference=SOS/26-27/0418+A');
    expect(path).not.toMatch(/%2f/i);
    expect(allowedProductRequest('vouchers', 'GET', path)).toBe(true);
  });

  it('names only parameters the service accepts, and the ledger when it is given', () => {
    expect([...new URL('http://x' + path).searchParams.keys()].sort()).toEqual(['bill_reference', 'document_date', 'exclude_voucher_id', 'party_id']);
    const both = duplicateBillQuery(base, { partyId: id(10), payableId: id(11), billReference: 'X/1', documentDate: '2026-10-31', excludeVoucherId: id(90) });
    expect([...new URL('http://x' + both).searchParams.keys()].sort()).toEqual(['bill_reference', 'document_date', 'exclude_voucher_id', 'party_account_id', 'party_id']);
    const ledgerOnly = duplicateBillQuery(base, { payableId: id(11), billReference: 'X/1', documentDate: '2026-10-31', excludeVoucherId: id(90) });
    expect(ledgerOnly).not.toContain('party_id=');
    expect(ledgerOnly).toContain('party_account_id=' + id(11));
    expect(allowedProductRequest('vouchers', 'GET', ledgerOnly)).toBe(true);
  });

  it('keeps characters that would change the query out of the reference', () => {
    const odd = duplicateBillQuery(base, { partyId: id(10), billReference: 'A&party_id=x#y', documentDate: '2026-10-31', excludeVoucherId: id(90) });
    expect(new URL('http://x' + odd).searchParams.get('bill_reference')).toBe('A&party_id=x#y');
    expect(new URL('http://x' + odd).searchParams.getAll('party_id')).toEqual([id(10)]);
  });
});

describe('the service answers the page reads', () => {
  it('accepts up to five well-formed rows', () => {
    expect(verifyDuplicateBills({ items: [row(1), row(2)] })).toHaveLength(2);
    expect(verifyDuplicateBills({ items: [] })).toEqual([]);
  });

  it.each([
    ['no items', {}], ['null', null], ['six rows', { items: [1, 2, 3, 4, 5, 6].map(n => row(n)) }], ['a bad id', { items: [row(1, { id: 'nope' })] }],
    ['a bad date', { items: [row(1, { document_date: '12/09/2026' })] }], ['a bad status', { items: [row(1, { status: 'posted soon' })] }], ['a zero revision', { items: [row(1, { revision_number: 0 })] }],
  ])('refuses %s', (_name, value) => expect(() => verifyDuplicateBills(value)).toThrow('could not be verified'));

  it('reads the refusal rows out of the flat fields map, and ignores rows that are not whole', () => {
    const fields = { 'matches.0.id': id(1), 'matches.0.status': 'DRAFT', 'matches.0.document_date': '2026-09-12', 'matches.0.bill_reference': 'X/1', 'matches.0.revision_number': '2',
      'matches.1.id': id(2), 'matches.1.status': 'POSTED' };
    expect(duplicateBillsFromFields(fields)).toEqual([{ id: id(1), status: 'DRAFT', document_date: '2026-09-12', bill_reference: 'X/1', revision_number: 2 }]);
    expect(duplicateBillsFromFields(undefined)).toEqual([]);
  });
});

describe('DuplicateBillNotice', () => {
  it('shows nothing when there is no other bill', () => {
    const { container } = render(<DuplicateBillNotice matches={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('names each earlier bill with a link to it, its state and its date', () => {
    render(<DuplicateBillNotice matches={[row(1), row(2, { status: 'DRAFT', bill_reference: 'SOS/26-27/0418 ' })]} />);
    expect(screen.getByText('This supplier invoice number is already recorded')).toBeVisible();
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute('href', '/vouchers/' + id(1));
    expect(screen.getAllByText(/revision 3/)).toHaveLength(2);
    expect(screen.getByText(/Draft/)).toBeVisible();
  });
});

describe('DuplicateBillModal', () => {
  it('is closed until the service has refused a submit', () => {
    render(<DuplicateBillModal matches={null} busy={false} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('asks, and lets the person decline or submit anyway', () => {
    const onCancel = vi.fn(), onConfirm = vi.fn();
    render(<DuplicateBillModal matches={[row(1)]} busy={false} onCancel={onCancel} onConfirm={onConfirm} />);
    expect(screen.getByRole('dialog', { name: 'Submit a possible duplicate bill?' })).toBeVisible();
    expect(screen.getByText(/recorded against your name/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Do not submit' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Submit anyway' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('still asks when the service named no rows (a caller who may not read them)', () => {
    render(<DuplicateBillModal matches={[]} busy={false} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByRole('dialog', { name: 'Submit a possible duplicate bill?' })).toBeVisible();
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('says the check was incomplete, not that a bill exists, when the service could not read every bill', () => {
    render(<DuplicateBillModal matches={[]} incomplete busy={false} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByText(/could not read them all/)).toBeVisible();
    expect(screen.queryByText(/is already recorded for this supplier/)).toBeNull();
  });

  it('still names the bills when some were found and the check was also incomplete', () => {
    render(<DuplicateBillModal matches={[row(1)]} incomplete busy={false} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByText(/is already recorded for this supplier/)).toBeVisible();
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });

  it('cannot be answered twice while a request is running', () => {
    render(<DuplicateBillModal matches={[row(1)]} busy onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Submit anyway' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Do not submit' })).toBeDisabled();
  });
});
