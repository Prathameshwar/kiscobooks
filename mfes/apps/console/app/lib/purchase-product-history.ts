import * as D from './fixed-decimal';
import { trackingId } from './stock-tracking-resources';
import type { ServiceRequest } from './service-call';
import type { SupplierPurchaseRow } from './purchase-supplier-history';

type Reader = <T>(request: ServiceRequest) => Promise<T>;
type Wire = Record<string, unknown>;
export type ProductPurchaseLine = { key: string; quantity: string; price: string | null; priceFor: string | null; includesTax: boolean;
  discount: string | null; tax: string | null; amount: string | null; reverseCharge: boolean };
export type ProductPurchaseEntry = { invoice: SupplierPurchaseRow; supplierId: string; currency: string; lines: ProductPurchaseLine[]; calculationReady: boolean };
const decimal = (value: unknown): value is string => typeof value === 'string' && D.parse(value) !== null;
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);

/** One invoice detail, then its accepted calculation if available. Never infer GST or discounts from unit price. */
export async function readProductPurchase(read: Reader, company: string, supplier: string | null, product: string, invoiceRow: SupplierPurchaseRow, signal: AbortSignal): Promise<ProductPurchaseEntry> {
  if (![company, product, invoiceRow.id].every(value => trackingId.test(value)) || supplier !== null && !trackingId.test(supplier)) throw Error('Invalid product history reference.');
  const base = `/v1/companies/${company}/vouchers/${invoiceRow.id}`;
  const voucher = await read<Wire>({ service: 'vouchers', path: base, signal });
  if (!voucher || voucher.id !== invoiceRow.id || voucher.company_id !== company || voucher.kind !== 'PURCHASE'
    || invoiceRow.date && voucher.document_date !== invoiceRow.date || typeof voucher.currency !== 'string' || !/^[A-Z]{3}$/.test(voucher.currency)
    || invoiceRow.currency && voucher.currency !== invoiceRow.currency || !Array.isArray(voucher.parties)) throw Error('Product purchase invoice could not be verified.');
  const parties = voucher.parties.filter(raw => { const party = raw as Wire; return party?.role === 'SUPPLIER' && typeof party.party_id === 'string' && trackingId.test(party.party_id); }) as Wire[];
  if (parties.length !== 1 || supplier !== null && parties[0]?.party_id !== supplier) throw Error('Product purchase supplier could not be verified.');
  const supplierId = parties[0]!.party_id as string;
  const invoice = voucher.invoice as Wire | null;
  if (!invoice || !Array.isArray(invoice.supplies) || !Array.isArray(voucher.lines)) throw Error('Product purchase lines are not readable.');
  const common = new Map<string, Wire>();
  for (const raw of voucher.lines) {
    const line = raw as Wire;
    if (typeof line?.line_key === 'string' && trackingId.test(line.line_key)) common.set(line.line_key, line);
  }
  const supplies = invoice.supplies as Wire[];
  const matching = supplies.filter(supply => {
    const line = common.get(String(supply.item_line_key ?? supply.line_key));
    return supply.supply_kind === 'GOODS' && (line?.item as Wire | undefined)?.item_id === product;
  });
  if (!matching.length || matching.length > 200) throw Error('The selected product is not in this purchase invoice.');
  const lines: ProductPurchaseLine[] = matching.map(supply => {
    const key = supply.line_key, line = common.get(String(supply.item_line_key ?? key)), item = line?.item as Wire | undefined;
    const quantity = item?.billed_quantity, denominator = supply.price_denominator == null ? '1' : String(supply.price_denominator);
    if (typeof key !== 'string' || !trackingId.test(key) || !decimal(quantity) || D.parse(quantity)! < 0n
      || !decimal(denominator) || D.parse(denominator)! <= 0n || supply.unit_price != null && !decimal(supply.unit_price)
      || supply.price_basis != null && !['NET_EXCL_TAX', 'GROSS_INCL_TAX'].includes(String(supply.price_basis))) throw Error('Product quantity or price could not be verified.');
    return { key, quantity, price: decimal(supply.unit_price) ? supply.unit_price : null,
      priceFor: D.parse(denominator)! === D.ONE ? null : denominator, includesTax: supply.price_basis === 'GROSS_INCL_TAX',
      discount: null, tax: null, amount: null, reverseCharge: false };
  });
  if (new Set(lines.map(line => line.key)).size !== lines.length) throw Error('Duplicate product lines in purchase history.');
  const accepted = invoice.accepted_calculation_hash;
  if (!hash(accepted) || typeof voucher.row_version !== 'number' || !Number.isSafeInteger(voucher.row_version) || voucher.row_version <= 0) return { invoice: invoiceRow, supplierId, currency: voucher.currency, lines, calculationReady: false };
  try {
    const calculation = await read<Wire>({ service: 'vouchers', path: base + '/invoice-preview', method: 'POST', body: { expected_version: voucher.row_version }, signal });
    if (calculation?.calculation_hash !== accepted || calculation.currency !== voucher.currency || !Array.isArray(calculation.lines)
      || !Array.isArray(calculation.allocations) || invoice.components != null && !Array.isArray(invoice.components)) throw Error('Accepted calculation is unavailable.');
    const discounts = new Set(((invoice.components ?? []) as Wire[]).filter(row => row.purpose === 'DISCOUNT' && typeof row.component_key === 'string').map(row => row.component_key));
    const calculated = new Map<string, Wire>();
    for (const row of calculation.lines as Wire[]) if (typeof row.key === 'string') calculated.set(row.key, row);
    const resolved = lines.map(line => {
      const value = calculated.get(line.key);
      if (!value || !decimal(value.payable) || !Array.isArray(value.taxes)) throw Error('Product calculation is incomplete.');
      let tax = D.ZERO, discount = D.ZERO, reverseCharge = false;
      for (const raw of value.taxes) {
        const component = raw as Wire;
        if (!decimal(component.amount) || typeof component.supplier_charged !== 'boolean') throw Error('Product tax is incomplete.');
        tax += D.parse(component.amount)!;
        if (!component.supplier_charged) reverseCharge = true;
      }
      for (const raw of calculation.allocations as Wire[]) {
        if (raw.line_key !== line.key || raw.purpose !== 'COMMERCIAL' || !discounts.has(raw.component_key)) continue;
        if (!decimal(raw.amount) || D.parse(raw.amount)! > 0n) throw Error('Product discount is incomplete.');
        discount -= D.parse(raw.amount)!;
      }
      return { ...line, discount: D.format(discount), tax: D.format(tax), amount: value.payable, reverseCharge };
    });
    return { invoice: invoiceRow, supplierId, currency: voucher.currency, lines: resolved, calculationReady: true };
  } catch {
    if (signal.aborted) throw Error('Product history request cancelled.');
    return { invoice: invoiceRow, supplierId, currency: voucher.currency, lines, calculationReady: false };
  }
}

/** Accounting owns the name; use its company-scoped party read rather than a voucher-side copy. */
export async function readProductPurchaseSupplierName(read: Reader, company: string, supplier: string, signal: AbortSignal): Promise<string> {
  if (!trackingId.test(company) || !trackingId.test(supplier)) throw Error('Invalid supplier reference.');
  const party = await read<Wire>({ service: 'accounting', path: `/v1/companies/${company}/parties/${supplier}`, signal });
  if (!party || party.id !== supplier || party.company_id !== company) throw Error('Supplier name could not be verified.');
  const name = typeof party.name === 'string' && party.name.trim() ? party.name.trim() : typeof party.code === 'string' && party.code.trim() ? party.code.trim() : '';
  if (!name || name.length > 160) throw Error('Supplier name is unavailable.');
  return name;
}
