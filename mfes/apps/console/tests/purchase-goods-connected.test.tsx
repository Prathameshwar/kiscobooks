import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { PurchaseEntryConnected } from '../app/components/PurchaseEntryConnected';
import { serviceCall } from '../app/lib/service-call';
import { purchaseSource, supplierPayables } from '../app/lib/purchase-entry';
import { purchaseGoodsContext, purchaseItem } from '../app/lib/purchase-goods';
import { purchaseTracking } from '../app/lib/purchase-stock';
import { company, draft as sources, metadata as fixture } from './purchase-entry-fixtures';
import type { PurchaseWorkspaceController } from '../app/components/PurchaseWorkspace';
import type { FieldSet } from '../app/lib/voucher-fields';

vi.mock('../app/lib/service-call', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/purchase-entry', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/purchase-entry')>(), purchaseSource: vi.fn(), supplierPayables: vi.fn(), purchaseLookup: vi.fn(() => vi.fn()) }));
vi.mock('../app/lib/purchase-goods', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/purchase-goods')>(), purchaseItem: vi.fn(), purchaseGoodsContext: vi.fn(), purchaseItemLookup: vi.fn(() => vi.fn()) }));
vi.mock('../app/lib/purchase-stock', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/purchase-stock')>(), purchaseTracking: vi.fn() }));
vi.mock('../app/components/PurchaseWorkspace', () => ({ PurchaseWorkspace: ({ controller: c, policy }: { controller: PurchaseWorkspaceController; policy: { modes: readonly string[]; itemLookup?: unknown } }) => <section>{c.header}{c.banner(null)}
  <p>Mode {c.draft.mode} · {policy.modes.join(',')} · {policy.itemLookup ? 'product search' : 'no product search'}</p>
  <p>Line {c.draft.lines[0]!.kind} {c.draft.lines[0]!.label} {c.draft.lines[0]!.unit} {c.draft.lines[0]!.received}/{c.draft.lines[0]!.billed}</p>
  <button onClick={() => c.dispatch({ type: 'supplier', value: sources.party!.id, policy: {} as never })}>Choose supplier</button>
  <button onClick={() => c.dispatch({ type: 'subject', key: c.draft.lines[0]!.key, subject: { id: milk, label: 'Milk', kind: 'ITEM', unit: '', meta: '' } })}>Choose product</button>
  <input aria-label="Invoice" value={c.draft.invoice} onChange={e => c.dispatch({ type: 'header', field: 'invoice', value: e.target.value })} />
  <input aria-label="Billed" value={c.draft.lines[0]!.billed} onChange={e => c.dispatch({ type: 'line', key: c.draft.lines[0]!.key, patch: { billed: e.target.value } })} />
  <input aria-label="Rate" value={c.draft.lines[0]!.rate} onChange={e => c.dispatch({ type: 'line', key: c.draft.lines[0]!.key, patch: { rate: e.target.value } })} />
  {c.sections}{c.actions({ validate: () => true, review: () => undefined })}</section> }));

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const milk = id(50), base = '/v1/companies/' + company;
const props = { company, currency: 'INR', actor: id(12), year: id(13), canCreate: true, permissions: ['vouchers.read', 'vouchers.create', 'vouchers.edit'] };
let metadata: FieldSet, writes: unknown[];
beforeEach(() => {
  sessionStorage.clear(); vi.mocked(serviceCall).mockReset(); writes = [];
  metadata = structuredClone(fixture);
  Object.assign(metadata.native.properties!, Object.fromEntries(['document_date', 'currency', 'narration', 'mode', 'lines', 'stock_date', 'stock', 'attachments', 'links', 'custom_fields'].map(key => [key, {}])));
  metadata.native.properties!.stock = { properties: { lines: { items: { properties: Object.fromEntries(['item_id', 'quantity', 'warehouse_id', 'bin_id', 'lot_id', 'unit_ids'].map(key => [key, {}])) } } } };
  Object.assign(metadata.configuration.policy, { allowed_modes: ['ITEMS', 'ACCOUNTS', 'MIXED'], default_mode: 'ITEMS', invoice: { allowed_supply_kinds: ['GOODS', 'ACCOUNT'] } });
  vi.mocked(purchaseSource).mockImplementation(async (_company, resource) => resource === 'suppliers' ? sources.party! : sources.payable!);
  vi.mocked(supplierPayables).mockImplementation(async () => [sources.payable!]);
  vi.mocked(purchaseItem).mockResolvedValue({ id: milk, company, version: 3, baseUnitId: id(51), label: 'Milk 1L', unit: 'L' });
  vi.mocked(purchaseGoodsContext).mockResolvedValue({ inventory: { id: id(60), version: 2 }, warehouse: id(61) });
  vi.mocked(purchaseTracking).mockImplementation(async () => ({ itemId: milk, companyId: company, profileRevisionId: id(67), lotTracking: false, serialTracking: false }));
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('/voucher-types?')) return { items: [{ id: id(2), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', name: 'Goods purchases' }], page: { next_cursor: null } };
    if (request.path.endsWith('/voucher-capabilities')) return { financial_execution: false, invoice_execution: false, kinds: [] };
    if (request.path.includes('/field-set')) return metadata;
    if (request.method === 'POST') { writes.push(structuredClone(request.body)); throw { status: 422, message: 'Stopped after the request was captured' }; }
    throw Error('Unexpected test route ' + request.path);
  });
});
it('opens a goods type as a product bill, verifies the product, and saves its stock with the bill', async () => {
  render(<PurchaseEntryConnected {...props} />);
  expect(await screen.findByText('Mode ITEMS · ITEMS,ACCOUNTS,MIXED · product search')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Choose supplier' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Create' })).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button', { name: 'Choose product' }));
  await waitFor(() => expect(purchaseItem).toHaveBeenCalledWith(company, milk));
  expect(await screen.findByText(/Line ITEM Milk 1L L/)).toBeVisible();
  fireEvent.change(screen.getByLabelText('Invoice'), { target: { value: 'SUP-9' } });
  fireEvent.change(screen.getByLabelText('Billed'), { target: { value: '12' } });
  // Receipt follows billed: the bill brings in what it bills.
  expect(screen.getByText(/Line ITEM Milk 1L L 12\/12/)).toBeVisible();
  fireEvent.change(screen.getByLabelText('Rate'), { target: { value: '45.5' } });
  fireEvent.click(screen.getByRole('checkbox', { name: 'This bill carries no tax' }));
  fireEvent.click(screen.getByRole('button', { name: 'Create' }));
  await screen.findByText('Stopped after the request was captured');
  expect(purchaseGoodsContext).toHaveBeenCalledWith(company, expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/));
  const body = writes[0] as { mode: string; stock: { action: string; lines: { warehouse_id: string; quantity: string }[] }; invoice: { supplies: { supply_kind: string; account_id: string; amount: string }[] } };
  expect(body.mode).toBe('ITEMS');
  expect(body.stock).toMatchObject({ action: 'PURCHASE_INVOICE', lines: [{ warehouse_id: id(61), quantity: '12.0000' }] });
  expect(body.invoice.supplies[0]).toMatchObject({ supply_kind: 'GOODS', account_id: id(60), amount: '546.0000' });
});

