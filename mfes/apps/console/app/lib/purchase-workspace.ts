import * as D from './fixed-decimal';
import type { SearchSelectLoader } from '@janso/ui';
import { PURCHASE_DETAIL_POLICY, blankPurchaseDetails, purchaseComponentPreview, purchaseDetailProblems, purchaseSettlementPreview,
  type PurchaseDetails, type PurchaseDetailPolicy, type PurchasePanel, type PurchaseTaxEvidence } from './purchase-workspace-details';
import { blankPurchaseTax, type PurchaseTaxDraft } from './purchase-tax';
import type { SupplierBalance } from './purchase-supplier-balance';
import type {PurchaseCalculationPolicy} from './purchase-calculation';

/** Presentation-only Purchase state. Never send this shape to the vouchers API. */
export type PurchaseMode = 'ITEMS' | 'ACCOUNTS' | 'MIXED';
export type PurchaseLineKind = 'ITEM' | 'ACCOUNT';
export type PurchaseStock = { warehouseId: string; binId: string; lotId: string; unitIds: string[] };
export const blankPurchaseStock = (): PurchaseStock => ({ warehouseId: '', binId: '', lotId: '', unitIds: [] });
export type PurchaseLine = {
  key: string; kind: PurchaseLineKind; subject: string; label: string; unit: string;
  received: string; billed: string; rate: string; amount: string; discount: string;
  description: string; quantityReason: string;
  stock?: PurchaseStock;
};
export type PurchaseWorkspaceDraft = {
  mode: PurchaseMode; supplier: string; payable: string; invoice: string;
  invoiceDate: string; postingDate: string; lines: PurchaseLine[]; nextKey: number;
  evidence: PurchaseTaxEvidence | null;
  details: PurchaseDetails;
  /** Whether GST applies to the bill and the facts it is raised under. The live page's; the previews leave it blank. */
  tax: PurchaseTaxDraft;
};
export type PurchaseSupplier = {
  id: string; label: string; meta: string; payables: { value: string; label: string }[];
};
export type PurchaseSubject = { id: string; label: string; meta: string; kind: PurchaseLineKind; unit: string };
export type PurchaseWorkspacePolicy = {
  stockCompany?: string;
  stockAccess?: { warehouse: boolean; bin: boolean; batch: boolean; serial: boolean };
  canReadBatch?: boolean;
  canPrepareBatch?: boolean;
  canPrepareSerial?: boolean;
  calculation?:PurchaseCalculationPolicy;
  live?: boolean;
  discountsAllowed?: boolean;
  chargesAllowed?: boolean;
  /** Live master search is supplied by the connected controller: accounts, and products for item lines. */
  subjectLookup?: SearchSelectLoader;
  itemLookup?: SearchSelectLoader;
  currency: string; currencySymbol?: string;
  /** Supplied presentation capabilities/results. Real field authorization stays server-side. */
  costAccess?: 'VISIBLE' | 'DENIED';
  duplicateCheck?: { supplier: string; invoice: string; references: readonly string[] };
  /** Live page only: the chosen supplier's balance, read in the background. Advice shown beside the supplier; never part of the bill. */
  supplierBalance?: SupplierBalance;
  balanceAccess?: { ledger: boolean; stock: boolean };
  supplierHistoryAccess?: boolean;
  details: PurchaseDetailPolicy;
  modes: readonly PurchaseMode[]; suppliers: readonly PurchaseSupplier[]; subjects: readonly PurchaseSubject[];
};

