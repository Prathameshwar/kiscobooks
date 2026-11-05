import { customCondition, customValue, type CustomField } from '@janso/ui';
import * as D from './fixed-decimal';
import {componentDependencies,componentRecipeProblem} from './purchase-calculation';
const COMPONENT_FACTOR=10n**BigInt(D.SCALE);
import type { PurchaseWorkspaceDraft, PurchaseWorkspacePolicy } from './purchase-workspace';
import type { PurchaseStoredFile } from './purchase-files';

export const PURCHASE_PANELS = {
  components: 'Discounts & charges', tax: 'Tax details', receipt: 'Goods receipt',
  tracking: 'Line tracking', settlement: 'Payment & terms', evidence: 'Supplier bill & attachments',
} as const;
export type PurchasePanel = keyof typeof PURCHASE_PANELS;
export type PurchaseComponent = {
  id: string; label: string; kind: 'DISCOUNT' | 'CHARGE'; basis: 'AMOUNT' | 'PERCENT'; value: string;
  purpose?:'DISCOUNT'|'FREIGHT'|'PACKING'|'INSURANCE'|'HANDLING'|'OTHER_CHARGE';
  amountBasis?:'NET_EXCL_TAX'|'GROSS_INCL_TAX';basisRecipe?:'ORIGINAL'|'AFTER_DISCOUNTS'|'AFTER_STEPS';
  dependencies?:string[];scope?:'INVOICE'|'SELECTED_LINES'|'LINE';presetKey?:string;
  targets: string[]; payable: boolean; taxTreatment: 'INCLUDED' | 'EXCLUDED' | 'UNRESOLVED';
};
export type PurchaseTracking = { location: string; batch: string; expiry: string; serials: string };
export type PurchaseAttachment = { id: string; name: string; size: number; file: File; status: 'checking' | 'ready' | 'failed'; error?: string };
export type PurchaseDetails = {
  components: PurchaseComponent[]; nextComponent: number;
  receiptIntent: 'DIRECT' | 'REFERENCE' | 'DEFERRED';
  receipts: { lineKey: string; sourceId: string; quantity: string }[];
  tracking: Record<string, PurchaseTracking>;
  termsDays: string; termsBasis: 'INVOICE_DATE' | 'POSTING_DATE';
  advances: { id: string; amount: string }[];
  payment: { amount: string; method: 'BANK' | 'CASH'; account: string; reference: string };
  declaredTotal: string; comparison: 'REVIEW_ENTRY' | 'SUPPLIER_REVISED'; revisedTotal: string; comparisonReason: string;
  notes: string; custom: Record<string, unknown>; attachments: PurchaseAttachment[];
  supportingFiles?: PurchaseStoredFile[];
  roundingAccount?: string;
};
export type PurchaseTaxEvidence = {
  signature: string; reference: string; jurisdiction: string; registration: string;
  classification: string; components: { label: string; rate: string; liability: 'SUPPLIER' | 'RECIPIENT' }[];
};
export type PurchaseDetailPolicy = {
  panels: Record<PurchasePanel, { available: boolean; writable: boolean }>;
  receipts: { id: string; label: string; supplier: string; currency: string; subject: string; unit: string; remaining: string }[];
  advances: { id: string; label: string; supplier: string; currency: string; available: string }[];
  paymentAccounts: { id: string; label: string; currency: string; method: 'BANK' | 'CASH' }[];
  locations: { value: string; label: string }[];
  tracking: Record<string, { batch: boolean; expiry: boolean; serials: boolean }>;
  customFields: CustomField[]; maxFiles: number; maxFileBytes: number;
};
const custom = (key: string, label: string, data_type: string, choices: string[] = []): CustomField => ({
  key, label, source: 'custom', visible: true, writable: true, required: false,
  custom: { key, data_type, is_active: true, is_immutable_after_create: false,
    validation: { required: false, max_length: 200, min: '0', max: '999' },
    choices: choices.map(value => ({ value, label: value, is_active: true })) },
});
export const PURCHASE_DETAIL_POLICY: PurchaseDetailPolicy = {
  panels: Object.fromEntries(Object.keys(PURCHASE_PANELS).map(key => [key, { available: true, writable: true }])) as PurchaseDetailPolicy['panels'],
  receipts: [
    { id: 'demo-grn-notebooks', label: 'GRN-104 · Notebooks · already received', supplier: 'demo-paper', currency: 'INR', subject: 'demo-notebook', unit: 'pack', remaining: '10' },
    { id: 'demo-grn-organisers', label: 'GRN-109 · Organisers · already received', supplier: 'demo-paper', currency: 'INR', subject: 'demo-organiser', unit: 'each', remaining: '5' },
  ],
  advances: [
    { id: 'demo-advance-paper', label: 'ADV-018 · Paper & Co.', supplier: 'demo-paper', currency: 'INR', available: '1000' },
    { id: 'demo-advance-services', label: 'ADV-021 · Northstar', supplier: 'demo-services', currency: 'INR', available: '500' },
  ],
  paymentAccounts: [
    { id: 'demo-bank', label: 'Operating bank · example', currency: 'INR', method: 'BANK' },
    { id: 'demo-cash', label: 'Office cash · example', currency: 'INR', method: 'CASH' },
  ],
  locations: [{ value: 'demo-store', label: 'Main store' }, { value: 'demo-office', label: 'Office supplies room' }],
  tracking: { 'demo-batch-ink': { batch: true, expiry: true, serials: false }, 'demo-serial-device': { batch: false, expiry: false, serials: true } },
  customFields: [custom('cf_purchase_project', 'Purchase project', 'select', ['Office', 'Retail']), custom('cf_purchase_request', 'Requisition reference', 'text'), custom('cf_purchase_parcels', 'Number of parcels', 'integer')],
  maxFiles: 5, maxFileBytes: 5 * 1024 * 1024,
};
export function blankPurchaseDetails(): PurchaseDetails {
  return { components: [], nextComponent: 1, receiptIntent: 'DIRECT', receipts: [], tracking: {},
    termsDays: '30', termsBasis: 'INVOICE_DATE', advances: [], payment: { amount: '0', method: 'BANK', account: '', reference: '' },
    declaredTotal: '', comparison: 'REVIEW_ENTRY', revisedTotal: '', comparisonReason: '', notes: '', custom: {}, attachments: [] };
}
export const blankPurchaseTracking = (): PurchaseTracking => ({ location: '', batch: '', expiry: '', serials: '' });
export const purchaseSerials = (text: string) => text.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
export function purchaseDecimal(text: string, signed = false): D.Fixed | null {
  const value = D.parse(text);
  return value === null || (!signed && value < 0n) || value > 9999999999999999999n || value < -9999999999999999999n ? null : value;
}
export function purchaseDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
}
export function purchaseDueDate(draft: PurchaseWorkspaceDraft): string | null {
  const details = draft.details, basis = details.termsBasis === 'INVOICE_DATE' ? draft.invoiceDate : draft.postingDate;
  if (!purchaseDate(basis) || !/^\d{1,4}$/.test(details.termsDays) || Number(details.termsDays) > 3650) return null;
  const result = new Date(basis + 'T00:00:00Z');
  result.setUTCDate(result.getUTCDate() + Number(details.termsDays));
  return result.toISOString().slice(0, 10);
}

