import type { SearchSelectLoader } from '@janso/ui';
import type { components } from '@janso/api-client/vouchers';
import type { components as accounting } from '@janso/api-client/accounting';
import { productFieldRequest as request } from './product-fields';
import type { FieldSet, Native } from './voucher-fields';
import { trackingId } from './stock-tracking-resources';
import { validMasterDate } from './catalog-masters';

export type PurchaseSource = { id: string; company: string; version: number; label: string; partyId?: string };
export type PurchaseDraft = {
  party: PurchaseSource | null; payable: PurchaseSource | null;
  partyLineKey: string; reference: string; dueDate: string; declaredTotal: string;
  supplies: { key: string; account: PurchaseSource | null; description: string; amount: string }[];
};
export const nativeProperties = (field?: Native): Record<string, Native> => field?.properties ?? field?.anyOf?.find(branch => branch.properties)?.properties ?? {};
export const initialPurchase = (date: string): PurchaseDraft => ({ party: null, payable: null, partyLineKey: crypto.randomUUID(), reference: '', dueDate: date, declaredTotal: '', supplies: [] });
const decimal = /^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;
const version = (value: number) => Number.isSafeInteger(value) && value >= 1;
const fail = (message: string): never => { throw new Error(message); };
export class PurchaseValidationError extends Error {
  constructor(message: string, public field: string) { super(message); }
}
const invalid = (field: string, message: string): never => { throw new PurchaseValidationError(message, field); };
const sourceValid = (source: PurchaseSource | null, company: string) => !!source && trackingId.test(source.id) && source.company === company && version(source.version);