/** Explicit synthetic adapters; these are neither company masters nor resolved tax policy. */
export const PURCHASE_DEMO_POLICY: PurchaseWorkspacePolicy = {
  currency: 'INR', currencySymbol: '₹',
  details: PURCHASE_DETAIL_POLICY,
  modes: ['ITEMS', 'ACCOUNTS', 'MIXED'],
  suppliers: [
    { id: 'demo-paper', label: 'Paper & Co. Supplies', meta: 'SUP-001 · Pune · Example supplier', payables: [{ value: 'demo-trade', label: 'Trade payables' }] },
    { id: 'demo-services', label: 'Northstar Business Services', meta: 'SUP-002 · Mumbai · Example supplier', payables: [{ value: 'demo-services-inr', label: 'Service payables · INR' }] },
    { id: 'demo-incomplete', label: 'New supplier · setup incomplete', meta: 'SUP-003 · No payable account configured', payables: [] },
  ],
  subjects: [
    { id: 'demo-notebook', label: 'A5 ruled notebooks · pack of 4', meta: 'NB-A5-4 · Item', kind: 'ITEM', unit: 'pack' },
    { id: 'demo-organiser', label: 'Document organisers · A4', meta: 'ORG-A4 · Item', kind: 'ITEM', unit: 'each' },
    { id: 'demo-paper-box', label: 'Copier paper · A4 · box of 5 reams', meta: 'CP-A4-5 · Item', kind: 'ITEM', unit: 'box' },
    { id: 'demo-stationery', label: 'Office stationery expense', meta: 'EXP-001 · Expense account', kind: 'ACCOUNT', unit: '' },
    { id: 'demo-maintenance', label: 'Repairs & maintenance', meta: 'EXP-002 · Service account', kind: 'ACCOUNT', unit: '' },
    { id: 'demo-batch-ink', label: 'Printer ink · tracked batch', meta: 'INK-B01 · Batch and expiry required', kind: 'ITEM', unit: 'each' },
    { id: 'demo-serial-device', label: 'Barcode scanner · tracked serial', meta: 'SCAN-S01 · Serial numbers required', kind: 'ITEM', unit: 'each' },
  ],
};

export const MODE_LABELS: Record<PurchaseMode, string> = { ITEMS: 'Items', ACCOUNTS: 'Accounts / services', MIXED: 'Mixed' };
/** The live search for a line's subject: products for an item line, accounts otherwise. Absent, the supplied subjects are offered. */
export function purchaseSubjectLookup(policy: PurchaseWorkspacePolicy, kind: PurchaseLineKind): SearchSelectLoader | undefined {
  return kind === 'ITEM' ? policy.itemLookup : policy.subjectLookup;
}
export function blankPurchaseLine(key: string, kind: PurchaseLineKind): PurchaseLine {
  return { key, kind, subject: '', label: '', unit: '', received: '', billed: '', rate: '', amount: '', discount: '0', description: '', quantityReason: '' };
}
export function newPurchaseWorkspace(today: string): PurchaseWorkspaceDraft {
  return { mode: 'ITEMS', supplier: '', payable: '', invoice: '', invoiceDate: today, postingDate: today,
    lines: [blankPurchaseLine('p1', 'ITEM')], nextKey: 2, evidence: null, details: blankPurchaseDetails(), tax: blankPurchaseTax() };
}
export function isBlankPurchaseLine(line: PurchaseLine): boolean {
  return !line.subject && !line.label && !line.received && !line.billed && !line.rate && !line.amount && !line.description && !line.quantityReason && (!line.discount || D.parse(line.discount) === 0n);
}
/** Only calculation inputs participate. Descriptions and row order do not invalidate evidence. */
export function purchaseEvidenceSignature(draft: PurchaseWorkspaceDraft): string {
  const decimal = (text: string) => { const value = D.parse(text); return value === null ? text : D.format(value); };
  return JSON.stringify([draft.supplier, draft.invoiceDate, draft.postingDate,
    draft.lines.filter(line => !isBlankPurchaseLine(line)).map(line => [line.key, line.kind, line.subject, ...[line.received, line.billed, line.rate, line.amount, line.discount].map(decimal)]).sort((a, b) => String(a[0]).localeCompare(String(b[0]))) ]);
}
export function purchaseExample(today: string): PurchaseWorkspaceDraft {
  const draft = newPurchaseWorkspace(today);
  Object.assign(draft, { supplier: 'demo-paper', payable: 'demo-trade', invoice: 'PC-261034', nextKey: 3 });
  draft.lines = [
    { ...blankPurchaseLine('p1', 'ITEM'), subject: 'demo-notebook', label: 'A5 ruled notebooks · pack of 4', unit: 'pack', received: '24', billed: '24', rate: '125', discount: '150' },
    { ...blankPurchaseLine('p2', 'ITEM'), subject: 'demo-organiser', label: 'Document organisers · A4', unit: 'each', received: '10', billed: '10', rate: '200', discount: '100' },
  ];
  // Bounded supplied recipe for the UI fixture; no statutory tax resolution.
  draft.details.components = [{ id: 'pc1', label: 'Freight', kind: 'CHARGE', basis: 'AMOUNT', value: '100', targets: [], payable: true, taxTreatment: 'INCLUDED' }];
  draft.details.nextComponent = 2;
  draft.details.advances = [{ id: 'demo-advance-paper', amount: '1000' }];
  draft.evidence = { signature: purchaseEvidenceSignature(draft), reference: 'PU02 · synthetic tax recipe', jurisdiction: 'Maharashtra · example only', registration: 'Paper & Co. · example registration',
    classification: 'Stationery · supplied example', components: [{ label: 'CGST · supplied example', rate: '9', liability: 'SUPPLIER' }, { label: 'SGST · supplied example', rate: '9', liability: 'SUPPLIER' }] };
  return draft;
}

