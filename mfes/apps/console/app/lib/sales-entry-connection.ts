/**
 * The sales bill page, connected: what the vouchers service says a Sales bill may be, read into
 * the shape the page renders from.
 *
 * The page was built against `SalesEntryPolicy` — a proposal for the per-control effective
 * policy the Sales configuration plan says the service should expose (§3). The service exposes
 * the coarser `InvoicePolicy` today. This adapter maps one onto the other, and **every control
 * the service does not decide is taken from the page's own defaults and named here**, so the
 * difference is reviewable in one place rather than discovered later.
 */
import {
  isAvailable,
  type Control,
  type EntryMode,
  type SalesEntryPolicy,
  type TenderMode,
} from './sales-entry-policy';

/** `InvoicePolicy` as it travels on the wire (`voucher_execution.invoice`), the fields read here. */
export type WireInvoicePolicy = {
  readonly allowed_supply_kinds?: readonly ('GOODS' | 'SERVICE' | 'ACCOUNT')[];
  readonly allowed_price_bases?: readonly ('NET_EXCL_TAX' | 'GROSS_INCL_TAX')[];
  readonly manual_discounts_allowed?: boolean;
  readonly discount_input_kinds?: readonly ('FIXED' | 'PERCENT' | 'PER_QUANTITY')[];
  readonly max_discount_pct?: string | number;
  readonly charges_allowed?: boolean;
  readonly manual_free_allowed?: boolean;
  readonly sales_supply_account_ids?: readonly string[] | null;
  readonly sales_party_account_ids?: readonly string[] | null;
  readonly sales_tax_profiles?: readonly string[];
  readonly sales_discount_scopes?: readonly ('LINE' | 'SELECTED_LINES' | 'INVOICE')[];
  readonly sales_charge_purposes?: readonly string[];
  readonly sales_tender_modes?: readonly string[];
  readonly sales_credit_allowed?: boolean;
  readonly sales_split_tenders_allowed?: boolean;
  readonly sales_advance_adjustments_allowed?: boolean;
  readonly sales_invoice_rounding_allowed?: boolean;
};

/** The evidence `GET /voucher-types/{id}/effective-configuration` returns. */
export type EffectiveConfiguration = {
  readonly type_revision_id: string;
  readonly class_id: string | null;
  readonly policy_revision_ids?: readonly string[];
  readonly policy: {
    readonly invoice?: WireInvoicePolicy | null;
    readonly allowed_modes?: readonly EntryMode[];
    readonly default_mode?: EntryMode;
  };
  readonly kind: string;
  readonly profile: string;
  readonly digest: string;
};

const off = (reason: string) => ({ available: false, reason }) as const;
const on = <T = string,>(base: Control<T>, editable = true): Control<T> =>
  isAvailable(base) ? { ...base, editable } : { available: true, required: false, editable };

/** The page's tender modes, against the service's. NEFT, RTGS and IMPS are bank transfers to a reader. */
const TENDER: Record<string, TenderMode> = {
  CASH: 'CASH',
  UPI: 'UPI',
  CARD: 'CARD',
  CHEQUE: 'CHEQUE',
  BANK_TRANSFER: 'BANK_TRANSFER',
  NEFT: 'BANK_TRANSFER',
  RTGS: 'BANK_TRANSFER',
  IMPS: 'BANK_TRANSFER',
};

/**
 * The service's answer, as the page's policy.
 *
 * `base` supplies what the service does not decide yet, each named below: price levels, the
 * rate-override rule and its approval threshold, quantity-difference reasons, free-item
 * purposes, and the document's numbering preview. The statutory surfaces and issuance stay
 * unavailable, because Sales issuance is refused by the service (open question 1).
 */