/** Bounded fixture presentation: ordered discounts then charges. No statutory tax resolver. */
export function purchaseOrderedComponents(components: readonly PurchaseComponent[]): PurchaseComponent[] {
  if(components.some(component=>component.basisRecipe!==undefined))return [...components];
  return [...components.filter(component => component.kind === 'DISCOUNT'), ...components.filter(component => component.kind === 'CHARGE')];
}
export function purchaseComponentPreview(draft: PurchaseWorkspaceDraft, lineNets: { key: string; net: D.Fixed;original?:D.Fixed }[] | null,grossRate:D.Fixed|null=null) {
  const original = new Map(lineNets?.map(line => [line.key, line.original??line.net]));
  const remaining = new Map(lineNets?.map(line => [line.key, line.net]));
  const commercialBalance=new Map(remaining),taxBalance=new Map(remaining);
  const lineDiscounts=[...original.keys()].filter(key=>original.get(key)!==remaining.get(key)).map(key=>'discount:'+key);
  const shares=new Map<string,Map<string,D.Fixed>>(lineDiscounts.map(id=>{const key=id.slice(9);return [id,new Map([[key,remaining.get(key)!-original.get(key)!]])];}));
  const entries: { id: string; amount: D.Fixed | null; base: D.Fixed | null;requiresOwner?:boolean }[] = [];
  const roundRatio=(numerator:bigint,denominator:bigint):D.Fixed=>{
    const units=numerator*100n/denominator,rest=numerator*100n%denominator;
    return (units+(rest*2n>=denominator?1n:0n))*100n;
  };
  let discount = 0n, taxDiscount = 0n, supplierCharges = 0n, landedCharges = 0n, taxCharges = 0n;
  let known = lineNets !== null, taxKnown = true, ownerPending = false;
  const components = purchaseOrderedComponents(draft.details.components);
  for (const [index,component] of components.entries()) {
    const targets = component.targets.length ? component.targets : [...remaining.keys()];
    const eligible = targets.filter(key => remaining.has(key));
    const dependencies=componentDependencies(component,components.slice(0,index),lineDiscounts);
    const validDependencies=dependencies.every(key=>shares.has(key));
    const bases=eligible.map(key=>original.get(key)!+D.add(...dependencies.map(id=>shares.get(id)?.get(key)??0n)));
    const needsTax=component.amountBasis==='GROSS_INCL_TAX';
    const recipeProblem=componentRecipeProblem(component,components.slice(0,index),lineDiscounts);
    const inputsValid=!recipeProblem&&eligible.length===targets.length&&eligible.length>0;
    const requiresOwner:boolean=inputsValid&&(ownerPending||needsTax&&grossRate===null);
    const netBase=known&&validDependencies?D.add(...bases):null;
    const base=netBase!==null&&!requiresOwner?(needsTax?netBase+D.percent(netBase,grossRate!):netBase):null;
    const value = purchaseDecimal(component.value);
    let amount = base !== null && value !== null && inputsValid
      && !(component.scope==='SELECTED_LINES'&&!component.targets.length)
      && bases.every(value=>value>=0n)
      && D.add(...bases)>0n
      ? component.basis === 'PERCENT' ? roundRatio(base*value,100n*COMPONENT_FACTOR*COMPONENT_FACTOR) : D.round(value,2) : null;
    if (component.basis === 'PERCENT' && value !== null && value > 1000000n) amount = null;
    if (component.kind === 'DISCOUNT' && amount !== null && base !== null && amount > base) amount = null;
    entries.push({ id: component.id, amount, base,requiresOwner });
    if (amount === null) { known = false; ownerPending=requiresOwner; continue; }
    const allocated=D.allocate(amount,eligible.map((_,index)=>bases[index]!),2);
    const netShares=allocated.map(value=>needsTax?roundRatio(value*100n,100n*COMPONENT_FACTOR+grossRate!):value);
    const netAmount=D.add(...netShares);
    if(component.kind==='DISCOUNT'&&eligible.some((key,index)=>netShares[index]!>commercialBalance.get(key)!||component.taxTreatment==='INCLUDED'&&netShares[index]!>taxBalance.get(key)!)){entries[entries.length-1]!.amount=null;known=false;continue;}
    shares.set(component.id,new Map(eligible.map((key,index)=>[key,component.kind==='DISCOUNT'?-netShares[index]!:netShares[index]!] )));
    if (component.kind === 'DISCOUNT') {
      discount += netAmount;
      if(component.taxTreatment==='INCLUDED')taxDiscount+=netAmount;
      eligible.forEach((key, index) => remaining.set(key, remaining.get(key)! - netShares[index]!));
    } else {
      if (component.payable) supplierCharges += netAmount;
      else landedCharges += netAmount;
      if (component.taxTreatment === 'INCLUDED' && component.payable) taxCharges += netAmount;
      if (component.taxTreatment === 'UNRESOLVED' || (!component.payable && component.taxTreatment === 'INCLUDED')) taxKnown = false;
    }
    eligible.forEach((key,index)=>{
      const signed=component.kind==='DISCOUNT'?-netShares[index]!:netShares[index]!;
      if(component.payable)commercialBalance.set(key,commercialBalance.get(key)!+signed);
      if(component.taxTreatment==='INCLUDED'&&component.payable)taxBalance.set(key,taxBalance.get(key)!+signed);
    });
  }
  return { entries, discount: known ? discount : null, supplierCharges: known ? supplierCharges : null, landedCharges: known ? landedCharges : null,
    afterDiscounts: known ? D.add(...remaining.values()) : null,taxAfterDiscounts:known?D.add(...lineNets!.map(line=>line.net))-taxDiscount:null, taxCharges: known && taxKnown ? taxCharges : null };
}

