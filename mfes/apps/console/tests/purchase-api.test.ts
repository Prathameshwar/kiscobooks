import { beforeEach, describe, expect, it } from 'vitest';
import { livePurchasePolicy, purchaseAdvancePage, purchaseBase, purchaseFromVoucher, purchaseInput, verifyPurchaseFieldSet, purchasePaymentAccount, purchasePendingKey, readPurchasePending, verifyPurchaseCalculation, verifyPurchaseOperation, verifyPurchaseVoucher, type PurchaseBinding, type PurchaseCalculation, type PurchaseVoucher } from '../app/lib/purchase-api';
import { blankPurchaseLine, newPurchaseWorkspace } from '../app/lib/purchase-workspace';
import { company, draft as native, metadata as baseMetadata } from './purchase-entry-fixtures';
import type { FieldSet } from '../app/lib/voucher-fields';
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
let metadata: FieldSet, binding: PurchaseBinding;
const draft = () => {
  const value = newPurchaseWorkspace('2026-10-30');
  Object.assign(value, { mode: 'ACCOUNTS', supplier: native.party!.id, payable: native.payable!.id, invoice: 'SUP-42', lines: [{ ...blankPurchaseLine('p1', 'ACCOUNT'), subject: native.supplies[0]!.account!.id, label: 'Expense', description: 'Consulting', amount: '42.1234' }] });
  value.details.termsDays = '2'; return value;
};
beforeEach(() => {
  metadata = structuredClone(baseMetadata);
  Object.assign(metadata.native.properties!, Object.fromEntries(['document_date', 'credit_terms_date', 'currency', 'narration', 'mode', 'lines', 'attachments', 'links', 'custom_fields'].map(key => [key, {}])));
  const invoice = metadata.native.properties!.invoice!.anyOf![0]!.properties!;
  invoice.components = {};
  invoice.allocations = {};
  invoice.tenders = {};
  binding = { company, currency: 'INR', metadata, keys: new Map(), partyKey: native.partyLineKey, sources: new Map([native.party!, native.payable!, native.supplies[0]!.account!].map(source => [source.id, source])) };
});
describe('proposed payment boundary', () => {
  it('retains full invoice amounts and creates an exact cash tender instruction', () => {
    const value = draft(); value.details.payment = { amount: '10.1234', method: 'CASH', account: id(81), reference: '' };
    binding.paymentAccounts = new Map([[id(81), { id: id(81), company, currency: 'INR', version: 8, method: 'CASH', label: 'Cash' }]]);
    const wire = purchaseInput(value, binding); expect(wire.invoice!.supplies[0]!.amount).toBe('42.1234');
    expect(wire.invoice!.tenders![0]).toMatchObject({ account_id: id(81), account_version: 8, tender: { mode: 'CASH', amount: '10.1234', recognition: 'BOOK_DATE' } });
    expect(purchaseInput(value, binding).invoice!.tenders).toEqual(wire.invoice!.tenders);
  });
  it('records an optional bank reference and requires a matching verified account', () => {
    const value = draft(); value.details.payment = { amount: '10', method: 'BANK', account: id(81), reference: '' };
    expect(() => purchaseInput(value, binding)).toThrow(/verified payment/);
    binding.paymentAccounts = new Map([[id(81), { id: id(81), company, currency: 'INR', version: 8, method: 'BANK', label: 'Bank' }]]);
    const unreferenced = purchaseInput(value, binding).invoice!.tenders![0]!.tender;
    expect(unreferenced.mode).toBe('BANK_TRANSFER'); expect(unreferenced).not.toHaveProperty('reference');
    value.details.payment.reference = 'TR-1'; expect(purchaseInput(value, binding).invoice!.tenders![0]!.tender).toMatchObject({ mode: 'BANK_TRANSFER', reference: 'TR-1' });
  });
  it('does not coerce a foreign payment account into the current currency', async () => {
    const reader = async <T,>(): Promise<T> => ({ id: id(81), company_id: company, status: 'ACTIVE', row_version: 8, kind: 'BANK', currency_mode: 'FIXED', currency: 'USD', posting_policy: 'MANUAL_ALLOWED' }) as T;
    await expect(purchasePaymentAccount(reader, company, 'INR', id(81))).rejects.toThrow(/currency/);
  });
  it('verifies current same-company cash account versions', async () => {
    const reader = async <T,>(): Promise<T> => ({ id: id(81), company_id: company, status: 'ACTIVE', row_version: 8, kind: 'CASH', currency_mode: 'BASE', posting_policy: 'MANUAL_ALLOWED' }) as T;
    await expect(purchasePaymentAccount(reader, company, 'INR', id(81))).resolves.toMatchObject({ id: id(81), version: 8, method: 'CASH', currency: 'INR' });
  });
});
describe('asynchronous execution receipts', () => {
  it('refuses an operation envelope attached to an ordinary draft command', () => {
    const scope = 'mismatched-operation'; sessionStorage.setItem(purchasePendingKey(scope), JSON.stringify({ schema: 1, scope, operation: { voucherId: id(90), revisionId: id(91) }, request: { service: 'vouchers', method: 'POST', path: purchaseBase(company) + '/vouchers', key: id(94), body: {} } }));
    expect(() => readPurchasePending(sessionStorage, scope, company)).toThrow();
  });
  it('verifies exact voucher/revision lineage without claiming PENDING is committed', () => {
    expect(() => verifyPurchaseOperation({ id: id(80), voucher_id: id(90), revision_id: id(91), row_version: 1, status: 'PENDING' }, { voucherId: id(90), revisionId: id(91) })).not.toThrow();
    expect(() => verifyPurchaseOperation({ id: id(80), voucher_id: id(99), row_version: 1, status: 'COMMITTED' }, { voucherId: id(90), revisionId: id(91) })).toThrow();
  });
});
const voucher = (): PurchaseVoucher => ({ ...purchaseInput(draft(), binding), id: id(90), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', status: 'DRAFT', revision_id: id(91), row_version: 7, revision_number: 3, lines: [], attachments: [], links: [], custom_fields: {} } as PurchaseVoucher);
const calculation = (): PurchaseCalculation => ({ calculation_hash: 'a'.repeat(64), calculation_version: 1, currency: 'INR', commercial_total: '42.1234', tax_total: '0.0000', charged_tax_total: '0.0000', rounding: '-0.0034', payable: '42.1200', supplier_difference: null, lines: [], components: [], allocations: [], tax_evidence: [] });
describe('Purchase wire boundary', () => {
  it('pins a verified rounding account and restores it when a saved bill is reopened', () => {
    const invoice = metadata.native.properties!.invoice!.anyOf![0]!.properties!;
    invoice.rounding_account_id = {}; invoice.rounding_account_version = {};
    const value = draft(); Object.assign(value.details, { roundingAccount: native.supplies[0]!.account!.id });
    const wire = purchaseInput(value, binding);
    expect(wire.invoice).toMatchObject({ rounding_account_id: native.supplies[0]!.account!.id, rounding_account_version: 4 });
    const loaded = purchaseFromVoucher({ ...voucher(), invoice: wire.invoice }, company, metadata);
    expect(loaded.draft.details).toMatchObject({ roundingAccount: native.supplies[0]!.account!.id });
    Object.assign(value.details, { roundingAccount: id(99) });
    expect(() => purchaseInput(value, binding)).toThrow(/rounding account/i);
  });
  it('sends a native supplier difference reason without changing financial line amounts', () => {
    const invoice = metadata.native.properties!.invoice!.anyOf![0]!.properties!; invoice.supplier_difference_reason = {};
    const value = draft(); value.details.declaredTotal = '42.13'; value.details.comparisonReason = 'Supplier rounding reviewed';
    const wire = purchaseInput(value, binding); expect(wire.invoice!.supplier_difference_reason).toBe('Supplier rounding reviewed');
    expect(wire.invoice!.supplies[0]!.amount).toBe('42.1234');
    const loaded = purchaseFromVoucher({ ...voucher(), invoice: wire.invoice }, company, metadata); expect(loaded.draft.details.comparisonReason).toBe('Supplier rounding reviewed');
    invoice.supplier_difference_reason = { readOnly: true }; expect(() => purchaseInput(value, binding)).toThrow(/write access/i);
  });
  it('sends an emptied supplier-declared total as empty, not as the saved one', () => {
    const first = draft(); first.details.declaredTotal = '100.0000';
    binding.previous = purchaseInput(first, binding);
    const cleared = draft(); cleared.details.declaredTotal = '';
    expect(purchaseInput(cleared, binding).invoice!.supplier_declared_total).toBeNull();
    // Clearing is a write, so it needs the access that setting needs.
    metadata.native.properties!.invoice!.anyOf![0]!.properties!.supplier_declared_total = { readOnly: true };
    expect(() => purchaseInput(cleared, binding)).toThrow(/write access/i);
  });
  it('does not mention the supplier-declared total on a first save that has none', () => {
    expect(purchaseInput(draft(), binding).invoice).not.toHaveProperty('supplier_declared_total');
  });
  it('preserves saved file references and allows their explicit removal in a new draft', () => {
    const value = voucher(); value.attachments = [{ object_key: `${id(80)}/${company}/purchase/${value.id}/${'a'.repeat(64)}`, content_hash: 'a'.repeat(64), media_type: 'application/pdf', size_bytes: 8 }];
    const loaded = purchaseFromVoucher(value, company, metadata); expect(loaded.draft.details.supportingFiles).toHaveLength(1);
    expect(purchaseInput(loaded.draft, loaded.binding).attachments).toEqual(value.attachments);
    loaded.draft.details.supportingFiles = []; expect(purchaseInput(loaded.draft, loaded.binding).attachments).toEqual([]);
  });
  it('sends exact strings, verified versions and stable UUIDs; never sends fixture evidence', () => {
    const value = draft(); const first = purchaseInput(value, binding), second = purchaseInput(value, binding);
    expect(first).toEqual(second); expect(first.invoice!.supplies[0]!.amount).toBe('42.1234');
    expect(first.invoice!.supplies[0]!.account_version).toBe(4); expect(first.invoice!.due_date).toBe('2026-11-01');
    expect(first.invoice!.tax.profile).toBe('UNTAXED_ACCOUNT'); expect(first).not.toHaveProperty('evidence');
    expect(first.invoice!.supplies[0]!.line_key).toMatch(/^[a-f0-9-]{36}$/);
  });
  it('maps posting-date credit terms without changing invoice identity', () => {
    const value = draft(); value.postingDate = '2026-11-02'; value.details.termsBasis = 'POSTING_DATE';
    expect(purchaseInput(value, binding).invoice!.due_date).toBe('2026-11-04');
    expect(purchaseInput(value, binding).credit_terms_date).toBe('2026-11-02');
  });
  it('does not post a provisional total as supplier evidence', () => {
    expect(purchaseInput(draft(), binding).invoice!.supplier_declared_total).toBeUndefined();
  });
  it.each(['attachments', 'advances', 'receipts'] as const)('refuses unsupported %s instead of silently dropping it', key => {
    const value = draft(); (value.details[key] as unknown[]).push({ id: 'unsupported' });
    expect(() => purchaseInput(value, binding)).toThrow(/cannot save/);
  });
  it('refuses goods in the account profile', () => { const value = draft(); value.mode = 'ITEMS'; expect(() => purchaseInput(value, binding)).toThrow(/not allowed by the selected voucher type/); });
  it('refuses a wrong-company source', () => { binding.sources.set(native.party!.id, { ...native.party!, company: id(99) }); expect(() => purchaseInput(draft(), binding)).toThrow(/supplier/); });
  it('refuses a payable belonging to another supplier', () => { binding.sources.set(native.payable!.id, { ...native.payable!, partyId: id(99) }); expect(() => purchaseInput(draft(), binding)).toThrow(/payable/); });
  it('requires field access for every added header', () => { delete metadata.native.properties!.document_date; expect(() => purchaseInput(draft(), binding)).toThrow(/document_date/); });
  it('refuses discounts forbidden by effective policy', () => { const value = draft(); value.lines[0]!.discount = '1'; expect(() => purchaseInput(value, binding)).toThrow(/policy/); });
  it('maps an allowed line discount to an explicit component, preserving base amount', () => {
    metadata.configuration.policy.invoice!.manual_discounts_allowed = true; const value = draft(); value.lines[0]!.discount = '1.1234';
    const wire = purchaseInput(value, binding); expect(wire.invoice!.supplies[0]!.amount).toBe('42.1234');
    expect(wire.invoice!.components![0]).toMatchObject({ purpose: 'DISCOUNT', value: '1.1234', effect: 'DEDUCT', targets: [wire.invoice!.supplies[0]!.line_key] });
  });
  it('refuses an adjustment targeting a removed line', () => {
    metadata.configuration.policy.invoice!.manual_discounts_allowed = true;
    const value = draft(); value.details.components = [{ id: 'c1', label: 'Discount', kind: 'DISCOUNT', basis: 'AMOUNT', value: '1', targets: ['gone'], payable: true, taxTreatment: 'INCLUDED' }];
    expect(() => purchaseInput(value, binding)).toThrow(/removed line/);
  });
});
describe('supplier advance owner facts', () => {
  it('maps a verified advance without reducing the full supplier bill', () => {
    const value = draft(); value.details.advances = [{ id: id(80), amount: '10.1234' }];
    binding.advances = new Map([[id(80), { id: id(80), company, supplier: value.supplier, payable: value.payable, currency: 'INR', remaining: '20.0000', label: 'Advance', asOf: value.postingDate }]]);
    const wire = purchaseInput(value, binding); expect(wire.invoice!.supplies[0]!.amount).toBe('42.1234');
    expect(wire.invoice!.allocations![0]).toMatchObject({ debt: { line_key: binding.partyKey }, credit: { item_id: id(80) }, amount: '10.1234', currency: 'INR' });
    expect(purchaseInput(value, binding).invoice!.allocations).toEqual(wire.invoice!.allocations);
  });
  it('refuses stale, foreign or insufficient advances', () => {
    const value = draft(); value.details.advances = [{ id: id(80), amount: '30.0000' }];
    binding.advances = new Map([[id(80), { id: id(80), company, supplier: value.supplier, payable: value.payable, currency: 'INR', remaining: '20.0000', label: 'Advance', asOf: value.postingDate }]]);
    expect(() => purchaseInput(value, binding)).toThrow(/excessive/);
    value.details.advances[0]!.amount = '10'; binding.advances.get(id(80))!.asOf = '2026-01-01'; expect(() => purchaseInput(value, binding)).toThrow(/unverified/);
  });
  it('verifies list identity, supplier, payable, role and exact as-of balances', async () => {
    const requests: string[] = [];
    const reader = async <T,>(request: import('../app/lib/service-call').ServiceRequest): Promise<T> => {
      requests.push(request.path);
      return (request.path.includes('/balance?') ? { item_id: id(80), as_of: '2026-10-30', currency: 'INR', remaining: '10.0000' } : { items: [{ id: id(80), company_id: company, party_id: native.party!.id, account_id: native.payable!.id, role: 'SUPPLIER', direction: 'CREDIT', currency: 'INR', posting_date: '2026-10-01', reference: 'ADV-1' }], page: { next_cursor: null } }) as T;
    };
    const page = await purchaseAdvancePage(reader, company, native.party!.id, native.payable!.id, 'INR', '2026-10-30');
    expect(page.items[0]).toMatchObject({ remaining: '10.0000', supplier: native.party!.id, payable: native.payable!.id });
    expect(requests[0]).toContain('direction=CREDIT'); expect(requests[0]).not.toContain('DEBIT'); expect(requests[1]).toContain('as_of=2026-10-30');
  });
  it('refuses a foreign advance before querying its balance', async () => {
    let calls = 0;
    const reader = async <T,>(): Promise<T> => { calls++; return { items: [{ id: id(80), company_id: id(99) }], page: { next_cursor: null } } as T; };
    await expect(purchaseAdvancePage(reader, company, native.party!.id, native.payable!.id, 'INR', '2026-10-30')).rejects.toThrow(/list could not be verified/); expect(calls).toBe(1);
  });
});
describe('saved revisions and authoritative evidence', () => {
  it('rehydrates saved line discounts with zero-padded service decimals', () => {
    metadata.configuration.policy.invoice!.manual_discounts_allowed = true;
    const entry = draft(); entry.lines[0]!.discount = '2.5';
    const wire = purchaseInput(entry, binding);
    const saved = voucher(); saved.invoice = wire.invoice;
    const savedComponents = saved.invoice!.components as { value: string }[];
    savedComponents[0]!.value = '2.50000000';
    const reopened = purchaseFromVoucher(saved, company, metadata);
    expect(reopened.draft.lines[0]!.discount).toBe('2.5000');
    expect(reopened.draft.details.components).toEqual([]);
    expect(purchaseInput(reopened.draft, reopened.binding).invoice!.components![0]!.value).toBe('2.5000');
    savedComponents[0]!.value = '2.50000001';
    expect(() => purchaseFromVoucher(saved, company, metadata)).toThrow(/broader Purchase profile/);
  });
  it('keeps row version, revision number and revision ID distinct', () => {
    const value = voucher(); const result = purchaseFromVoucher(value, company, metadata);
    expect(result.draft.lines[0]!.key).toBe((value.invoice!.supplies as { line_key: string }[])[0]!.line_key);
    expect(result.binding.sources.get(native.supplies[0]!.account!.id)!.version).toBe(4);
    expect(purchaseInput(result.draft, result.binding).invoice!.supplies[0]!.line_key).toBe((value.invoice!.supplies as { line_key: string }[])[0]!.line_key);
  });
  it.each(['company_id', 'kind', 'id', 'revision_id'] as const)('refuses invalid %s on service responses', key => { const value = voucher(); Object.assign(value, { [key]: key === 'company_id' ? id(99) : 'wrong' }); expect(() => verifyPurchaseVoucher(value, company)).toThrow(); });
  it('reopens a bill whose voucher type has been revised, under the current revision, and says so', () => {
    const value = voucher();
    const current = id(77);
    metadata.configuration.type_revision_id = current;
    const result = purchaseFromVoucher(value, company, metadata);
    expect(result.typeRevised).toBe(true);
    // The next save names the revision the service will validate it against, not the stale pinned one.
    expect(purchaseInput(result.draft, result.binding).type_revision_id).toBe(current);
    expect(purchaseFromVoucher(voucher(), company, { ...metadata, configuration: { ...metadata.configuration, type_revision_id: voucher().type_revision_id } }).typeRevised).toBe(false);
  });
  it('refuses to open a saved bill as a Purchase when its type is another kind', () => {
    const value = voucher();
    metadata.configuration.kind = 'SALES';
    expect(() => purchaseFromVoucher(value, company, metadata)).toThrow(/not a Purchase/);
  });
  it('says why a saved bill cannot be opened for editing when the service says its type cannot give an edit view', () => {
    expect(() => verifyPurchaseFieldSet({ configuration_unavailable: 'voucher type revision is retired or superseded' } as never)).toThrow(/cannot be opened for editing here: voucher type revision is retired or superseded/);
  });
  it.each([null, undefined, {}, { native: {}, custom: [] }, { native: {}, custom: 'x', configuration: { type_revision_id: id(77) } }, { native: {}, custom: [], configuration: { type_revision_id: 'x' } }])(
    'does not trust a saved-bill field-set without a native schema, custom list and type revision: %j', shape => {
      expect(() => verifyPurchaseFieldSet(shape as never)).toThrow(/field access could not be verified/);
    });
  it('accepts the edit view the service returns for a saved bill', () => { expect(verifyPurchaseFieldSet(metadata)).toBe(metadata); });
  it('requires a new row version for mutations', () => { const value = voucher(); expect(() => verifyPurchaseVoucher(value, company, { version: 7 })).toThrow(/new revision/); });
  it('requires the requested voucher identity', () => expect(() => verifyPurchaseVoucher(voucher(), company, { id: id(99) })).toThrow());
  it('refuses a partially hidden replace capture', () => { const value = voucher(); value.references = null; expect(() => purchaseFromVoucher(value, company, metadata)).toThrow(/not readable/); });
  it('refuses a hidden invoice adjustment collection instead of replacing it with an empty one', () => { const value = voucher(); delete value.invoice!.components; expect(() => purchaseFromVoucher(value, company, metadata)).toThrow(/not fully readable/); });
  it('retains unrelated references, parties and rounding evidence when editing', () => {
    const value = voucher(); (value.references as object[]).push({ purpose: 'EXTERNAL', reference: 'REQ-99' });
    Object.assign(value.invoice!, { rounding_account_id: id(88), rounding_account_version: 5 });
    const result = purchaseFromVoucher(value, company, metadata), wire = purchaseInput(result.draft, result.binding);
    expect(wire.references).toContainEqual({ purpose: 'EXTERNAL', reference: 'REQ-99' });
    expect(wire.invoice).toMatchObject({ rounding_account_id: id(88), rounding_account_version: 5 });
  });
  it('refuses tax profiles the editor cannot represent', () => { const value = voucher(); (value.invoice!.tax as Record<string, unknown>).profile = 'INDIA_DOMESTIC_SERVICE'; expect(() => purchaseFromVoucher(value, company, metadata)).toThrow(/broader/); });
  it('accepts null supplier difference when no declared total was provided', () => expect(() => verifyPurchaseCalculation(calculation(), 'INR')).not.toThrow());
  it.each(['payable', 'commercial_total', 'tax_total'] as const)('refuses numeric %s instead of an exact string', key => { const value = calculation(); Object.assign(value, { [key]: 42.12 }); expect(() => verifyPurchaseCalculation(value, 'INR')).toThrow(); });
  it('refuses a calculation in another currency', () => expect(() => verifyPurchaseCalculation(calculation(), 'USD')).toThrow());
  it('never exposes fixture masters through the live policy', () => { const value = livePurchasePolicy('INR', metadata); expect(value.suppliers).toEqual([]); expect(value.details.advances).toEqual([]); expect(value.details.maxFiles).toBe(0); });
});
describe('tab command recovery', () => {
  it('retains the exact body/key only for the same actor/company/year', () => {
    const scope = JSON.stringify(['actor', company, 'year']); const request = { service: 'vouchers', path: purchaseBase(company) + '/vouchers', method: 'POST', key: id(94), body: purchaseInput(draft(), binding) };
    sessionStorage.setItem(purchasePendingKey(scope), JSON.stringify({ schema: 1, scope, request, createdAt: '2026-10-31T00:00:00Z' }));
    expect(readPurchasePending(sessionStorage, scope, company)!.request).toEqual(request);
    expect(readPurchasePending(sessionStorage, scope + 'other', company)).toBeNull();
    expect(() => readPurchasePending(sessionStorage, scope, id(99))).toThrow(/cannot be verified/);
  });
  it('refuses malformed retained commands', () => { sessionStorage.setItem(purchasePendingKey('bad'), '{}'); expect(() => readPurchasePending(sessionStorage, 'bad', company)).toThrow(); });
  it('refuses a retained path that merely starts with the vouchers resource name', () => {
    const scope = 'unsafe'; sessionStorage.setItem(purchasePendingKey(scope), JSON.stringify({ schema: 1, scope, request: { service: 'vouchers', path: purchaseBase(company) + '/vouchers-unsafe', method: 'POST', key: id(94), body: {} } }));
    expect(() => readPurchasePending(sessionStorage, scope, company)).toThrow();
  });
});
