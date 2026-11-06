import { beforeEach, describe, expect, it } from 'vitest';
import { purchaseFromVoucher, purchaseInput, type PurchaseBinding, type PurchaseInput, type PurchaseVoucher } from '../app/lib/purchase-api';
import { blankPurchaseLine, newPurchaseWorkspace, purchaseWorkspaceReducer, type PurchaseWorkspaceDraft } from '../app/lib/purchase-workspace';
import { blankPurchaseTax, noTaxFacts, type CompanyGst, type PurchaseTaxFacts, type SupplierGst } from '../app/lib/purchase-tax';
import { company, draft as native, metadata as baseMetadata } from './purchase-entry-fixtures';
import type { FieldSet } from '../app/lib/voucher-fields';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const mine: CompanyGst = { id: id(20), number: '27AAAAA0000A1Z5', state: 'IN-MH', primary: true, from: '2020-04-01', to: null };
const regular: SupplierGst = { id: id(30), type: 'REGULAR', state: 'IN-GJ', number: '24BBBBB1111B1Z6', from: '2019-07-01', to: null };
const supplier = native.party!.id;
const facts = (): PurchaseTaxFacts => ({ ...noTaxFacts(), companies: [mine], suppliers: new Map([[supplier, [regular]]]) });
let metadata: FieldSet, binding: PurchaseBinding;

