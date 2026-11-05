import { describe, expect, it, vi } from 'vitest';
import {
  blankPurchaseTax, choiceOfProfile, defaultKey, isTaxed, loadAccountTaxDefault, loadCompanyGst, loadSupplierGst, noTaxFacts, purchaseTaxContext, registrationsInForce,
  resolvePurchaseTax, rowTaxStatus, subdivision, type AccountTaxDefault, type CompanyGst, type PurchaseTaxDraft, type PurchaseTaxFacts, type SupplierGst,
} from '../app/lib/purchase-tax';
import type { ServiceRequest } from '../app/lib/service-call';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), supplier = id(3), account = id(7);
const taxed = (patch: Partial<PurchaseTaxDraft> = {}): PurchaseTaxDraft => ({ ...blankPurchaseTax(), choice: 'FORWARD', ...patch });
const mine: CompanyGst = { id: id(20), number: '27AAAAA0000A1Z5', state: 'IN-MH', primary: true, from: '2020-04-01', to: null };
const other: CompanyGst = { id: id(21), number: '29AAAAA0000A1Z5', state: 'IN-KA', primary: false, from: '2020-04-01', to: null };
const regular: SupplierGst = { id: id(30), type: 'REGULAR', state: 'IN-GJ', number: '24BBBBB1111B1Z6', from: '2019-07-01', to: null };
const facts = (patch: Partial<PurchaseTaxFacts> = {}): PurchaseTaxFacts => ({ ...noTaxFacts(), companies: [mine], suppliers: new Map([[supplier, [regular]]]), ...patch });
const base = { invoiceDate: '2026-10-30', supplier, invoice: 'SUP-42' };
const sac = (patch: Partial<AccountTaxDefault> = {}): AccountTaxDefault => ({ id: id(40), account, code: '998399', codeSystem: 'SAC', supplyKind: 'SERVICE', treatment: 'TAXABLE', reverse: false, ...patch });

describe('state codes', () => {
  it.each([['IN-MH', 'IN-MH'], ['mh', 'IN-MH'], [' in-ka ', 'IN-KA'], ['27', 'IN-27'], ['', ''], [null, ''], ['MAHARASHTRA', ''], ['US-CA', '']])('reads %j as %j', (code, expected) => {
    expect(subdivision(code as string | null)).toBe(expected);
  });
});

describe('choices', () => {
  it('knows a taxed bill from an untaxed or undecided one', () => {
    expect(isTaxed(taxed())).toBe(true);
    expect(isTaxed(taxed({ choice: 'REVERSE' }))).toBe(true);
    expect(isTaxed(taxed({ choice: 'NONE' }))).toBe(false);
    expect(isTaxed(blankPurchaseTax())).toBe(false);
  });
  it('maps a saved profile to its choice, and refuses a profile it does not capture', () => {
    expect(choiceOfProfile('UNTAXED_ACCOUNT')).toBe('NONE');
    expect(choiceOfProfile('INDIA_DOMESTIC_SERVICE')).toBe('FORWARD');
    expect(choiceOfProfile('INDIA_DOMESTIC_SERVICE_RCM')).toBe('REVERSE');
    expect(choiceOfProfile('SOMETHING_ELSE')).toBeNull();
    expect(choiceOfProfile(undefined)).toBeNull();
  });
});

describe('reading the company’s GST registrations', () => {
  const row = (patch: Record<string, unknown> = {}) => ({ id: id(20), is_primary: true, jurisdiction_code: 'IN-MH', number: '27AAAAA0000A1Z5', tax_system: 'gst_in', valid_from: '2020-04-01', valid_to: null, ...patch });
  const reader = (items: unknown) => vi.fn(async () => ({ items, page: { next_cursor: null } })) as unknown as <T>(request: ServiceRequest) => Promise<T>;

  it('reads the company’s own list from Identity and keeps GST registrations, primary first', async () => {
    const read = vi.fn(async (_request: ServiceRequest) => ({ items: [row({ id: id(21), is_primary: false, number: '09AAAAA0000A1Z5', jurisdiction_code: 'UP' }), row(), row({ id: id(22), tax_system: 'vat', jurisdiction_code: 'IN-MH' })], page: { next_cursor: null } }));
    const found = await loadCompanyGst(read as never, company);
    expect(read.mock.calls[0]![0]).toMatchObject({ service: 'identity', path: `/v1/companies/${company}/tax-registrations?limit=50` });
    // The primary comes first even though the other registration's number sorts before it.
    expect(found.map(entry => [entry.id, entry.state, entry.primary])).toEqual([[id(20), 'IN-MH', true], [id(21), 'IN-UP', false]]);
  });
  it('leaves out a registration that has no usable state or start date', async () => {
    expect(await loadCompanyGst(reader([row({ jurisdiction_code: '' }), row({ id: id(23), valid_from: 'soon' })]), company)).toEqual([]);
  });
  it.each([['a row with a malformed id', [row({ id: 'nope' })]], ['a list that is not a list', { nope: true }], ['too many rows', Array.from({ length: 51 }, () => row())]])('refuses %s', async (_name, items) => {
    await expect(loadCompanyGst(reader(items), company)).rejects.toThrow(/could not be verified/);
  });
});

