import { beforeEach, describe, expect, it, vi } from 'vitest';
import { supplierPayables } from '../app/lib/purchase-entry';
import { productFieldRequest } from '../app/lib/product-fields';
import { PURCHASE_DEMO_POLICY, payableCountIssue, purchaseExample, purchaseWorkspaceProblems, purchaseWorkspaceReducer, supplierAccountIssue, type PurchaseSupplier, type PurchaseWorkspacePolicy } from '../app/lib/purchase-workspace';

/**
 * A bill never asks for the supplier's payable account: a supplier has exactly one, and choosing the supplier chooses it
 * (docs/party-ledger-mandatory-plan.md PL-D06). `supplierPayables` is the one read that finds it, and the workspace rules say
 * what to do when older data leaves a supplier with none or with several.
 */
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const COMPANY = id(1), SUPPLIER = id(10), OTHER_SUPPLIER = id(11), PAYABLE = id(14), SECOND = id(15), RECEIVABLE = id(16);
const listPath = `/v1/companies/${COMPANY}/accounts?kind=PARTY&party_id=${SUPPLIER}&role=SUPPLIER&status=ACTIVE&limit=200`;
const read = vi.mocked(productFieldRequest);
type Row = { id: string; company_id?: string; party_role?: string | null; party_id?: string };
const row = (accountId: string, patch: Partial<Row> = {}): Row => ({ id: accountId, company_id: COMPANY, party_id: SUPPLIER, party_role: 'SUPPLIER', ...patch });
const detail = (accountId: string, patch: Record<string, unknown> = {}) => ({ id: accountId, company_id: COMPANY, row_version: 3, name: 'Supplier payable ' + accountId.slice(-2), status: 'ACTIVE', kind: 'PARTY', party_id: SUPPLIER, party_role: 'SUPPLIER', ...patch });
/** What Accounting answers: the supplier's account list, then each account by id. */
function accounting(items: unknown, options: { next?: string | null; details?: Record<string, unknown> } = {}) {
  read.mockImplementation((async (_service: string, _method: string, path: string) => {
    if (path.includes('/accounts?')) return { items, page: { next_cursor: options.next ?? null } };
    const found = path.split('/accounts/')[1];
    if (found && options.details?.[found]) return options.details[found];
    throw new Error('Unexpected read ' + path);
  }) as never);
}
beforeEach(() => { read.mockReset(); });

