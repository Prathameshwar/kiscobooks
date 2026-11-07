import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, beforeEach, expect, it, vi } from 'vitest';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { DisplayConfigProvider } from '@janso/ui';
import { SimpleProductCreate } from '../app/components/SimpleProductCreate';
import { serviceCall } from '../app/lib/service-call';
import { scenario, COMPANY, GROUP, UNIT } from './simple-config-scenarios-fixtures';

vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: () => ({ data: { product_family_sku_enabled: false } }) }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const api = vi.mocked(serviceCall), root = `/v1/companies/${COMPANY}/simple-product-creations`;
let snapshot = scenario(1);
const evidence: { scenario: number; body: unknown }[] = [];
afterAll(() => {
  const directory = process.env.REVIEW_SIMPLE_EVIDENCE_DIR;
  if (!directory) return;
  mkdirSync(directory, { recursive: true });
  writeFileSync(resolve(directory, 'client-bodies.json'), JSON.stringify(evidence, null, 2));
});
beforeEach(() => {
  sessionStorage.clear(); api.mockReset();
  api.mockImplementation(async (_, request) => {
    if (request.path.includes('/options?')) return { ...snapshot.options, kind: new URL(request.path, 'http://test').searchParams.get('kind') } as never;
    if (request.path.endsWith('/item-groups/' + GROUP)) return { id: GROUP, name: 'Default' } as never;
    if (request.path.includes('/option-sources/') || request.path.includes('/tax-')) return { items: [{ id: UNIT, value: UNIT, label: 'Fixture choice' }], page: { has_more: false } } as never;
    if (request.path === root) return { id: '22222222-2222-4222-8222-222222222222', company_id: COMPANY, code: 'SIMREADY01', status: 'COMPLETE', step: 'COMPLETE', opening_posted: true } as never;
    throw { status: 404, message: 'Fixture unavailable' };
  });
});
function show() { render(<DisplayConfigProvider config={{ currency: 'INR', timezone: 'Asia/Kolkata' }}><SimpleProductCreate company={COMPANY} /></DisplayConfigProvider>); }
const user = () => userEvent.setup({ delay: null });
async function choose(label: string) {
  await user().click(screen.getByRole('combobox', { name: label }));
  await user().click(await screen.findByRole('option', { name: /Fixture choice/ }));
}
function enter(label: string, value: string) { fireEvent.change(screen.getByRole('textbox', { name: label }), { target: { value } }); }
async function basic(number: number) {
  await screen.findByDisplayValue('Default');
  if (number === 5) {
    fireEvent.change(screen.getByRole('combobox', { name: 'Type' }), { target: { value: 'SERVICE' } });
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Base unit' })).toBeEnabled());
  }
  enter('Product name', 'SIM-S' + number); await choose('Base unit');
}
async function details(number: number) {
  if (number === 2 || number === 5) { await choose(number === 5 ? 'SAC' : 'HSN'); await choose('GST treatment / rate'); }
  if (number === 4) { await choose('Brand'); await choose('Manufacturer'); await choose('Category 1'); }
  for (const [label, value] of Object.entries(snapshot.entries)) enter(label, value);
}
async function tracking(number: number) {
  if (number === 7) {
    for (const [index, quantity, cost, purchase] of [[1, '10', '50', '60'], [2, '20', '55', '65']] as const) {
      await user().click(screen.getByRole('button', { name: 'Add batch' }));
      enter('Batch ' + index, 'LOT-' + index); enter('Opening quantity ' + index, quantity); enter('Opening unit cost ' + index, cost);
      enter('Purchase reference ' + index, purchase); enter('Selling price ' + index, '90');
      fireEvent.change(screen.getByLabelText('Manufacture date ' + index), { target: { value: '2026-03-01' } });
      fireEvent.change(screen.getByLabelText('Expiry date ' + index), { target: { value: '2027-03-01' } });
    }
  }
  if (number === 8) {
    enter('Opening unit cost', '20000');
    for (const i of [1, 2]) { await user().click(screen.getByRole('button', { name: 'Add serial unit' })); enter('Serial number, unit ' + i, 'SER-' + i); }
  }
}
it.each(Array.from({ length: 10 }, (_, i) => i + 1))('S%02i creates using its independent resolved configuration snapshot', async number => {
  snapshot = scenario(number); show(); await basic(number); await details(number);
  if (number === 7 || number === 8) await user().click(screen.getByRole('button', { name: 'Next: Stock and prices' }));
  await tracking(number); await user().click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  const requests = api.mock.calls.filter(([, request]) => request.path === root);
  expect(requests).toHaveLength(1);
  const body = requests[0]![1].body;
  evidence.push({ scenario: number, body });
  expect(body).toMatchObject({ name: 'SIM-S' + number, kind: number === 5 ? 'SERVICE' : 'GOODS', base_unit_id: UNIT });
  if (number === 1) for (const key of ['purchase_price', 'sale_price', 'mrp', 'opening_unit_cost', 'batches', 'serials']) expect(body).not.toHaveProperty(key);
  if (number === 1) expect(screen.queryByText('Prices')).toBeNull();
  if (number === 2) expect(body).toMatchObject({ opening_quantity: '20', opening_unit_cost: '80', purchase_price: '85', sale_price: '120', mrp: '150' });
  if (number === 3) for (const key of ['brand_id', 'model_code', 'barcode', 'manufacturer_id', 'categories']) expect(body).not.toHaveProperty(key);
  if (number === 5) for (const key of ['opening_quantity', 'mrp', 'manufacturer_id', 'batches', 'serials']) expect(body).not.toHaveProperty(key);
  if (number === 6) { expect(body).not.toHaveProperty('sale_price'); expect(body).toMatchObject({ sale_prices: [{ amount: '120' }, { amount: '100' }] }); }
  if (number === 7) { expect(body).toMatchObject({ batches: [{ opening_unit_cost: '50' }, { opening_unit_cost: '55' }] }); expect(body).not.toHaveProperty('opening_quantity'); }
  if (number === 8) expect(body).toMatchObject({ opening_quantity: '2', opening_unit_cost: '20000' });
  if (number === 9) expect(body).toMatchObject({ opening_quantity: '12.345', opening_unit_cost: '42.5' });
  if (number === 10) expect(body).toMatchObject({ custom_fields: { cf_note: 'Fixture note', cf_count: 0, cf_flag: false } });
}, 15000);

it.each([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])('S%02i rejects missing product name before any mutation', async number => {
  snapshot = scenario(number); show(); await screen.findByDisplayValue('Default');
  await user().click(screen.getByRole('button', { name: number === 7 || number === 8 ? 'Next: Stock and prices' : 'Save product' }));
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
  expect(screen.getByRole('textbox', { name: 'Product name' })).toHaveAttribute('aria-invalid', 'true');
});
it('S06 requires both configured price levels and preserves details on failure', async () => {
  snapshot = scenario(6); show(); await basic(6); enter('Retail', '120');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  expect(screen.getByRole('textbox', { name: 'Wholesale' })).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByRole('textbox', { name: 'Retail' })).toHaveValue('120');
  expect(api.mock.calls.some(([, request]) => request.path === root)).toBe(false);
});
it('S02 rejects a zero purchase reference even with a separate valid stock cost', async () => {
  snapshot = scenario(2); show(); await basic(2); await details(2); enter('Purchase price', '0');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  expect(screen.getByRole('textbox', { name: 'Purchase price' })).toHaveAttribute('aria-invalid', 'true');
  expect(api.mock.calls.some(([, request]) => request.path === root)).toBe(false);
});