/**
 * Why a chosen supplier cannot be billed yet; nothing when it has its one payable account.
 * A bill never asks for the account: every supplier has exactly one, and choosing the supplier chooses it.
 * Only older data can break that, and it is repaired in Accounting, not worked around on the bill.
 */
export function payableCountIssue(count: number): string | undefined {
  if (count === 1) return undefined;
  return count
    ? 'This supplier has more than one payable account, so the bill cannot tell which to use. An administrator should keep one and retire the others.'
    : 'This supplier has no payable account yet, so it cannot be billed. An administrator can add it with the party ledger repair.';
}
export function supplierAccountIssue(supplier: PurchaseSupplier | undefined): string | undefined {
  return supplier ? payableCountIssue(supplier.payables.length) : undefined;
}

type HeaderField = 'invoice' | 'invoiceDate' | 'postingDate';
export type PurchaseWorkspaceAction =
  | { type: 'header'; field: HeaderField; value: string }
  | { type: 'supplier'; value: string; policy: PurchaseWorkspacePolicy }
  | { type: 'mode'; mode: PurchaseMode }
  | { type: 'line'; key: string; patch: Partial<Omit<PurchaseLine, 'key'>> }
  | { type: 'receipt_commit'; key: string; value: string }
  | { type: 'subject'; key: string; subject: PurchaseSubject | null }
  | { type: 'kind'; key: string; kind: PurchaseLineKind }
  | { type: 'add'; after?: string }
  | { type: 'remove' | 'duplicate'; key: string }
  | { type: 'move'; key: string; by: -1 | 1 }
  | { type: 'restore'; line: PurchaseLine; index: number }
  | { type: 'details'; details: PurchaseDetails }
  | { type: 'tax'; patch: Partial<PurchaseTaxDraft> }
  | { type: 'replace'; draft: PurchaseWorkspaceDraft };

