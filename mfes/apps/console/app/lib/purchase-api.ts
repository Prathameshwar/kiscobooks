import type { components } from '@janso/api-client/vouchers';
import { buildPurchase, nativeProperties, purchaseAvailability, purchaseGoodsAllowed, purchaseModes, purchaseStockAccess, type PurchaseSource, type PurchaseTaxWire } from './purchase-entry';
import { goodsLine, PURCHASE_GOODS_LINE_LIMIT, type PurchaseGoodsContext, type PurchaseItem, type PurchaseRounding } from './purchase-goods';
import { choiceOfProfile, isTaxed, noTaxFacts, purchaseTaxContext, TAX_PROFILES, type PurchaseTaxFacts } from './purchase-tax';
import { blankPurchaseLine, isBlankPurchaseLine, newPurchaseWorkspace, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from './purchase-workspace';
import { purchaseDueDate, purchaseOrderedComponents } from './purchase-workspace-details';
import { trackingId } from './stock-tracking-resources';
import type { FieldSet } from './voucher-fields';
import type { ServiceRequest } from './service-call';
import * as D from './fixed-decimal';
import {componentDependencies,componentEvidence,componentRecipeProblem,readComponentEvidence,readCalculationPolicy,type PurchaseCalculationPolicy} from './purchase-calculation';
import { purchaseStockLine, type PurchaseTracking } from './purchase-stock';
import type {PurchaseComponent} from './purchase-workspace-details';

export type PurchaseVoucher = components['schemas']['VoucherDetail'];
export type PurchaseInput = components['schemas']['VoucherInput'];
export type PurchaseCalculation = components['schemas']['InvoiceCalculationDetail'];
export type PurchaseCapabilities = { financial_execution: boolean; invoice_execution: boolean; purchase_supporting_files?: boolean; kinds: { kind: string; execution_ready: boolean }[] };
export type PurchaseAdvance = { id: string; company: string; supplier: string; payable: string; currency: string; remaining: string; label: string; asOf: string };
export type PurchasePaymentAccount = { id: string; company: string; version: number; currency: string; method: 'BANK' | 'CASH'; label: string };
export type PurchaseBinding = { company: string; currency: string; metadata: FieldSet; sources: Map<string, PurchaseSource>; keys: Map<string, string>; partyKey: string; previous?: PurchaseInput; advances?: Map<string, PurchaseAdvance>; paymentAccounts?: Map<string, PurchasePaymentAccount>;
  /** B24: verified products by id, where goods post and land, and the company's amount rounding. */
  items?: Map<string, PurchaseItem>; goods?: PurchaseGoodsContext; rounding?: PurchaseRounding;
  tracking?: Map<string, PurchaseTracking> };
function refuse(message: string): never { throw new Error(message); }
/** A saved Purchase this screen does not capture (goods, quantities, stock, other tax profiles). */
export const PURCHASE_BROADER_CAPTURE = 'This capture requires a broader Purchase profile. Its saved facts remain available in voucher review.';
/** The GST profile of a bill for purchased goods: supplier-charged, taxed on the invoice date. */
const GOODS_PROFILE = 'INDIA_DOMESTIC_GOODS';
type SavedStock = { action?: string; stock_date?: string; lines?: { line_id: string; item_id: string; warehouse_id: string; quantity: string | number; [key: string]: unknown }[] };
/** The stock identities this direct-bill screen can capture and save back unchanged. */
const STOCK_LINE_FIELDS = new Set(['line_id', 'item_id', 'warehouse_id', 'quantity', 'bin_id', 'lot_id', 'unit_ids']);
const positiveVersion = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
const decimal = (value: unknown): value is string => typeof value === 'string' && /^-?(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/.test(value) && D.parse(value) !== null;
function savedDecimal(value: unknown): string {
  // The service serializes DECIMAL(19,4) values with extra zero scale. Strip only
  // zeroes: a saved value with nonzero precision beyond the editor's scale is unsafe to edit.
  if (typeof value !== 'string' || !/^-?(?:0|[1-9]\d{0,14})(?:\.\d+)?$/.test(value)) refuse(PURCHASE_BROADER_CAPTURE);
  const normalized = value.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
  if (!decimal(normalized)) refuse(PURCHASE_BROADER_CAPTURE);
  return D.format(D.parse(normalized)!);
}
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export function purchaseBase(company: string): string {
  if (!trackingId.test(company)) refuse('A valid company is required.');
  return `/v1/companies/${company}`;
}
export function verifyPurchaseVoucher(value: PurchaseVoucher, company: string, expected?: { id?: string; type?: string; version?: number; revision?: string }): void {
  if (!value || value.company_id !== company || !trackingId.test(value.id) || value.kind !== 'PURCHASE' || value.profile !== 'STANDARD' || !trackingId.test(value.type_revision_id) || !trackingId.test(value.revision_id) || !positiveVersion(value.row_version) || !positiveVersion(value.revision_number) || !['DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'CANCELLED', 'POSTED', 'REVERSED'].includes(value.status)) refuse('The Purchase response could not be verified for this company.');
  if (expected?.id && value.id !== expected.id || expected?.type && value.type_revision_id !== expected.type || expected?.version !== undefined && value.row_version <= expected.version || expected?.revision && value.revision_id === expected.revision) refuse('The Purchase response does not match the requested record or new revision. Refresh before continuing.');
}
export function verifyPurchaseCalculation(value: PurchaseCalculation, currency: string): void {
  if (!value || !hash(value.calculation_hash) || value.currency !== currency || ![value.commercial_total, value.tax_total, value.payable, value.rounding, value.charged_tax_total].every(decimal) || value.supplier_difference != null && !decimal(value.supplier_difference) || !Array.isArray(value.lines) || !Array.isArray(value.tax_evidence)) refuse('Accounting calculation evidence could not be verified.');
}
function writable(metadata: FieldSet, field: string): void {
  const parts = field.split('.'); let node = metadata.native;
  for (const part of parts) {
    if (node.readOnly) refuse(`Write access to ${field} is required.`);
    const next = nativeProperties(node)[part];
    if (!next || next.readOnly) refuse(`Write access to ${field} is required.`);
    node = next;
  }
}
export function purchaseWireKey(binding: PurchaseBinding, key: string): string {
  if (trackingId.test(key)) return key;
  let value = binding.keys.get(key);
  if (!value) { value = crypto.randomUUID(); binding.keys.set(key, value); }
  return value;
}
/**
 * Presentation state is mapped explicitly; no provisional total or fixture tax crosses the boundary.
 *
 * `facts` are the masters the tax choice was made against. A bill not yet decided (`''`) is untaxed here: the page
 * refuses to save it before it gets this far, and a saved untaxed bill must keep round-tripping as it always has.
 */
export function purchaseInput(draft: PurchaseWorkspaceDraft, binding: PurchaseBinding, facts: PurchaseTaxFacts = noTaxFacts()): PurchaseInput {
  const { company, currency, metadata, sources } = binding;
  const unavailable = purchaseAvailability(metadata); if (unavailable) refuse(unavailable);
  if (!purchaseModes(metadata).includes(draft.mode)) refuse('This Purchase entry mode is not allowed by the selected voucher type. Choose an available mode.');
  const goodsLines = draft.lines.filter(line => !isBlankPurchaseLine(line) && line.kind === 'ITEM');
  if (draft.mode === 'ACCOUNTS' ? goodsLines.length > 0 : !purchaseGoodsAllowed(metadata)) refuse('This Purchase type records account and service bills; choose a Product or Mixed Purchase type for goods.');
  if (draft.mode === 'ITEMS' && draft.lines.some(line => !isBlankPurchaseLine(line) && line.kind !== 'ITEM')) refuse('A product bill has product lines only; choose Mixed to add expense or service lines.');
  if (draft.mode !== 'ACCOUNTS' && !goodsLines.length) refuse('Add at least one product line, or choose Accounts / services.');
  if (goodsLines.length > PURCHASE_GOODS_LINE_LIMIT) refuse('A bill brings in at most ' + PURCHASE_GOODS_LINE_LIMIT + ' product lines; split it into two bills.');
  if (goodsLines.length && (!binding.goods || !binding.rounding)) refuse('The company’s stock accounts and purchase warehouse are not ready. Refresh, or set them up under Inventory before billing goods.');
  if (draft.details.receiptIntent !== 'DIRECT' || draft.details.receipts.length || Object.keys(draft.details.tracking).length || draft.details.attachments.length) refuse('This bill contains receipt or file instructions that this connected profile cannot save.');
  if (draft.details.comparison === 'SUPPLIER_REVISED') refuse('Record the supplier revision as a new supplier reference before changing the declared amount.');
  const due = purchaseDueDate(draft); if (!due) refuse('Enter valid credit terms.');
  const active = draft.lines.filter(line => !isBlankPurchaseLine(line));
  const accountLines = active.filter(line => line.kind !== 'ITEM');
  if (accountLines.length && !isTaxed(draft.tax) && metadata.configuration.policy.invoice?.allowed_supply_kinds && !metadata.configuration.policy.invoice.allowed_supply_kinds.includes('ACCOUNT')) refuse('This Purchase type does not allow untaxed account lines. Choose a type with Account supplies or use a supported taxed service bill.');
  const service: PurchaseTaxWire | undefined = isTaxed(draft.tax)
    ? { context: purchaseTaxContext({ tax: draft.tax, invoiceDate: draft.invoiceDate, invoice: draft.invoice, supplier: draft.supplier, facts }), supplyKind: 'SERVICE' }
    : undefined;
  if (service && goodsLines.length && service.context.profile !== TAX_PROFILES.FORWARD) refuse('Reverse charge is recorded on service bills; record this goods bill with GST charged by the supplier.');
  // A goods bill's header is the goods GST profile; any service line beside it carries its own service context.
  const goodsContext: PurchaseTaxWire['context'] | undefined = service && goodsLines.length
    ? { ...service.context, profile: GOODS_PROFILE, service_completion_date: null } : undefined;
  const tax: PurchaseTaxWire | undefined = goodsContext ? { context: goodsContext, supplyKind: accountLines.length ? 'SERVICE' : 'ACCOUNT' } : service;
  const built = buildPurchase(company, {
    party: sources.get(draft.supplier) ?? null, payable: sources.get(draft.payable) ?? null, partyLineKey: binding.partyKey,
    reference: draft.invoice, dueDate: due!, declaredTotal: draft.details.declaredTotal,
    supplies: accountLines.map(line => ({ key: purchaseWireKey(binding, line.key), account: sources.get(line.subject) ?? null, description: line.description.trim() || line.label, amount: line.amount })),
  }, draft.invoiceDate, metadata, tax, goodsLines.length);
  if (goodsContext && service) built.invoice!.supplies = built.invoice!.supplies.map(line => ({ ...line, tax: service.context }));
  const commonLines: NonNullable<PurchaseInput['lines']> = [];
  const stockLines: NonNullable<NonNullable<PurchaseInput['stock']>['lines']> = [];
  const usedSerials = new Set<string>();
  const stockAccess = purchaseStockAccess(metadata);
  const goodsSupplies = goodsLines.map(line => {
    const index = active.indexOf(line), item = binding.items?.get(line.subject);
    const checked = goodsLine(line, item, binding.rounding!, index), key = purchaseWireKey(binding, line.key);
    const description = (line.description.trim() || item!.label).slice(0, 1000);
    commonLines.push({ line_key: key, line_kind: 'ITEM', description, item: { item_id: item!.id, item_version: item!.version, unit_id: item!.baseUnitId, actual_quantity: checked.quantity, billed_quantity: checked.quantity } } as NonNullable<PurchaseInput['lines']>[number]);
    const profile = binding.tracking?.get(item!.id);
    if (!profile || profile.companyId !== company || !trackingId.test(profile.profileRevisionId)) refuse(`Purchase line ${index + 1}: product tracking requirements could not be verified.`);
    const stock = purchaseStockLine(line, binding.goods!.warehouse, profile, usedSerials, index + 1);
    if ((stock.binId && !stockAccess.bin) || (stock.lotId && !stockAccess.batch) || (stock.unitIds.length > 0 && !stockAccess.serial)) refuse(`Purchase line ${index + 1}: write access to its selected bin, batch or serials is required.`);
    stockLines.push({ line_id: key, item_id: item!.id, warehouse_id: stock.warehouseId, quantity: checked.quantity,
      ...(stock.binId ? { bin_id: stock.binId } : {}), ...(stock.lotId ? { lot_id: stock.lotId } : {}), ...(stock.unitIds.length ? { unit_ids: stock.unitIds } : {}) });
    return { line_key: key, item_line_key: key, account_id: binding.goods!.inventory.id, account_version: binding.goods!.inventory.version, supply_kind: 'GOODS' as const, description, amount: checked.amount, unit_price: checked.rate, price_basis: 'NET_EXCL_TAX' as const,
      quantities: [{ basis: 'ACTUAL' as const, quantity: checked.quantity, unit_id: item!.baseUnitId }, { basis: 'BILLED' as const, quantity: checked.quantity, unit_id: item!.baseUnitId }] };
  });
  if (usedSerials.size > 1000) refuse('A Purchase bill can receive at most 1,000 serials. Split the bill.');
  // Lines keep the order the person entered them in, goods and services together.
  const order = new Map(active.map((line, index) => [purchaseWireKey(binding, line.key), index]));
  built.invoice!.supplies = [...built.invoice!.supplies, ...goodsSupplies].sort((a, b) => order.get(a.line_key)! - order.get(b.line_key)!);
  const components: NonNullable<PurchaseInput['invoice']>['components'] = [];
  const policy = metadata.configuration.policy.invoice!;
  const preceding:PurchaseComponent[]=[];
  const rowDiscountKeys=active.filter(line=>(D.parse(line.discount)??0n)>0n).map(line=>'discount:'+line.key);
  if(draft.details.components.length||rowDiscountKeys.length||binding.previous?.invoice?.components?.length)writable(metadata,'invoice.components');
  const add = (key: string, purpose: NonNullable<NonNullable<PurchaseInput['invoice']>['components']>[number]['purpose'], value: string, targets: string[], input: 'FIXED' | 'PERCENT', label: string, assessable = true,component?:PurchaseComponent) => {
    writable(metadata, 'invoice.components');
    if (purpose === 'DISCOUNT' ? !policy.manual_discounts_allowed : !policy.charges_allowed) refuse('This adjustment is not allowed by the effective Purchase policy.');
    if (!decimal(value) || D.parse(value)! < 0n || !label.trim() || label.length > 500) refuse('Enter a valid adjustment and its description.');
    const problem=component&&componentRecipeProblem(component,preceding,rowDiscountKeys);
    if(problem)refuse(problem);
    const dependencies=component?componentDependencies(component,preceding,rowDiscountKeys).map(id=>purchaseWireKey(binding,id)):[];
    components.push({ component_key: purchaseWireKey(binding, key), purpose, effect: purpose === 'DISCOUNT' ? 'DEDUCT' : 'ADD', scope: component?.scope??(targets.length === 1 ? 'LINE' : 'SELECTED_LINES'), input_kind: input, value, targets, dependencies, amount_basis:component?.amountBasis?? 'NET_EXCL_TAX', allocation_basis: 'VALUE', commercial_treatment: 'COUNTERPARTY', tax_treatment: assessable ? 'ASSESSABLE' : 'NO_CHANGE', source_evidence: component?componentEvidence(component):label.trim() });
    if(component)preceding.push(component);
  };
  for (const line of active) {
    const amount = D.parse(line.discount);
    if (amount === null || amount < 0n) refuse('Enter a valid line discount.');
    if (amount > 0n) add('discount:' + line.key, 'DISCOUNT', D.format(amount), [purchaseWireKey(binding, line.key)], 'FIXED', 'Line discount: ' + (line.description || line.label).slice(0, 470));
  }
  for (const component of purchaseOrderedComponents(draft.details.components)) {
    if (!component.payable || component.taxTreatment === 'UNRESOLVED') refuse('Adjustments require a supported counterparty and tax treatment.');
    const targets = (component.targets.length ? component.targets : active.map(line => line.key)).map(key => {
      if (!active.some(line => line.key === key)) refuse('Adjustment references a removed line.');
      return purchaseWireKey(binding, key);
    });
    add(component.id, component.purpose??(component.kind === 'DISCOUNT' ? 'DISCOUNT' : 'OTHER_CHARGE'), component.value, targets, component.basis === 'PERCENT' ? 'PERCENT' : 'FIXED', component.label, component.taxTreatment === 'INCLUDED',component);
  }
  writable(metadata, 'document_date'); writable(metadata, 'currency');
  const old = binding.previous;
  const parties = (old?.parties ?? []).filter(row => row.role !== 'SUPPLIER');
  const references = (old?.references ?? []).filter(row => row.purpose !== 'SUPPLIER_INVOICE' || row.reference !== old?.invoice?.bill_reference);
  const result: PurchaseInput = { ...old, ...built, parties: [...parties, ...built.parties!], references: [...references, ...built.references!], type_revision_id: metadata.configuration.type_revision_id, document_date: draft.invoiceDate, posting_date: draft.postingDate, currency, invoice: { ...old?.invoice, ...built.invoice!, components, accepted_calculation_hash: null } };
  if (goodsLines.length) {
    // B24: the bill brings its goods in on its posting date; Accounting values them at landed cost.
    writable(metadata, 'lines'); writable(metadata, 'stock');
    result.mode = draft.mode;
    result.lines = commonLines; result.stock_date = draft.postingDate;
    result.stock = { action: 'PURCHASE_INVOICE', stock_date: draft.postingDate, currency, reason: ('Supplier bill ' + draft.invoice.trim()).slice(0, 500), lines: stockLines } as PurchaseInput['stock'];
  } else if (old?.lines?.length || old?.stock_date) {
    // A goods bill turned into an account bill no longer brings anything in.
    writable(metadata, 'lines'); result.mode = 'ACCOUNTS'; result.lines = []; result.stock_date = null; result.stock = null;
  } else result.mode = 'ACCOUNTS';
  const differenceReason = draft.details.comparisonReason.trim();
  if (differenceReason.length > 500) refuse('Use at most 500 characters for the supplier-total difference reason.');
  if (differenceReason !== (old?.invoice?.supplier_difference_reason ?? '')) writable(metadata, 'invoice.supplier_difference_reason');
  result.invoice!.supplier_difference_reason = differenceReason || null;
  // An emptied supplier total must be sent as empty: the spread above would keep the saved one. Clearing is a write.
  if (!draft.details.declaredTotal && old?.invoice?.supplier_declared_total != null) { writable(metadata, 'invoice.supplier_declared_total'); result.invoice!.supplier_declared_total = null; }
  const roundingId = draft.details.roundingAccount ?? '';
  if (roundingId !== (old?.invoice?.rounding_account_id ?? '')) {
    writable(metadata, 'invoice.rounding_account_id'); writable(metadata, 'invoice.rounding_account_version');
  }
  if (roundingId) {
    const account = sources.get(roundingId);
    if (!account || account.company !== company || !positiveVersion(account.version) || account.partyId || [draft.supplier, draft.payable].includes(roundingId)) refuse('Select a verified rounding account for this company.');
    result.invoice!.rounding_account_id = account.id; result.invoice!.rounding_account_version = account.version;
  } else if (old?.invoice?.rounding_account_id) {
    result.invoice!.rounding_account_id = null; result.invoice!.rounding_account_version = null;
  }
  if (metadata.native.properties?.credit_terms_date) {
    const basisDate = draft.details.termsBasis === 'POSTING_DATE' ? draft.postingDate : draft.invoiceDate;
    if (old?.credit_terms_date !== basisDate) writable(metadata, 'credit_terms_date');
    result.credit_terms_date = basisDate;
  } else if (draft.details.termsBasis === 'POSTING_DATE') refuse('Posting-date credit terms need readable credit-terms-date access.');
  if (draft.details.advances.length) {
    writable(metadata, 'invoice.allocations');
    const seen = new Set<string>();
    result.invoice!.allocations = draft.details.advances.map(selected => {
      const source = binding.advances?.get(selected.id), amount = typeof selected.amount === 'string' && decimal(selected.amount) ? D.parse(selected.amount) : null;
      if (!source || seen.has(selected.id) || source.company !== company || source.supplier !== draft.supplier || source.payable !== draft.payable || source.currency !== currency || source.asOf !== draft.postingDate || amount === null || amount <= 0n || amount > D.parse(source.remaining)!) refuse('This bill cannot save an unverified or excessive supplier advance. Refresh eligible advances and review the selection.');
      seen.add(selected.id);
      return { allocation_key: purchaseWireKey(binding, 'advance:' + selected.id), debt: { line_key: binding.partyKey }, credit: { item_id: selected.id }, amount: selected.amount, currency };
    });
  }
  const payment = draft.details.payment;
  if (!decimal(payment.amount) || D.parse(payment.amount)! < 0n) refuse('Enter a valid proposed payment amount.');
  if (D.parse(payment.amount)! > 0n) {
    writable(metadata, 'invoice.tenders');
    const account = binding.paymentAccounts?.get(payment.account);
    if (!account || account.company !== company || account.currency !== currency || account.method !== payment.method) refuse('Refresh and select a verified payment account for this company and currency.');
    result.invoice!.tenders = [{ account_id: account.id, account_version: account.version, tender: { tender_key: purchaseWireKey(binding, 'payment:tender'), line_key: purchaseWireKey(binding, 'payment:line'), mode: payment.method === 'CASH' ? 'CASH' : 'BANK_TRANSFER', amount: payment.amount, currency, recognition: 'BOOK_DATE', ...(payment.reference.trim() ? { reference: payment.reference.trim() } : {}) } }];
  }
  if (draft.details.notes !== (binding.previous?.narration ?? '')) { writable(metadata, 'narration'); result.narration = draft.details.notes; }
  const attachments = (draft.details.supportingFiles ?? []).map(file => ({ object_key: file.object_key, content_hash: file.content_hash, media_type: file.media_type, size_bytes: file.size_bytes }));
  if (JSON.stringify(attachments) !== JSON.stringify(binding.previous?.attachments ?? [])) writable(metadata, 'attachments');
  result.attachments = attachments;
  const custom = draft.details.custom;
  if (Object.keys(custom).length) { writable(metadata, 'custom_fields'); result.custom_fields = { ...binding.previous?.custom_fields, ...custom }; }
  return result;
}

/** Read a fully visible supported capture. Refuse a partial PUT instead of discarding hidden facts. */
/**
 * The edit view of a saved voucher: its type's native schema and effective configuration, as the
 * Vouchers service resolves them for a write. The service answers with a reason instead when the type
 * can no longer be edited under (retired, or its configuration is not readable by this person).
 */
export function verifyPurchaseFieldSet(metadata: FieldSet | null | undefined): FieldSet {
  if (metadata?.configuration_unavailable) refuse('This purchase cannot be opened for editing here: ' + metadata.configuration_unavailable + '. Review it from the voucher list.');
  if (!metadata?.native || !Array.isArray(metadata.custom) || !trackingId.test(metadata.configuration?.type_revision_id ?? '')) refuse('The saved Purchase field access could not be verified.');
  return metadata!;
}
/**
 * What the screen sends for a line is an account, an amount before tax and a description. A saved line that says more —
 * its price includes tax, it has quantities, a promotion, a reason for being free, a price per many — would lose that on the
 * next save and be read as a different bill, so it is reviewed, not edited. The service's own defaults are not "more".
 */
function plainSupply(line: NonNullable<PurchaseInput['invoice']>['supplies'][number]): boolean {
  const denominator = line.price_denominator == null ? D.ONE : D.parse(String(line.price_denominator));
  return (line.price_basis ?? 'NET_EXCL_TAX') === 'NET_EXCL_TAX' && !line.quantities?.length && line.promotion_revision_id == null && line.promotion_version == null
    && line.free_reason == null && denominator === D.ONE;
}
export function purchaseFromVoucher(value: PurchaseVoucher, company: string, metadata: FieldSet, labels: Map<string, string> = new Map()): { draft: PurchaseWorkspaceDraft; binding: PurchaseBinding; typeRevised: boolean } {
  verifyPurchaseVoucher(value, company);
  verifyPurchaseFieldSet(metadata);
  // A write is validated against the type's CURRENT revision, so that is what the editor is given. When the
  // type has been revised since this bill was saved, the next save adopts the new rules; the page says so.
  if (metadata.configuration.kind !== 'PURCHASE') refuse('The saved voucher is not a Purchase.');
  const required = ['document_date', 'currency', 'mode', 'lines', 'parties', 'references', 'attachments', 'links', 'custom_fields', 'invoice'] as const;
  if (required.some(key => !metadata.native.properties?.[key] || value[key] === null || value[key] === undefined)) refuse('The full Purchase capture is not readable. Request field access before editing it.');
  const body = value.invoice as PurchaseInput['invoice'];
  if (!body || !['supplies', 'components', 'tenders', 'allocations'].every(key => Array.isArray((body as unknown as Record<string, unknown>)[key]))) refuse('The invoice capture is not fully readable. Request field access before editing it.');
  const header = body?.tax, goodsBill = value.mode === 'ITEMS' || value.mode === 'MIXED';
  const goodsHeader = goodsBill && header?.profile === GOODS_PROFILE;
  // A goods bill's header carries the goods GST profile; the screen keeps the one service context its other lines share.
  const context: typeof header = goodsHeader ? body!.supplies.find(line => line.supply_kind === 'SERVICE')?.tax ?? { ...header!, profile: TAX_PROFILES.FORWARD, service_completion_date: value.document_date } : header;
  const choice = goodsHeader ? 'FORWARD' as const : choiceOfProfile(header?.profile), taxed = choice === 'FORWARD' || choice === 'REVERSE';
  // What the bill says about GST must be what this screen would send back: a context it would rewrite (another invoice
  // date, a withholding section, a line with its own registration) is reviewed, not silently edited.
  const sameContext = (line: NonNullable<typeof context>) => line.profile === context!.profile && (['company_registration_id', 'party_registration_id', 'place_of_supply', 'service_completion_date'] as const).every(key => (line[key] ?? null) === (context![key] ?? null));
  const taxFacts = !taxed || !!context && !!context.company_registration_id && !!context.party_registration_id && !!context.place_of_supply && !!context.service_completion_date
    && context.supplier_invoice_number === body!.bill_reference && context.supplier_invoice_date === value.document_date && !context.withholding_section_id && !context.payment_date
    && (!goodsHeader || header!.service_completion_date == null && !header!.withholding_section_id && !header!.payment_date && (['company_registration_id', 'party_registration_id', 'place_of_supply', 'supplier_invoice_number', 'supplier_invoice_date'] as const).every(key => (header![key] ?? null) === (context![key] ?? null)));
  // Each goods row bills what it receives into its own selected physical destination.
  const common = new Map((value.lines as NonNullable<PurchaseInput['lines']> | undefined ?? []).map(line => [line.line_key, line]));
  const stock = value.stock as SavedStock | null | undefined;
  const savedUnits = stock?.lines?.flatMap(row => Array.isArray(row.unit_ids) ? row.unit_ids : []) ?? [];
  const same = (a: unknown, b: unknown) => a != null && b != null && D.parse(String(a)) !== null && D.parse(String(a)) === D.parse(String(b));
  const goodsSupply = (line: NonNullable<PurchaseInput['invoice']>['supplies'][number]) => {
    const item = common.get(line.line_key)?.item;
    return !!item && line.item_line_key === line.line_key && !line.tax && line.unit_price != null && decimal(String(line.unit_price)) && line.quantities?.length === 2 && new Set(line.quantities.map(row => row.basis)).size === 2
      && line.quantities.every(row => (row.basis === 'ACTUAL' || row.basis === 'BILLED') && row.unit_id === item.unit_id && same(row.quantity, item.billed_quantity))
      && plainSupply({ ...line, quantities: [] }) && (!line.free_purpose || line.free_purpose === 'NONE');
  };
  const goodsCount = body?.supplies.filter(line => line.supply_kind === 'GOODS').length ?? 0;
  const goodsShape = !goodsBill ? !common.size && !value.stock
    : goodsCount > 0 && goodsCount === common.size && (value.mode === 'MIXED' || goodsCount === body!.supplies.length) && (!taxed || goodsHeader)
      && stock?.action === 'PURCHASE_INVOICE' && stock.stock_date === value.posting_date && value.stock_date === value.posting_date && Array.isArray(stock.lines) && stock.lines.length === common.size
      && savedUnits.length <= 1000 && new Set(savedUnits).size === savedUnits.length
      && stock.lines.every((row, index) => {
        const line = [...common.values()][index]!;
        return trackingId.test(row.warehouse_id) && (!row.bin_id || typeof row.bin_id === 'string' && trackingId.test(row.bin_id)) && (!row.lot_id || typeof row.lot_id === 'string' && trackingId.test(row.lot_id))
          && (!row.unit_ids || Array.isArray(row.unit_ids) && row.unit_ids.length <= 200 && row.unit_ids.every(id => typeof id === 'string' && trackingId.test(id)))
          && Object.entries(row).every(([key, field]) => STOCK_LINE_FIELDS.has(key) || field == null || Array.isArray(field) && !field.length)
          && row.line_id === line.line_key && row.item_id === line.item.item_id && same(row.quantity, line.item.actual_quantity) && same(line.item.actual_quantity, line.item.billed_quantity)
          && line.item.planned_quantity == null && !Object.keys(line.item.custom_fields ?? {}).length;
      });
  if (!body || !choice || !taxFacts || !goodsShape || value.fulfillment_terms || (body.tenders?.length ?? 0) > 1 || body.supplies.some(line => line.supply_kind === 'GOODS' ? !goodsSupply(line)
    : line.supply_kind !== (taxed ? 'SERVICE' : 'ACCOUNT') || (goodsHeader ? !line.tax || !sameContext(line.tax) : line.tax && !sameContext(line.tax)) || line.item_line_key || line.unit_price != null || line.free_purpose && line.free_purpose !== 'NONE' || !plainSupply(line))) refuse(PURCHASE_BROADER_CAPTURE);
  const source = (id: string, version: number, partyId?: string): PurchaseSource => {
    if (!trackingId.test(id) || !positiveVersion(version)) refuse('Source identity or version is not readable.');
    return { id, company, version, label: labels.get(id) ?? id, ...(partyId ? { partyId } : {}) };
  };
  const party = (value.parties as PurchaseInput['parties'])!.find(row => row.role === 'SUPPLIER');
  if (!party || !value.document_date || !value.posting_date || !value.currency || !body.due_date || !body.bill_reference || !body.party_line_key) refuse('Required Purchase facts are not readable.');
  const draft = newPurchaseWorkspace(value.document_date!);
  draft.mode = value.mode as PurchaseWorkspaceDraft['mode']; draft.invoice = body.bill_reference; draft.invoiceDate = value.document_date!; draft.postingDate = value.posting_date!;
  draft.supplier = party!.party_id; draft.payable = body.party_account_id;
  // An untaxed bill is a decision already taken; a taxed one keeps only what the person chose, so the rest follows the masters.
  draft.tax = { choice: choice!, companyRegistration: taxed ? context!.company_registration_id! : '', placeOfSupply: taxed ? context!.place_of_supply! : '', completionDate: taxed && context!.service_completion_date !== value.document_date ? context!.service_completion_date! : '', supplierRegistration: taxed ? context!.party_registration_id! : '' };
  const sources = new Map<string, PurchaseSource>();
  sources.set(party!.party_id, source(party!.party_id, party!.source_version)); sources.set(body.party_account_id, source(body.party_account_id, body.party_account_version, party!.party_id));
  const items = new Map<string, PurchaseItem>();
  draft.lines = body.supplies.map(line => {
    if (line.supply_kind === 'GOODS') {
      const item = common.get(line.line_key)!.item, quantity = D.format(D.parse(String(item.billed_quantity))!);
      if (!trackingId.test(item.item_id) || !positiveVersion(item.item_version) || !trackingId.test(item.unit_id)) refuse('Saved product identity or version is not readable.');
      items.set(item.item_id, { id: item.item_id, company, version: item.item_version, baseUnitId: item.unit_id, label: labels.get(item.item_id) ?? line.description, unit: '' });
      const physical = stock!.lines!.find(row => row.line_id === line.line_key)!;
      return { ...blankPurchaseLine(line.line_key, 'ITEM'), subject: item.item_id, label: labels.get(item.item_id) ?? line.description, description: line.description, received: quantity, billed: quantity, rate: D.format(D.parse(String(line.unit_price))!), amount: line.amount,
        stock: { warehouseId: physical.warehouse_id, binId: typeof physical.bin_id === 'string' ? physical.bin_id : '', lotId: typeof physical.lot_id === 'string' ? physical.lot_id : '', unitIds: Array.isArray(physical.unit_ids) ? physical.unit_ids as string[] : [] } };
    }
    sources.set(line.account_id, source(line.account_id, line.account_version));
    return { ...blankPurchaseLine(line.line_key, 'ACCOUNT'), subject: line.account_id, label: labels.get(line.account_id) ?? line.description, description: line.description, amount: line.amount };
  });
  draft.details.termsBasis = value.credit_terms_date && value.credit_terms_date === value.posting_date && value.posting_date !== value.document_date ? 'POSTING_DATE' : 'INVOICE_DATE';
  const termsDate = value.credit_terms_date ?? value.document_date!;
  draft.details.termsDays = String((Date.parse(body.due_date!) - Date.parse(termsDate)) / 86400000);
  draft.details.declaredTotal = body.supplier_declared_total ?? ''; draft.details.notes = value.narration ?? ''; draft.details.custom = value.custom_fields ?? {};
  draft.details.comparisonReason = body.supplier_difference_reason ?? '';
  draft.details.roundingAccount = body.rounding_account_id ?? '';
  if (body.rounding_account_id) sources.set(body.rounding_account_id, source(body.rounding_account_id, body.rounding_account_version!));
  if (value.attachments!.length) draft.details.supportingFiles = value.attachments!.map(raw => {
    if (typeof raw.object_key !== 'string' || !hash(raw.content_hash) || typeof raw.size_bytes !== 'number' || !Number.isInteger(raw.size_bytes) || raw.size_bytes <= 0 || raw.size_bytes > 10 * 1024 * 1024 || !['application/pdf', 'image/png', 'image/jpeg', 'text/plain'].includes(String(raw.media_type))) refuse('Saved supporting-file metadata could not be verified.');
    const file = raw as NonNullable<PurchaseInput['attachments']>[number];
    return { ...file, id: '', company_id: company, voucher_id: value.id, filename: 'Saved supporting file · ' + file.content_hash.slice(0, 8), download_token: null };
  });
  const keys = new Map<string, string>();
  draft.details.advances = (body.allocations ?? []).map(row => {
    if (row.debt.line_key !== body.party_line_key || !trackingId.test(row.credit.item_id ?? '') || row.fx_account_id || row.currency !== value.currency) refuse('This settlement requires its full native editor.');
    keys.set('advance:' + row.credit.item_id!, row.allocation_key);
    return { id: row.credit.item_id!, amount: row.amount };
  });
  const payment = body.tenders?.[0];
  const paymentAccounts = new Map<string, PurchasePaymentAccount>();
  if (payment) {
    if (!['CASH', 'BANK_TRANSFER'].includes(payment.tender.mode) || payment.tender.currency !== value.currency || payment.tender.recognition !== 'BOOK_DATE' || payment.tender.instrument_date) refuse('This payment instruction requires its full native editor.');
    draft.details.payment = { account: payment.account_id, amount: payment.tender.amount, method: payment.tender.mode === 'CASH' ? 'CASH' : 'BANK', reference: payment.tender.reference ?? '' };
    keys.set('payment:tender', payment.tender.tender_key); keys.set('payment:line', payment.tender.line_key);
    paymentAccounts.set(payment.account_id, { id: payment.account_id, company, currency: value.currency!, version: payment.account_version, method: payment.tender.mode === 'CASH' ? 'CASH' : 'BANK', label: labels.get(payment.account_id) ?? payment.account_id });
  }
  const lineKeys = new Set(draft.lines.map(line => line.key));
  draft.details.components = (body.components ?? []).flatMap(component => {
    if (!['DISCOUNT','FREIGHT','PACKING','INSURANCE','HANDLING','OTHER_CHARGE'].includes(component.purpose) || !['FIXED', 'PERCENT'].includes(component.input_kind) || component.commercial_treatment !== 'COUNTERPARTY' || component.allocation_basis !== 'VALUE' || component.account_id || component.tax_targets?.length || component.cost_targets?.length || component.targets.some(key => !lineKeys.has(key))) refuse('This adjustment needs its full native editor.');
    const amount = savedDecimal(component.value);
    const target = draft.lines.find(line => line.key === component.targets[0]);
    if (component.purpose === 'DISCOUNT' && component.effect === 'DEDUCT' && component.scope === 'LINE' && component.input_kind === 'FIXED' && component.tax_treatment === 'ASSESSABLE' && (component.amount_basis ?? 'NET_EXCL_TAX') === 'NET_EXCL_TAX' && component.targets.length === 1 && !component.dependencies?.length && typeof component.source_evidence === 'string' && component.source_evidence === 'Line discount: ' + (target?.description || target?.label || '').slice(0, 470)) {
      if (!target || (D.parse(target.discount) ?? 0n) > 0n) refuse(PURCHASE_BROADER_CAPTURE);
      target.discount = amount;
      return [];
    }
    const evidence=readComponentEvidence(component.source_evidence);
    // Persisted dependencies are authoritative even if a preset has since changed.
    return [{ id: component.component_key, label:evidence.label, kind: component.purpose === 'DISCOUNT' ? 'DISCOUNT' : 'CHARGE',purpose:component.purpose, basis: component.input_kind === 'FIXED' ? 'AMOUNT' : 'PERCENT', value: amount, targets: component.scope==='INVOICE'?[]:[...component.targets], payable: true, taxTreatment: component.tax_treatment === 'NO_CHANGE' ? 'EXCLUDED' : 'INCLUDED',amountBasis:component.amount_basis??'NET_EXCL_TAX',basisRecipe:component.dependencies?.length?'AFTER_STEPS':'ORIGINAL',dependencies:[...component.dependencies??[]],scope:component.scope,presetKey:evidence.preset }];
  });
  const previous: Record<string, unknown> = {};
  for (const key of ['type_revision_id', 'class_id', 'document_date', 'posting_date', 'stock_date', 'statutory_date', 'credit_terms_date', 'mode', 'currency', 'narration', 'lines', 'parties', 'references', 'attachments', 'links', 'assignments', 'counter', 'custom_fields', 'invoice'] as const) if (value[key] !== undefined) previous[key] = value[key];
  // The saved goods keep their warehouse; the inventory account is read again, for the posting date, before the next save.
  const firstGoods = body.supplies.find(line => line.supply_kind === 'GOODS');
  const goods = firstGoods && stock?.lines?.[0] ? { goods: { inventory: { id: firstGoods.account_id, version: firstGoods.account_version }, warehouse: stock.lines[0].warehouse_id }, items } : {};
  return { typeRevised: metadata.configuration.type_revision_id !== value.type_revision_id, draft, binding: { company, currency: value.currency!, metadata, sources, keys, paymentAccounts, partyKey: body.party_line_key, previous: previous as PurchaseInput, ...goods } };
}

export async function purchaseAdvancePage(reader: <T>(request: ServiceRequest) => Promise<T>, company: string, supplier: string, payable: string, currency: string, date: string, cursor?: string): Promise<{ items: PurchaseAdvance[]; nextCursor: string | null }> {
  if (![supplier, payable].every(value => trackingId.test(value))) refuse('Select a verified supplier and payable before loading advances.');
  const base = purchaseBase(company), params = new URLSearchParams({ party_id: supplier, role: 'SUPPLIER', direction: 'CREDIT', account_id: payable, limit: '50', ...(cursor ? { cursor } : {}) });
  const page = await reader<{ items: { id: string; company_id: string; party_id?: string; role?: string; direction?: string; account_id?: string; currency?: string; reference?: string; posting_date?: string; reversal_date?: string | null }[]; page: { next_cursor: string | null } }>({ service: 'accounting', path: base + '/open-items?' + params });
  if (!Array.isArray(page.items) || page.items.length > 50 || !page.page || page.page.next_cursor !== null && typeof page.page.next_cursor !== 'string' || page.items.some(row => !trackingId.test(row.id) || row.company_id !== company || row.party_id !== supplier || row.account_id !== payable || row.role !== 'SUPPLIER' || row.direction !== 'CREDIT')) refuse('The supplier advance list could not be verified.');
  const items: PurchaseAdvance[] = [];
  // Keep owner reads bounded; never fan out 50 balance calls at once.
  for (let offset = 0; offset < page.items.length; offset += 5) {
    const batch = await Promise.all(page.items.slice(offset, offset + 5).filter(row => row.currency === currency && row.posting_date && row.posting_date <= date && (!row.reversal_date || row.reversal_date > date)).map(async row => {
      const balance = await reader<{ item_id: string; as_of: string; currency: string; remaining: string }>({ service: 'accounting', path: base + '/open-items/' + row.id + '/balance?as_of=' + encodeURIComponent(date) });
      if (balance.item_id !== row.id || balance.as_of !== date || balance.currency !== currency || !decimal(balance.remaining)) refuse('The supplier advance balance could not be verified.');
      return { id: row.id, company, supplier, payable, currency, remaining: balance.remaining, label: row.reference ?? 'Supplier advance', asOf: date };
    }));
    items.push(...batch.filter(row => D.parse(row.remaining)! > 0n));
  }
  return { items, nextCursor: page.page.next_cursor };
}
export async function purchasePaymentAccount(reader: <T>(request: ServiceRequest) => Promise<T>, company: string, currency: string, id: string): Promise<PurchasePaymentAccount> {
  if (!trackingId.test(id)) refuse('Select a valid payment account.');
  const value = await reader<{ id: string; company_id: string; kind?: string; status?: string; row_version: number; currency_mode?: string; currency?: string | null; name?: string; code?: string; posting_policy?: string }>({ service: 'accounting', path: purchaseBase(company) + '/accounts/' + id });
  if (value.id !== id || value.company_id !== company || value.status !== 'ACTIVE' || !positiveVersion(value.row_version) || !['BANK', 'CASH'].includes(value.kind ?? '') || !['BASE', 'FIXED'].includes(value.currency_mode ?? '') || value.currency_mode === 'FIXED' && value.currency !== currency || value.posting_policy !== 'MANUAL_ALLOWED') refuse('The payment account is unavailable for this company and currency.');
  return { id, company, currency, version: value.row_version, method: value.kind === 'CASH' ? 'CASH' : 'BANK', label: value.name ?? value.code ?? id };
}
export function livePurchasePolicy(currency: string, metadata: FieldSet, company?: string): PurchaseWorkspacePolicy {
  const invoice = metadata.configuration.policy.invoice;
  const components = nativeProperties(metadata.native.properties?.invoice).components;
  const adjustments = !!(invoice?.manual_discounts_allowed || invoice?.charges_allowed);
  return { live: true, stockCompany: company, stockAccess: purchaseStockAccess(metadata), calculation:readCalculationPolicy((metadata.configuration.policy as {purchase_calculation?:PurchaseCalculationPolicy}).purchase_calculation),discountsAllowed: !!invoice?.manual_discounts_allowed, chargesAllowed: !!invoice?.charges_allowed, currency, modes: purchaseModes(metadata), suppliers: [], subjects: [], details: { panels: { components: { available: adjustments, writable: adjustments && !!components && !components.readOnly && !metadata.native.properties?.invoice?.readOnly }, tax: { available: false, writable: false }, receipt: { available: false, writable: false }, tracking: { available: false, writable: false }, settlement: { available: false, writable: false }, evidence: { available: false, writable: false } }, receipts: [], advances: [], paymentAccounts: [], locations: [], tracking: {}, customFields: [], maxFiles: 0, maxFileBytes: 0 }, costAccess: metadata.native.properties?.invoice ? 'VISIBLE' : 'DENIED' };
}

export type PurchaseOperationTarget = { voucherId: string; revisionId: string };
export type PurchaseOperation = { id: string; voucher_id: string; revision_id?: string; status: string; row_version: number; rejection_code?: string | null };
export function verifyPurchaseOperation(value: PurchaseOperation, target: PurchaseOperationTarget): void {
  if (!value || !trackingId.test(value.id) || value.voucher_id !== target.voucherId || value.revision_id && value.revision_id !== target.revisionId || !positiveVersion(value.row_version) || !['PENDING', 'COMMITTED', 'REJECTED', 'CANCELLED'].includes(value.status)) refuse('The Purchase execution response could not be verified.');
}
export type PurchasePending = { schema: 1; scope: string; request: ServiceRequest; createdAt: string; operation?: PurchaseOperationTarget };
/** Tab-scoped, actor/company/year-isolated recovery. Never auto-replay after reload. */
export function purchasePendingKey(scope: string): string { return 'purchase-api-command:' + scope; }
export function readPurchasePending(storage: Pick<Storage, 'getItem'>, scope: string, company: string): PurchasePending | null {
  const raw = storage.getItem(purchasePendingKey(scope)); if (!raw) return null;
  try {
    const pending = JSON.parse(raw) as PurchasePending, request = pending.request;
    const root = purchaseBase(company) + '/vouchers', uuid = '[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}';
    const operation = pending.operation;
    const operationPath = request && operation && trackingId.test(operation.voucherId) && trackingId.test(operation.revisionId) && request.method === 'POST' && (request.path === root + '/' + operation.voucherId + '/post' || new RegExp('^' + purchaseBase(company) + '/voucher-operations/' + uuid + '/(?:recover|cancel)$', 'i').test(request.path));
    const mutation = operation ? operationPath : request && (request.method === 'POST' && (request.path === root || new RegExp('^' + root + '/' + uuid + '/(?:invoice-acceptance|submit|approve|reject|cancel)$', 'i').test(request.path)) || request.method === 'PUT' && new RegExp('^' + root + '/' + uuid + '$', 'i').test(request.path));
    if (pending.schema !== 1 || pending.scope !== scope || !request || !request.key || !trackingId.test(request.key) || !mutation || request.service !== 'vouchers' || !request.body || typeof request.body !== 'object') refuse('Recovery record is invalid.');
    return pending;
  } catch { refuse('The retained Purchase command cannot be verified. Keep this tab open and review the saved voucher before continuing.'); }
}

/** The service refuses a submit that repeats a supplier's bill until the person confirms it. */
export const DUPLICATE_BILL_CODE = 'duplicate_supplier_bill';
export type DuplicateBill = { id: string; status: string; document_date: string; bill_reference: string; revision_number: number };
const duplicateShape = (row: Partial<DuplicateBill>): row is DuplicateBill => !!row && typeof row.id === 'string' && trackingId.test(row.id) && typeof row.status === 'string' && /^[A-Z_]{3,20}$/.test(row.status)
  && typeof row.document_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(row.document_date) && typeof row.bill_reference === 'string' && row.bill_reference.length <= 200 && Number.isInteger(row.revision_number) && row.revision_number! > 0;
/** The lookup's answer, checked: at most five rows of the shape the service documents. */
export function verifyDuplicateBills(value: unknown): DuplicateBill[] {
  const items = (value as { items?: unknown } | null)?.items;
  if (!Array.isArray(items) || items.length > 5 || !items.every(row => duplicateShape(row as Partial<DuplicateBill>))) refuse('The duplicate bill check could not be verified.');
  return items as DuplicateBill[];
}
/** The 409 carries its rows in the flat `fields` map as `matches.<n>.<name>`; every value is a string. */
export function duplicateBillsFromFields(fields: Record<string, string> | undefined): DuplicateBill[] {
  const rows: DuplicateBill[] = [];
  for (let index = 0; index < 5; index++) {
    const get = (name: string) => fields?.[`matches.${index}.${name}`];
    const row = { id: get('id'), status: get('status'), document_date: get('document_date'), bill_reference: get('bill_reference'), revision_number: Number(get('revision_number')) };
    if (duplicateShape(row as Partial<DuplicateBill>)) rows.push(row as DuplicateBill);
  }
  return rows;
}
/** The supplier party and/or the payable ledger the bill posts to: a bill with no header supplier is still the same supplier's by its ledger. */
export function duplicateBillQuery(base: string, input: { partyId?: string; payableId?: string; billReference: string; documentDate: string; excludeVoucherId: string }): string {
  const query = new URLSearchParams({ ...(input.partyId ? { party_id: input.partyId } : {}), ...(input.payableId ? { party_account_id: input.payableId } : {}), bill_reference: input.billReference, document_date: input.documentDate, exclude_voucher_id: input.excludeVoucherId });
  // A supplier's reference usually has slashes (SOS/26-27/0418). A slash is legal unescaped in a query, and the proxy
  // refuses an escaped one anywhere in a path, so the lookup would otherwise never reach the service.
  return base + '/vouchers/duplicate-bills?' + query.toString().replace(/%2F/gi, '/');
}
