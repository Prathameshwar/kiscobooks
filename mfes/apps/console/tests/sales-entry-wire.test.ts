/**
 * W2 and W4 without a DOM: the service's policy read into the page's, and the page's draft
 * written as the service's `VoucherInput`.
 */
import { describe, expect, it } from 'vitest';
import { bindingFrom, policyFromConfiguration, type EffectiveConfiguration } from '../app/lib/sales-entry-connection';
import { initialDraft, reduceDraft, type DraftLine, type SalesDraft } from '../app/lib/sales-entry-draft';
import { SAMPLE_SALES_POLICY, isAvailable } from '../app/lib/sales-entry-policy';
import { toVoucherInput, type SaveRefs, type SubjectRef } from '../app/lib/sales-entry-wire';
import { priceRate, taxPercent } from '../app/lib/sales-entry-lookups';

const EVIDENCE: EffectiveConfiguration = {
  type_revision_id: '01990000-0000-7000-8000-00000000a001',
  class_id: null,
  policy_revision_ids: ['01990000-0000-7000-8000-00000000a002'],
  kind: 'SALES',
  profile: 'STANDARD',
  digest: 'd'.repeat(64),
  policy: {
    invoice: {
      allowed_supply_kinds: ['GOODS', 'SERVICE', 'ACCOUNT'],
      allowed_price_bases: ['NET_EXCL_TAX', 'GROSS_INCL_TAX'],
      manual_discounts_allowed: true,
      sales_discount_scopes: ['LINE', 'INVOICE'],
      charges_allowed: false,
      manual_free_allowed: false,
      sales_tender_modes: ['CASH', 'UPI', 'NEFT', 'CHEQUE'],
      sales_credit_allowed: true,
      sales_split_tenders_allowed: false,
      sales_advance_adjustments_allowed: true,
      sales_invoice_rounding_allowed: true,
      sales_tax_profiles: ['INDIA_DOMESTIC_SERVICE', 'UNTAXED_ACCOUNT'],
    },
  },
};

describe('W2 the service’s policy, as the page’s', () => {
  const policy = policyFromConfiguration(EVIDENCE, SAMPLE_SALES_POLICY);

  it('takes what the service decides', () => {
    expect(policy.modes.allowed).toEqual(['ITEMS', 'ACCOUNTS', 'MIXED']);
    expect(policy.source.digest).toBe('d'.repeat(64));
    expect(isAvailable(policy.components.lineDiscount)).toBe(true);
    expect(isAvailable(policy.components.documentDiscount)).toBe(true);
    // Not in the scopes, so not offered — with the reason said.
    expect(policy.components.selectedLineDiscount).toEqual({
      available: false,
      reason: 'This bill type does not take discounts typed on the bill.',
    });
    expect(policy.components.charges).toMatchObject({ available: false });
    expect(policy.quantities.freeItem).toMatchObject({ available: false });
    expect(policy.settlement.splitTender).toMatchObject({ available: false });
    // NEFT is a bank transfer to a reader; every non-cash mode needs its reference.
    expect(policy.settlement.tenderModes).toEqual(['CASH', 'UPI', 'BANK_TRANSFER', 'CHEQUE']);
    expect(policy.settlement.referenceRequired).toEqual([]);
    expect(policy.numbering.preview).toBeNull();
  });

  it('keeps only the entry modes allowed by the effective type policy', () => {
    const evidence = { ...EVIDENCE, policy: { ...EVIDENCE.policy, allowed_modes: ['ACCOUNTS'] as const, default_mode: 'ACCOUNTS' as const } };
    expect(policyFromConfiguration(evidence, SAMPLE_SALES_POLICY).modes).toEqual({ allowed: ['ACCOUNTS'], default: 'ACCOUNTS' });
  });

  it('starts with the configured default mode when that mode is available', () => {
    const evidence = { ...EVIDENCE, policy: { ...EVIDENCE.policy, allowed_modes: ['ACCOUNTS', 'ITEMS'] as const, default_mode: 'ACCOUNTS' as const } };
    expect(policyFromConfiguration(evidence, SAMPLE_SALES_POLICY).modes).toEqual({ allowed: ['ITEMS', 'ACCOUNTS'], default: 'ACCOUNTS' });
  });

  it('refuses configuration with no compatible permitted entry mode', () => {
    const evidence = { ...EVIDENCE, policy: { ...EVIDENCE.policy, allowed_modes: ['ACCOUNTS'] as const,
      invoice: { ...EVIDENCE.policy.invoice, allowed_supply_kinds: ['SERVICE'] as const } } };
    expect(() => policyFromConfiguration(evidence, SAMPLE_SALES_POLICY)).toThrow('no supported entry mode');
  });

  it('offers no discounts when the service takes none typed on the bill', () => {
    const none = policyFromConfiguration(
      { ...EVIDENCE, policy: { invoice: { ...EVIDENCE.policy.invoice, manual_discounts_allowed: false } } },
      SAMPLE_SALES_POLICY,
    );
    expect(isAvailable(none.components.lineDiscount)).toBe(false);
    expect(isAvailable(none.components.documentDiscount)).toBe(false);
  });

  it('offers only the modes the supply kinds allow', () => {
    const services = policyFromConfiguration(
      { ...EVIDENCE, policy: { invoice: { allowed_supply_kinds: ['ACCOUNT'] } } },
      SAMPLE_SALES_POLICY,
    );
    expect(services.modes).toEqual({ allowed: ['ACCOUNTS'], default: 'ACCOUNTS' });
  });

  it('keeps the bill’s pins', () => {
    expect(bindingFrom(EVIDENCE, { id: 't1', name: 'Sales' })).toMatchObject({
      typeId: 't1',
      typeRevisionId: EVIDENCE.type_revision_id,
      taxProfiles: ['INDIA_DOMESTIC_SERVICE', 'UNTAXED_ACCOUNT'],
    });
  });
});

