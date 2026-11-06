import { describe, expect, it, vi } from 'vitest';
import { readSupplierPurchaseDetail, readSupplierPurchases } from '../app/lib/purchase-supplier-history';
import type { ServiceRequest } from '../app/lib/service-call';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), supplier = id(2), voucher = id(3), line = id(4), product = id(5);
const signal = new AbortController().signal;

describe('supplier purchase history reads', () => {
  it('requests only a bounded supplier page and preserves exact amounts', async () => {
    const read = vi.fn(async (_request: ServiceRequest) => ({ items: [{ id: voucher, company_id: company, kind: 'PURCHASE', status: 'POSTED', ref_number: 'SUP-42', document_date: '2026-11-01', amount: '1250.2500', currency: 'INR' }], page: { next_cursor: 'more' } }));
    const result = await readSupplierPurchases(read as never, company, supplier, signal);
    expect(result).toEqual({ items: [{ id: voucher, invoice: 'SUP-42', date: '2026-11-01', amount: '1250.2500', currency: 'INR', status: 'POSTED' }], next: 'more' });
    expect(read).toHaveBeenCalledTimes(1);
    const request = read.mock.calls[0]![0];
    expect(request.service).toBe('vouchers'); expect(request.signal).toBe(signal);
    expect(Object.fromEntries(new URL(request.path, 'https://example.invalid').searchParams)).toEqual({ kind: 'PURCHASE', party_id: supplier, sort: '-document_date', limit: '25' });
  });

  it('loads only the opened voucher and shows its saved billed quantity and unit price', async () => {
    const read = vi.fn(async (_request: ServiceRequest) => ({ id: voucher, company_id: company, kind: 'PURCHASE', parties: [{ role: 'SUPPLIER', party_id: supplier }],
      lines: [{ line_key: line, item: { item_id: product, billed_quantity: '3.5000' } }], invoice: { supplies: [{ line_key: line, item_line_key: line, supply_kind: 'GOODS', description: 'Paper boxes', amount: '700.0000', unit_price: '200.0000' }] } }));
    const result = await readSupplierPurchaseDetail(read as never, company, supplier, voucher, signal);
    expect(result.lines).toEqual([{ key: line, description: 'Paper boxes', quantity: '3.5000', price: '200.0000', priceFor: null, includesTax: false, amount: '700.0000', kind: 'ITEM' }]);
    expect(read.mock.calls[0]![0].path).toBe(`/v1/companies/${company}/vouchers/${voucher}`);
    expect(read).toHaveBeenCalledTimes(1);
  });

  it('rejects a detail for another supplier or an unverified product quantity', async () => {
    const base = { id: voucher, company_id: company, kind: 'PURCHASE', parties: [{ role: 'SUPPLIER', party_id: id(9) }], lines: [], invoice: { supplies: [] } };
    await expect(readSupplierPurchaseDetail((async () => base) as never, company, supplier, voucher, signal)).rejects.toThrow('does not belong');
    await expect(readSupplierPurchaseDetail((async () => ({ ...base, parties: [{ role: 'SUPPLIER', party_id: supplier }], invoice: { supplies: [{ line_key: line, supply_kind: 'GOODS', description: 'Paper', amount: '2.0000', unit_price: '1.0000' }] } })) as never, company, supplier, voucher, signal)).rejects.toThrow('quantity');
  });

  it('keeps a saved price per pack and its inclusive tax basis visible', async () => {
    const result = await readSupplierPurchaseDetail((async () => ({ id: voucher, company_id: company, kind: 'PURCHASE', parties: [{ role: 'SUPPLIER', party_id: supplier }],
      lines: [{ line_key: line, item: { item_id: product, billed_quantity: '10.0000' } }], invoice: { supplies: [{ line_key: line, supply_kind: 'GOODS', description: 'Ten pens', amount: '120.0000', unit_price: '120.0000', price_denominator: '10', price_basis: 'GROSS_INCL_TAX' }] } })) as never, company, supplier, voucher, signal);
    expect(result.lines[0]).toMatchObject({ price: '120.0000', priceFor: '10', includesTax: true });
  });

  it('shows an account-only bill even when it has no common product lines', async () => {
    const result = await readSupplierPurchaseDetail((async () => ({ id: voucher, company_id: company, kind: 'PURCHASE', parties: [{ role: 'SUPPLIER', party_id: supplier }],
      invoice: { supplies: [{ line_key: line, supply_kind: 'SERVICE', description: 'Repairs', amount: '500.0000' }] } })) as never, company, supplier, voucher, signal);
    expect(result.lines[0]).toMatchObject({ kind: 'ACCOUNT', description: 'Repairs', quantity: null, price: null });
  });
});
