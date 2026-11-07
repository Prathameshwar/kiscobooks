import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanGstin, defaultExpenseGroup, expenseAccountRequest, loadExpenseGroups, suggestCode, supplierRequest, type ExpenseGroup, type SupplierDraft } from '../app/lib/purchase-quick-create';
import { serviceCall } from '../app/lib/service-call';

vi.mock('../app/lib/service-call', async original => ({ ...await original<object>(), serviceCall: vi.fn() }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1);
const groups: ExpenseGroup[] = [{ id: id(20), name: 'Direct Expenses', head: 'Expenses' }, { id: id(21), name: 'Indirect Expenses', head: 'Expenses' }];
const supplier: SupplierDraft = { name: 'Sharma & Sons Traders', code: 'SHARMA', countryCode: 'IN', gstStatus: 'NONE', stateCode: '', gstin: '' };
const withTax = { tax: true }, withoutTax = { tax: false };
const GSTIN = '27ABCDE1234F1Z5';
const account = { name: 'Office rent', code: 'OFFICE-RENT', groupId: id(21), description: '' };
beforeEach(() => { vi.mocked(serviceCall).mockReset(); });

describe('suggestCode', () => {
  it.each([
    ['Sharma & Sons Traders', 'SHARMA-SONS-TRADERS'],
    ['  office  rent ', 'OFFICE-RENT'],
    ['Café Déjà Vu', 'CAFE-DEJA-VU'],
    ['---', ''],
    ['', ''],
    ['A very long supplier name that goes on', 'A-VERY-LONG-SUPPLIER-NAM'],
  ])('turns %j into %j', (name, code) => expect(suggestCode(name)).toBe(code));
  it('keeps a numeric suffix when a long name is truncated', () => {
    expect(suggestCode('Purchase test supplier 1234567')).toBe('PURCHASE-TEST-SU-1234567');
    expect(suggestCode('Purchase test supplier 7654321')).toBe('PURCHASE-TEST-SU-7654321');
  });

  it('never leaves a dangling separator when it cuts a long name', () => {
    expect(suggestCode('abcdefghijklmnopqrstuvw xyz')).toBe('ABCDEFGHIJKLMNOPQRSTUVW');
    expect(suggestCode('abcdefghijklmnopqrstuvw-xyz', 24)).toBe('ABCDEFGHIJKLMNOPQRSTUVW');
  });
});

describe('supplierRequest', () => {
  it('asks for the supplier, its role and its payable account in one body, trimmed, with the name as the legal name', () => {
    const { body, errors } = supplierRequest({ ...supplier, name: '  Sharma & Sons Traders ', code: ' SHARMA ' }, withTax);
    expect(errors).toEqual({});
    expect(body).toEqual({ code: 'SHARMA', name: 'Sharma & Sons Traders', legal_name: 'Sharma & Sons Traders', party_type: 'ORGANISATION', country_code: 'IN', role: 'SUPPLIER', ledger: {} });
  });

  it('names every missing field and builds no body', () => {
    const { body, errors } = supplierRequest({ ...supplier, name: ' ', code: '', countryCode: '' }, withTax);
    expect(body).toBeUndefined();
      expect(Object.keys(errors).sort()).toEqual(['country_code', 'name']);
  });

  it.each([
    ['name', { name: 'x'.repeat(161) }, 'name'],
    ['code', { code: 'x'.repeat(41) }, 'code'],
    ['name with a control character', { name: 'bad\u0007name' }, 'name'],
    ['country that is not an ISO code', { countryCode: 'india' }, 'country_code'],
  ])('rejects a %s the service would refuse', (_what, patch, key) => {
    const { body, errors } = supplierRequest({ ...supplier, ...patch }, withTax);
    expect(body).toBeUndefined();
    expect(errors[key]).toBeTruthy();
  });

  it('accepts the limits exactly', () => {
    expect(supplierRequest({ ...supplier, name: 'x'.repeat(160), code: 'z'.repeat(40) }, withTax).body).toBeDefined();
  });

  describe('GST registration', () => {
    const regular = { ...supplier, gstStatus: 'REGULAR' as const, stateCode: 'MH', gstin: GSTIN };

    it('sends a regular registration with the state and the GSTIN, in the same command', () => {
      expect(supplierRequest(regular, withTax).body?.tax_registration).toEqual({ scheme: 'GST_IN', registration_type: 'REGULAR', country_code: 'IN', state_code: 'MH', registration_number: GSTIN });
    });

    it('sends a composition registration the same way', () => {
      expect(supplierRequest({ ...regular, gstStatus: 'COMPOSITION' }, withTax).body?.tax_registration).toMatchObject({ registration_type: 'COMPOSITION', registration_number: GSTIN, state_code: 'MH' });
    });

    it('records an unregistered supplier by its state alone, never with a number', () => {
      const registration = supplierRequest({ ...regular, gstStatus: 'UNREGISTERED' }, withTax).body?.tax_registration;
      expect(registration).toEqual({ scheme: 'GST_IN', registration_type: 'UNREGISTERED', country_code: 'IN', state_code: 'MH' });
      expect(registration).not.toHaveProperty('registration_number');
    });

    it('stores the GSTIN as Accounting does: capitals, no spaces or hyphens', () => {
      expect(supplierRequest({ ...regular, gstin: ' 27abcde-1234 f1z5 ' }, withTax).body?.tax_registration?.registration_number).toBe(GSTIN);
      expect(cleanGstin('27 abcde-1234f1z5')).toBe(GSTIN);
    });

    it('needs a state, because GST is charged by state', () => {
      const { body, errors } = supplierRequest({ ...regular, stateCode: '' }, withTax);
      expect(body).toBeUndefined();
      expect(errors.state_code).toBeTruthy();
      expect(supplierRequest({ ...regular, gstStatus: 'UNREGISTERED', stateCode: ' ' }, withTax).errors.state_code).toBeTruthy();
    });

    it.each([['nothing', ''], ['too short', '27ABCDE1234F1Z'], ['too long', GSTIN + '5'], ['a symbol', '27ABCDE1234F1Z!']])('needs a GSTIN of 15 letters and digits for a regular supplier, not %s', (_what, gstin) => {
      const { body, errors } = supplierRequest({ ...regular, gstin }, withTax);
      expect(body).toBeUndefined();
      expect(errors.registration_number).toBeTruthy();
    });

    it('does not ask an unregistered supplier for a GSTIN it must not have', () => {
      expect(supplierRequest({ ...regular, gstStatus: 'UNREGISTERED', gstin: '' }, withTax).errors).toEqual({});
    });

    it('sends no registration when the person will add it later, whatever is typed in the hidden fields', () => {
      expect(supplierRequest({ ...regular, gstStatus: 'NONE' }, withTax).body).not.toHaveProperty('tax_registration');
      expect(supplierRequest({ ...regular, gstStatus: 'NONE', stateCode: '', gstin: '' }, withTax).errors).toEqual({});
    });

    it('sends none for a supplier outside India, which GST does not describe', () => {
      expect(supplierRequest({ ...regular, countryCode: 'US', stateCode: '', gstin: '' }, withTax)).toMatchObject({ errors: {}, body: { country_code: 'US' } });
      expect(supplierRequest({ ...regular, countryCode: 'US' }, withTax).body).not.toHaveProperty('tax_registration');
    });

    it('sends none, and asks for none, when the actor cannot record registrations', () => {
      expect(supplierRequest(regular, withoutTax).body).not.toHaveProperty('tax_registration');
      expect(supplierRequest({ ...regular, stateCode: '', gstin: '' }, withoutTax).errors).toEqual({});
    });
  });
});

describe('expenseAccountRequest', () => {
  it('asks for exactly what an account bill accepts: general, postable, not stock, in the company currency', () => {
    expect(expenseAccountRequest(account, groups)).toEqual({ errors: {}, body: {
      code: 'OFFICE-RENT', name: 'Office rent', group_id: id(21), kind: 'GENERAL', currency_mode: 'BASE', posting_policy: 'MANUAL_ALLOWED', inventory_affected: false } });
  });

  it('adds the description only when there is one', () => {
    expect(expenseAccountRequest({ ...account, description: '  Monthly office rent ' }, groups).body?.description).toBe('Monthly office rent');
    expect(expenseAccountRequest(account, groups).body).not.toHaveProperty('description');
  });

  it('accepts a multi-line description, and refuses other control characters in it', () => {
    expect(expenseAccountRequest({ ...account, description: 'Line one\nline two' }, groups).errors).toEqual({});
    expect(expenseAccountRequest({ ...account, description: 'bad\u0007' }, groups).errors.description).toBeTruthy();
    expect(expenseAccountRequest({ ...account, description: 'x'.repeat(501) }, groups).errors.description).toBeTruthy();
  });

  it('refuses a group that was not offered, however the id got there', () => {
    expect(expenseAccountRequest({ ...account, groupId: '' }, groups).errors.group_id).toBeTruthy();
    expect(expenseAccountRequest({ ...account, groupId: id(99) }, groups)).toEqual({ errors: { group_id: expect.any(String) } });
  });

  it('names each missing field', () => {
      expect(Object.keys(expenseAccountRequest({ name: '', code: '', groupId: '', description: '' }, groups).errors).sort()).toEqual(['group_id', 'name']);
  });
});

describe('defaultExpenseGroup', () => {
  it('prefers Indirect Expenses, which is where service and overhead bills belong', () => {
    expect(defaultExpenseGroup(groups)).toBe(id(21));
    expect(defaultExpenseGroup([{ ...groups[1]!, name: ' indirect expense ' }, groups[0]!])).toBe(id(21));
  });
  it('takes a lone group, and otherwise leaves the choice to the person', () => {
    expect(defaultExpenseGroup([groups[0]!])).toBe(id(20));
    expect(defaultExpenseGroup([groups[0]!, { id: id(22), name: 'Marketing', head: 'Expenses' }])).toBe('');
    expect(defaultExpenseGroup([])).toBe('');
  });
});

describe('loadExpenseGroups', () => {
  const head = (n: number, nature: string, name = 'Head ' + n) => ({ id: id(n), company_id: company, name, nature });
  const group = (n: number, headId: number, name: string) => ({ id: id(n), company_id: company, name, head_id: id(headId) });
  const page = (items: unknown[], next: string | null = null) => ({ items, page: { next_cursor: next, has_more: !!next } });
  // As the real API answers: a head's list row is lean (no nature); its own read has the nature.
  function serve(heads: { id: string }[], grouped: unknown[]) {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (request.path.includes('/account-heads?')) return page(heads.map(({ id: rowId, ...row }) => ({ id: rowId, company_id: company, name: (row as { name?: string }).name }))) as never;
      const detail = heads.find(row => request.path.endsWith('/account-heads/' + row.id));
      if (detail) return detail as never;
      return page(grouped) as never;
    });
  }

  it('lists only active groups whose head is an expense head, A to Z', async () => {
    serve([head(10, 'EXPENSE', 'Expenses'), head(11, 'INCOME'), head(12, 'ASSET')],
      [group(21, 10, 'Marketing'), group(22, 11, 'Sales Accounts'), group(23, 10, 'Admin'), group(24, 12, 'Current Assets')]);
    expect(await loadExpenseGroups(company)).toEqual([{ id: id(23), name: 'Admin', head: 'Expenses' }, { id: id(21), name: 'Marketing', head: 'Expenses' }]);
  });

  it('asks for the company’s heads (which have no status to filter on) and its active groups, 200 at a time', async () => {
    serve([head(10, 'EXPENSE')], []);
    await loadExpenseGroups(company);
    const paths = vi.mocked(serviceCall).mock.calls.map(call => call[1].path);
    expect(paths).toHaveLength(3);
    expect(paths).toEqual(expect.arrayContaining([`/v1/companies/${company}/account-heads?limit=200`, `/v1/companies/${company}/account-heads/${id(10)}`, `/v1/companies/${company}/account-groups?status=ACTIVE&limit=200`]));
    expect(vi.mocked(serviceCall).mock.calls.every(call => call[1].service === 'accounting' && (call[1].method ?? 'GET') === 'GET')).toBe(true);
  });

  it('follows the cursor to the next page, and stops after three', async () => {
    let served = 0;
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (request.path.includes('/account-heads?')) return page([{ id: id(10), company_id: company }]) as never;
      if (request.path.endsWith('/account-heads/' + id(10))) return head(10, 'EXPENSE') as never;
      served += 1;
      return page([group(30 + served, 10, 'Group ' + served)], 'next-' + served) as never;
    });
    const found = await loadExpenseGroups(company);
    expect(found.map(row => row.name)).toEqual(['Group 1', 'Group 2', 'Group 3']);
    expect(vi.mocked(serviceCall).mock.calls.filter(call => call[1].path.includes('/account-groups?'))).toHaveLength(3);
    expect(vi.mocked(serviceCall).mock.calls.at(-1)![1].path).toContain('cursor=next-2');
  });

  it('refuses a row from another company or with a malformed id rather than offering it', async () => {
    serve([head(10, 'EXPENSE')], [{ ...group(21, 10, 'Foreign'), company_id: id(2) }]);
    await expect(loadExpenseGroups(company)).rejects.toMatchObject({ status: 502 });
    serve([head(10, 'EXPENSE')], [{ ...group(21, 10, 'Bad'), id: 'not-an-id' }]);
    await expect(loadExpenseGroups(company)).rejects.toMatchObject({ status: 502 });
  });

  it('refuses a head read that answers for another head or another company', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (request.path.includes('/account-heads?')) return page([{ id: id(10), company_id: company }]) as never;
      if (request.path.includes('/account-heads/')) return head(11, 'EXPENSE') as never;
      return page([]) as never;
    });
    await expect(loadExpenseGroups(company)).rejects.toMatchObject({ status: 502 });
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (request.path.includes('/account-heads?')) return page([{ id: id(10), company_id: company }]) as never;
      if (request.path.includes('/account-heads/')) return { ...head(10, 'EXPENSE'), company_id: id(2) } as never;
      return page([]) as never;
    });
    await expect(loadExpenseGroups(company)).rejects.toMatchObject({ status: 502 });
  });

  it('does not take a head’s nature from its list row, which does not carry one', async () => {
    serve([head(10, 'INCOME')], [group(21, 10, 'Sales Accounts')]);
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      if (request.path.includes('/account-heads?')) return page([{ id: id(10), company_id: company, name: 'Income', nature: 'EXPENSE' }]) as never;
      if (request.path.includes('/account-heads/')) return head(10, 'INCOME') as never;
      return page([group(21, 10, 'Sales Accounts')]) as never;
    });
    expect(await loadExpenseGroups(company)).toEqual([]);
  });

  it('passes a service failure through for the drawer to show', async () => {
    vi.mocked(serviceCall).mockRejectedValue({ status: 403, message: 'You do not have access to account groups.' });
    await expect(loadExpenseGroups(company)).rejects.toMatchObject({ status: 403 });
  });
});