it('says why a goods bill cannot be saved when the stock accounts are missing, and sends nothing', async () => {
  vi.mocked(purchaseGoodsContext).mockRejectedValue(Error('Set up the company’s stock accounts (Inventory → Stock accounts) before billing goods.'));
  render(<PurchaseEntryConnected {...props} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Choose supplier' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Create' })).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button', { name: 'Choose product' }));
  await screen.findByText(/Line ITEM Milk 1L/);
  fireEvent.change(screen.getByLabelText('Invoice'), { target: { value: 'SUP-9' } });
  fireEvent.change(screen.getByLabelText('Billed'), { target: { value: '1' } });
  fireEvent.change(screen.getByLabelText('Rate'), { target: { value: '1' } });
  fireEvent.click(screen.getByRole('checkbox', { name: 'This bill carries no tax' }));
  fireEvent.click(screen.getByRole('button', { name: 'Create' }));
  expect(await screen.findByText(/Set up the company’s stock accounts/)).toBeVisible();
  expect(writes).toHaveLength(0);
});

it('shows a product that cannot be bought instead of putting it on the line', async () => {
  vi.mocked(purchaseItem).mockRejectedValue(Error('Activate this product before buying it: open the product and choose Review and activate.'));
  render(<PurchaseEntryConnected {...props} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Choose supplier' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Create' })).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button', { name: 'Choose product' }));
  expect(await screen.findByText(/Activate this product before buying it/)).toBeVisible();
  expect(screen.getByText(/^Line ITEM\s+\/$/)).toBeVisible();
});

it('keeps an account-only type on account lines without a product search', async () => {
  Object.assign(metadata.configuration.policy, { allowed_modes: ['ACCOUNTS'], default_mode: 'ACCOUNTS', invoice: { allowed_supply_kinds: ['ACCOUNT'] } });
  render(<PurchaseEntryConnected {...props} />);
  expect(await screen.findByText('Mode ACCOUNTS · ACCOUNTS · no product search')).toBeVisible();
  expect(vi.mocked(serviceCall).mock.calls.some(call => call[1].path.startsWith(base + '/items'))).toBe(false);
});