describe('reading a supplier’s GST registrations', () => {
  const listed = (patch: Record<string, unknown> = {}) => ({ id: id(30), company_id: company, party_id: supplier, scheme: 'GST_IN', ...patch });
  const detail = (patch: Record<string, unknown> = {}) => ({ ...listed(), registration_type: 'REGULAR', state_code: 'IN-GJ', registration_number: '24BBBBB1111B1Z6', valid_from: '2019-07-01', valid_to: null, ...patch });
  const serve = (list: unknown[], reads: Record<string, unknown>) => vi.fn(async (request: ServiceRequest) => request.path.includes('?') ? { items: list, page: { next_cursor: null } } : reads[request.path.split('/').at(-1)!]);

  it('lists the supplier’s registrations, then reads each GST one for its type and state', async () => {
    const read = serve([listed(), listed({ id: id(31), scheme: 'VAT' })], { [id(30)]: detail() });
    const found = await loadSupplierGst(read as never, company, supplier);
    expect(found).toEqual([{ id: id(30), type: 'REGULAR', state: 'IN-GJ', number: '24BBBBB1111B1Z6', from: '2019-07-01', to: null }]);
    expect(read.mock.calls.map(call => (call[0] as ServiceRequest).path)).toEqual([
      `/v1/companies/${company}/party-tax-registrations?party_id=${supplier}&limit=50`,
      `/v1/companies/${company}/party-tax-registrations/${id(30)}`,
    ]);
    expect(read.mock.calls.every(call => (call[0] as ServiceRequest).service === 'accounting')).toBe(true);
  });
  it('says there are none when the supplier has none', async () => {
    expect(await loadSupplierGst(serve([], {}) as never, company, supplier)).toEqual([]);
  });
  it.each([
    ['another company', listed({ company_id: id(99) })],
    ['another party', listed({ party_id: id(98) })],
    ['a malformed id', listed({ id: 'nope' })],
  ] as const)('refuses a registration of %s', async (_name, row) => {
    // Its detail is readable and well formed, so only the ownership check can refuse it.
    await expect(loadSupplierGst(serve([row], { [row.id]: detail(row) }) as never, company, supplier)).rejects.toThrow(/could not be verified/);
  });
  it('refuses a detail that is not the registration that was listed', async () => {
    await expect(loadSupplierGst(serve([listed()], { [id(30)]: detail({ id: id(32) }) }) as never, company, supplier)).rejects.toThrow(/could not be verified/);
  });
  it('does not read a dozen registrations one by one', async () => {
    const many = Array.from({ length: 13 }, (_, index) => listed({ id: id(100 + index) }));
    await expect(loadSupplierGst(serve(many, {}) as never, company, supplier)).rejects.toThrow(/too many GST registrations/);
  });
});