/** Typing billed quantity first may seed an empty received field; receipt entry commits on blur. */
export function withPairedQuantity(line: PurchaseLine, patch: Partial<Omit<PurchaseLine, 'key'>>): Partial<Omit<PurchaseLine, 'key'>> {
  if (line.kind !== 'ITEM' || patch.kind && patch.kind !== 'ITEM' || (patch.billed === undefined) === (patch.received === undefined)) return patch;
  if (patch.billed !== undefined && line.received === '') return { ...patch, received: patch.billed };
  return patch;
}
export function purchaseWorkspaceReducer(draft: PurchaseWorkspaceDraft, action: PurchaseWorkspaceAction): PurchaseWorkspaceDraft {
  const mapLine = (key: string, fn: (line: PurchaseLine) => PurchaseLine) => ({ ...draft, lines: draft.lines.map(line => line.key === key ? fn(line) : line) });
  switch (action.type) {
    case 'header': return { ...draft, [action.field]: action.value };
    case 'supplier': {
      const accounts = action.policy.suppliers.find(supplier => supplier.id === action.value)?.payables ?? [];
      // A GST registration belongs to one supplier: choosing another supplier drops it.
      return { ...draft, supplier: action.value, payable: accounts.length === 1 ? accounts[0]!.value : '', tax: action.value === draft.supplier ? draft.tax : { ...draft.tax, supplierRegistration: '' } };
    }
    case 'mode': return { ...draft, mode: action.mode, lines: draft.lines.map(line => isBlankPurchaseLine(line) ? { ...line, kind: action.mode === 'ACCOUNTS' ? 'ACCOUNT' : 'ITEM' } : line) };
    case 'line': return mapLine(action.key, line => ({ ...line, ...action.patch }));
    case 'receipt_commit': return mapLine(action.key, line =>
      line.kind === 'ITEM' && !line.billed && action.value
        ? { ...line, received: action.value, billed: action.value }
        : line);
    case 'subject': return mapLine(action.key, line => ({ ...line, subject: action.subject?.id ?? '', label: action.subject?.label ?? '', unit: action.subject?.unit ?? '', stock: action.subject?.id === line.subject ? line.stock : undefined }));
    // Changing the kind is explicit. Keep numeric facts in the draft so switching back recovers them.
    case 'kind': return mapLine(action.key, line => ({ ...line, kind: action.kind, subject: '', label: '', unit: '', stock: undefined }));
    case 'add': {
      const lines = [...draft.lines];
      const index = action.after ? lines.findIndex(line => line.key === action.after) + 1 : lines.length;
      lines.splice(index, 0, blankPurchaseLine(`p${draft.nextKey}`, draft.mode === 'ACCOUNTS' ? 'ACCOUNT' : 'ITEM'));
      return { ...draft, lines, nextKey: draft.nextKey + 1 };
    }
    case 'remove': {
      const lines = draft.lines.filter(line => line.key !== action.key);
      return lines.length ? { ...draft, lines } : { ...draft, lines: [blankPurchaseLine(`p${draft.nextKey}`, draft.mode === 'ACCOUNTS' ? 'ACCOUNT' : 'ITEM')], nextKey: draft.nextKey + 1 };
    }
    case 'duplicate': {
      const index = draft.lines.findIndex(line => line.key === action.key);
      if (index < 0) return draft;
      const lines = [...draft.lines];
      lines.splice(index + 1, 0, { ...lines[index]!, key: `p${draft.nextKey}`, stock: lines[index]!.stock ? { ...lines[index]!.stock!, unitIds: [] } : undefined });
      return { ...draft, lines, nextKey: draft.nextKey + 1 };
    }
    case 'move': {
      const index = draft.lines.findIndex(line => line.key === action.key), to = index + action.by;
      if (index < 0 || to < 0 || to >= draft.lines.length) return draft;
      const lines = [...draft.lines];
      [lines[index], lines[to]] = [lines[to]!, lines[index]!];
      return { ...draft, lines };
    }
    case 'restore': {
      if (draft.lines.some(line => line.key === action.line.key)) return draft;
      const lines = [...draft.lines];
      lines.splice(action.index, 0, action.line);
      return { ...draft, lines };
    }
    case 'details': return { ...draft, details: action.details };
    case 'tax': return { ...draft, tax: { ...draft.tax, ...action.patch } };
    case 'replace': return action.draft;
  }
}

