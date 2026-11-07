import { beforeEach, describe, expect, it, vi } from 'vitest';
import { livePurchasePolicy, purchaseFromVoucher, purchaseInput, PURCHASE_BROADER_CAPTURE, type PurchaseBinding, type PurchaseInput, type PurchaseVoucher } from '../app/lib/purchase-api';
import { purchaseAvailability, purchaseGoodsAllowed, purchaseModes } from '../app/lib/purchase-entry';
import { goodsLine, pricedAmount, purchaseGoodsContext, purchaseItem, purchaseItemLookup, type PurchaseItem } from '../app/lib/purchase-goods';
import { blankPurchaseLine, newPurchaseWorkspace, purchaseSubjectLookup, purchaseWorkspaceReducer, withPairedQuantity, type PurchaseWorkspaceDraft } from '../app/lib/purchase-workspace';
import { blankPurchaseTax, noTaxFacts, type CompanyGst, type PurchaseTaxFacts, type SupplierGst } from '../app/lib/purchase-tax';
import { productFieldRequest } from '../app/lib/product-fields';
import * as D from '../app/lib/fixed-decimal';
import { company, draft as native, metadata as baseMetadata } from './purchase-entry-fixtures';
import type { FieldSet } from '../app/lib/voucher-fields';

vi.mock('../app/lib/product-fields', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/product-fields')>(), productFieldRequest: vi.fn() }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const supplier = native.party!.id;
const milk: PurchaseItem = { id: id(50), company, version: 3, baseUnitId: id(51), label: 'Milk 1L', unit: 'L' };
const ghee: PurchaseItem = { id: id(52), company, version: 1, baseUnitId: id(53), label: 'Ghee 500g', unit: 'pc' };
const goods = { inventory: { id: id(60), version: 2 }, warehouse: id(61) };
const mine: CompanyGst = { id: id(20), number: '27AAAAA0000A1Z5', state: 'IN-MH', primary: true, from: '2020-04-01', to: null };
const regular: SupplierGst = { id: id(30), type: 'REGULAR', state: 'IN-GJ', number: '24BBBBB1111B1Z6', from: '2019-07-01', to: null };
const facts = (): PurchaseTaxFacts => ({ ...noTaxFacts(), companies: [mine], suppliers: new Map([[supplier, [regular]]]) });
let metadata: FieldSet, binding: PurchaseBinding;

const item = (key: string, product: PurchaseItem, quantity: string, rate: string) => ({ ...blankPurchaseLine(key, 'ITEM'), subject: product.id, label: product.label, unit: product.unit, received: quantity, billed: quantity, rate });
const draft = (mode: PurchaseWorkspaceDraft['mode'] = 'ITEMS', choice: 'NONE' | 'FORWARD' | 'REVERSE' = 'NONE'): PurchaseWorkspaceDraft => {
  const value = newPurchaseWorkspace('2026-10-30');
  Object.assign(value, { mode, supplier, payable: native.payable!.id, invoice: 'SUP-77', postingDate: '2026-10-31', lines: [item('p1', milk, '10', '100'), item('p2', ghee, '5', '100')] });
  if (mode === 'MIXED') value.lines.splice(1, 0, { ...blankPurchaseLine('p3', 'ACCOUNT'), subject: native.supplies[0]!.account!.id, label: 'Expense', description: 'Unloading', amount: '150' });
  value.details.termsDays = '2'; value.tax = { ...blankPurchaseTax(), choice };
  return value;
};
/** The saved voucher the service returns for a wire capture: the same capture, with its identity. */
const saved = (wire: PurchaseInput): PurchaseVoucher => structuredClone({ ...wire, id: id(90), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', status: 'DRAFT', revision_id: id(91), row_version: 7, revision_number: 3, attachments: [], links: [], custom_fields: {} }) as unknown as PurchaseVoucher;

beforeEach(() => {
  vi.mocked(productFieldRequest).mockReset();
  metadata = structuredClone(baseMetadata);
  Object.assign(metadata.native.properties!, Object.fromEntries(['document_date', 'credit_terms_date', 'currency', 'narration', 'mode', 'lines', 'stock_date', 'stock', 'attachments', 'links', 'custom_fields'].map(key => [key, {}])));
  metadata.native.properties!.stock = { properties: { lines: { items: { properties: Object.fromEntries(['item_id', 'quantity', 'warehouse_id', 'bin_id', 'lot_id', 'unit_ids'].map(key => [key, {}])) } } } };
  Object.assign(metadata.native.properties!.invoice!.anyOf![0]!.properties!, { components: {}, allocations: {}, tenders: {} });
  Object.assign(metadata.configuration.policy, { allowed_modes: ['ITEMS', 'ACCOUNTS', 'MIXED'], default_mode: 'ITEMS', invoice: { allowed_supply_kinds: ['GOODS', 'ACCOUNT', 'SERVICE'] } });
  binding = { company, currency: 'INR', metadata, keys: new Map(), partyKey: native.partyLineKey, sources: new Map([native.party!, native.payable!, native.supplies[0]!.account!].map(source => [source.id, source])),
    items: new Map([[milk.id, milk], [ghee.id, ghee]]), goods, rounding: { places: 2, mode: 'half_up' },
    tracking: new Map([milk, ghee].map(product => [product.id, { itemId: product.id, companyId: company, profileRevisionId: id(67), lotTracking: false, serialTracking: false }])) };
});

describe('which Purchase types take goods', () => {
  it('offers products, accounts and mixed bills where the type allows goods supplies, in that order', () => {
    expect(purchaseGoodsAllowed(metadata)).toBe(true);
    expect(purchaseModes(metadata)).toEqual(['ITEMS', 'ACCOUNTS', 'MIXED']);
    expect(livePurchasePolicy('INR', metadata).modes).toEqual(['ITEMS', 'ACCOUNTS', 'MIXED']);
    expect(purchaseAvailability(metadata)).toBeNull();
  });
  it('keeps an account type to account bills, and a product type without goods supplies away from goods', () => {
    Object.assign(metadata.configuration.policy, { allowed_modes: ['ACCOUNTS'], invoice: { allowed_supply_kinds: ['ACCOUNT'] } });
    expect(purchaseGoodsAllowed(metadata)).toBe(false); expect(purchaseModes(metadata)).toEqual(['ACCOUNTS']);
    Object.assign(metadata.configuration.policy, { allowed_modes: ['ITEMS', 'MIXED'], invoice: { allowed_supply_kinds: ['ACCOUNT'] } });
    expect(purchaseGoodsAllowed(metadata)).toBe(false); expect(purchaseModes(metadata)).toEqual([]);
  });
  it('respects the type mode and the goods stock field access', () => {
    const entry = draft(); entry.mode = 'MIXED'; entry.lines = [entry.lines[0]!];
    expect(purchaseInput(entry, binding).mode).toBe('MIXED');
    metadata.configuration.policy.allowed_modes = ['ITEMS'];
    expect(() => purchaseInput(entry, binding)).toThrow(/entry mode is not allowed/);
    metadata.configuration.policy.allowed_modes = ['ITEMS', 'MIXED'];
    delete metadata.native.properties!.stock_date;
    expect(purchaseAvailability(metadata)).toMatch(/stock date/);
  });
  it('treats omitted supply kinds as the invoice policy default', () => {
    metadata.configuration.policy.invoice = {};
    expect(purchaseModes(metadata)).toEqual(['ITEMS', 'ACCOUNTS', 'MIXED']);
  });
  it('searches products for an item line and accounts for the others', () => {
    const accounts = vi.fn(), products = vi.fn(), policy = { ...livePurchasePolicy('INR', metadata), subjectLookup: accounts, itemLookup: products };
    expect(purchaseSubjectLookup(policy, 'ITEM')).toBe(products); expect(purchaseSubjectLookup(policy, 'ACCOUNT')).toBe(accounts);
  });
});

describe('a product bill on the wire', () => {
  it('bills each product into inventory, receives it into the warehouse on the posting date, and keeps the entered order', () => {
    const wire = purchaseInput(draft(), binding);
    expect(wire.mode).toBe('ITEMS');
    const [first, second] = wire.invoice!.supplies;
    expect(first).toMatchObject({ supply_kind: 'GOODS', account_id: goods.inventory.id, account_version: 2, amount: '1000.0000', unit_price: '100.0000', description: 'Milk 1L', item_line_key: first!.line_key,
      quantities: [{ basis: 'ACTUAL', quantity: '10.0000', unit_id: milk.baseUnitId }, { basis: 'BILLED', quantity: '10.0000', unit_id: milk.baseUnitId }] });
    expect(second!.amount).toBe('500.0000');
    expect(wire.lines).toEqual([
      { line_key: first!.line_key, line_kind: 'ITEM', description: 'Milk 1L', item: { item_id: milk.id, item_version: 3, unit_id: milk.baseUnitId, actual_quantity: '10.0000', billed_quantity: '10.0000' } },
      { line_key: second!.line_key, line_kind: 'ITEM', description: 'Ghee 500g', item: { item_id: ghee.id, item_version: 1, unit_id: ghee.baseUnitId, actual_quantity: '5.0000', billed_quantity: '5.0000' } },
    ]);
    expect(wire.stock_date).toBe('2026-10-31');
    expect(wire.stock).toEqual({ action: 'PURCHASE_INVOICE', stock_date: '2026-10-31', currency: 'INR', reason: 'Supplier bill SUP-77', lines: [
      { line_id: first!.line_key, item_id: milk.id, warehouse_id: goods.warehouse, quantity: '10.0000' }, { line_id: second!.line_key, item_id: ghee.id, warehouse_id: goods.warehouse, quantity: '5.0000' }] });
    // Untaxed goods carry the untaxed profile; Accounting decides whether a GST-registered company may bill them so.
    expect(wire.invoice!.tax).toEqual({ profile: 'UNTAXED_ACCOUNT' });
  });
  it('keeps the same line identities on a second save', () => {
    const first = purchaseInput(draft(), binding), second = purchaseInput(draft(), binding);
    expect(second.invoice!.supplies.map(line => line.line_key)).toEqual(first.invoice!.supplies.map(line => line.line_key));
  });
  it('mixes products and an expense line in the order they were entered', () => {
    const wire = purchaseInput(draft('MIXED'), binding);
    expect(wire.mode).toBe('MIXED');
    expect(wire.invoice!.supplies.map(line => line.supply_kind)).toEqual(['GOODS', 'ACCOUNT', 'GOODS']);
    expect(wire.lines).toHaveLength(2); expect(wire.stock!.lines).toHaveLength(2);
  });
  it('carries the goods GST profile on the bill and the service context on a service line beside the goods', () => {
    const wire = purchaseInput(draft('MIXED', 'FORWARD'), binding, facts());
    expect(wire.invoice!.tax).toEqual({ profile: 'INDIA_DOMESTIC_GOODS', company_registration_id: mine.id, party_registration_id: regular.id, place_of_supply: 'IN-MH',
      service_completion_date: null, supplier_invoice_number: 'SUP-77', supplier_invoice_date: '2026-10-30' });
    const [goodsLine, service] = wire.invoice!.supplies;
    expect(goodsLine).not.toHaveProperty('tax');
    expect(service).toMatchObject({ supply_kind: 'SERVICE', tax: { profile: 'INDIA_DOMESTIC_SERVICE', service_completion_date: '2026-10-30' } });
  });
  it('records a product-only GST bill on a type that does not take services', () => {
    metadata.configuration.policy.invoice = { allowed_supply_kinds: ['GOODS'] };
    expect(purchaseInput(draft('ITEMS', 'FORWARD'), binding, facts()).invoice!.tax!.profile).toBe('INDIA_DOMESTIC_GOODS');
  });
  it('refuses reverse charge on goods, a missing stock setup, unequal quantities and an unverified product', () => {
    expect(() => purchaseInput(draft('ITEMS', 'REVERSE'), binding, facts())).toThrow(/Reverse charge is recorded on service bills/);
    expect(() => purchaseInput(draft(), { ...binding, goods: undefined })).toThrow(/stock accounts and purchase warehouse/);
    const short = draft(); short.lines[0]!.received = '9';
    expect(() => purchaseInput(short, binding)).toThrow(/line 1: a bill that brings goods in bills what it receives/);
    expect(() => purchaseInput(draft(), { ...binding, items: new Map([[milk.id, milk]]) })).toThrow(/line 2: select a verified active product/);
    expect(() => purchaseInput(draft(), { ...binding, tracking: undefined })).toThrow(/tracking requirements could not be verified/);
  });
  it('refuses goods on an account bill, account lines on a product bill, and an empty product bill', () => {
    const accounts = draft(); accounts.mode = 'ACCOUNTS';
    expect(() => purchaseInput(accounts, binding)).toThrow(/choose a Product or Mixed Purchase type/);
    const mixed = draft('MIXED'); mixed.mode = 'ITEMS';
    expect(() => purchaseInput(mixed, binding)).toThrow(/product lines only/);
    const none = draft(); none.lines = [{ ...blankPurchaseLine('p9', 'ACCOUNT'), subject: native.supplies[0]!.account!.id, label: 'Expense', description: 'Fee', amount: '5' }]; none.mode = 'MIXED';
    expect(() => purchaseInput(none, binding)).toThrow(/at least one product line/);
  });
  it('refuses more product lines than one stock movement carries', () => {
    const many = draft(); many.lines = Array.from({ length: 101 }, (_, index) => item('m' + index, milk, '1', '1'));
    expect(() => purchaseInput(many, binding)).toThrow(/at most 100 product lines/);
  });
  it('clears the goods of a saved product bill that becomes an account bill', () => {
    const wire = purchaseInput(draft(), binding);
    const accounts = draft(); accounts.mode = 'ACCOUNTS'; accounts.lines = [{ ...blankPurchaseLine('p9', 'ACCOUNT'), subject: native.supplies[0]!.account!.id, label: 'Expense', description: 'Fee', amount: '5' }];
    const next = purchaseInput(accounts, { ...binding, previous: wire });
    expect(next).toMatchObject({ mode: 'ACCOUNTS', lines: [], stock: null, stock_date: null });
  });
});

describe('a saved product bill reopened', () => {
  it('round-trips a product bill exactly and keeps its warehouse', () => {
    const wire = purchaseInput(draft('MIXED', 'FORWARD'), binding, facts());
    const reopened = purchaseFromVoucher(saved(wire), company, metadata);
    expect(reopened.draft.mode).toBe('MIXED');
    expect(reopened.draft.lines.map(line => [line.kind, line.subject, line.billed, line.received, line.rate])).toEqual([
      ['ITEM', milk.id, '10.0000', '10.0000', '100.0000'], ['ACCOUNT', native.supplies[0]!.account!.id, '', '', ''], ['ITEM', ghee.id, '5.0000', '5.0000', '100.0000']]);
    expect(reopened.draft.tax.choice).toBe('FORWARD');
    expect(reopened.binding.goods).toEqual(goods);
    expect(reopened.binding.items!.get(milk.id)).toMatchObject({ version: 3, baseUnitId: milk.baseUnitId });
    const again = purchaseInput(reopened.draft, { ...reopened.binding, tracking: binding.tracking, rounding: binding.rounding }, facts());
    expect(again.invoice!.supplies).toEqual(wire.invoice!.supplies);
    expect([again.lines, again.stock, again.mode, again.invoice!.tax]).toEqual([wire.lines, wire.stock, wire.mode, wire.invoice!.tax]);
  });
  it('keeps distinct warehouses and a bin when reopening and saving', () => {
    const value = saved(purchaseInput(draft(), binding));
    const rows = (value.stock as { lines: Record<string, unknown>[] }).lines;
    rows[0]!.bin_id = id(63); rows[1]!.warehouse_id = id(62);
    const reopened = purchaseFromVoucher(value, company, metadata);
    expect(reopened.draft.lines[0]!.stock).toMatchObject({ warehouseId: goods.warehouse, binId: id(63) });
    expect(reopened.draft.lines[1]!.stock).toMatchObject({ warehouseId: id(62) });
    const again = purchaseInput(reopened.draft, { ...reopened.binding, tracking: binding.tracking, rounding: binding.rounding });
    expect((again.stock as { lines: Record<string, unknown>[] }).lines).toEqual(rows);
  });
  it('captures a prepared batch and serials and preserves their identities', () => {
    const entry = draft();
    entry.lines[0]!.received = '2'; entry.lines[0]!.billed = '2';
    entry.lines[0]!.stock = { warehouseId: id(62), binId: id(63), lotId: id(64), unitIds: [id(65), id(66)] };
    const tracked = { itemId: milk.id, companyId: company, profileRevisionId: id(67), lotTracking: true, serialTracking: true };
    const checked = { ...binding, tracking: new Map([[milk.id, tracked], [ghee.id, { itemId: ghee.id, companyId: company, profileRevisionId: id(68), lotTracking: false, serialTracking: false }]]) };
    const wire = purchaseInput(entry, checked);
    expect(wire.stock!.lines[0]).toMatchObject({ warehouse_id: id(62), bin_id: id(63), lot_id: id(64), unit_ids: [id(65), id(66)] });
    const reopened = purchaseFromVoucher(saved(wire), company, metadata);
    const again = purchaseInput(reopened.draft, { ...reopened.binding, tracking: checked.tracking, rounding: binding.rounding });
    expect(again.stock!.lines).toEqual(wire.stock!.lines);
    entry.lines[1]!.subject = milk.id; entry.lines[1]!.stock = { warehouseId: id(62), binId: '', lotId: id(64), unitIds: [id(65), id(69), id(70), id(71), id(72)] };
    expect(() => purchaseInput(entry, checked)).toThrow(/distinct prepared serials/);
  });
  it('requires a prepared batch and exact serial count for tracked goods', () => {
    const entry = draft(); entry.lines[0]!.received = '2'; entry.lines[0]!.billed = '2';
    const tracked = { itemId: milk.id, companyId: company, profileRevisionId: id(67), lotTracking: true, serialTracking: true };
    const checked = { ...binding, tracking: new Map([[milk.id, tracked], [ghee.id, binding.tracking!.get(ghee.id)!]]) };
    expect(() => purchaseInput(entry, checked)).toThrow(/select a prepared batch/);
    entry.lines[0]!.stock = { warehouseId: goods.warehouse, binId: '', lotId: id(64), unitIds: [id(65)] };
    expect(() => purchaseInput(entry, checked)).toThrow(/one prepared serial/);
  });
  it('honours stock-line field permissions for the chosen dimensions', () => {
    const entry = draft(); entry.lines[0]!.stock = { warehouseId: goods.warehouse, binId: id(63), lotId: '', unitIds: [] };
    metadata.native.properties!.stock!.properties!.lines!.items!.properties!.bin_id = { readOnly: true };
    expect(() => purchaseInput(entry, binding)).toThrow(/write access to its selected bin/);
  });
  it('retains a duplicated line location but requires new serials', () => {
    const entry = draft();
    entry.lines[0]!.stock = { warehouseId: id(62), binId: id(63), lotId: id(64), unitIds: [id(65)] };
    const copied = purchaseWorkspaceReducer(entry, { type: 'duplicate', key: 'p1' });
    expect(copied.lines[1]!.stock).toEqual({ ...entry.lines[0]!.stock, unitIds: [] });
    expect(entry.lines[0]!.stock!.unitIds).toEqual([id(65)]);
  });
  it('sends a saved bill with unsupported stock value or a shortfall to voucher review', () => {
    const broken: ((value: PurchaseVoucher) => void)[] = [
      value => { (value.stock as { lines: Record<string, unknown>[] }).lines[0]!.received_value = '1000.0000'; },
      value => { (value.lines as { item: { actual_quantity: string } }[])[0]!.item.actual_quantity = '9.0000'; },
      value => { value.stock = null; },
    ];
    for (const change of broken) {
      const value = saved(purchaseInput(draft(), binding)); change(value);
      expect(() => purchaseFromVoucher(value, company, metadata)).toThrow(PURCHASE_BROADER_CAPTURE);
    }
  });
  it('accepts unset optional stock fields as the service returns them', () => {
    const value = saved(purchaseInput(draft(), binding));
    (value.stock as { lines: Record<string, unknown>[] }).lines.forEach(line => Object.assign(line, { bin_id: null, lot_id: null, unit_ids: [] }));
    expect(purchaseFromVoucher(value, company, metadata).draft.lines).toHaveLength(2);
  });
});

describe('pricing a goods line as Accounting does', () => {
  it('rounds quantity × rate once, in the company rounding mode', () => {
    const q = D.parse('3')!, r = D.parse('33.3350')!;
    expect(D.format(pricedAmount(q, r, { places: 2, mode: 'half_up' }))).toBe('100.0100');
    expect(D.format(pricedAmount(q, r, { places: 2, mode: 'down' }))).toBe('100.0000');
    // Rounded once: 0.0049 × 1.0001 is 0.00490049, never 0.0049 → 0.01.
    expect(D.format(pricedAmount(D.parse('0.0049')!, D.parse('1.0001')!, { places: 2, mode: 'half_up' }))).toBe('0.0000');
  });
  it('takes the billed quantity when only it is entered and refuses a zero line', () => {
    expect(goodsLine({ ...item('p1', milk, '', '2'), billed: '4' }, milk, { places: 2, mode: 'half_up' }, 0)).toEqual({ quantity: '4.0000', rate: '2.0000', amount: '8.0000' });
    expect(() => goodsLine({ ...item('p1', milk, '1', '0') }, milk, { places: 2, mode: 'half_up' }, 0)).toThrow(/amount must be greater than zero/);
    expect(() => goodsLine({ ...item('p1', milk, '0', '5') }, milk, { places: 2, mode: 'half_up' }, 0)).toThrow(/quantity greater than zero/);
  });
  it('waits for a completed receipt and preserves an entered billed quantity', () => {
    const line = item('p1', milk, '', '1');
    expect(withPairedQuantity(line, { billed: '4' })).toEqual({ billed: '4', received: '4' });
    expect(withPairedQuantity({ ...line, billed: '4', received: '4' }, { received: '6' })).toEqual({ received: '6' });
    expect(withPairedQuantity({ ...line, billed: '4', received: '3' }, { billed: '5' })).toEqual({ billed: '5' });
    expect(withPairedQuantity({ ...blankPurchaseLine('a', 'ACCOUNT') }, { billed: '5' })).toEqual({ billed: '5' });
    expect(withPairedQuantity(line, { billed: '2', received: '1' })).toEqual({ billed: '2', received: '1' });
    const draft = newPurchaseWorkspace('2026-10-31');
    draft.lines = [{ ...line, received: '123', billed: '' }];
    expect(purchaseWorkspaceReducer(draft, { type: 'receipt_commit', key: line.key, value: '123' }).lines[0]?.billed).toBe('123');
    draft.lines[0]!.billed = '100';
    expect(purchaseWorkspaceReducer(draft, { type: 'receipt_commit', key: line.key, value: '123' }).lines[0]?.billed).toBe('100');
  });
});

describe('reading products and the stock setup', () => {
  const request = () => vi.mocked(productFieldRequest);
  it('verifies an active purchasable product of this company and names its unit', async () => {
    request().mockImplementation(async (_service, _method, path) => (path.includes('/units/') ? { id: milk.baseUnitId, symbol: 'L' } : { id: milk.id, company_id: company, row_version: 3, base_unit_id: milk.baseUnitId, status: 'ACTIVE', purchasable: true, name: 'Milk 1L', sku: 'MLK' }) as never);
    await expect(purchaseItem(company, milk.id)).resolves.toEqual({ ...milk, sku: 'MLK' });
  });
  it('keeps a product whose unit name cannot be read, and refuses one that is draft, unpurchasable or another company’s', async () => {
    const row = { id: milk.id, company_id: company, row_version: 3, base_unit_id: milk.baseUnitId, status: 'ACTIVE', purchasable: true, name: 'Milk 1L' };
    request().mockImplementation(async (_service, _method, path) => { if (path.includes('/units/')) throw { status: 403 }; return row as never; });
    await expect(purchaseItem(company, milk.id)).resolves.toMatchObject({ unit: '' });
    for (const [change, message] of [[{ status: 'DRAFT' }, /Activate this product/], [{ purchasable: false }, /not set up to be purchased/], [{ company_id: id(99) }, /unavailable for this company/]] as const) {
      request().mockResolvedValue({ ...row, ...change } as never);
      await expect(purchaseItem(company, milk.id)).rejects.toThrow(message);
    }
  });
  it('lists only active purchasable products and refuses a foreign row', async () => {
    request().mockResolvedValue({ items: [{ id: milk.id, name: 'Milk 1L', sku: 'MLK' }], page: { next_cursor: null } } as never);
    await expect(purchaseItemLookup(company)({ q: ' mil ', cursor: null, signal: new AbortController().signal } as never)).resolves.toEqual({ items: [{ id: milk.id, label: 'Milk 1L', meta: 'MLK' }], nextCursor: null });
    expect(request().mock.calls[0]![2]).toContain('status=ACTIVE&purchasable=true&limit=25&q=mil');
    request().mockResolvedValue({ items: [{ id: milk.id, company_id: id(99) }], page: { next_cursor: null } } as never);
    await expect(purchaseItemLookup(company)({ q: '', cursor: null, signal: new AbortController().signal } as never)).rejects.toThrow(/could not be verified/);
  });
  it('reads the inventory account in force on the posting date and the purchase warehouse', async () => {
    const routes: Record<string, unknown> = {
      '/stock/account-policies?limit=50&sort=-id': { items: [{ id: id(70), valid_from: '2026-04-01', valid_to: '2026-09-30' }, { id: id(71), valid_from: '2026-10-01', valid_to: null }], page: { next_cursor: null } },
      ['/stock/account-policies/' + id(71)]: { id: id(71), company_id: company, inventory_account_id: goods.inventory.id },
      ['/accounts/' + goods.inventory.id]: { id: goods.inventory.id, company_id: company, row_version: 2, status: 'ACTIVE' },
      '/warehouse-configuration': { company_id: company, main_warehouse_id: id(64), default_purchase_warehouse_id: goods.warehouse },
    };
    request().mockImplementation(async (_service, _method, path) => routes[path.replace('/v1/companies/' + company, '')] as never);
    await expect(purchaseGoodsContext(company, '2026-10-31')).resolves.toEqual(goods);
    routes['/stock/account-policies?limit=50&sort=-id'] = { items: [], page: { next_cursor: null } };
    await expect(purchaseGoodsContext(company, '2026-10-31')).rejects.toThrow(/Set up the company’s stock accounts/);
  });
});