export function policyFromConfiguration(evidence: EffectiveConfiguration, base: SalesEntryPolicy): SalesEntryPolicy {
  const invoice = evidence.policy.invoice ?? {};
  const kinds = new Set(invoice.allowed_supply_kinds ?? ['GOODS', 'SERVICE', 'ACCOUNT']);
  const itemLines = kinds.has('GOODS') || kinds.has('SERVICE');
  const accountLines = kinds.has('ACCOUNT');
  const supplyModes: EntryMode[] = [
    ...(itemLines ? (['ITEMS'] as const) : []),
    ...(accountLines ? (['ACCOUNTS'] as const) : []),
    ...(itemLines && accountLines ? (['MIXED'] as const) : []),
  ];
  const modes = supplyModes.filter(mode => !evidence.policy.allowed_modes || evidence.policy.allowed_modes.includes(mode));
  if (!modes.length) throw new Error('This bill type has no supported entry mode. Review its configuration.');
  const configuredDefault = evidence.policy.default_mode;
  const defaultMode = configuredDefault && modes.includes(configuredDefault) ? configuredDefault : modes[0]!;
  const scopes = new Set(invoice.sales_discount_scopes ?? ['LINE', 'SELECTED_LINES', 'INVOICE']);
  const discounts = invoice.manual_discounts_allowed === true;
  const noDiscount = 'This bill type does not take discounts typed on the bill.';
  const discount = (scope: 'LINE' | 'SELECTED_LINES' | 'INVOICE', control: Control) =>
    discounts && scopes.has(scope) ? on(control) : off(noDiscount);
  const tenderModes = [
    ...new Set((invoice.sales_tender_modes ?? []).map((mode) => TENDER[mode]).filter((mode): mode is TenderMode => !!mode)),
  ];

  return {
    ...base,
    source: {
      companyPolicyRevisionId: evidence.policy_revision_ids?.[0] ?? '',
      typeRevisionId: evidence.type_revision_id,
      classRevisionId: evidence.class_id,
      digest: evidence.digest,
    },
    modes: { allowed: modes, default: defaultMode },
    numbering: { ...base.numbering, preview: null },
    pricing: {
      ...base.pricing,
      taxInclusiveEntry: (invoice.allowed_price_bases ?? ['NET_EXCL_TAX', 'GROSS_INCL_TAX']).includes('GROSS_INCL_TAX')
        ? on(base.pricing.taxInclusiveEntry)
        : off('This bill type takes rates before tax.'),
    },
    quantities: {
      ...base.quantities,
      freeItem: invoice.manual_free_allowed
        ? on(base.quantities.freeItem)
        : off('A free line needs its own authorisation; this bill type does not allow one.'),
    },
    components: {
      ...base.components,
      lineDiscount: discount('LINE', base.components.lineDiscount),
      selectedLineDiscount: discount('SELECTED_LINES', base.components.selectedLineDiscount),
      documentDiscount: discount('INVOICE', base.components.documentDiscount),
      charges: invoice.charges_allowed ? on(base.components.charges) : off('This bill type does not take charges.'),
      rounding: invoice.sales_invoice_rounding_allowed === false
        ? off('This bill type is not rounded.')
        : { available: true, required: false, editable: false, default: 'NEAREST_1' },
    },
    settlement: {
      ...base.settlement,
      credit: invoice.sales_credit_allowed === false ? off('This bill type is paid in full when it is raised.') : on(base.settlement.credit),
      immediateTender: tenderModes.length > 0 ? on(base.settlement.immediateTender) : off('This bill type records no payment at billing.'),
      splitTender: invoice.sales_split_tenders_allowed === false
        ? off('This bill type takes one payment mode.')
        : { available: true, required: false, editable: true, default: false },
      advanceApplication: invoice.sales_advance_adjustments_allowed === false
        ? off('This bill type does not apply advances.')
        : on(base.settlement.advanceApplication),
      tenderModes,
      // A non-cash reference is recorded when given and never demanded (`money.Tender`, 0.3.10).
      referenceRequired: [],
    },
  };
}

/** What a connected bill keeps beside its policy: the type it is raised under, and its pins. */
export type SalesBinding = {
  readonly typeId: string;
  readonly typeName: string;
  readonly typeRevisionId: string;
  readonly classId: string | null;
  readonly digest: string;
  readonly taxProfiles: readonly string[];
  readonly supplyAccountIds: readonly string[] | null;
  readonly partyAccountIds: readonly string[] | null;
};

export function bindingFrom(evidence: EffectiveConfiguration, type: { id: string; name?: string }): SalesBinding {
  const invoice = evidence.policy.invoice ?? {};
  return {
    typeId: type.id,
    typeName: type.name ?? 'Sales',
    typeRevisionId: evidence.type_revision_id,
    classId: evidence.class_id,
    digest: evidence.digest,
    taxProfiles: invoice.sales_tax_profiles ?? ['INDIA_DOMESTIC_SERVICE', 'INDIA_DOMESTIC_SERVICE_RCM', 'UNTAXED_ACCOUNT'],
    supplyAccountIds: invoice.sales_supply_account_ids ?? null,
    partyAccountIds: invoice.sales_party_account_ids ?? null,
  };
}