/** Why a product or mixed Purchase type cannot be used here: its rules do not allow goods lines. */
export const PURCHASE_GOODS_UNAVAILABLE = 'This Purchase type takes item lines but its rules do not allow goods supplies. An administrator can allow Goods in the type’s purchase rules; an Account Bill type records expense and service bills.';
/** A Product or Mixed Purchase type whose bill brings its goods into stock (B24). */
export function purchaseGoodsAllowed(metadata: FieldSet): boolean {
  const { kind, profile, policy } = metadata.configuration;
  return kind === 'PURCHASE' && profile === 'STANDARD' && !!policy.invoice?.allowed_supply_kinds?.includes('GOODS')
    && !!policy.allowed_modes?.some(mode => mode === 'ITEMS' || mode === 'MIXED');
}
/** The entry modes this screen offers for the type, in its own order: products, accounts, both. */
export function purchaseModes(metadata: FieldSet): ('ITEMS' | 'ACCOUNTS' | 'MIXED')[] {
  const allowed = metadata.configuration.policy.allowed_modes ?? ['ACCOUNTS'];
  const goods = purchaseGoodsAllowed(metadata);
  return (['ITEMS', 'ACCOUNTS', 'MIXED'] as const).filter(mode => allowed.includes(mode) && (mode === 'ACCOUNTS' || goods));
}
export function purchaseGoodsType(metadata: FieldSet): boolean {
  const { kind, policy } = metadata.configuration;
  return kind === 'PURCHASE' && ((policy.default_mode !== undefined && policy.default_mode !== 'ACCOUNTS') || !policy.allowed_modes?.includes('ACCOUNTS') || !!policy.required_sections?.includes('ITEMS'));
}
export function purchaseAvailability(metadata: FieldSet): string | null {
  const { kind, profile, policy } = metadata.configuration;
  const issues: string[] = [];
  if (kind !== 'PURCHASE') issues.push(`Choose a Purchase voucher type. The selected kind is ${kind}.`);
  if (profile !== 'STANDARD') issues.push(`This form requires Standard Purchase; the selected profile is ${profile}.`);
  const goods = purchaseGoodsAllowed(metadata);
  if (!policy.invoice) issues.push('Invoice rules are missing. Enable invoice entry for this Purchase voucher type.');
  else if (!goods && !policy.invoice.allowed_supply_kinds?.includes('ACCOUNT')) issues.push('Account purchase lines are disabled. Allow Account in the invoice supply kinds.');
  if (!goods && !policy.allowed_modes?.includes('ACCOUNTS')) issues.push('Accounts mode is disabled. Allow Accounts in the voucher type entry modes.');
  if (!policy.allowed_party_roles?.includes('SUPPLIER')) issues.push('Supplier parties are disabled. Allow the Supplier party role.');
  if (policy.max_parties === 0) issues.push('The party limit is zero. Set maximum parties to at least 1.');
  if (!goods && policy.required_sections?.includes('ITEMS')) issues.push('Item lines are required, but this form prepares account purchase bills. Remove Items from Required sections to use account entry; keep this requirement if the type is intended for item purchases.');
  if (policy.required_sections?.includes('CHARGES') && !policy.invoice?.charges_allowed && !policy.invoice?.manual_discounts_allowed) issues.push('Charges are required, but charges and manual discounts are disabled. Remove Charges from Required sections or enable the applicable invoice components.');
  const forbidden = policy.forbidden_sections?.filter(section => ['ACCOUNTS', 'PARTIES', 'REFERENCES', 'TAX'].includes(section));
  if (forbidden?.length) issues.push(`Required purchase sections are disabled: ${forbidden.join(', ')}. Allow these sections in the entry rules.`);
  if (issues.length) return issues.join(' ');
  const fields = metadata.native.properties ?? {}, invoice = nativeProperties(fields.invoice);
  const protectedFields = [['invoice', 'invoice'], ['posting_date', 'posting date'], ['parties', 'supplier'], ['references', 'supplier reference']]
    .filter(([key]) => !fields[key!] || fields[key!].readOnly).map(([, label]) => label);
  if (protectedFields.length) return `Missing write access for ${protectedFields.join(', ')}. Ask a company administrator to grant access before preparing this bill.`;
  const required = ['party_line_key', 'party_account_id', 'party_account_version', 'bill_reference', 'due_date', 'supplies', 'tax'];
  const missingInvoice = required.filter(key => !invoice[key] || invoice[key].readOnly);
  if (missingInvoice.length) return `Missing invoice write access: ${missingInvoice.map(key => key.replaceAll('_', ' ')).join(', ')}. Ask a company administrator to review field access.`;
  const supplies = nativeProperties(invoice.supplies?.items);
  const missingLines = ['line_key', 'account_id', 'account_version', 'description', 'amount', 'supply_kind'].filter(key => !supplies[key] || supplies[key].readOnly);
  if (missingLines.length) return `Missing purchase-line write access: ${missingLines.map(key => key.replaceAll('_', ' ')).join(', ')}. Ask a company administrator to review field access.`;
  return null;
}

/** How the bill is taxed, as the invoice carries it: the tax block, and what each line is a supply of. */
export type PurchaseTaxWire = { context: components['schemas']['InvoiceTaxContext']; supplyKind: 'ACCOUNT' | 'SERVICE' };
const UNTAXED: PurchaseTaxWire = { context: { profile: 'UNTAXED_ACCOUNT' }, supplyKind: 'ACCOUNT' };