/* ------------------------------------------------------------------ W4 */

const SERVICE_ITEM = '01990000-0000-7000-8000-0000000000e9';
const GOODS_ITEM = '01990000-0000-7000-8000-0000000000e1';
const ACCOUNT = '01990000-0000-7000-8000-0000000000f2';
const UNIT = '01990000-0000-7000-8000-0000000000u1'.replace('u', '0');

function refs(patch: Partial<SaveRefs> = {}): SaveRefs {
  const subjects = new Map<string, SubjectRef>([
    [SERVICE_ITEM, { kind: 'ITEM', itemVersion: 3, unitId: UNIT, nature: 'SERVICE', incomeAccount: { id: 'svc-rev', version: 2 } }],
    [GOODS_ITEM, { kind: 'ITEM', itemVersion: 1, unitId: UNIT, nature: 'GOODS', incomeAccount: { id: 'sales-rev', version: 1 } }],
    [ACCOUNT, { kind: 'ACCOUNT', account: { id: ACCOUNT, version: 4 } }],
  ]);
  let counter = 0;
  const keys = new Map<string, string>();
  return {
    binding: bindingFrom(EVIDENCE, { id: 't1' }),
    currency: 'INR',
    customer: { partyId: 'party-1', partyVersion: 5, account: { id: 'receivable-1', version: 2 } },
    subjects,
    tenderAccounts: { CASH: { id: 'cash', version: 1 }, UPI: { id: 'bank', version: 1 } },
    rounding: { gain: { id: 'gain', version: 1 }, loss: { id: 'loss', version: 1 } },
    companyRegistrationId: 'gstin-1',
    placeOfSupply: 'IN-KA',
    partyLineKey: 'party-line',
    billReference: 'SB-1',
    keyFor: (pageKey) => {
      if (!keys.has(pageKey)) keys.set(pageKey, `uuid-${++counter}-${pageKey}`);
      return keys.get(pageKey)!;
    },
    roundOff: null,
    ...patch,
  };
}

function bill(line: Partial<DraftLine>, header: Partial<SalesDraft> = {}): SalesDraft {
  let draft = initialDraft(SAMPLE_SALES_POLICY, '2026-10-29');
  draft = reduceDraft(draft, { type: 'header', patch: { customerId: 'party-1', customerLabel: 'Nandini', creditDays: '30', ...header } });
  return reduceDraft(draft, {
    type: 'line',
    key: draft.lines[0]!.key,
    patch: { subjectId: SERVICE_ITEM, subjectLabel: 'Installation', subjectKind: 'ITEM', subjectNature: 'SERVICE', actualQuantity: '2', billedQuantity: '2', rate: '1500', ...line },
  });
}