describe('supplierPayables', () => {
  it('asks for the supplier’s ACTIVE party accounts in the SUPPLIER role with one bounded read, and then reads each account by id', async () => {
    accounting([row(PAYABLE)], { details: { [PAYABLE]: detail(PAYABLE) } });
    const found = await supplierPayables(COMPANY, SUPPLIER);
    expect(read.mock.calls.map(call => [call[0], call[1], call[2]])).toEqual([
      ['accounting', 'GET', listPath],
      ['accounting', 'GET', `/v1/companies/${COMPANY}/accounts/${PAYABLE}`],
    ]);
    // No party_role (not a query parameter), no cursor, no search: exactly the role, the status and the largest page.
    expect(listPath).not.toContain('party_role');
    expect(found).toEqual([{ id: PAYABLE, company: COMPANY, version: 3, label: 'Supplier payable 14', partyId: SUPPLIER }]);
  });

  it('answers nothing, and reads nothing more, for a supplier that has no payable account', async () => {
    accounting([]);
    await expect(supplierPayables(COMPANY, SUPPLIER)).resolves.toEqual([]);
    expect(read).toHaveBeenCalledTimes(1);
  });

  it('answers every account when a supplier has several, and leaves the choice to the caller, which refuses it', async () => {
    accounting([row(PAYABLE), row(SECOND)], { details: { [PAYABLE]: detail(PAYABLE), [SECOND]: detail(SECOND) } });
    const found = await supplierPayables(COMPANY, SUPPLIER);
    expect(found.map(source => source.id)).toEqual([PAYABLE, SECOND]);
    expect(read).toHaveBeenCalledTimes(3);
  });

  it.each([
    ['an account of another company', [row(PAYABLE, { company_id: id(9) })]],
    ['an account whose id is not an identifier', [row('not-a-uuid')]],
    ['an account with no company', [row(PAYABLE, { company_id: undefined })]],
    ['a receivable, which is a customer account and never a payable', [row(RECEIVABLE, { party_role: 'CUSTOMER' })]],
    ['an account of the OTHER role', [row(PAYABLE, { party_role: 'OTHER' })]],
    ['an account that does not say its role', [row(PAYABLE, { party_role: undefined })]],
    ['an account whose role is null', [row(PAYABLE, { party_role: null })]],
    ['a page that mixes the payable with a receivable', [row(PAYABLE), row(RECEIVABLE, { party_role: 'CUSTOMER' })]],
  ])('refuses the whole page when it holds %s, without reading any account', async (_name, items) => {
    accounting(items, { details: { [PAYABLE]: detail(PAYABLE), [RECEIVABLE]: detail(RECEIVABLE, { party_role: 'CUSTOMER' }) } });
    await expect(supplierPayables(COMPANY, SUPPLIER)).rejects.toThrow('The supplier payable accounts could not be verified.');
    expect(read).toHaveBeenCalledTimes(1);
  });

  it('refuses a page that says there is more, since a supplier with that many accounts cannot be told apart', async () => {
    accounting([row(PAYABLE)], { next: 'signed-cursor', details: { [PAYABLE]: detail(PAYABLE) } });
    await expect(supplierPayables(COMPANY, SUPPLIER)).rejects.toThrow('The supplier payable accounts could not be verified.');
    expect(read).toHaveBeenCalledTimes(1);
  });

  it.each([['no items', { page: { next_cursor: null } }], ['items that are not a list', { items: 'x', page: { next_cursor: null } }]])('refuses an answer with %s', async (_name, answer) => {
    read.mockResolvedValue(answer as never);
    await expect(supplierPayables(COMPANY, SUPPLIER)).rejects.toThrow('The supplier payable accounts could not be verified.');
  });

  it.each([
    ['another supplier’s account', detail(PAYABLE, { party_id: OTHER_SUPPLIER })],
    ['a customer account', detail(PAYABLE, { party_role: 'CUSTOMER' })],
    ['an account of another company', detail(PAYABLE, { company_id: id(9) })],
    ['an account that is not active', detail(PAYABLE, { status: 'INACTIVE' })],
    ['an account without a version', detail(PAYABLE, { row_version: 0 })],
  ])('refuses a listed account whose own record is %s', async (_name, account) => {
    accounting([row(PAYABLE)], { details: { [PAYABLE]: account } });
    await expect(supplierPayables(COMPANY, SUPPLIER)).rejects.toThrow();
  });

  it('passes a failed read on, rather than answering as if the supplier had none', async () => {
    read.mockRejectedValue(new Error('Accounting is not available.'));
    await expect(supplierPayables(COMPANY, SUPPLIER)).rejects.toThrow('Accounting is not available.');
  });
});

describe('what a chosen supplier’s payable accounts mean for the bill', () => {
  it('says nothing for exactly one account, and names the problem otherwise', () => {
    expect(payableCountIssue(1)).toBeUndefined();
    expect(payableCountIssue(0)).toBe('This supplier has no payable account yet, so it cannot be billed. An administrator can add it with the party ledger repair.');
    for (const count of [2, 3, 12]) expect(payableCountIssue(count)).toBe('This supplier has more than one payable account, so the bill cannot tell which to use. An administrator should keep one and retire the others.');
  });

  it('asks the chosen supplier, and says nothing before one is chosen', () => {
    const supplier = (count: number): PurchaseSupplier => ({ id: 's', label: 'S', meta: '', payables: Array.from({ length: count }, (_, index) => ({ value: 'p' + index, label: 'P' + index })) });
    expect(supplierAccountIssue(undefined)).toBeUndefined();
    expect(supplierAccountIssue(supplier(1))).toBeUndefined();
    expect(supplierAccountIssue(supplier(0))).toBe(payableCountIssue(0));
    expect(supplierAccountIssue(supplier(2))).toBe(payableCountIssue(2));
  });
});

