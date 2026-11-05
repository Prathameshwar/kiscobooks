import type { components } from '@janso/api-client/vouchers';
import { trackingId } from './stock-tracking-resources';
import { buildPurchase, type PurchaseDraft, type PurchaseSource } from './purchase-entry';
import type { FieldSet } from './voucher-fields';

type Voucher = components['schemas']['VoucherDetail'];
type Capture = components['schemas']['VoucherInput'];
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const text = (value: unknown) => typeof value === 'string' ? value : '';
const version = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) > 0;
export function editableDraft(company: string, id: string, voucher: Voucher, metadata: FieldSet): Capture {
  if (voucher.id !== id || voucher.company_id !== company || voucher.status !== 'DRAFT' || !version(voucher.row_version) || !trackingId.test(voucher.type_revision_id)) throw new Error('Only a verified draft for this company can be edited.');
  if (metadata.configuration.type_revision_id !== voucher.type_revision_id || metadata.configuration.kind !== voucher.kind) throw new Error('Voucher configuration changed. Review its type before editing this draft.');
  const required = ['document_date', 'currency', 'mode', 'narration', 'lines', 'parties', 'references', 'attachments', 'links', 'custom_fields'] as const;
  if (required.some(key => !metadata.native.properties?.[key] || voucher[key] === null || voucher[key] === undefined)) throw new Error('The full draft capture is not readable. Request field access before replacing its content.');
  const money = ['JOURNAL', 'CONTRA', 'RECEIPT', 'PAYMENT'].includes(voucher.kind ?? '') && !!voucher.financial;
  const invoice = object(voucher.invoice), tax = object(invoice.tax);
  const purchase = voucher.kind === 'PURCHASE' && voucher.profile === 'STANDARD' && tax.profile === 'UNTAXED_ACCOUNT' && ['supplies', 'components', 'tenders', 'allocations'].every(key => Array.isArray(invoice[key])) && ['components', 'tenders', 'allocations'].every(key => (invoice[key] as unknown[]).length === 0);
  if ((!money && !purchase) || voucher.stock || voucher.fulfillment_terms || voucher.mode !== 'ACCOUNTS' || voucher.lines!.length) throw new Error('This capture requires its dedicated voucher editor. Its saved details remain available for review.');
  const key = money ? 'financial' : 'invoice';
  if (!metadata.native.properties?.[key] || metadata.native.properties[key].readOnly) throw new Error('Draft capture edit access is required.');
  const body: Record<string, unknown> = {};
  // Native PUT replaces content. Retain every readable captured field; never copy detail metadata.
  const keys = ['type_revision_id', 'class_id', 'document_date', 'posting_date', 'stock_date', 'statutory_date', 'credit_terms_date', 'mode', 'currency', 'narration', 'lines', 'parties', 'references', 'attachments', 'links', 'custom_fields', 'financial', 'invoice', 'fulfillment_terms', 'stock', 'counter', 'cashier_id'] as const;
  for (const field of keys) if (voucher[field] !== undefined) body[field] = voucher[field];
  if (money && !Array.isArray(object(voucher.financial).accounts)) throw new Error('The financial capture is not fully readable.');
  return body as Capture;
}

/** Labels may resolve to current masters; IDs and versions stay pinned to the saved capture. */
export function purchaseDraftFromCapture(company: string, content: Capture, names: Record<string, string>): PurchaseDraft {
  const invoice = content.invoice!, party = content.parties?.find(row => row.role === 'SUPPLIER');
  const source = (id: string, version: number, partyId?: string): PurchaseSource => {
    if (!trackingId.test(id) || !Number.isSafeInteger(version) || version < 1) throw new Error('The purchase source evidence is not fully readable.');
    return { id, company, version, label: names[id] ?? id, ...(partyId ? { partyId } : {}) };
  };
  if (!party || !invoice.party_line_key || !invoice.party_account_id || !invoice.party_account_version || !invoice.due_date || !invoice.bill_reference) throw new Error('The purchase capture is not fully readable.');
  return { party: source(party.party_id, party.source_version), payable: source(invoice.party_account_id, invoice.party_account_version, party.party_id), partyLineKey: invoice.party_line_key, reference: invoice.bill_reference, dueDate: invoice.due_date, declaredTotal: invoice.supplier_declared_total ?? '', supplies: invoice.supplies.map(line => ({ key: line.line_key, account: source(line.account_id, line.account_version), description: line.description, amount: line.amount })) };
}

/** Replace only the Purchase fields exposed by this editor; retain other capture. */
export function replacePurchaseDraft(company: string, content: Capture, draft: PurchaseDraft, metadata: FieldSet): Pick<Capture, 'invoice' | 'parties' | 'references' | 'mode'> {
  const built = buildPurchase(company, draft, content.document_date, metadata);
  const supplier = content.parties?.findIndex(row => row.role === 'SUPPLIER') ?? -1;
  const invoiceReference = content.references?.findIndex(row => row.purpose === 'SUPPLIER_INVOICE' && row.reference === content.invoice!.bill_reference) ?? -1;
  const parties = (content.parties ?? []).map((row, index) => index === supplier ? { ...row, ...built.parties![0]! } : row);
  const references = (content.references ?? []).map((row, index) => index === invoiceReference ? { ...row, ...built.references![0]! } : row);
  if (supplier < 0) parties.push(built.parties![0]!);
  if (invoiceReference < 0) references.push(built.references![0]!);
  const previous = new Map(content.invoice!.supplies.map(row => [row.line_key, row]));
  return {
    mode: built.mode, parties, references,
    invoice: {
      ...content.invoice!, ...built.invoice!,
      tax: { ...content.invoice!.tax, ...built.invoice!.tax },
      supplies: built.invoice!.supplies.map(row => ({ ...previous.get(row.line_key), ...row })),
      supplier_declared_total: draft.declaredTotal || null,
      accepted_calculation_hash: null,
    },
  };
}