const draft = (choice: 'NONE' | 'FORWARD' | 'REVERSE' | '' = 'FORWARD'): PurchaseWorkspaceDraft => {
  const value = newPurchaseWorkspace('2026-10-30');
  Object.assign(value, { mode: 'ACCOUNTS', supplier, payable: native.payable!.id, invoice: 'SUP-42', lines: [{ ...blankPurchaseLine('p1', 'ACCOUNT'), subject: native.supplies[0]!.account!.id, label: 'Expense', description: 'Consulting', amount: '1000' }] });
  value.details.termsDays = '2'; value.tax = { ...blankPurchaseTax(), choice };
  return value;
};
/** The invoice of a saved voucher, as the wire shape it was built from. */
const invoiceOf = (value: PurchaseVoucher) => value.invoice as unknown as NonNullable<PurchaseInput['invoice']>;
const voucherOf = (wire: ReturnType<typeof purchaseInput>): PurchaseVoucher => ({ ...wire, id: id(90), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', status: 'DRAFT', revision_id: id(91), row_version: 7, revision_number: 3, lines: [], attachments: [], links: [], custom_fields: {} } as unknown as PurchaseVoucher);

beforeEach(() => {
  metadata = structuredClone(baseMetadata);
  Object.assign(metadata.native.properties!, Object.fromEntries(['document_date', 'credit_terms_date', 'currency', 'narration', 'mode', 'lines', 'attachments', 'links', 'custom_fields'].map(key => [key, {}])));
  const invoice = metadata.native.properties!.invoice!.anyOf![0]!.properties!;
  Object.assign(invoice, { components: {}, allocations: {}, tenders: {} });
  metadata.configuration.policy.invoice = { allowed_supply_kinds: ['ACCOUNT', 'SERVICE'] };
  binding = { company, currency: 'INR', metadata, keys: new Map(), partyKey: native.partyLineKey, sources: new Map([native.party!, native.payable!, native.supplies[0]!.account!].map(source => [source.id, source])) };
});

describe('sending a taxed bill', () => {
  it('carries the GST context on the invoice and bills each line as a service', () => {
    const wire = purchaseInput(draft(), binding, facts());
    expect(wire.invoice!.tax).toEqual({
      profile: 'INDIA_DOMESTIC_SERVICE', company_registration_id: mine.id, party_registration_id: regular.id, place_of_supply: 'IN-MH',
      service_completion_date: '2026-10-30', supplier_invoice_number: 'SUP-42', supplier_invoice_date: '2026-10-30',
    });
    expect(wire.invoice!.supplies.map(line => [line.supply_kind, line.amount, line.price_basis])).toEqual([['SERVICE', '1000', 'NET_EXCL_TAX']]);
    // Amounts and rates are Accounting's: nothing but the entered amount goes with the line.
    expect(JSON.stringify(wire)).not.toMatch(/tax_total|rate|percent/i);
  });
  it('uses the reverse-charge profile for a reverse-charge bill', () => {
    expect(purchaseInput(draft('REVERSE'), binding, facts()).invoice!.tax).toMatchObject({ profile: 'INDIA_DOMESTIC_SERVICE_RCM' });
  });
  it('sends what the person chose over what the masters would have defaulted to', () => {
    const value = draft(); value.tax = { ...value.tax, placeOfSupply: 'IN-KA', completionDate: '2026-10-05' };
    expect(purchaseInput(value, binding, facts()).invoice!.tax).toMatchObject({ place_of_supply: 'IN-KA', service_completion_date: '2026-10-05' });
  });
  it('still sends an untaxed bill as before, and an undecided one is untaxed here (the page refuses it first)', () => {
    for (const choice of ['NONE', ''] as const) {
      const wire = purchaseInput(draft(choice), binding);
      expect(wire.invoice!.tax).toEqual({ profile: 'UNTAXED_ACCOUNT' });
      expect(wire.invoice!.supplies[0]!.supply_kind).toBe('ACCOUNT');
    }
  });
  it('does not send a taxed bill without the masters it was checked against', () => {
    expect(() => purchaseInput(draft(), binding)).toThrow(/not been read yet/);
    expect(() => purchaseInput(draft(), binding, { ...facts(), suppliers: new Map([[supplier, []]]) })).toThrow(/no GST registration on record/);
  });
  it('does not send GST on a type that does not take service supplies', () => {
    metadata.configuration.policy.invoice = { allowed_supply_kinds: ['ACCOUNT'] };
    expect(() => purchaseInput(draft(), binding, facts())).toThrow(/does not allow them/);
    expect(purchaseInput(draft('NONE'), binding).invoice!.tax).toEqual({ profile: 'UNTAXED_ACCOUNT' });
  });
  it('requires a compatible supply kind for an untaxed account bill', () => {
    metadata.configuration.policy.invoice = { allowed_supply_kinds: ['SERVICE'] };
    expect(() => purchaseInput(draft('NONE'), binding)).toThrow(/does not allow untaxed account lines/);
    expect(purchaseInput(draft(), binding, facts()).invoice!.supplies[0]!.supply_kind).toBe('SERVICE');
  });
  it('replaces a saved bill’s tax block, not merges into it', () => {
    binding.previous = { ...purchaseInput(draft('NONE'), binding) };
    const wire = purchaseInput(draft(), binding, facts());
    expect(Object.keys(wire.invoice!.tax).sort()).toEqual(['company_registration_id', 'party_registration_id', 'place_of_supply', 'profile', 'service_completion_date', 'supplier_invoice_date', 'supplier_invoice_number']);
  });
});

describe('opening a saved bill', () => {
  const saved = (choice: 'FORWARD' | 'REVERSE' = 'FORWARD', patch: (voucher: PurchaseVoucher) => void = () => undefined) => {
    const value = voucherOf(purchaseInput(draft(choice), binding, facts())); patch(value); return value;
  };
  const open = (value: PurchaseVoucher) => purchaseFromVoucher(value, company, metadata);

  it('restores a supplier-charged bill with only what the person chose explicit', () => {
    const { draft: opened } = open(saved());
    expect(opened.tax).toEqual({ choice: 'FORWARD', companyRegistration: mine.id, placeOfSupply: 'IN-MH', completionDate: '', supplierRegistration: regular.id });
  });
  it('restores a reverse-charge bill and a completion date that differs from the invoice date', () => {
    const { draft: opened } = open(saved('REVERSE', value => { (invoiceOf(value).tax as { service_completion_date: string }).service_completion_date = '2026-10-02'; }));
    expect(opened.tax).toMatchObject({ choice: 'REVERSE', completionDate: '2026-10-02' });
  });
  it('restores an untaxed bill as a decision already taken', () => {
    expect(open(voucherOf(purchaseInput(draft('NONE'), binding))).draft.tax).toEqual({ ...blankPurchaseTax(), choice: 'NONE' });
  });
  it('round-trips: what was saved is what is sent back', () => {
    const value = saved();
    const { draft: opened, binding: reopened } = open(value);
    expect(purchaseInput(opened, reopened, facts()).invoice!.tax).toEqual(invoiceOf(value).tax);
  });
  it('accepts a line that carries the same context as the header', () => {
    const value = saved(); invoiceOf(value).supplies[0]!.tax = { ...invoiceOf(value).tax };
    expect(() => open(value)).not.toThrow();
  });

  it.each([
    ['a line with its own registration', (value: PurchaseVoucher) => { invoiceOf(value).supplies[0]!.tax = { ...invoiceOf(value).tax, party_registration_id: id(99) }; }],
    ['a line with its own profile', (value: PurchaseVoucher) => { invoiceOf(value).supplies[0]!.tax = { ...invoiceOf(value).tax, profile: 'INDIA_DOMESTIC_SERVICE_RCM' }; }],
    ['a line billed as an account', (value: PurchaseVoucher) => { invoiceOf(value).supplies[0]!.supply_kind = 'ACCOUNT'; }],
    ['a supplier invoice number that is not the bill reference', (value: PurchaseVoucher) => { (invoiceOf(value).tax as { supplier_invoice_number: string }).supplier_invoice_number = 'OTHER'; }],
    ['a supplier invoice date that is not the document date', (value: PurchaseVoucher) => { (invoiceOf(value).tax as { supplier_invoice_date: string }).supplier_invoice_date = '2026-10-01'; }],
    ['a withholding section', (value: PurchaseVoucher) => { (invoiceOf(value).tax as { withholding_section_id: string }).withholding_section_id = id(98); }],
    ['a payment date', (value: PurchaseVoucher) => { (invoiceOf(value).tax as { payment_date: string }).payment_date = '2026-10-30'; }],
    ['no company registration', (value: PurchaseVoucher) => { delete (invoiceOf(value).tax as { company_registration_id?: string }).company_registration_id; }],
    ['no supplier registration', (value: PurchaseVoucher) => { delete (invoiceOf(value).tax as { party_registration_id?: string }).party_registration_id; }],
    ['no place of supply', (value: PurchaseVoucher) => { delete (invoiceOf(value).tax as { place_of_supply?: string }).place_of_supply; }],
    ['no completion date', (value: PurchaseVoucher) => { delete (invoiceOf(value).tax as { service_completion_date?: string }).service_completion_date; }],
    ['a profile this screen does not capture', (value: PurchaseVoucher) => { (invoiceOf(value).tax as { profile: string }).profile = 'SOMETHING_ELSE'; }],
  ])('sends it to voucher review instead of editing it: %s', (_name, change) => {
    expect(() => open(saved('FORWARD', change))).toThrow(/broader Purchase profile/);
  });
  it('still refuses a taxed supply on an untaxed bill', () => {
    const value = voucherOf(purchaseInput(draft('NONE'), binding)); invoiceOf(value).supplies[0]!.supply_kind = 'SERVICE';
    expect(() => open(value)).toThrow(/broader Purchase profile/);
  });
});

describe('the bill’s tax in the draft', () => {
  it('starts undecided, and a patch changes only what it names', () => {
    const value = newPurchaseWorkspace('2026-10-30');
    expect(value.tax).toEqual(blankPurchaseTax());
    const next = purchaseWorkspaceReducer(value, { type: 'tax', patch: { choice: 'FORWARD', placeOfSupply: 'IN-KA' } });
    expect(next.tax).toEqual({ ...blankPurchaseTax(), choice: 'FORWARD', placeOfSupply: 'IN-KA' });
    expect(next.lines).toBe(value.lines);
    expect(purchaseWorkspaceReducer(next, { type: 'tax', patch: { completionDate: '2026-10-01' } }).tax).toEqual({ ...next.tax, completionDate: '2026-10-01' });
  });
  it('drops the supplier’s registration when another supplier is chosen, and keeps it for the same one', () => {
    const value = purchaseWorkspaceReducer(newPurchaseWorkspace('2026-10-30'), { type: 'tax', patch: { choice: 'FORWARD', supplierRegistration: regular.id, companyRegistration: mine.id } });
    const policy = { currency: 'INR', suppliers: [{ id: 's1', label: 'One', meta: '', payables: [] }, { id: 's2', label: 'Two', meta: '', payables: [] }] } as never;
    const first = purchaseWorkspaceReducer(value, { type: 'supplier', value: 's1', policy });
    expect(first.tax.supplierRegistration).toBe('');
    const again = purchaseWorkspaceReducer(purchaseWorkspaceReducer(first, { type: 'tax', patch: { supplierRegistration: regular.id } }), { type: 'supplier', value: 's1', policy });
    expect(again.tax.supplierRegistration).toBe(regular.id);
    expect(purchaseWorkspaceReducer(again, { type: 'supplier', value: 's2', policy }).tax).toMatchObject({ supplierRegistration: '', companyRegistration: mine.id, choice: 'FORWARD' });
  });
});

describe('opening a saved bill with supply facts this screen never shows', () => {
  const open = (change: (line: Record<string, unknown>) => void) => {
    const value = voucherOf(purchaseInput(draft('NONE'), binding));
    change(invoiceOf(value).supplies[0] as unknown as Record<string, unknown>);
    return () => purchaseFromVoucher(value, company, metadata);
  };
  it('accepts the defaults the service writes beside a plain line', () => {
    expect(open(line => Object.assign(line, { price_basis: 'NET_EXCL_TAX', quantities: [], free_purpose: 'NONE', free_reason: null, price_denominator: '1.0000', unit_price: null, item_line_key: null, promotion_revision_id: null, promotion_version: null }))).not.toThrow();
    expect(open(line => Object.assign(line, { price_denominator: '1' }))).not.toThrow();
  });
  it.each([
    ['a price that includes tax', { price_basis: 'GROSS_INCL_TAX' }],
    ['quantities', { quantities: [{ basis: 'BILLED', quantity: '2.0000', unit_id: id(9) }] }],
    ['a promotion', { promotion_revision_id: id(8), promotion_version: 1 }],
    ['a promotion version alone', { promotion_version: 2 }],
    ['a reason for a free line', { free_reason: 'Sample' }],
    ['a price denominator', { price_denominator: '10.0000' }],
  ])('sends %s to voucher review rather than saving it back as an ordinary line', (_name, patch) => {
    // Saving would send the line again without these facts: a bill priced with tax included would be taxed on top.
    expect(open(line => Object.assign(line, patch))).toThrow(/broader Purchase profile/);
  });
});