describe('reading what an expense account says about purchase tax', () => {
  const listed = (patch: Record<string, unknown> = {}) => ({ id: id(40), company_id: company, account_id: account, direction: 'PURCHASE', ...patch });
  const detail = (patch: Record<string, unknown> = {}) => ({ ...listed(), code: '998399', code_system: 'SAC', supply_kind: 'SERVICE', treatment: 'TAXABLE', rcm_applicable: false, ...patch });
  const serve = (list: unknown[], one: unknown) => vi.fn(async (request: ServiceRequest) => request.path.includes('?') ? { items: list, page: { next_cursor: null } } : one);

  it('asks for the account’s purchase default on the date, and maps the detail', async () => {
    const read = serve([listed()], detail({ rcm_applicable: true }));
    expect(await loadAccountTaxDefault(read as never, company, account, '2026-10-30')).toEqual({ id: id(40), account, code: '998399', codeSystem: 'SAC', supplyKind: 'SERVICE', treatment: 'TAXABLE', reverse: true });
    expect((read.mock.calls[0]![0] as ServiceRequest).path).toBe(`/v1/companies/${company}/account-tax-defaults?account_id=${account}&direction=PURCHASE&as_of=2026-10-30&limit=5`);
    expect((read.mock.calls[1]![0] as ServiceRequest).path).toBe(`/v1/companies/${company}/account-tax-defaults/${id(40)}`);
  });
  it('is null, not an error, when the account says nothing', async () => {
    const read = serve([], null);
    expect(await loadAccountTaxDefault(read as never, company, account, '2026-10-30')).toBeNull();
    expect(read).toHaveBeenCalledTimes(1);
  });
  it('refuses overlapping defaults rather than choosing one', async () => {
    await expect(loadAccountTaxDefault(serve([listed(), listed({ id: id(41) })], detail()) as never, company, account, '2026-10-30')).rejects.toThrow(/overlapping/);
  });
  it.each([
    ['another account', listed({ account_id: id(98) })],
    ['a sale default', listed({ direction: 'SALE' })],
    ['another company', listed({ company_id: id(99) })],
  ])('refuses a default for %s', async (_name, row) => {
    await expect(loadAccountTaxDefault(serve([row], detail()) as never, company, account, '2026-10-30')).rejects.toThrow(/could not be verified/);
  });
  it('refuses a detail that is another record or has no treatment', async () => {
    await expect(loadAccountTaxDefault(serve([listed()], detail({ id: id(42) })) as never, company, account, '2026-10-30')).rejects.toThrow(/could not be verified/);
    await expect(loadAccountTaxDefault(serve([listed()], detail({ treatment: undefined })) as never, company, account, '2026-10-30')).rejects.toThrow(/could not be verified/);
  });
});

