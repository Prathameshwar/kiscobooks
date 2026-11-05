/**
 * The draft, as the vouchers service takes it: `VoucherInput` with an `invoice` section.
 *
 * Pure, so every rule of the mapping is tested without a DOM or a network. It never invents a
 * fact the page does not hold — an income account, an item's version, a registration — and
 * where the service cannot take what the page holds, it says so as a sentence instead of
 * sending something that would be read as a different bill.
 *
 * Two rules the contract makes, and this follows:
 *
 *  - **Each line is a supply**, and an item line is also the common item detail
 *    (`lines[]`) the supply points at, with the same actual and billed quantities.
 *  - **Discounts and charges are components** with a scope, targets, the stages they apply
 *    after, and the evidence of where they came from. A typed discount's evidence is that it
 *    was typed: decision W-4 in `voucher-sales-entry-ui.md`.
 */
import * as D from './fixed-decimal';
import { isAccountLine, isBlank, type DraftLine, type SalesDraft } from './sales-entry-draft';
import { addDays } from './sales-entry-preview';
import type { TenderMode } from './sales-entry-policy';
import type { SalesBinding } from './sales-entry-connection';

export type AccountRef = { readonly id: string; readonly version: number };

/** What a chosen subject is, as the masters say — kept by the page beside the draft. */
export type SubjectRef =
  | {
      readonly kind: 'ITEM';
      readonly itemVersion: number;
      readonly unitId: string;
      readonly nature: 'GOODS' | 'SERVICE';
      /** The income account its sale is credited to. */
      readonly incomeAccount: AccountRef | null;
    }
  | { readonly kind: 'ACCOUNT'; readonly account: AccountRef };

export type CustomerRef = {
  readonly partyId: string;
  readonly partyVersion: number;
  /** The customer's receivable account: the invoice is a debit to it. */
  readonly account: AccountRef | null;
};

export type SaveRefs = {
  readonly binding: SalesBinding;
  readonly currency: string;
  readonly customer: CustomerRef | null;
  readonly subjects: ReadonlyMap<string, SubjectRef>;
  /** Where money received in each mode is recorded: cash in hand, a bank account. */
  readonly tenderAccounts: Partial<Record<TenderMode, AccountRef>>;
  readonly rounding: { readonly gain: AccountRef | null; readonly loss: AccountRef | null };
  /** The company's GST registration, and the place of supply as an ISO subdivision (`IN-KA`). */
  readonly companyRegistrationId: string | null;
  readonly placeOfSupply: string | null;
  /** The receivable line's key and the bill's reference, stable across saves of one draft. */
  readonly partyLineKey: string;
  readonly billReference: string;
  /** A stable UUID for a page key — a line, a discount, a tender — across saves. */
  readonly keyFor: (pageKey: string) => string;
  /** The rounding the preview applied, to say which account takes it. */
  readonly roundOff: string | null;
};

export type WireResult =
  | { readonly ok: true; readonly body: Record<string, unknown> }
  | { readonly ok: false; readonly problems: readonly string[] };

const FREE_PURPOSE: Record<string, 'GIFT' | 'SAMPLE'> = { Gift: 'GIFT', Sample: 'SAMPLE' };
const CHARGE_PURPOSE: Record<string, string> = {
  FREIGHT: 'FREIGHT',
  PACKING: 'PACKING',
  INSURANCE: 'INSURANCE',
  HANDLING: 'HANDLING',
  OTHER: 'OTHER_CHARGE',
};
/** The service's tender mode for the page's. A bank transfer is sent as one. */
const WIRE_MODE: Record<TenderMode, string> = {
  CASH: 'CASH',
  UPI: 'UPI',
  CARD: 'CARD',
  CHEQUE: 'CHEQUE',
  BANK_TRANSFER: 'BANK_TRANSFER',
};

/** Canonical decimal text, exactly — never through a float. */
const exact = (text: string) => {
  const value = D.parse(text.trim());
  return value === null ? null : D.format(value).replace(/\.?0+$/, '') || '0';
};