describe('W4 the draft, as the service takes it', () => {
  it('writes a service bill: the item detail, its supply, the tax context and the terms', () => {
    const result = toVoucherInput(bill({}), refs());
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const body = result.body as Record<string, any>;
    expect(body).toMatchObject({
      type_revision_id: EVIDENCE.type_revision_id,
      document_date: '2026-10-29',
      posting_date: '2026-10-29',
      mode: 'ITEMS',
      currency: 'INR',
      parties: [{ role: 'CUSTOMER', party_id: 'party-1', source_version: 5 }],
    });
    expect(body.lines).toEqual([
      expect.objectContaining({
        line_kind: 'ITEM',
        item: { item_id: SERVICE_ITEM, item_version: 3, unit_id: UNIT, actual_quantity: '2', billed_quantity: '2' },
      }),
    ]);
    const invoice = body.invoice;
    expect(invoice).toMatchObject({
      party_line_key: 'party-line',
      party_account_id: 'receivable-1',
      party_account_version: 2,
      bill_reference: 'SB-1',
      due_date: '2026-11-28',
      tax: {
        profile: 'INDIA_DOMESTIC_SERVICE',
        company_registration_id: 'gstin-1',
        place_of_supply: 'IN-KA',
        service_completion_date: '2026-10-29',
      },
    });
    expect(invoice.supplies[0]).toMatchObject({
      account_id: 'svc-rev',
      supply_kind: 'SERVICE',
      amount: '3000',
      unit_price: '1500',
      // One identity: the contract refuses an item supply whose key is not its item line's.
      line_key: body.lines[0].line_key,
      item_line_key: body.lines[0].line_key,
      quantities: [
        { basis: 'ACTUAL', quantity: '2', unit_id: UNIT },
        { basis: 'BILLED', quantity: '2', unit_id: UNIT },
      ],
    });
  });

  it('refuses goods, because the service has no goods tax profile yet', () => {
    const result = toVoucherInput(bill({ subjectId: GOODS_ITEM, subjectNature: 'GOODS' }), refs());
    expect(result).toEqual({
      ok: false,
      problems: [
        'Line 1: goods cannot be billed through the service yet — its GST profile for goods is not released. Bill services or accounts.',
      ],
    });
  });

  it('writes discounts as staged components with their evidence, and the inclusive basis', () => {
    let draft = bill({ discountKind: 'PERCENT', discountInput: '10' }, { taxInclusive: true });
    draft = reduceDraft(draft, { type: 'addDiscount', scope: 'DOCUMENT' });
    draft = reduceDraft(draft, { type: 'discount', key: draft.discounts[0]!.key, patch: { kind: 'AMOUNT', input: '100' } });
    const result = toVoucherInput(draft, refs());
    if (!result.ok) throw new Error(result.problems.join(' '));
    const components = (result.body as any).invoice.components;
    expect(components).toHaveLength(2);
    expect(components[0]).toMatchObject({ purpose: 'DISCOUNT', scope: 'LINE', input_kind: 'PERCENT', value: '10', amount_basis: 'GROSS_INCL_TAX', source_evidence: 'Entered on the bill' });
    // The bill discount applies after the line's: it depends on it.
    expect(components[1]).toMatchObject({ scope: 'INVOICE', input_kind: 'FIXED', value: '100', dependencies: [components[0].component_key] });
    expect((result.body as any).invoice.supplies[0].price_basis).toBe('GROSS_INCL_TAX');
  });

  it('writes cash with no instrument, UPI with its reference, and advances as allocations', () => {
    let draft = bill({});
    draft = reduceDraft(draft, { type: 'addTender', mode: 'CASH', amount: '500' });
    draft = reduceDraft(draft, { type: 'addTender', mode: 'UPI', amount: '1000' });
    draft = reduceDraft(draft, { type: 'tender', key: draft.tenders[1]!.key, patch: { reference: 'UTR123' } });
    draft = reduceDraft(draft, { type: 'applyAdvance', sourceId: 'open-item-1', sourceLabel: 'Advance', available: '800', amount: '800' });
    const result = toVoucherInput(draft, refs());
    if (!result.ok) throw new Error(result.problems.join(' '));
    const invoice = (result.body as any).invoice;
    expect(invoice.tenders[0]).toMatchObject({ account_id: 'cash', tender: { mode: 'CASH', amount: '500', currency: 'INR' } });
    expect(invoice.tenders[0].tender).not.toHaveProperty('reference');
    expect(invoice.tenders[1]).toMatchObject({ account_id: 'bank', tender: { mode: 'UPI', reference: 'UTR123' } });
    expect(invoice.allocations).toEqual([
      expect.objectContaining({ debt: { line_key: 'party-line' }, credit: { item_id: 'open-item-1' }, amount: '800', currency: 'INR' }),
    ]);
  });

  it('sends the rounding to the gain or the loss account by its sign', () => {
    const gain = toVoucherInput(bill({}), refs({ roundOff: '0.40' }));
    const loss = toVoucherInput(bill({}), refs({ roundOff: '-0.40' }));
    expect(gain.ok && (gain.body as any).invoice).toMatchObject({ rounding_increment: '1', rounding_account_id: 'gain' });
    expect(loss.ok && (loss.body as any).invoice).toMatchObject({ rounding_account_id: 'loss' });
  });

  it('bills an untaxed account when the company has no GST registration', () => {
    const draft = reduceDraft(bill({}), { type: 'mode', mode: 'ACCOUNTS' });
    const accounts = reduceDraft(draft, {
      type: 'line',
      key: draft.lines[0]!.key,
      patch: { subjectId: ACCOUNT, subjectLabel: 'Consulting', subjectKind: 'ACCOUNT', rate: '2000' },
    });
    const result = toVoucherInput(accounts, refs({ companyRegistrationId: null }));
    if (!result.ok) throw new Error(result.problems.join(' '));
    const invoice = (result.body as any).invoice;
    expect(invoice.tax).toEqual({ profile: 'UNTAXED_ACCOUNT' });
    expect(invoice.supplies[0]).toMatchObject({ account_id: ACCOUNT, account_version: 4, supply_kind: 'ACCOUNT', amount: '2000' });
    expect((result.body as any).lines).toEqual([]);
  });

  it('says what is missing rather than inventing it', () => {
    const none = toVoucherInput(bill({}), refs({ customer: { partyId: 'party-1', partyVersion: 1, account: null } }));
    expect(none).toMatchObject({ ok: false, problems: ['This customer needs exactly one receivable account to be billed to, and has none or several. An administrator can repair it with the party ledger repair.'] });
    const nowhere = toVoucherInput(bill({}), refs({ placeOfSupply: null }));
    expect(nowhere).toMatchObject({ ok: false, problems: ['Choose the customer’s address: the place of supply is needed to tax a service.'] });
    const short = toVoucherInput(bill({ actualQuantity: '1' }), refs());
    expect(short).toMatchObject({ ok: false, problems: ['Line 1: a short supply cannot be recorded by the service yet. Bill what was supplied.'] });
  });

  it('keeps every key stable from one save to the next', () => {
    const shared = refs();
    const first = toVoucherInput(bill({}), shared);
    const second = toVoucherInput(bill({}), shared);
    expect(first.ok && second.ok && (first.body as any).lines[0].line_key).toBe(second.ok && (second.body as any).lines[0].line_key);
  });
});

describe('what the catalog answers', () => {
  it('reads a resolved price as a unit rate, exactly', () => {
    expect(priceRate({ status: 'RESOLVED', amount: '2450.0000', price_basis_quantity: '1' })).toBe('2450');
    expect(priceRate({ status: 'RESOLVED', amount: '100', price_basis_quantity: '12' })).toBe('8.3333');
    expect(priceRate({ status: 'MISSING', amount: null })).toBeNull();
  });

  it('reads the GST rate from IGST, or from its halves', () => {
    expect(taxPercent({ status: 'COMPLETE', rates: [{ components: [{ component: 'IGST', percentage: '18' }] }] })).toBe('18');
    expect(taxPercent({ status: 'COMPLETE', rates: [{ components: [{ component: 'CGST', percentage: '2.5' }, { component: 'SGST', percentage: '2.5' }] }] })).toBe('5');
    expect(taxPercent({ status: 'MISSING' })).toBeNull();
  });
});
