import { describe, expect, it, vi } from 'vitest';
import { readSupplierPurchases, type SupplierPurchaseRow } from '../app/lib/purchase-supplier-history';
import { readProductPurchase, readProductPurchaseSupplierName } from '../app/lib/purchase-product-history';
import type { ServiceRequest } from '../app/lib/service-call';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), supplier = id(2), product = id(3), voucher = id(4), line = id(5), second = id(6), discount = id(7);
const accepted = 'a'.repeat(64), signal = new AbortController().signal;
const row: SupplierPurchaseRow = { id: voucher, invoice: 'INV-28', date: '2026-11-04', amount: '200.0000', currency: 'INR', status: 'POSTED' };
const detail = {
  id: voucher, company_id: company, kind: 'PURCHASE', document_date: row.date, currency: 'INR', row_version: 2,
  parties: [{ role: 'SUPPLIER', party_id: supplier }],
  lines: [{ line_key: line, item: { item_id: product, billed_quantity: '2.0000' } }, { line_key: second, item: { item_id: product, billed_quantity: '1.0000' } }],
  invoice: { accepted_calculation_hash: accepted, components: [{ component_key: discount, purpose: 'DISCOUNT' }], supplies: [
    { line_key: line, item_line_key: line, supply_kind: 'GOODS', unit_price: '100.0000', price_denominator: '1', price_basis: 'NET_EXCL_TAX' },
    { line_key: second, item_line_key: second, supply_kind: 'GOODS', unit_price: '50.0000', price_denominator: '1', price_basis: 'NET_EXCL_TAX' },
  ] },
};
const calculation = { calculation_hash: accepted, currency: 'INR', lines: [
  { key: line, payable: '210.0000', taxes: [{ amount: '20.0000', supplier_charged: true }] },
  { key: second, payable: '55.0000', taxes: [{ amount: '5.0000', supplier_charged: false }] },
], allocations: [{ component_key: discount, line_key: line, purpose: 'COMMERCIAL', amount: '-10.0000' }] };

describe('product purchases from selected supplier', () => {
  it('requests a date-descending, supplier and product filtered page of ten', async () => {
    const read = vi.fn(async (_request: ServiceRequest) => ({ items: [], page: { next_cursor: null } }));
    await readSupplierPurchases(read as never, company, supplier, signal, undefined, product);
    expect(Object.fromEntries(new URL(read.mock.calls[0]![0].path, 'https://example.invalid').searchParams)).toEqual({
      kind: 'PURCHASE', party_id: supplier, sort: '-document_date', limit: '10', item_id: product,
    });
    expect(read).toHaveBeenCalledTimes(1);
  });

  it('requests all suppliers for the product without a party filter', async () => {
    const read = vi.fn(async (_request: ServiceRequest) => ({ items: [], page: { next_cursor: null } }));
    await readSupplierPurchases(read as never, company, null, signal, undefined, product);
    expect(Object.fromEntries(new URL(read.mock.calls[0]![0].path, 'https://example.invalid').searchParams)).toEqual({
      kind: 'PURCHASE', sort: '-document_date', limit: '10', item_id: product,
    });
    await expect(readSupplierPurchases(read as never, company, null, signal)).rejects.toThrow('Invalid');
  });

  it('shows each matching line with saved quantity and price and accepted discount, tax and payable', async () => {
    const read = vi.fn(async (request: ServiceRequest) => request.path.endsWith('/invoice-preview') ? calculation : detail);
    const result = await readProductPurchase(read as never, company, supplier, product, row, signal);
    expect(read).toHaveBeenCalledTimes(2);
    expect(read.mock.calls[1]![0].body).toEqual({ expected_version: 2 });
    expect(result.calculationReady).toBe(true);
    expect(result.supplierId).toBe(supplier);
    expect(result.lines).toMatchObject([
      { quantity: '2.0000', price: '100.0000', discount: '10.0000', tax: '20.0000', amount: '210.0000', reverseCharge: false },
      { quantity: '1.0000', price: '50.0000', discount: '0.0000', tax: '5.0000', amount: '55.0000', reverseCharge: true },
    ]);
  });

  it('does not display unaccepted calculated money', async () => {
    const read = vi.fn(async (request: ServiceRequest) => request.path.endsWith('/invoice-preview') ? { ...calculation, calculation_hash: 'b'.repeat(64) } : detail);
    const result = await readProductPurchase(read as never, company, supplier, product, row, signal);
    expect(result.calculationReady).toBe(false);
    expect(result.lines[0]).toMatchObject({ quantity: '2.0000', price: '100.0000', discount: null, tax: null, amount: null });
  });

  it('does not request a calculation for an invoice without an accepted hash', async () => {
    const read = vi.fn(async (_request: ServiceRequest) => ({ ...detail, invoice: { ...detail.invoice, accepted_calculation_hash: null } }));
    const result = await readProductPurchase(read as never, company, supplier, product, row, signal);
    expect(read).toHaveBeenCalledTimes(1);
    expect(result.calculationReady).toBe(false);
    expect(result.lines[0]?.amount).toBeNull();
  });

  it('rejects invoices from another supplier or without the selected product', async () => {
    await expect(readProductPurchase((async () => ({ ...detail, parties: [{ role: 'SUPPLIER', party_id: id(9) }] })) as never, company, supplier, product, row, signal)).rejects.toThrow('verified');
    await expect(readProductPurchase((async () => ({ ...detail, lines: [] })) as never, company, supplier, product, row, signal)).rejects.toThrow('selected product');
  });

  it('identifies each supplier in the all-suppliers view and reads its company-scoped name', async () => {
    const other = id(9);
    const entry = await readProductPurchase((async (request: ServiceRequest) => request.path.endsWith('/invoice-preview') ? calculation : { ...detail, parties: [{ role: 'SUPPLIER', party_id: other }] }) as never, company, null, product, row, signal);
    expect(entry.supplierId).toBe(other);
    const read = vi.fn(async (_request: ServiceRequest) => ({ id: other, company_id: company, name: '  New Supplier  ' }));
    expect(await readProductPurchaseSupplierName(read as never, company, other, signal)).toBe('New Supplier');
    expect(read.mock.calls[0]![0].path).toBe(`/v1/companies/${company}/parties/${other}`);
    await expect(readProductPurchaseSupplierName((async () => ({ id: other, company_id: id(10), name: 'Wrong company' })) as never, company, other, signal)).rejects.toThrow('verified');
  });
});