export function toVoucherInput(draft: SalesDraft, refs: SaveRefs): WireResult {
  const problems: string[] = [];
  const say = (message: string) => {
    if (!problems.includes(message)) problems.push(message);
  };
  const entered = draft.lines.filter((line) => !isBlank(line));

  /* ---- the tax context: which profile, and the facts it needs ---- */
  const profiles = new Set(refs.binding.taxProfiles);
  const serviceTax = profiles.has('INDIA_DOMESTIC_SERVICE') && refs.companyRegistrationId !== null;
  const profile = serviceTax ? 'INDIA_DOMESTIC_SERVICE' : profiles.has('UNTAXED_ACCOUNT') ? 'UNTAXED_ACCOUNT' : null;
  if (!profile) say('This company has no GST registration the service can bill services under, and the bill type takes no untaxed supplies.');
  if (serviceTax && !refs.placeOfSupply) say('Choose the customer’s address: the place of supply is needed to tax a service.');

  /* ---- the customer ---- */
  if (!refs.customer) say('Choose the customer.');
  else if (!refs.customer.account) say('This customer needs exactly one receivable account to be billed to, and has none or several. An administrator can repair it with the party ledger repair.');

  /* ---- lines: the common item detail, and a supply for each ---- */
  const items: Record<string, unknown>[] = [];
  const supplies: Record<string, unknown>[] = [];
  // One identity per line: an item line's supply *is* its common item line (the contract
  // requires `item_line_key == line_key`), so both use the line's key.
  const supplyKey = (line: DraftLine) => refs.keyFor(`line:${line.key}`);
  for (const line of entered) {
    const ordinal = draft.lines.indexOf(line) + 1;
    const subject = line.subjectId ? refs.subjects.get(line.subjectId) : undefined;
    if (!line.subjectId || !subject) {
      say(`Line ${ordinal}: choose what is sold.`);
      continue;
    }
    const account = isAccountLine(draft, line);
    if (!account && subject.kind === 'ITEM' && subject.nature === 'GOODS') {
      // The service's invoice tax profiles cover services and untaxed accounts; goods have none
      // yet (blocker B1). Sending goods under a service profile would claim a tax nobody computed.
      say(`Line ${ordinal}: goods cannot be billed through the service yet — its GST profile for goods is not released. Bill services or accounts.`);
      continue;
    }
    const rate = exact(line.rate);
    if (rate === null) continue; // the draft's own rules already say "Enter a rate."
    const description = (line.description || line.subjectLabel).trim() || 'Supply';
    const freeText = line.freePurpose ? FREE_PURPOSE[line.freePurpose] : undefined;
    if (line.freePurpose && !freeText) say(`Line ${ordinal}: “${line.freePurpose}” is not a free purpose the service records.`);

    if (subject.kind === 'ACCOUNT' || account) {
      const target = subject.kind === 'ACCOUNT' ? subject.account : subject.incomeAccount;
      if (!target) {
        say(`Line ${ordinal}: no income account to credit.`);
        continue;
      }
      supplies.push({
        line_key: supplyKey(line),
        account_id: target.id,
        account_version: target.version,
        supply_kind: profile === 'UNTAXED_ACCOUNT' ? 'ACCOUNT' : 'SERVICE',
        description,
        amount: rate,
        price_basis: draft.taxInclusive ? 'GROSS_INCL_TAX' : 'NET_EXCL_TAX',
        ...(freeText ? { free_purpose: freeText, free_reason: line.freePurpose } : {}),
      });
      continue;
    }

    // An item line — a service item, since goods stopped above.
    if (subject.kind !== 'ITEM') continue;
    if (!subject.incomeAccount) {
      say(`Line ${ordinal}: no income account to credit for this item.`);
      continue;
    }
    const billed = exact(line.billedQuantity);
    const actual = exact(line.actualQuantity || line.billedQuantity);
    if (billed === null || actual === null) continue;
    const more = D.parse(actual)! > D.parse(billed)!;
    const less = D.parse(actual)! < D.parse(billed)!;
    if (less) say(`Line ${ordinal}: a short supply cannot be recorded by the service yet. Bill what was supplied.`);
    const lineKey = supplyKey(line);
    items.push({
      line_key: lineKey,
      line_kind: 'ITEM',
      description,
      item: {
        item_id: line.subjectId,
        item_version: subject.itemVersion,
        unit_id: subject.unitId,
        actual_quantity: actual,
        billed_quantity: billed,
      },
    });
    supplies.push({
      line_key: supplyKey(line),
      account_id: subject.incomeAccount.id,
      account_version: subject.incomeAccount.version,
      supply_kind: profile === 'UNTAXED_ACCOUNT' ? 'ACCOUNT' : 'SERVICE',
      description,
      amount: exact(D.format(D.round(D.mul(D.parse(billed)!, D.parse(rate)!), 4))) ?? '0',
      price_basis: draft.taxInclusive ? 'GROSS_INCL_TAX' : 'NET_EXCL_TAX',
      item_line_key: lineKey,
      quantities: [
        { basis: 'ACTUAL', quantity: actual, unit_id: subject.unitId },
        { basis: 'BILLED', quantity: billed, unit_id: subject.unitId },
      ],
      unit_price: rate,
      // More leaving than billed is a paid bundle, with the reason as its source (draft only).
      ...(more ? { free_purpose: 'MANUAL_PAID_BUNDLE', free_reason: line.quantityReason || 'Bonus quantity' } : {}),
      ...(freeText && !more ? { free_purpose: freeText, free_reason: line.freePurpose } : {}),
    });
  }
  if (entered.length > 0 && supplies.length === 0 && problems.length === 0) say('Add at least one line the service can bill.');

  /* ---- components: line, then selected, then bill discounts; then charges ---- */
  const components: Record<string, unknown>[] = [];
  const basis = draft.taxInclusive ? 'GROSS_INCL_TAX' : 'NET_EXCL_TAX';
  const evidence = 'Entered on the bill';
  const lineDiscountKeys = new Map<string, string>();
  for (const line of entered) {
    const value = exact(line.discountInput);
    if (!line.discountInput.trim() || value === null || D.parse(value) === D.ZERO) continue;
    if (!supplies.some((supply) => supply.line_key === supplyKey(line))) continue;
    const key = refs.keyFor(`line-discount:${line.key}`);
    lineDiscountKeys.set(line.key, key);
    components.push({
      component_key: key,
      purpose: 'DISCOUNT',
      scope: 'LINE',
      effect: 'DEDUCT',
      input_kind: line.discountKind === 'PERCENT' ? 'PERCENT' : 'FIXED',
      value,
      targets: [supplyKey(line)],
      amount_basis: basis,
      source_evidence: evidence,
    });
  }
  const sent = new Set(supplies.map((supply) => supply.line_key as string));
  const earlier: string[] = [...lineDiscountKeys.values()];
  for (const scope of ['SELECTED', 'DOCUMENT'] as const) {
    for (const discount of draft.discounts.filter((entry) => entry.scope === scope)) {
      const value = exact(discount.input);
      if (value === null || D.parse(value) === D.ZERO) continue;
      const targets =
        scope === 'DOCUMENT'
          ? [...sent]
          : discount.lineKeys
              .map((key) => draft.lines.find((line) => line.key === key))
              .filter((line): line is DraftLine => !!line)
              .map(supplyKey)
              .filter((key) => sent.has(key));
      if (targets.length === 0) continue;
      const key = refs.keyFor(`discount:${discount.key}`);
      components.push({
        component_key: key,
        purpose: 'DISCOUNT',
        scope: scope === 'DOCUMENT' ? 'INVOICE' : 'SELECTED_LINES',
        effect: 'DEDUCT',
        input_kind: discount.kind === 'PERCENT' ? 'PERCENT' : 'FIXED',
        value,
        targets,
        // Each stage applies to what the stages before it left (calculation §4).
        dependencies: [...earlier],
        amount_basis: basis,
        source_evidence: evidence,
      });
      earlier.push(key);
    }
  }
  for (const charge of draft.charges) {
    const value = exact(charge.amount);
    if (value === null || D.parse(value) === D.ZERO || sent.size === 0) continue;
    components.push({
      component_key: refs.keyFor(`charge:${charge.key}`),
      purpose: CHARGE_PURPOSE[charge.purpose] ?? 'OTHER_CHARGE',
      scope: 'INVOICE',
      effect: 'ADD',
      input_kind: 'FIXED',
      value,
      targets: [...sent],
      source_evidence: charge.label.trim() || evidence,
    });
  }

  /* ---- settlement: money received now, and advances applied ---- */
  const tenders: Record<string, unknown>[] = [];
  for (const tender of draft.tenders) {
    const amount = exact(tender.amount);
    if (amount === null) continue;
    const account = refs.tenderAccounts[tender.mode];
    if (!account) {
      say(`There is no account to receive ${tender.mode === 'CASH' ? 'cash' : 'this payment'} into. Set one up in the chart of accounts.`);
      continue;
    }
    tenders.push({
      account_id: account.id,
      account_version: account.version,
      tender: {
        tender_key: refs.keyFor(`tender:${tender.key}`),
        // Tenders into one account share its line, as the service books them.
        line_key: refs.keyFor(`tender-account:${account.id}`),
        mode: WIRE_MODE[tender.mode],
        amount,
        currency: refs.currency,
        // Cash carries no instrument; everything else carries its reference.
        ...(tender.mode === 'CASH' ? {} : { reference: tender.reference.trim() || null }),
        ...(tender.mode === 'CHEQUE' && tender.instrumentDate ? { instrument_date: tender.instrumentDate } : {}),
      },
    });
  }
  const allocations = draft.advances
    .map((advance) => ({ advance, amount: exact(advance.amount) }))
    .filter((entry) => entry.amount !== null && D.parse(entry.amount!) !== D.ZERO)
    .map(({ advance, amount }) => ({
      allocation_key: refs.keyFor(`advance:${advance.key}`),
      debt: { line_key: refs.partyLineKey },
      credit: { item_id: advance.sourceId },
      amount,
      currency: refs.currency,
    }));

  /* ---- rounding ---- */
  const roundOff = refs.roundOff === null ? null : D.parse(refs.roundOff);
  const roundingAccount =
    roundOff === null || roundOff === D.ZERO ? null : roundOff > D.ZERO ? refs.rounding.gain : refs.rounding.loss;
  if (roundOff !== null && roundOff !== D.ZERO && !roundingAccount) {
    say('There is no round-off account to take the rounding. Set one up in the chart of accounts.');
  }

  if (problems.length > 0) return { ok: false, problems };

  const due =
    /^\d{1,3}$/.test(draft.creditDays.trim()) && draft.documentDate
      ? addDays(draft.documentDate, Number(draft.creditDays))
      : draft.documentDate;

  return {
    ok: true,
    body: {
      type_revision_id: refs.binding.typeRevisionId,
      ...(refs.binding.classId ? { class_id: refs.binding.classId } : {}),
      document_date: draft.documentDate,
      posting_date: draft.postingDate,
      mode: draft.mode,
      currency: refs.currency,
      parties: [{ role: 'CUSTOMER', party_id: refs.customer!.partyId, source_version: refs.customer!.partyVersion }],
      lines: items,
      invoice: {
        party_line_key: refs.partyLineKey,
        party_account_id: refs.customer!.account!.id,
        party_account_version: refs.customer!.account!.version,
        bill_reference: refs.billReference,
        due_date: due,
        tax: {
          profile,
          ...(serviceTax
            ? {
                company_registration_id: refs.companyRegistrationId,
                place_of_supply: refs.placeOfSupply,
                service_completion_date: draft.supplyDate || draft.documentDate,
              }
            : {}),
        },
        supplies,
        components,
        tenders,
        allocations,
        ...(roundingAccount
          ? { rounding_increment: '1', rounding_account_id: roundingAccount.id, rounding_account_version: roundingAccount.version }
          : {}),
      },
    },
  };
}