describe('resolving how the bill is taxed', () => {
  it('follows the masters for everything the person did not choose', () => {
    const result = resolvePurchaseTax({ tax: taxed(), ...base, facts: facts() });
    expect(result.company).toBe(mine);
    expect(result.place).toBe('IN-MH');
    expect(result.completion).toBe('2026-10-30');
    expect(result.supplier).toEqual({ kind: 'ready', registration: regular });
    expect(result.problems).toEqual([]);
  });
  it('prefers what the person chose', () => {
    const result = resolvePurchaseTax({ tax: taxed({ companyRegistration: other.id, placeOfSupply: 'IN-DL', completionDate: '2026-10-01' }), ...base, facts: facts({ companies: [mine, other] }) });
    expect(result).toMatchObject({ company: other, place: 'IN-DL', completion: '2026-10-01', problems: [] });
  });
  it('offers only the registrations in force on the invoice date', () => {
    const expired: CompanyGst = { ...other, to: '2026-03-31' };
    const future: CompanyGst = { ...other, id: id(22), from: '2027-04-01' };
    const all = facts({ companies: [mine, expired, future] });
    expect(registrationsInForce(all, '2026-10-30')).toEqual([mine]);
    expect(registrationsInForce(all, '2026-03-31')).toEqual([mine, expired]);
    expect(registrationsInForce(noTaxFacts(), '2026-10-30')).toEqual([]);
  });
  it('does not fall back to another registration when the one chosen is not in force', () => {
    const result = resolvePurchaseTax({ tax: taxed({ companyRegistration: id(77) }), ...base, facts: facts() });
    expect(result.company).toBeNull();
    expect(result.problems).toContainEqual({ field: 'companyRegistration', message: 'Choose the GST registration this bill is under.' });
  });
  it('says the company has no registration in force, rather than asking to choose one', () => {
    const result = resolvePurchaseTax({ tax: taxed(), ...base, facts: facts({ companies: [{ ...mine, to: '2026-03-31' }] }) });
    expect(result.problems[0]).toMatchObject({ field: 'companyRegistration', message: expect.stringMatching(/no GST registration in force on the invoice date/) });
  });
  it('waits, and says so, until the company’s registrations have been read', () => {
    expect(resolvePurchaseTax({ tax: taxed(), ...base, facts: noTaxFacts() }).problems[0]).toMatchObject({ field: 'companyRegistration', message: expect.stringMatching(/not been read yet/) });
  });
  it('needs a place of supply in the ISO form, and a real completion date', () => {
    const result = resolvePurchaseTax({ tax: taxed({ placeOfSupply: 'Maharashtra', completionDate: '2026-02-30' }), ...base, facts: facts() });
    expect(result.problems.map(entry => entry.field)).toEqual(['placeOfSupply', 'completionDate']);
  });

  describe('the supplier’s registration', () => {
    const of = (registrations: readonly SupplierGst[] | undefined, tax = taxed(), supplierId = supplier) =>
      resolvePurchaseTax({ tax, ...base, supplier: supplierId, facts: facts({ suppliers: registrations ? new Map([[supplierId, registrations]]) : new Map() }) });
    it('is not asked about before there is a supplier', () => {
      const result = of(undefined, taxed(), '');
      expect(result.supplier).toEqual({ kind: 'unselected' });
      expect(result.problems).toEqual([]);
    });
    it('is unread until it has been read', () => {
      expect(of(undefined).supplier).toEqual({ kind: 'unread' });
      expect(of(undefined).problems[0]).toMatchObject({ field: 'supplierRegistration', message: expect.stringMatching(/not been read yet/) });
    });
    it('is none when the supplier has no GST registration', () => {
      expect(of([]).supplier).toEqual({ kind: 'none' });
      expect(of([]).problems[0]!.message).toMatch(/no GST registration on record/);
    });
    it.each([['COMPOSITION', /composition/], ['UNREGISTERED', /unregistered/], ['OVERSEAS', /overseas/]])('refuses a %s supplier, in words', (type, words) => {
      const result = of([{ ...regular, type }]);
      expect(result.supplier).toEqual({ kind: 'ineligible', type });
      expect(result.problems[0]!.message).toMatch(/only be recorded here for a regular GST supplier/);
      expect(result.problems[0]!.message).toMatch(words);
    });
    it('is ineligible, not ready, when the only regular registration has expired', () => {
      expect(of([{ ...regular, to: '2025-03-31' }]).supplier.kind).toBe('ineligible');
    });
    it('is chosen by the person when there are several regular ones', () => {
      const second: SupplierGst = { ...regular, id: id(31), state: 'IN-KA', number: '29BBBBB1111B1Z6' };
      expect(of([regular, second]).supplier).toEqual({ kind: 'choose', options: [regular, second] });
      expect(of([regular, second]).problems[0]!.field).toBe('supplierRegistration');
      expect(of([regular, second], taxed({ supplierRegistration: second.id })).supplier).toEqual({ kind: 'ready', registration: second });
      expect(of([regular, second], taxed({ supplierRegistration: second.id })).problems).toEqual([]);
    });
    it('keeps offering the choice once one is made, so it can be changed', () => {
      const second: SupplierGst = { ...regular, id: id(31), state: 'IN-KA', number: '29BBBBB1111B1Z6' };
      const chosen = of([regular, second], taxed({ supplierRegistration: second.id }));
      expect(chosen.supplier).toEqual({ kind: 'ready', registration: second });
      expect(chosen.supplierOptions).toEqual([regular, second]);
      // A supplier with one regular registration has nothing to choose.
      expect(of([regular]).supplierOptions).toEqual([regular]);
      expect(of([{ ...regular, type: 'COMPOSITION' }]).supplierOptions).toEqual([]);
      expect(of([]).supplierOptions).toEqual([]);
    });
    it('ignores a chosen registration that is not one of the supplier’s', () => {
      expect(of([regular], taxed({ supplierRegistration: id(99) })).supplier).toEqual({ kind: 'ready', registration: regular });
    });
    it('raises no supplier problem for an untaxed bill, whatever the supplier is', () => {
      expect(of([], { ...blankPurchaseTax(), choice: 'NONE' }).problems).toEqual([]);
    });
  });
});