describe('the workspace problems for a supplier with none, one or several payable accounts', () => {
  const today = '2026-10-31';
  const policyWith = (count: number): PurchaseWorkspacePolicy => ({ ...PURCHASE_DEMO_POLICY, suppliers: [{ id: 'demo-count', label: 'Counted supplier', meta: '', payables: Array.from({ length: count }, (_, index) => ({ value: 'acc-' + index, label: 'Account ' + index })) }] });
  const chosen = (count: number) => { const policy = policyWith(count); return { policy, draft: purchaseWorkspaceReducer(purchaseExample(today), { type: 'supplier', value: 'demo-count', policy }) }; };
  const payableProblems = (count: number) => { const { policy, draft } = chosen(count); return purchaseWorkspaceProblems(draft, policy).filter(problem => problem.field === 'payable'); };

  it('has no payable problem, and the account chosen with the supplier, for exactly one account', () => {
    const { draft } = chosen(1);
    expect(draft.payable).toBe('acc-0');
    expect(payableProblems(1)).toEqual([]);
  });

  it('reports the exact “no payable account” message once, on no line, and chooses nothing', () => {
    expect(chosen(0).draft.payable).toBe('');
    expect(payableProblems(0)).toEqual([{ key: 'header:payable', field: 'payable', message: payableCountIssue(0), lineKey: undefined }]);
    expect(payableProblems(0)[0]!.message).toBe('This supplier has no payable account yet, so it cannot be billed. An administrator can add it with the party ledger repair.');
  });

  it('reports the exact “more than one payable account” message once, and does not guess between them', () => {
    expect(chosen(2).draft.payable).toBe('');
    expect(payableProblems(2)).toEqual([{ key: 'header:payable', field: 'payable', message: payableCountIssue(2), lineKey: undefined }]);
    expect(payableProblems(2)[0]!.message).toBe('This supplier has more than one payable account, so the bill cannot tell which to use. An administrator should keep one and retire the others.');
  });

  it('asks for the supplier first when none is chosen, and not for an account', () => {
    const policy = policyWith(1), draft = { ...chosen(1).draft, supplier: '', payable: '' };
    const problems = purchaseWorkspaceProblems(draft, policy);
    expect(problems.filter(problem => problem.field === 'supplier').map(problem => problem.message)).toEqual(['Choose a supplier.']);
    expect(problems.some(problem => problem.field === 'payable')).toBe(false);
  });

  it('never leaves a supplier with one account without it: a draft that lost its account is told to choose the supplier again', () => {
    const { policy, draft } = chosen(1);
    expect(purchaseWorkspaceProblems({ ...draft, payable: '' }, policy).filter(problem => problem.field === 'payable').map(problem => problem.message))
      .toEqual(['The supplier’s payable account could not be chosen. Choose the supplier again.']);
  });

  it('drops the account when another supplier is chosen, and takes the new supplier’s own', () => {
    const both: PurchaseWorkspacePolicy = { ...PURCHASE_DEMO_POLICY, suppliers: [
      { id: 'a', label: 'A', meta: '', payables: [{ value: 'pa', label: 'PA' }] },
      { id: 'b', label: 'B', meta: '', payables: [{ value: 'pb1', label: 'PB1' }, { value: 'pb2', label: 'PB2' }] },
      { id: 'c', label: 'C', meta: '', payables: [{ value: 'pc', label: 'PC' }] },
    ] };
    const first = purchaseWorkspaceReducer(purchaseExample(today), { type: 'supplier', value: 'a', policy: both });
    expect(first.payable).toBe('pa');
    expect(purchaseWorkspaceReducer(first, { type: 'supplier', value: 'b', policy: both }).payable).toBe('');
    expect(purchaseWorkspaceReducer(first, { type: 'supplier', value: 'c', policy: both }).payable).toBe('pc');
    expect(purchaseWorkspaceReducer(first, { type: 'supplier', value: '', policy: both }).payable).toBe('');
  });
});