export function purchaseSettlementPreview(draft: PurchaseWorkspaceDraft, total: D.Fixed | null) {
  const advances = draft.details.advances.map(advance => purchaseDecimal(advance.amount));
  const advance = advances.every(value => value !== null) ? D.add(...advances as D.Fixed[]) : null;
  const payment = purchaseDecimal(draft.details.payment.amount);
  const remainder = total !== null && advance !== null && payment !== null ? total - advance - payment : null;
  const declared = draft.details.declaredTotal === '' ? null : purchaseDecimal(draft.details.declaredTotal);
  const revised = draft.details.comparison === 'SUPPLIER_REVISED' ? purchaseDecimal(draft.details.revisedTotal) : null;
  const comparisonTotal = draft.details.comparison === 'SUPPLIER_REVISED' ? revised : declared;
  return { advance, payment, remaining: remainder !== null && remainder >= 0n ? remainder : null, overpaid: remainder !== null && remainder < 0n,
    declared, revised, difference: total !== null && comparisonTotal !== null ? comparisonTotal - total : null, dueDate: purchaseDueDate(draft) };
}

export type PurchaseDetailProblem = { panel: PurchasePanel; field: string; message: string; lineKey?: string };
export function purchaseDetailProblems(draft: PurchaseWorkspaceDraft, policy: PurchaseWorkspacePolicy, total: D.Fixed | null, stage: 'APPLY' | 'REVIEW' = 'REVIEW'): PurchaseDetailProblem[] {
  const details = draft.details, config = policy.details, problems: PurchaseDetailProblem[] = [];
  const add = (panel: PurchasePanel, field: string, message: string, lineKey?: string) => problems.push({ panel, field, message, lineKey });
  const active = draft.lines.filter(line => !!line.subject);
  const items = active.filter(line => line.kind === 'ITEM');
  const used = new Map<string, D.Fixed>();
  const seenSerials = new Map<string, string>();
  if (details.receiptIntent === 'REFERENCE') for (const line of items) {
    const allocation = details.receipts.find(receipt => receipt.lineKey === line.key);
    const source = config.receipts.find(receipt => receipt.id === allocation?.sourceId && receipt.supplier === draft.supplier && receipt.currency === policy.currency && receipt.subject === line.subject && receipt.unit === line.unit);
    const quantity = purchaseDecimal(allocation?.quantity ?? '');
    if (!source) add('receipt', `receipt-${line.key}`, 'Choose an eligible existing receipt for this item.', line.key);
    else if (quantity === null || quantity <= 0n || quantity !== purchaseDecimal(line.billed)) add('receipt', `receipt-quantity-${line.key}`, 'Matched quantity must equal this line’s billed quantity and be greater than zero.', line.key);
    if (source && quantity !== null) used.set(source.id, (used.get(source.id) ?? 0n) + quantity);
  }
  for (const [id, quantity] of used) if (quantity > D.parse(config.receipts.find(receipt => receipt.id === id)!.remaining)!) add('receipt', 'receipt-allocation', 'Selected quantities exceed the remaining quantity on an existing receipt.');
  if (details.receiptIntent === 'DIRECT') for (const line of items) {
    const rule = config.tracking[line.subject], tracking = details.tracking[line.key];
    if (rule && !config.locations.some(location => location.value === tracking?.location)) add('tracking', `location-${line.key}`, 'Choose a receipt location for this tracked item.', line.key);
    if (rule?.batch && !tracking?.batch.trim()) add('tracking', `batch-${line.key}`, 'Enter the required batch number.', line.key);
    if (rule?.expiry && !purchaseDate(tracking?.expiry ?? '')) add('tracking', `expiry-${line.key}`, 'Enter a valid expiry date.', line.key);
    if (rule?.serials) {
      const serials = purchaseSerials(tracking?.serials ?? ''), quantity = purchaseDecimal(line.received);
      if (quantity === null || quantity % D.ONE !== 0n || BigInt(serials.length) * D.ONE !== quantity) add('tracking', `serials-${line.key}`, 'Enter one serial number per whole unit received.', line.key);
      if (new Set(serials).size !== serials.length) add('tracking', `serials-${line.key}`, 'Serial numbers on a line must be unique.', line.key);
      for (const serial of serials) {
        const id = line.subject + ':' + serial;
        if (seenSerials.has(id) && seenSerials.get(id) !== line.key) add('tracking', `serials-${line.key}`, 'A serial number for this item is already entered on another line.', line.key);
        seenSerials.set(id, line.key);
      }
    }
  }
  for (const line of items) {
    const location = details.tracking[line.key]?.location;
    if (location && !config.locations.some(entry => entry.value === location)) add('tracking', `location-${line.key}`, 'Choose a location from the supplied list.', line.key);
  }
  if (!purchaseDueDate(draft)) add('settlement', 'termsDays', 'Credit days must be a whole number from 0 to 3650, with a valid basis date.');
  const advanceIds = new Set<string>();
  for (const requested of details.advances) {
    const eligible = config.advances.find(advance => advance.id === requested.id && advance.supplier === draft.supplier && advance.currency === policy.currency);
    const amount = purchaseDecimal(requested.amount);
    if (!eligible || advanceIds.has(requested.id)) add('settlement', 'advances', 'An advance no longer matches this supplier/currency. Remove it or select an eligible advance.');
    else if (amount === null || amount <= 0n || amount > D.parse(eligible.available)!) add('settlement', `advance-${requested.id}`, 'Advance amount must be positive and within the available balance.');
    advanceIds.add(requested.id);
  }
  const payment = purchaseDecimal(details.payment.amount);
  if (payment === null) add('settlement', 'paymentAmount', 'Enter a valid proposed payment amount.');
  if (payment !== null && payment > 0n && !config.paymentAccounts.some(account => account.id === details.payment.account && account.method === details.payment.method && account.currency === policy.currency)) add('settlement', 'paymentAccount', 'Choose a payment account for this method and currency.');
  const settlement = purchaseSettlementPreview(draft, total);
  if (settlement.overpaid) add('settlement', 'paymentAmount', 'Proposed advances and payment cannot exceed the full bill total.');
  if (details.declaredTotal !== '' && purchaseDecimal(details.declaredTotal) === null) add('evidence', 'declaredTotal', 'Enter a valid supplier-declared total.');
  if (details.comparison === 'SUPPLIER_REVISED' && details.declaredTotal === '') add('evidence', 'declaredTotal', 'Enter the original supplier total before recording its revision.');
  if (details.comparison === 'SUPPLIER_REVISED' && (purchaseDecimal(details.revisedTotal) === null || !details.comparisonReason.trim())) add('evidence', 'revisedTotal', 'Keep the supplier’s original total and enter a revised total with the supporting reason.');
  if (stage === 'REVIEW' && settlement.difference !== null && settlement.difference !== 0n) add('evidence', 'declaredTotal', 'The supplier total differs from this bill. Correct the entry or record a matching supplier revision.');
  if (details.attachments.some(attachment => attachment.status !== 'ready')) add('evidence', 'attachments', 'Finish checking attachments or remove failed files. Nothing has been uploaded.');
  for (const field of config.customFields) {
    if (!field.visible || !field.custom?.is_active || !customCondition(field.custom.visibility, details.custom)) continue;
    const value = details.custom[field.key];
    if (field.required && (value == null || value === '')) add('evidence', field.key, `${field.label} is required.`);
    if (value == null || value === '') continue;
    try {
      const typed = customValue(field.custom, value);
      if (typeof typed === 'string' && typed.length > field.custom.validation.max_length) throw Error('too long');
      if (field.custom.data_type === 'select' && !field.custom.choices.some(choice => choice.value === typed && choice.is_active)) throw Error('invalid choice');
      if (field.custom.data_type === 'integer' && (Number(typed) < Number(field.custom.validation.min ?? '-9007199254740991') || Number(typed) > Number(field.custom.validation.max ?? '9007199254740991'))) throw Error('out of range');
    } catch { add('evidence', field.key, `Check ${field.label.toLowerCase()}. Its value must match the configured type and limits.`); }
  }
  return problems;
}

export function normalizePurchaseCustom(details: PurchaseDetails, policy: PurchaseDetailPolicy): PurchaseDetails {
  const custom = { ...details.custom };
  for (const field of policy.customFields) if (field.writable && field.custom && field.key in custom) custom[field.key] = customValue(field.custom, custom[field.key]);
  return { ...details, custom };
}