const MAX_DECIMAL = 9999999999999999999n;
function nonnegative(text: string): D.Fixed | null {
  const parsed = D.parse(text);
  return parsed === null || parsed < 0n || parsed > MAX_DECIMAL ? null : parsed;
}
export function purchaseLineAmounts(line: PurchaseLine): { gross: D.Fixed; discount: D.Fixed; net: D.Fixed } | null {
  if (!line.subject) return null;
  const billed = nonnegative(line.billed), rate = nonnegative(line.rate);
  const gross = line.kind === 'ACCOUNT' ? nonnegative(line.amount) : billed !== null && billed > 0n && rate !== null ? D.mul(billed, rate) : null;
  const discount = nonnegative(line.discount || '0');
  if (gross === null || gross > MAX_DECIMAL || discount === null || discount > gross) return null;
  return { gross, discount, net: gross - discount };
}
export function purchaseWorkspacePreview(draft: PurchaseWorkspaceDraft, unstorable = false) {
  const active = draft.lines.filter(line => !isBlankPurchaseLine(line));
  const amounts = active.map(purchaseLineAmounts);
  const grossCandidate = amounts.every(Boolean) ? D.add(...amounts.map(amount => amount!.gross)) : null;
  const known = active.length > 0 && amounts.every(Boolean) && !unstorable && grossCandidate !== null && grossCandidate <= MAX_DECIMAL;
  const gross = known ? D.add(...amounts.map(amount => amount!.gross)) : null;
  const discount = known ? D.add(...amounts.map(amount => amount!.discount)) : null;
  const net = gross !== null && discount !== null ? gross - discount : null;
  const candidate = known && draft.evidence?.signature === purchaseEvidenceSignature(draft) ? draft.evidence : null;
  const grossRates=candidate?.components.filter(component=>component.liability==='SUPPLIER').map(component=>D.parse(component.rate));
  const grossRate=grossRates&&grossRates.every(rate=>rate!==null)?D.add(...grossRates as D.Fixed[]):null;
  const components = purchaseComponentPreview(draft, known ? active.map((line, index) => ({ key: line.key, net: amounts[index]!.net,original:amounts[index]!.gross })) : null,grossRate);
  const taxBase = components.taxAfterDiscounts !== null && components.taxCharges !== null ? components.taxAfterDiscounts + components.taxCharges : null;
  const rates = candidate?.components.map(component => D.parse(component.rate)) ?? [];
  const taxKnown = !!candidate && taxBase !== null && taxBase <= MAX_DECIMAL && rates.every(rate => rate !== null && rate >= 0n && rate <= 1000000n);
  const taxes = taxKnown ? candidate!.components.map((component, index) => ({ ...component, amount: D.format(D.round(D.percent(taxBase!, rates[index]!), 2)) })) : [];
  const evidence = taxKnown ? { ...candidate!, taxes: taxes.filter(component => component.liability === 'SUPPLIER') } : null;
  const tax = evidence ? D.add(...evidence.taxes.map(component => D.parse(component.amount)!)) : null;
  const recipientTax = evidence ? D.add(...taxes.filter(component => component.liability === 'RECIPIENT').map(component => D.parse(component.amount)!)) : null;
  const freight = components.supplierCharges;
  const rawTotal = components.afterDiscounts !== null && freight !== null && tax !== null ? D.add(components.afterDiscounts, freight, tax) : null;
  const total = rawTotal !== null && rawTotal <= MAX_DECIMAL ? rawTotal : null;
  const limitExceeded = (grossCandidate !== null && grossCandidate > MAX_DECIMAL) || (rawTotal !== null && rawTotal > MAX_DECIMAL);
  return { gross, discount, net, evidence, freight, tax, recipientTax, taxes, taxBase, total, components,
    settlement: purchaseSettlementPreview(draft, total), limitExceeded, activeCount: active.length };
}