/** Existing typed capture only; Accounting computes and validates the invoice. */
export function buildPurchase(company: string, draft: PurchaseDraft, documentDate: string, metadata: FieldSet, tax: PurchaseTaxWire = UNTAXED, goodsLines = 0): Pick<components['schemas']['VoucherInput'], 'invoice' | 'parties' | 'references' | 'mode'> {
  const unavailable = purchaseAvailability(metadata); if (unavailable) fail(unavailable);
  if (tax.supplyKind === 'SERVICE' && !metadata.configuration.policy.invoice?.allowed_supply_kinds?.includes('SERVICE')) fail('GST is recorded on service supplies, and this voucher type does not allow them. Allow service purchase lines in the voucher type’s purchase rules, or record the bill without tax.');
  if (!sourceValid(draft.party, company)) invalid('party', 'Select a verified active supplier.');
  if (!sourceValid(draft.payable, company) || draft.payable?.partyId !== draft.party?.id) invalid('payable', 'Select this supplier’s active payable account.');
  if (!trackingId.test(draft.partyLineKey)) fail('Reload the purchase entry to restore its line identity.');
  if (!validMasterDate(documentDate) || !validMasterDate(draft.dueDate) || draft.dueDate < documentDate) invalid('dueDate', 'Enter a valid due date on or after the document date.');
  const reference = draft.reference.trim();
  if (!reference || reference.length > 100 || /[\x00-\x1f]/.test(reference)) invalid('reference', 'Enter the supplier invoice reference (up to 100 printable characters).');
  // A product bill's goods lines are built beside these account/service lines; together they respect the limit.
  if (!draft.supplies.length && !goodsLines || draft.supplies.length + goodsLines > Math.min(metadata.configuration.policy.max_lines ?? 200, 200)) invalid('supplies', 'Add purchase lines within the configured limit.');
  const keys = new Set<string>();
  const supplies = draft.supplies.map((line, index) => {
    const prefix = 'Purchase line ' + (index + 1) + ': ';
    if (!trackingId.test(line.key) || keys.has(line.key)) fail(prefix + 'reload to restore a distinct line identity.'); keys.add(line.key);
    if (!sourceValid(line.account, company) || line.account?.partyId) invalid(line.key + '.account', prefix + 'select a verified general expense account.');
    if (!line.description.trim() || line.description.trim().length > 1000) invalid(line.key + '.description', prefix + 'enter a description of up to 1,000 characters.');
    if (!decimal.test(line.amount) || /^0(?:\.0+)?$/.test(line.amount)) invalid(line.key + '.amount', prefix + 'enter a positive amount with at most four decimal places.');
    return { line_key: line.key, account_id: line.account!.id, account_version: line.account!.version, supply_kind: tax.supplyKind, description: line.description.trim(), amount: line.amount, price_basis: 'NET_EXCL_TAX' as const };
  });
  const invoice: components['schemas']['InvoiceInput-Input'] = { party_line_key: draft.partyLineKey, party_account_id: draft.payable!.id, party_account_version: draft.payable!.version, bill_reference: reference, due_date: draft.dueDate, tax: tax.context, supplies, components: [], tenders: [], allocations: [] };
  if (draft.declaredTotal) {
    const field = nativeProperties(metadata.native.properties?.invoice).supplier_declared_total;
    if (!field || field.readOnly) fail('Supplier-declared total write access is required.');
    if (!decimal.test(draft.declaredTotal)) invalid('declaredTotal', 'Enter a valid supplier-declared total with at most four decimal places.');
    invoice.supplier_declared_total = draft.declaredTotal;
  }
  return { mode: 'ACCOUNTS', invoice, parties: [{ role: 'SUPPLIER', party_id: draft.party!.id, source_version: draft.party!.version }], references: [{ purpose: 'SUPPLIER_INVOICE', reference, reference_date: documentDate }] };
}

export function purchaseLookup(company: string, resource: 'suppliers' | 'payables' | 'expenses', supplier?: string): SearchSelectLoader {
  return async ({ q, cursor, signal }) => {
    if (resource === 'payables' && !trackingId.test(supplier ?? '')) return { items: [], nextCursor: null };
    const params = new URLSearchParams({ status: 'ACTIVE', limit: '50', ...(q ? { q: q.trim().slice(0, 200) } : {}), ...(cursor ? { cursor } : {}) });
    if (resource === 'suppliers') params.set('role', 'SUPPLIER');
    else { params.set('kind', resource === 'payables' ? 'PARTY' : 'GENERAL'); if (resource === 'payables') params.set('party_id', supplier!); }
    const page = await request<{ items: { id: string; company_id?: string; name?: string; code?: string }[]; page: { next_cursor: string | null } }>('accounting', 'GET', `/v1/companies/${company}/${resource === 'suppliers' ? 'parties' : 'accounts'}?${params}`, undefined, undefined, signal);
    if (!Array.isArray(page.items) || page.items.length > 50 || !page.page || page.page.next_cursor !== null && typeof page.page.next_cursor !== 'string' || page.items.some(row => !trackingId.test(row.id) || row.company_id && row.company_id !== company)) fail('The purchase lookup could not be verified.');
    return { items: page.items.filter(row => row.name || row.code).map(row => ({ id: row.id, label: row.name ?? row.code!, meta: row.code })), nextCursor: page.page.next_cursor };
  };
}