describe('what an expense account says, against how the bill is taxed', () => {
  it('is pending until it has been read', () => expect(rowTaxStatus('FORWARD', undefined)).toMatchObject({ tone: 'pending' }));
  it('is a problem, with the fix, when the account has no purchase tax default', () => {
    expect(rowTaxStatus('FORWARD', null)).toMatchObject({ tone: 'bad', fix: 'tax-default', text: expect.stringMatching(/no purchase tax default/) });
  });
  it('is a problem when the default is for goods', () => {
    expect(rowTaxStatus('FORWARD', sac({ supplyKind: 'GOODS', codeSystem: 'HSN' }))).toMatchObject({ tone: 'bad', text: expect.stringMatching(/for goods/) });
    expect(rowTaxStatus('FORWARD', sac({ codeSystem: 'HSN' }))).toMatchObject({ tone: 'bad' });
  });
  it('says what to change when the account and the bill disagree about reverse charge', () => {
    expect(rowTaxStatus('FORWARD', sac({ reverse: true }))).toMatchObject({ tone: 'bad', text: expect.stringMatching(/set to reverse charge.*Choose “Reverse charge”/) });
    expect(rowTaxStatus('REVERSE', sac())).toMatchObject({ tone: 'bad', text: expect.stringMatching(/not set to reverse charge.*Choose “Charged by the supplier”/) });
  });
  it('shows the SAC and treatment when they agree', () => {
    expect(rowTaxStatus('FORWARD', sac())).toEqual({ tone: 'ok', text: 'SAC 998399 · Taxable' });
    expect(rowTaxStatus('REVERSE', sac({ reverse: true }))).toEqual({ tone: 'ok', text: 'SAC 998399 · Taxable' });
  });
  it.each([['EXEMPT', 'Exempt'], ['NIL_RATED', 'Nil-rated'], ['NON_GST', 'Non-GST']])('says no GST is charged for a %s account', (treatment, label) => {
    expect(rowTaxStatus('FORWARD', sac({ treatment }))).toEqual({ tone: 'ok', text: `SAC 998399 · ${label}: no GST is charged` });
  });
  it('keys a default by account and date', () => expect(defaultKey(account, '2026-10-30')).toBe(account + '|2026-10-30'));
});

describe('the tax block of the bill', () => {
  it('carries exactly what Accounting needs, for the supplier-charged profile', () => {
    expect(purchaseTaxContext({ tax: taxed(), ...base, facts: facts() })).toEqual({
      profile: 'INDIA_DOMESTIC_SERVICE', company_registration_id: mine.id, party_registration_id: regular.id, place_of_supply: 'IN-MH',
      service_completion_date: '2026-10-30', supplier_invoice_number: 'SUP-42', supplier_invoice_date: '2026-10-30',
    });
  });
  it('uses the reverse-charge profile, and the person’s own choices', () => {
    expect(purchaseTaxContext({ tax: taxed({ choice: 'REVERSE', placeOfSupply: 'IN-KA', completionDate: '2026-10-02' }), ...base, invoice: '  SUP-43 ', facts: facts() }))
      .toMatchObject({ profile: 'INDIA_DOMESTIC_SERVICE_RCM', place_of_supply: 'IN-KA', service_completion_date: '2026-10-02', supplier_invoice_number: 'SUP-43' });
  });
  it('says what is missing instead of building a block Accounting would refuse', () => {
    expect(() => purchaseTaxContext({ tax: taxed(), ...base, facts: facts({ suppliers: new Map([[supplier, []]]) }) })).toThrow(/no GST registration on record/);
    expect(() => purchaseTaxContext({ tax: taxed(), ...base, facts: noTaxFacts() })).toThrow(/not been read yet/);
    expect(() => purchaseTaxContext({ tax: taxed(), ...base, supplier: '', facts: facts() })).toThrow(/Choose the supplier’s GST registration/);
  });
  it('needs the supplier’s invoice number, which GST is raised against', () => {
    expect(() => purchaseTaxContext({ tax: taxed(), ...base, invoice: '   ', facts: facts() })).toThrow(/invoice number/);
    expect(() => purchaseTaxContext({ tax: taxed(), ...base, invoice: 'x'.repeat(121), facts: facts() })).toThrow(/invoice number/);
  });
  it('is only for a taxed bill', () => {
    expect(() => purchaseTaxContext({ tax: { ...blankPurchaseTax(), choice: 'NONE' }, ...base, facts: facts() })).toThrow(/Only a taxed bill/);
    expect(() => purchaseTaxContext({ tax: blankPurchaseTax(), ...base, facts: facts() })).toThrow(/Only a taxed bill/);
  });
});