export type PurchaseProblem = { key: string; field: string; message: string; lineKey?: string; panel?: PurchasePanel };
function validDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
}
export function purchaseWorkspaceProblems(draft: PurchaseWorkspaceDraft, policy: PurchaseWorkspacePolicy): PurchaseProblem[] {
  const problems: PurchaseProblem[] = [];
  const add = (field: string, message: string, lineKey?: string) => problems.push({ key: `${lineKey ?? 'header'}:${field}`, field, message, lineKey });
  const supplier = policy.suppliers.find(entry => entry.id === draft.supplier);
  if (!supplier) add('supplier', 'Choose a supplier.');
  else if (!supplier.payables.some(account => account.value === draft.payable)) add('payable', supplierAccountIssue(supplier) ?? 'The supplier’s payable account could not be chosen. Choose the supplier again.');
  if (!draft.invoice.trim()) add('invoice', 'Enter the supplier invoice number.');
  if (policy.duplicateCheck?.supplier === draft.supplier && policy.duplicateCheck.invoice === draft.invoice.trim() && policy.duplicateCheck.references.length) add('invoice', 'Review the possible duplicate supplier bill before continuing. This preview cannot override the supplied check.');
  if (!validDate(draft.invoiceDate)) add('invoiceDate', 'Enter a valid supplier invoice date.');
  if (!validDate(draft.postingDate)) add('postingDate', 'Enter a valid posting date.');
  if (!policy.modes.includes(draft.mode)) add('mode', 'Choose an available entry mode.');
  const active = draft.lines.filter(line => !isBlankPurchaseLine(line));
  if (!active.length) add('subject', 'Add at least one item or expense account.', draft.lines[0]?.key);
  for (const line of active) {
    const subject = policy.subjects.find(entry => entry.id === line.subject && entry.kind === line.kind);
    if (!subject) add('subject', 'Choose an item or account from the list.', line.key);
    // The service refuses a longer description for the whole bill; say so on the line instead.
    if (line.description.length > 1000) add('description', 'Use at most 1,000 characters in the description.', line.key);
    if (draft.mode !== 'MIXED' && line.kind !== (draft.mode === 'ITEMS' ? 'ITEM' : 'ACCOUNT')) add('kind', 'This retained line needs Mixed mode or a matching entry mode.', line.key);
    if (line.kind === 'ITEM') {
      const billed = nonnegative(line.billed), received = nonnegative(line.received);
      if (billed === null || billed <= 0n) add('billed', 'Billed quantity must be greater than zero.', line.key);
      if (received === null) add('received', 'Enter a valid receipt quantity.', line.key);
      if (nonnegative(line.rate) === null) add('rate', 'Enter a valid rate.', line.key);
      if (billed !== null && received !== null && billed !== received) add('received', 'A direct Purchase bill must receive the same quantity it bills. Use a Receipt Note for a shortage or separate receipt.', line.key);
    } else {
      const amount = nonnegative(line.amount);
      if (amount === null || amount <= 0n) add('amount', 'Account amount must be greater than zero.', line.key);
    }
    if (subject && !purchaseLineAmounts(line)) add('discount', 'Check the amount and discount. Discount cannot exceed the line amount.', line.key);
  }
  const preview = purchaseWorkspacePreview(draft);
  if (preview.limitExceeded && active[0]) add(active[0].kind === 'ACCOUNT' ? 'amount' : 'rate', 'The bill exceeds the supported DECIMAL(19,4) amount range. Reduce or split the entered amounts.', active[0].key);
  problems.push(...purchaseDetailProblems(draft, policy, preview.total).map(problem => ({ ...problem, key: `details:${problem.panel}:${problem.field}:${problem.lineKey ?? ''}` })));
  for (const entry of preview.components.entries) {
    const component = draft.details.components.find(candidate => candidate.id === entry.id)!;
    if (!component.label.trim() || entry.amount === null&&!(policy.live&&entry.requiresOwner)) problems.push({ key: `details:components:${entry.id}`, panel: 'components', field: `component-${entry.id}`, message: 'Check the component name, amount, basis and selected lines.' });
  }
  return problems;
}