/**
 * The supplier's payable accounts: its active party accounts in the supplier role. A supplier is never asked for
 * one — it has exactly one, and choosing the supplier chooses it — so the caller takes the only one and treats any
 * other count as a data problem to report. A party that is also a customer holds a receivable too; that is not a
 * payable and is left out rather than failing the supplier.
 */
export async function supplierPayables(company: string, supplier: string): Promise<PurchaseSource[]> {
  const page = await request<{ items: { id: string; company_id: string; party_role?: string | null }[]; page: { next_cursor: string | null } }>('accounting', 'GET', `/v1/companies/${company}/accounts?kind=PARTY&party_id=${supplier}&role=SUPPLIER&status=ACTIVE&limit=200`);
  if (!Array.isArray(page.items) || page.page?.next_cursor || page.items.some(row => row.company_id !== company || !trackingId.test(row.id) || row.party_role !== 'SUPPLIER')) fail('The supplier payable accounts could not be verified.');
  return Promise.all(page.items.map(row => purchaseSource(company, 'payables', row.id, supplier)));
}

export async function purchaseSource(company: string, resource: 'suppliers' | 'payables' | 'expenses', id: string, supplier?: string): Promise<PurchaseSource> {
  if (!trackingId.test(id)) fail('Select a valid purchase reference.');
  const row = await request<accounting['schemas']['AccountDetail']>('accounting', 'GET', `/v1/companies/${company}/${resource === 'suppliers' ? 'parties' : 'accounts'}/${id}`);
  if (row.id !== id || row.company_id !== company || row.status !== 'ACTIVE' || !version(row.row_version) || !row.name && !row.code) fail('The selected purchase reference is unavailable for this company.');
  if (resource === 'suppliers') {
    const roles = await request<{ items: accounting['schemas']['PartyRoleDetail'][]; page: { next_cursor: string | null } }>('accounting', 'GET', `/v1/companies/${company}/party-roles?party_id=${id}&role=SUPPLIER&limit=50`);
    if (!Array.isArray(roles.items) || roles.items.length > 50 || !roles.items.some(role => role.company_id === company && role.party_id === id && role.role === 'SUPPLIER' && trackingId.test(role.id))) fail('The selected party has no readable supplier role for this company.');
  } else if (resource === 'payables' ? row.kind !== 'PARTY' || row.party_id !== supplier || row.party_role !== 'SUPPLIER' : row.kind !== 'GENERAL' || row.inventory_affected !== false) fail('Choose an active supplier, its payable, or a general expense account as appropriate.');
  if (resource === 'expenses') {
    if (!trackingId.test(row.group_id ?? '') || row.posting_policy !== 'MANUAL_ALLOWED') fail('Choose a general expense account that permits posting.');
    const group = await request<accounting['schemas']['AccountGroupDetail']>('accounting', 'GET', `/v1/companies/${company}/account-groups/${row.group_id}`);
    if (group.company_id !== company || group.id !== row.group_id || !trackingId.test(group.head_id ?? '')) fail('The expense account group could not be verified.');
    const head = await request<accounting['schemas']['AccountHeadDetail']>('accounting', 'GET', `/v1/companies/${company}/account-heads/${group.head_id}`);
    if (head.company_id !== company || head.id !== group.head_id || head.nature !== 'EXPENSE') fail('Choose an account under an expense head for this account bill.');
  }
  return { id: row.id, company, version: row.row_version, label: row.name ?? row.code!, ...(resource === 'payables' ? { partyId: row.party_id! } : {}) };
}
